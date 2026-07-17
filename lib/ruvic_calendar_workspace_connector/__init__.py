"""Conector Ruvic para Google Calendar (Google Workspace) vía cuenta de
servicio con delegación de dominio."""

from .client import CalendarWorkspaceClient
from .config import ENV_PREFIX, CalendarWorkspaceConfig
from .exceptions import (
    CalendarWorkspaceAuthError,
    CalendarWorkspaceConnectorError,
    CalendarWorkspaceDataError,
    CalendarWorkspaceNetworkError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "CalendarWorkspaceAuthError",
    "CalendarWorkspaceClient",
    "CalendarWorkspaceConfig",
    "CalendarWorkspaceConnectorError",
    "CalendarWorkspaceDataError",
    "CalendarWorkspaceNetworkError",
    "setup_logging",
]

__version__ = "1.0.0"
