import asyncio

from fastapi import APIRouter, WebSocket
from infra.stream import Stream

router = APIRouter()
bus = Stream()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        snapshot = await asyncio.to_thread(
            bus.consume, "mission_stream", "ui_group", "ui_consumer"
        )
        if snapshot:
            await ws.send_json(snapshot)
        else:
            await asyncio.sleep(0.25)
