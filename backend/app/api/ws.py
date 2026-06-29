"""WebSocket telemetry — the live feed behind the React Flow "God View".

`GET /ws/telemetry` streams every orchestrator event as JSON (the admin God View). Pass
`?run_id=<id>` to follow a single run; that variant closes once the run reaches a terminal
phase (done / error). A concurrent receive task detects client disconnects so the subscription
is always cleaned up.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, WebSocket

from app.telemetry.events import Phase

ws_router = APIRouter()

_TERMINAL = {Phase.DONE, Phase.ERROR}


def _authorize_ws(websocket: WebSocket, api_key: str | None) -> bool:
    """When auth is enabled, require a valid key. Browsers can't set WS headers easily, so the
    key may arrive as the `api_key` query param or an Authorization: Bearer header."""
    if not getattr(websocket.app.state, "auth_enabled", False):
        return True
    raw = api_key
    if not raw:
        header = websocket.headers.get("authorization", "")
        if header.startswith("Bearer "):
            raw = header[len("Bearer ") :].strip()
    if not raw:
        return False
    return websocket.app.state.keys.verify(raw) is not None


@ws_router.websocket("/ws/telemetry")
async def telemetry(
    websocket: WebSocket,
    run_id: str | None = Query(default=None),
    api_key: str | None = Query(default=None),
) -> None:
    if not _authorize_ws(websocket, api_key):
        # 4401 = application-level "unauthorized" close code.
        await websocket.close(code=4401)
        return

    await websocket.accept()
    bus = websocket.app.state.bus
    queue = bus.subscribe()

    async def _watch_disconnect() -> None:
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            return

    disconnect_task = asyncio.create_task(_watch_disconnect())
    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {get_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if disconnect_task in done:
                get_task.cancel()
                break

            event = get_task.result()
            if run_id is not None and event.run_id != run_id:
                continue

            try:
                await websocket.send_json(event.to_dict())
            except Exception:
                break

            if run_id is not None and event.run_id == run_id and event.phase in _TERMINAL:
                break
    finally:
        disconnect_task.cancel()
        bus.unsubscribe(queue)
