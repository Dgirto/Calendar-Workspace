"""Validacion local del conector calendar_workspace: ejercita las 3 capacidades.

Uso:
    python validate_local.py

Requiere las variables RUVIC_CALENDAR_WORKSPACE_* exportadas en el
entorno (JSON de la cuenta de servicio + usuario a impersonar). No
necesita ningun evento previo: crea uno de prueba, lo lista y lo cancela
en el calendario del usuario impersonado.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ruvic_calendar_workspace_connector import (
    CalendarWorkspaceClient,
    CalendarWorkspaceConfig,
    setup_logging,
)

setup_logging("INFO")
config = CalendarWorkspaceConfig.from_env()
client = CalendarWorkspaceClient(user_email=config.default_user, config=config)

start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
end = start + timedelta(hours=1)

print(f"== 0. Usuario impersonado: {config.default_user} ==")

print("== 1. Crear un evento de prueba ==")
created = client.create_event(
    "Prueba conector Calendar Workspace Ruvic",
    start=start.isoformat(),
    end=end.isoformat(),
    description="Evento creado por validate_local.py (se cancela solo).",
    location="Remoto",
)
event_id = created["id"]
print(f"  Creado: id={event_id}")
print(f"  Inicio: {created['start']}  Fin: {created['end']}")
print(f"  URL: {created['url']}")

print("== 2. Listar eventos (debe incluir el de prueba) ==")
events = client.list_events(
    time_min=start.isoformat(),
    time_max=(end + timedelta(minutes=1)).isoformat(),
    query="Prueba conector Calendar Workspace Ruvic",
)
print(f"  {len(events)} evento(s) encontrados:")
for e in events:
    print(f"    - {e['start']}  {e['summary']!r}  (id={e['id']})")
assert any(e["id"] == event_id for e in events), "El evento creado no aparece en la lista"

print("== 3. Cancelar el evento de prueba ==")
result = client.cancel_event(event_id)
print(f"  {result}")

print("== 4. Verificar que ya no aparece ==")
events = client.list_events(
    time_min=start.isoformat(),
    time_max=(end + timedelta(minutes=1)).isoformat(),
    query="Prueba conector Calendar Workspace Ruvic",
)
remaining = [e for e in events if e["id"] == event_id and e["status"] != "cancelled"]
print(f"  Eventos activos restantes con ese id: {len(remaining)}")
assert not remaining, "El evento sigue activo tras cancelarlo"

print("\nTodo OK: create_event, list_events y cancel_event funcionan.")
