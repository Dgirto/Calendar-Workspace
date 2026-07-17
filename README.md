# Conector Google Calendar Workspace (CON-009.1)

Conector Ruvic para Google Calendar en un dominio **Google Workspace**,
vía **cuenta de servicio con delegación de dominio**. Una sola credencial
puede impersonar a cualquier usuario autorizado del dominio y crear,
listar y cancelar eventos de sus calendarios (`facturacion@empresa.com`,
`soporte@empresa.com`, …) sin re-autorizar cada uno individualmente y
sin tokens que expiren.

Es el segundo conector Calendar del catálogo — ver CON-009 (OAuth2, un
usuario por autorización). Usa el mismo patrón de autenticación que
CON-005.2 (Gmail Workspace), CON-006.1 (Sheets Workspace), CON-007
(Drive Workspace) y CON-008.1 (Docs Workspace) — si ya tienes esa cuenta
de servicio configurada, puedes reutilizarla agregando el scope de
Calendar a la misma entrada de delegación en el Admin Console.

> **Solo Google Workspace.** La delegación de dominio no existe en las
> cuentas de Google personales; para esas usa el conector CON-009.

## Instalación

```bash
pip install git+https://github.com/Dgirto/Calendar-Workspace.git#subdirectory=lib
```

Python 3.10+. Dependencias: `google-auth` y `google-api-python-client`.

## Obtener credenciales

1. **Cuenta de servicio** (Google Cloud Console → IAM y administración →
   Cuentas de servicio): crea una (o reutiliza la de los otros conectores
   Workspace) y descarga una clave JSON.
2. **Habilita la Google Calendar API** en el mismo proyecto.
3. **Delegación de dominio** (requiere superadministrador de Workspace):
   Admin Console → Seguridad → Control de acceso a las API → Delegación
   en todo el dominio → Agregar nueva entrada:
   - **Client ID**: el `client_id` numérico del JSON de la cuenta de servicio.
   - **Scopes**: `https://www.googleapis.com/auth/calendar.events`
     (si reutilizas la cuenta de servicio de otros conectores, agrega este
     scope a la lista existente, separado por coma).

## Uso

```python
from ruvic_calendar_workspace_connector import CalendarWorkspaceClient

client = CalendarWorkspaceClient(user_email="facturacion@tuempresa.com")

# Crear un evento
event = client.create_event(
    "Reunión de seguimiento",
    start="2026-07-20T15:00:00",
    end="2026-07-20T16:00:00",
    timezone="America/Bogota",
    attendees=["cliente@empresa.com"],
)

# Listar eventos de la semana
events = client.list_events(
    time_min="2026-07-20T00:00:00Z",
    time_max="2026-07-27T00:00:00Z",
)

# Cancelar un evento
client.cancel_event(event["id"])
```

Ver [SKILL.md](SKILL.md) para la referencia completa de operaciones y manejo de errores.

## Variables de entorno

| Variable | Obligatoria | Contenido |
|----------|-------------|-----------|
| `RUVIC_CALENDAR_WORKSPACE_SERVICE_ACCOUNT_JSON` | Sí | JSON completo de la cuenta de servicio |
| `RUVIC_CALENDAR_WORKSPACE_DEFAULT_USER` | Sí | Usuario del dominio para "Probar conexión" |
| `RUVIC_CALENDAR_WORKSPACE_REQUEST_TIMEOUT` | No | Timeout en segundos (default 30) |

## Pruebas

```bash
# Prueba de conexión (verifica la delegación impersonando al usuario de prueba)
python test_connection.py

# Validación end-to-end: crea un evento de prueba, lo lista y lo cancela
python validate_local.py
```

## Permisos y seguridad

- Scope único: `https://www.googleapis.com/auth/calendar.events` — crear,
  listar y cancelar eventos. **No** puede cambiar la configuración de los
  calendarios, ni compartirlos, ni acceder a correo/archivos del dominio.
- La delegación de dominio la controla el superadministrador de Workspace:
  puede revocarla en cualquier momento eliminando la entrada del Admin
  Console (efecto inmediato).
- El JSON de la cuenta de servicio vive solo en variables de entorno; la
  librería nunca lo registra en logs.
- Rotación de claves: crea una clave nueva en Google Cloud Console,
  actualiza el formulario del conector y elimina la clave anterior.

## Estructura

```text
CON-009.1/
├── manifest.json          # definición del conector para el catálogo Ruvic
├── SKILL.md               # skill para el agente (operaciones y ejemplos)
├── test_connection.py     # prueba de conexión estándar
├── validate_local.py      # validación end-to-end de las 3 capacidades
├── docs/                  # guía de configuración para el portal
└── lib/                   # paquete pip-instalable ruvic-calendar-workspace-connector
    └── ruvic_calendar_workspace_connector/
```
