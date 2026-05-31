from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


@router.websocket("/ws/office")
async def office_socket(websocket: WebSocket) -> None:
    hub = websocket.app.state.support_hub

    try:
        connected = await hub.connect(websocket)
        if not connected:
            return

        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                continue
            await hub.handle_command(payload, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)

