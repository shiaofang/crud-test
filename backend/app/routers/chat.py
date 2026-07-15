"""智能助手聊天路由（SSE 流式输出）。

流程简述：
1. 前端 POST /api/chat，带上当前消息与历史对话
2. 本路由立刻返回 StreamingResponse（不会等模型整段说完）
3. 后台生成器不断从 chat_stream 拿到事件 dict
4. 把每个 dict 格式化成 SSE 文本推给前端
"""

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

# SSE 响应头：禁止缓存、保持连接、关闭 Nginx 缓冲（否则实时感会丢失）
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def format_sse_message(payload: dict) -> str:
    """把一个 Python 字典格式化成一条 SSE 文本。

    浏览器端会按行解析，形如::

        data: {"delta":"你好"}\\n\\n
    """
    json_text = json.dumps(payload, ensure_ascii=False)
    return f"data: {json_text}\n\n"


@router.post("")
async def chat(
    payload: schemas.ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
) -> StreamingResponse:
    """与云端 LLM 流式对话，返回 SSE 事件流；已登录时可调用数据库工具。"""

    async def event_generator() -> AsyncIterator[str]:
        """异步生成器：产出一条条 SSE 字符串，供 StreamingResponse 写出。"""
        try:
            async for event in chat_stream(
                message=payload.message,
                history=payload.history,
                db=db,
                current_user=current_user,
                is_cancelled=request.is_disconnected,
            ):
                yield format_sse_message(event)
        except ValueError as exc:
            # 配置类错误（例如缺少 API Key）
            yield format_sse_message({"error": str(exc)})
        except Exception as exc:
            # 流已经开始后无法再改 HTTP 状态码，只能用 SSE error 事件通知前端
            yield format_sse_message({"error": f"模型调用失败：{exc}"})

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
