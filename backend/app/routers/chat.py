"""智能助手聊天路由（SSE 流式输出）。"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user_optional
from ..llm import chat_stream

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(
    payload: schemas.ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
) -> StreamingResponse:
    """与云端 LLM 流式对话，返回 SSE 事件流；已登录时可调用数据库工具。"""

    async def event_gen() -> AsyncIterator[str]:
        try:
            async for event in chat_stream(
                payload.message,
                payload.history,
                db,
                current_user,
                is_cancelled=request.is_disconnected,
            ):
                if await request.is_disconnected():
                    break
                yield _sse(event)
        except ValueError as exc:
            yield _sse({"error": str(exc)})
        except Exception as exc:
            yield _sse({"error": f"模型调用失败：{exc}"})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
