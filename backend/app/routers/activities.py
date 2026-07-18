"""商品动态 SSE：首页订阅 Kafka 扇出后的实时时间线。"""

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..activity_hub import activity_hub
from .chat import format_sse_message

router = APIRouter(prefix="/activities", tags=["activities"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/stream")
async def activity_stream(request: Request) -> StreamingResponse:
    """SSE：先推最近缓存，再持续推送新的商品改动动态。"""

    async def event_generator() -> AsyncIterator[str]:
        queue = activity_hub.subscribe()
        try:
            yield format_sse_message({"type": "connected"})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield format_sse_message(event)
                except asyncio.TimeoutError:
                    # 心跳，避免代理断开空闲连接
                    yield format_sse_message({"type": "ping"})
        finally:
            activity_hub.unsubscribe(queue)

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
