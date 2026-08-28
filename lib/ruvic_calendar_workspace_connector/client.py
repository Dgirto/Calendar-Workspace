"""Cliente de Google Calendar (Google Workspace) vía cuenta de servicio
con delegación de dominio.

Mismo patrón de autenticación que los demás conectores Workspace
(CON-005.2 Gmail, CON-006.1 Sheets, CON-007 Drive, CON-008.1 Docs): el
constructor recibe el usuario del dominio a impersonar, y una sola
credencial (esta cuenta de servicio) puede actuar como cualquier usuario
autorizado del dominio sin volver a autorizar por usuario ni gestionar
expiración de tokens.

Capacidades:
- create_event():  crear un evento (con hora o de día completo, con invitados).
- list_events():   listar eventos de un rango de fechas (con búsqueda por texto).
- cancel_event():  cancelar (eliminar) un evento.

Las credenciales SIEMPRE provienen de variables de entorno
RUVIC_CALENDAR_WORKSPACE_* (ver config.CalendarWorkspaceConfig.from_env).
Prohibido hardcodearlas.
"""

from __future__ import annotations

import re
import socket
from typing import Any

from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import CalendarWorkspaceConfig
from .exceptions import (
    CalendarWorkspaceAuthError,
    CalendarWorkspaceConnectorError,
    CalendarWorkspaceDataError,
    CalendarWorkspaceNetworkError,
)
from .logging_utils import get_logger

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MAX_RESULTS_LIMIT = 250


def _service_disabled_info(exc: HttpError) -> tuple[str, str] | None:
    """Detecta el caso 403 SERVICE_DISABLED (la API no está habilitada en
    el proyecto de Google Cloud) y retorna (nombre de la API, URL de
    activación), o None si el error es de otro tipo."""
    try:
        details = exc.error_details or []
    except Exception:
        details = []
    for detail in details:
        if isinstance(detail, dict) and detail.get("reason") == "SERVICE_DISABLED":
            meta = detail.get("metadata", {})
            return (
                meta.get("serviceTitle", "API de Google"),
                meta.get(
                    "activationUrl",
                    "Google Cloud Console -> APIs y servicios -> Biblioteca",
                ),
            )
    return None


def _wrap_http_error(exc: HttpError) -> CalendarWorkspaceConnectorError:
    """Traduce un error HTTP de la API de Calendar a una excepción propia,
    sin dejar escapar nunca el tipo crudo del cliente HTTP."""
    status = exc.resp.status if getattr(exc, "resp", None) is not None else None
    if status == 403:
        disabled = _service_disabled_info(exc)
        if disabled is not None:
            service_title, activation_url = disabled
            return CalendarWorkspaceAuthError(
                f"La {service_title} no está habilitada en el proyecto de "
                f"Google Cloud de la cuenta de servicio. Habilítala en "
                f"{activation_url} y espera 1-2 minutos antes de reintentar."
            )
    if status in (401, 403):
        return CalendarWorkspaceAuthError(
            "Credenciales inválidas o sin permiso suficiente sobre este "
            "calendario. Verifica que el Client ID de la cuenta de servicio "
            "esté autorizado en el Admin Console de Workspace con el scope "
            "calendar.events, y que el usuario impersonado tenga acceso al "
            "calendario indicado."
        )
    if status in (404, 410):
        return CalendarWorkspaceDataError(
            "El evento o calendario solicitado no existe, ya fue eliminado, "
            "o el usuario impersonado no tiene acceso a él."
        )
    if status == 429 or (status is not None and status >= 500):
        return CalendarWorkspaceNetworkError(
            f"Calendar API no respondió correctamente (HTTP {status}). "
            "Puede ser un límite de cuota temporal; reintenta en unos segundos."
        )
    return CalendarWorkspaceDataError(f"Error de Calendar API (HTTP {status}): {exc}")


def _validate_non_empty(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise CalendarWorkspaceDataError(
            f"{field} debe ser un string, no {type(value).__name__}."
        )
    value = value.strip()
    if not value:
        raise CalendarWorkspaceDataError(f"{field} no puede estar vacío.")
    return value


def _validate_max_results(max_results: Any) -> int:
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise CalendarWorkspaceDataError(
            f"max_results debe ser un entero, no {type(max_results).__name__}."
        )
    if not 1 <= max_results <= _MAX_RESULTS_LIMIT:
        raise CalendarWorkspaceDataError(
            f"max_results debe estar entre 1 y {_MAX_RESULTS_LIMIT}."
        )
    return max_results


def _to_event_time(value: str, timezone: str | None) -> dict[str, str]:
    """Convierte un string ISO 8601 al formato start/end de la API.

    "2026-07-20T15:00:00" (con hora) -> {"dateTime": ..., "timeZone": ...}
    "2026-07-20" (solo fecha)        -> {"date": ...} (evento de día completo)
    """
    value = _validate_non_empty(value, "start/end")
    if "T" in value:
        time_obj: dict[str, str] = {"dateTime": value}
        if timezone:
            time_obj["timeZone"] = timezone
        return time_obj
    return {"date": value}


def _simplify_event(event: dict[str, Any]) -> dict[str, Any]:
    """Reduce un evento de la API a un dict plano y predecible."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id"),
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "status": event.get("status"),
        "organizer": event.get("organizer", {}).get("email", ""),
        "attendees": [
            {
                "email": a.get("email", ""),
                "response_status": a.get("responseStatus", ""),
            }
            for a in event.get("attendees", [])
        ],
        "url": event.get("htmlLink", ""),
    }


class CalendarWorkspaceClient:
    """Cliente de Google Calendar para un usuario específico de un dominio
    Google Workspace, vía cuenta de servicio con delegación de dominio.

    Args:
        user_email: correo del usuario del dominio a impersonar (ej.
            "facturacion@tuempresa.com"). La cuenta de servicio debe estar
            autorizada en el Admin Console para el dominio de ese correo.
            El conector opera sobre los calendarios a los que ese usuario
            tenga acceso.
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_CALENDAR_WORKSPACE_* (comportamiento
            estándar en el runtime de la plataforma).

    Ejemplo:
        >>> client = CalendarWorkspaceClient(user_email="facturacion@tuempresa.com")
        >>> client.list_events(time_min="2026-07-20T00:00:00Z")
        [{'id': 'abc123', 'summary': 'Reunión de equipo', ...}]
    """

    def __init__(
        self, user_email: str, config: CalendarWorkspaceConfig | None = None
    ) -> None:
        if not _EMAIL_RE.match(user_email):
            raise CalendarWorkspaceDataError(
                f"user_email={user_email!r} no parece un correo válido "
                "(ej. 'facturacion@tuempresa.com')."
            )
        self.user_email = user_email
        self.config = config or CalendarWorkspaceConfig.from_env()
        self._logger = get_logger()
        self._service: Any = None
        self._credentials: service_account.Credentials | None = None

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _get_credentials(self) -> service_account.Credentials:
        if self._credentials is not None:
            return self._credentials
        try:
            self._credentials = service_account.Credentials.from_service_account_info(
                self.config.service_account_info,
                scopes=_SCOPES,
                subject=self.user_email,
            )
        except (ValueError, KeyError) as exc:
            raise CalendarWorkspaceAuthError(
                f"El JSON de la cuenta de servicio es inválido o le faltan campos: {exc}"
            ) from exc
        return self._credentials

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service
        credentials = self._get_credentials()
        try:
            self._service = build(
                "calendar",
                "v3",
                credentials=credentials,
                cache_discovery=False,
                static_discovery=False,
            )
        except (GoogleAuthError, OSError) as exc:
            raise CalendarWorkspaceNetworkError(
                f"No se pudo inicializar el cliente de Calendar: {exc}"
            ) from exc
        return self._service

    def ping(self) -> bool:
        """Verifica la delegación de dominio refrescando el token de
        acceso para el usuario impersonado (no requiere ningún evento
        específico).

        Returns:
            True si la conexión y la delegación funcionan.

        Raises:
            CalendarWorkspaceAuthError / CalendarWorkspaceNetworkError /
            CalendarWorkspaceDataError.
        """
        credentials = self._get_credentials()
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            client_id = self.config.service_account_info.get("client_id", "?")
            raise CalendarWorkspaceAuthError(
                f"No se pudo autenticar como {self.user_email!r} (unauthorized_client). "
                "Revisa en el Admin Console de Google Workspace (Seguridad -> Control "
                "de acceso a las API -> Delegación en todo el dominio) que: "
                f"1) el Client ID '{client_id}' esté agregado, "
                "2) los scopes autorizados incluyan exactamente "
                "'https://www.googleapis.com/auth/calendar.events', y 3) el usuario "
                "pertenezca a ese mismo dominio."
            ) from exc
        except (socket.error, TimeoutError, OSError) as exc:
            raise CalendarWorkspaceNetworkError(
                f"No se pudo conectar con Calendar API: {exc}"
            ) from exc
        self._logger.info("Ping exitoso, usuario: %s", self.user_email)
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1 — Crear un evento
    # ------------------------------------------------------------------ #

    def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        timezone: str | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Crea un evento en el calendario del usuario impersonado.

        Args:
            summary: título del evento.
            start: inicio en ISO 8601. Con hora ("2026-07-20T15:00:00")
                crea un evento con horario; solo fecha ("2026-07-20")
                crea un evento de día completo.
            end: fin en ISO 8601 (mismo formato que start). En eventos de
                día completo el fin es EXCLUSIVO (un evento de un solo día
                el 20 termina el "2026-07-21").
            description: descripción del evento (opcional).
            location: ubicación (opcional).
            attendees: lista de correos de invitados (opcional; reciben
                la invitación por correo).
            timezone: zona horaria IANA (ej. "America/Bogota"). Necesaria
                si start/end llevan hora sin offset (+00:00 / Z).
            calendar_id: calendario destino (default "primary", el
                calendario principal del usuario impersonado).

        Returns:
            Dict del evento creado: id, summary, start, end, url, ...

        Ejemplo:
            >>> client.create_event(
            ...     "Reunión de seguimiento",
            ...     start="2026-07-20T15:00:00",
            ...     end="2026-07-20T16:00:00",
            ...     timezone="America/Bogota",
            ...     attendees=["cliente@empresa.com"],
            ... )
            {'id': 'abc123', 'summary': 'Reunión de seguimiento', ...}
        """
        summary = _validate_non_empty(summary, "summary")
        body: dict[str, Any] = {
            "summary": summary,
            "start": _to_event_time(start, timezone),
            "end": _to_event_time(end, timezone),
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            if not isinstance(attendees, list):
                raise CalendarWorkspaceDataError(
                    f"attendees debe ser una lista de strings, no {type(attendees).__name__}."
                )
            for email in attendees:
                if not isinstance(email, str):
                    raise CalendarWorkspaceDataError(
                        f"Cada correo en attendees debe ser un string, no {type(email).__name__}."
                    )
            body["attendees"] = [
                {"email": email.strip()} for email in attendees if email.strip()
            ]
        service = self._get_service()
        try:
            event = (
                service.events()
                .insert(calendarId=calendar_id, body=body, sendUpdates="all")
                .execute(num_retries=1)
            )
        except (RefreshError, GoogleAuthError) as exc:
            raise CalendarWorkspaceAuthError(
                f"No se pudo autenticar: el token OAuth/credenciales pueden "
                f"estar revocados, vencidos o ser inválidos. Vuelve a "
                f"autorizar el conector. Detalle: {exc}"
            ) from exc
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        self._logger.info(
            "Evento '%s' creado (id=%s, usuario %s)",
            summary, event.get("id"), self.user_email,
        )
        return _simplify_event(event)

    # ------------------------------------------------------------------ #
    # Capacidad 2 — Listar eventos
    # ------------------------------------------------------------------ #

    def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        query: str | None = None,
        max_results: int = 50,
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        """Lista eventos del calendario del usuario impersonado ordenados
        por fecha de inicio.

        Los eventos recurrentes se expanden en sus instancias individuales.

        Args:
            time_min: solo eventos que terminen después de este instante
                (ISO 8601 con zona, ej. "2026-07-20T00:00:00Z"). Opcional.
            time_max: solo eventos que empiecen antes de este instante.
                Opcional.
            query: búsqueda de texto libre (título, descripción,
                ubicación, invitados). Opcional.
            max_results: máximo de eventos a retornar (1-250, default 50).
            calendar_id: calendario a consultar (default "primary").

        Returns:
            Lista de dicts: id, summary, start, end, all_day, status,
            organizer, attendees, url.

        Ejemplo:
            >>> client.list_events(
            ...     time_min="2026-07-20T00:00:00Z",
            ...     time_max="2026-07-27T00:00:00Z",
            ... )
            [{'id': 'abc123', 'summary': 'Reunión de equipo', ...}]
        """
        max_results = _validate_max_results(max_results)
        params: dict[str, Any] = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query
        service = self._get_service()
        try:
            result = service.events().list(**params).execute(num_retries=1)
        except (RefreshError, GoogleAuthError) as exc:
            raise CalendarWorkspaceAuthError(
                f"No se pudo autenticar: el token OAuth/credenciales pueden "
                f"estar revocados, vencidos o ser inválidos. Vuelve a "
                f"autorizar el conector. Detalle: {exc}"
            ) from exc
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        events = [_simplify_event(e) for e in result.get("items", [])]
        self._logger.info(
            "Listados %d eventos del calendario %s (usuario %s)",
            len(events), calendar_id, self.user_email,
        )
        return events

    # ------------------------------------------------------------------ #
    # Capacidad 3 — Cancelar un evento
    # ------------------------------------------------------------------ #

    def cancel_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> dict[str, Any]:
        """Cancela (elimina) un evento del calendario del usuario
        impersonado. Los invitados reciben la notificación de cancelación
        por correo.

        Args:
            event_id: ID del evento (el campo "id" de list_events o
                create_event).
            calendar_id: calendario del evento (default "primary").

        Returns:
            Dict con: id, cancelled=True.

        Ejemplo:
            >>> client.cancel_event("abc123")
            {'id': 'abc123', 'cancelled': True}
        """
        event_id = _validate_non_empty(event_id, "event_id")
        service = self._get_service()
        try:
            service.events().delete(
                calendarId=calendar_id, eventId=event_id, sendUpdates="all"
            ).execute(num_retries=1)
        except (RefreshError, GoogleAuthError) as exc:
            raise CalendarWorkspaceAuthError(
                f"No se pudo autenticar: el token OAuth/credenciales pueden "
                f"estar revocados, vencidos o ser inválidos. Vuelve a "
                f"autorizar el conector. Detalle: {exc}"
            ) from exc
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        self._logger.info("Evento %s cancelado (usuario %s)", event_id, self.user_email)
        return {"id": event_id, "cancelled": True}
