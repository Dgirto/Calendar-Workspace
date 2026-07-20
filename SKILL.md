---
name: calendar-workspace
description: >
  Usa la librería ruvic_calendar_workspace_connector para gestionar
  eventos de Google Calendar en un dominio Google Workspace vía cuenta
  de servicio con delegación de dominio - crear un evento con horario o
  de día completo, con invitados (create_event), listar los eventos de
  un rango de fechas con búsqueda por texto (list_events) y cancelar un
  evento notificando a los invitados (cancel_event), impersonando a
  cualquier usuario autorizado del dominio. Úsala cuando el usuario pida
  agendar, programar o cancelar reuniones, o revisar la agenda de un
  usuario del dominio Workspace.
triggers:
- google calendar
- calendario
- evento
- eventos
- reunión
- agendar
- agenda
- workspace
- programar reunión
- cancelar evento
---

# Conector Google Calendar Workspace (ruvic_calendar_workspace_connector)

Librería Python para crear, listar y cancelar eventos de Google Calendar en un dominio **Google Workspace**, vía cuenta de servicio con delegación de dominio. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/Dgirto/Calendar-Workspace.git#subdirectory=lib`). Una sola credencial puede impersonar a cualquier usuario autorizado del dominio, sin re-autorizar por usuario y sin tokens que expiren.

Es el segundo conector Calendar del catálogo — ver `calendar` (OAuth2, un usuario por autorización). Usa el mismo patrón de autenticación que `gmail_workspace` (CON-005.2), `sheets_workspace` (CON-006.1), `drive` (CON-007) y `docs_workspace` (CON-008.1) — si ya tienes esa cuenta de servicio configurada, puedes reutilizarla agregando el scope de Calendar a la misma entrada de delegación en el Admin Console.

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `calendar_workspace` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_CALENDAR_WORKSPACE_SERVICE_ACCOUNT_JSON` | JSON completo de la cuenta de servicio |
| `RUVIC_CALENDAR_WORKSPACE_DEFAULT_USER` | Usuario del dominio para "Probar conexión" |
| `RUVIC_CALENDAR_WORKSPACE_REQUEST_TIMEOUT` | (opcional) timeout en segundos, default 30 |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**. El código generado **NUNCA** usa nombres con segmento de alias (`_DEFAULT_INSTANCIA_`, `_PRODUCCION_`, etc.) salvo que aparezcan en una sección autogenerada `## Variables en tu entorno` al final de este skill.

## Conexión (siempre igual)

```python
from ruvic_calendar_workspace_connector import CalendarWorkspaceClient

# El usuario del dominio cuyos calendarios se van a gestionar:
client = CalendarWorkspaceClient(user_email="facturacion@tuempresa.com")
```

El `user_email` es el usuario del dominio a impersonar. Si el usuario no dice cuál usar, usa el valor de `RUVIC_CALENDAR_WORKSPACE_DEFAULT_USER`.

## Formato de fechas

- Con hora: ISO 8601, ej. `"2026-07-20T15:00:00"` + `timezone="America/Bogota"` (o con offset: `"2026-07-20T15:00:00-05:00"`).
- Día completo: solo fecha, ej. `"2026-07-20"`. El `end` de eventos de día completo es **exclusivo** (evento de un día el 20 → `end="2026-07-21"`).
- En `list_events`, `time_min`/`time_max` requieren zona horaria (`Z` u offset), ej. `"2026-07-20T00:00:00Z"`.

## Capacidad 1 — Crear un evento

```python
event = client.create_event(
    "Reunión de seguimiento",
    start="2026-07-20T15:00:00",
    end="2026-07-20T16:00:00",
    timezone="America/Bogota",
    description="Revisión mensual de avances.",
    location="Google Meet",
    attendees=["cliente@empresa.com"],   # opcional; reciben invitación por correo
)
print(event["id"], event["url"])
```

Parámetros opcionales: `description`, `location`, `attendees`, `timezone`, `calendar_id` (default `"primary"`, el calendario principal del usuario impersonado).

## Capacidad 2 — Listar eventos

```python
events = client.list_events(
    time_min="2026-07-20T00:00:00Z",
    time_max="2026-07-27T00:00:00Z",
    query="seguimiento",     # opcional: búsqueda por texto
    max_results=50,          # 1-250
)
for e in events:
    print(e["start"], e["summary"], e["id"])
```

Cada evento retorna: `id`, `summary`, `description`, `location`, `start`, `end`, `all_day`, `status`, `organizer`, `attendees`, `url`. Los eventos recurrentes vienen expandidos en instancias individuales.

## Capacidad 3 — Cancelar un evento

```python
client.cancel_event("abc123")            # id obtenido de list_events/create_event
# {'id': 'abc123', 'cancelled': True}
```

Los invitados reciben la notificación de cancelación por correo.

## Manejo de errores

```python
from ruvic_calendar_workspace_connector import (
    CalendarWorkspaceAuthError,      # delegación no autorizada o credenciales inválidas
    CalendarWorkspaceNetworkError,   # sin conexión, timeout o error temporal del servidor
    CalendarWorkspaceDataError,      # evento/calendario inexistente o parámetros inválidos
)

try:
    events = client.list_events()
except CalendarWorkspaceAuthError:
    print("Revisa la delegación de dominio en el Admin Console de Workspace.")
except CalendarWorkspaceNetworkError:
    print("Reintenta en unos segundos.")
except CalendarWorkspaceDataError as exc:
    print(f"Revisa los datos: {exc}")
```

Todas las excepciones heredan de `CalendarWorkspaceConnectorError`; ninguna operación deja escapar errores crudos del cliente HTTP.
