"""
WebSocket handler — bridges EventBus events to connected clients.
Clients connect to ws://localhost:8420/ws and receive real-time events.
Clients can also send commands via WebSocket.

Requires token authentication: clients must send {"type": "auth", "token": "..."}
as their first message within 5 seconds.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nex.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()

# Connected (authenticated) WebSocket clients
_clients: set[WebSocket] = set()

AUTH_TIMEOUT = 5  # seconds to authenticate


async def broadcast(event_type: str, data: dict):
    """Send an event to all connected WebSocket clients."""
    message = json.dumps({"type": event_type, "data": data})
    disconnected = set()

    for ws in _clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)

    _clients.difference_update(disconnected)


async def _event_forwarder(data: dict):
    """EventBus handler that forwards all events to WebSocket clients."""
    event_type = data.get("_event_type", "unknown")
    await broadcast(event_type, data)


def _install_event_bridge(event_bus):
    """Subscribe to events that matter and forward them to WebSocket clients."""
    event_types = [
        "system.ready",
        "system.module_error",
        "command.response",
        "file.read_response",
        "system.stats",
        "tool.executing",
        "tool.completed",
        "settings.updated",
        "settings.voice_change",
        "mic.transcribed",
        "system.locked",
        "system.unlocked",
        "mic.listening",
        "mic.speech_detected",
        "mic.level",
    ]

    for evt in event_types:
        async def handler(data, _evt=evt):
            data_copy = dict(data)
            data_copy["_event_type"] = _evt
            await broadcast(_evt, data_copy)

        event_bus.subscribe(evt, handler)

    logger.info(f"WebSocket event bridge installed ({len(event_types)} events)")


_bridge_installed = False


async def _authenticate(ws: WebSocket) -> bool:
    """Wait for auth message within timeout. Returns True if authenticated."""
    from nex.api.server import session_token

    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") == "auth" and msg.get("token") == session_token:
            return True
        logger.warning("WebSocket auth failed: invalid token")
        return False
    except asyncio.TimeoutError:
        logger.warning("WebSocket auth failed: timeout")
        return False
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"WebSocket auth failed: {e}")
        return False


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time event streaming."""
    global _bridge_installed

    await ws.accept()

    # Require authentication
    if not await _authenticate(ws):
        await ws.send_text(json.dumps({
            "type": "error",
            "data": {"message": "Authentication required. Send {type: 'auth', token: '...'} first."},
        }))
        await ws.close(code=4001, reason="Authentication failed")
        return

    _clients.add(ws)
    logger.info(f"WebSocket client authenticated ({len(_clients)} total)")

    # Install event bridge on first connection
    if not _bridge_installed:
        from nex.api.server import engine
        if engine is not None:
            _install_event_bridge(engine.event_bus)
            _bridge_installed = True

    try:
        # Send welcome message
        await ws.send_text(json.dumps({
            "type": "connected",
            "data": {"message": "Connected to Nex", "clients": len(_clients)},
        }))

        # Listen for client messages (commands)
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                await _handle_client_message(ws, msg)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "Invalid JSON"},
                }))
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        logger.info(f"WebSocket client disconnected ({len(_clients)} remaining)")


async def _handle_client_message(sender: WebSocket, msg: dict):
    """Process a message from a WebSocket client."""
    msg_type = msg.get("type", "")

    if msg_type == "command":
        from nex.api.server import engine
        if engine is not None:
            await engine.event_bus.publish("system.command", {
                "command": msg.get("command", ""),
                "source": "websocket",
            })

    elif msg_type == "replay_tts":
        # Replay a response via TTS
        text = msg.get("text", "")
        if text:
            from nex.api.server import engine
            if engine is not None:
                await engine.event_bus.publish("command.response", {
                    "text": text,
                    "command": "_replay",
                })

    elif msg_type == "ping":
        await sender.send_text(json.dumps({
            "type": "pong",
            "data": {"message": "alive"},
        }))
