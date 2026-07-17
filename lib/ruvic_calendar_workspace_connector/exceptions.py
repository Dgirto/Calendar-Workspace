"""Excepciones propias del conector Google Calendar (Workspace).

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del cliente HTTP subyacente.
"""


class CalendarWorkspaceConnectorError(Exception):
    """Error base del conector."""


class CalendarWorkspaceAuthError(CalendarWorkspaceConnectorError):
    """Credenciales inválidas, delegación no autorizada o permisos insuficientes."""


class CalendarWorkspaceNetworkError(CalendarWorkspaceConnectorError):
    """No se pudo alcanzar la API de Calendar (red, timeout, error temporal del servidor)."""


class CalendarWorkspaceDataError(CalendarWorkspaceConnectorError):
    """La operación es válida pero el recurso no existe o los datos son inválidos."""
