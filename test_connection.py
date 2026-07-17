"""Prueba de conexión estándar del conector calendar_workspace.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_CALENDAR_WORKSPACE_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Verifica la delegación de dominio impersonando al usuario de prueba
    (RUVIC_CALENDAR_WORKSPACE_DEFAULT_USER)."""
    try:
        from ruvic_calendar_workspace_connector import (
            CalendarWorkspaceAuthError,
            CalendarWorkspaceClient,
            CalendarWorkspaceConfig,
            CalendarWorkspaceDataError,
            CalendarWorkspaceNetworkError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-calendar-workspace-connector no está instalada. "
            "Instala con: pip install git+https://github.com/Dgirto/"
            "Calendar-Workspace.git#subdirectory=lib",
        )

    try:
        config = CalendarWorkspaceConfig.from_env()
    except ValueError as exc:
        return False, str(exc)

    try:
        client = CalendarWorkspaceClient(user_email=config.default_user, config=config)
    except CalendarWorkspaceDataError as exc:
        return False, str(exc)

    try:
        client.ping()
    except CalendarWorkspaceAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except CalendarWorkspaceNetworkError as exc:
        return False, f"Error de red: {exc}"
    except CalendarWorkspaceDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return (
        True,
        f"Conexión exitosa: delegación de dominio válida para {config.default_user}",
    )


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
