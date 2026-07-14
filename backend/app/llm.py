"""LangChain + Ollama Cloud LLM 封装（含工具调用）。"""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .schemas import ChatMessage
from .tools import (
    build_tools,
    get_mutations,
    reset_tool_context,
    rollback_tool_db,
    run_with_tool_session,
    set_tool_context,
)

def _system_prompt(current_user: models.User | None) -> str:
    login_status = (
        f"已登录（用户名：{current_user.username}）"
        if current_user
        else "未登录"
    )
    return (
        "你是「智能商城管理系统」的智能助手，只服务本系统相关事务。\n"
        f"当前用户状态：{login_status}\n"
        "\n"
        "【回答范围】仅可处理以下内容：\n"
        "- 本系统内的商品（含热门商品）、用户数据的查询与管理\n"
        "- 本系统的登录 / 注册 / 权限说明\n"
        "- 本系统功能怎么用（首页、商品管理、智能助手等）\n"
        "- 与上述直接相关的简短确认或追问\n"
        "\n"
        "【禁止范围】与本商城系统无关的问题一律拒绝，例如但不限于：\n"
        "天气、新闻、娱乐、旅游、医疗、投资、写诗/作文、通用编程、数学题、"
        "翻译、闲聊八卦、其他网站/App、与本项目无关的知识问答等。\n"
        "拒绝时：用一两句中文说明你只能协助本智能商城管理系统相关问题，并简要提示可问什么"
        "（如查热门商品、管理商品/用户）；不要回答无关内容，不要调用工具，不要延伸发挥。\n"
        "\n"
        "规则：\n"
        "1. 始终用简体中文回复用户，不要输出英文思考过程、计划步骤或内部独白。\n"
        "2. 用户寒暄、确认在线（如「在吗」「你好」）时：直接简短中文回复并说明可协助的范围，"
        "不要调用任何工具，也不要继续执行历史对话里未完成的批量任务。\n"
        "3. 只有用户明确要求查/增/改/删本系统数据时才调用工具；一次回复里写操作（创建/更新/删除）"
        "不要贪多，优先少量确认后再继续。商品名称必须唯一：已存在同名商品时不要重复创建，"
        "应提示名称已存在（可建议改名或改为更新已有商品）。\n"
        "4. 权限：\n"
        "   - 「热门商品」查询是公开的：未登录也可直接调用 list_hot_products，不要要求登录。\n"
        "   - 其余商品/用户的查询、创建、更新、删除必须已登录。\n"
        "   - 若当前为「未登录」且用户意图是需登录的数据库操作（即使信息不全，如只说「添加商品肥皂」），"
        "立刻直接回复请先去导航栏登录，禁止追问价格、库存、描述等字段，禁止调用需登录的工具，"
        "禁止承诺稍后帮其添加或继续收集信息。\n"
        "   - 若工具返回未登录，同样提示先去导航栏登录。\n"
        "5. 操作完成后用简洁中文总结；查询结果整理成易读列表。"
        "若上文已列出商品/用户及其 ID，后续改删时直接使用这些 ID，不要再向用户索要。\n"
        "6. 不要把 JSON 参数当最终回复发给用户，应调用对应工具。"
    )

MAX_TOOL_ROUNDS = 6
MAX_WRITES_PER_REQUEST = 3
WRITE_TOOLS = frozenset(
    {
        "create_product",
        "update_product",
        "delete_product",
        "create_user",
        "update_user",
        "delete_user",
    }
)
TOOL_LABELS = {
    "list_hot_products": "查询热门商品",
    "list_products": "查询商品列表",
    "get_product": "查询商品详情",
    "create_product": "创建商品",
    "update_product": "更新商品",
    "delete_product": "删除商品",
    "list_users": "查询用户列表",
    "get_user": "查询用户详情",
    "create_user": "创建用户",
    "update_user": "更新用户",
    "delete_user": "删除用户",
}

# 无需登录即可调用的公开工具
PUBLIC_TOOLS = frozenset({"list_hot_products"})

# 未登录时用于短路拦截的数据库操作意图（避免模型先追问字段）
_DB_INTENT_RE = re.compile(
    r"(添加|创建|新增|删除|删掉|修改|更新|查询|查看|列出|搜索|找).{0,12}(商品|产品|用户)"
    r"|(商品|产品|用户).{0,12}(添加|创建|新增|删除|修改|更新|列表|库存|价格|详情)"
    r"|增删改查|数据库操作"
)
_HOT_PRODUCT_INTENT_RE = re.compile(r"热门\s*(商品|产品)|最热|畅销|点击量")

LOGIN_REQUIRED_REPLY = (
    "当前未登录。请先在导航栏登录后，再进行商品或用户的查询与管理操作。"
)

_llm: ChatOllama | None = None
_tools = build_tools()
_tools_by_name = {t.name: t for t in _tools}

CancelCheck = Callable[[], Awaitable[bool]]


def get_llm() -> ChatOllama:
    """懒加载并缓存 ChatOllama 实例，避免每次请求重复构造。"""
    global _llm
    if _llm is None:
        if not settings.ollama_api_key:
            raise ValueError("未配置 OLLAMA_API_KEY，无法调用云端模型")
        _llm = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.7,
            client_kwargs={
                "headers": {
                    "Authorization": f"Bearer {settings.ollama_api_key}",
                }
            },
        )
    return _llm


def _looks_like_db_intent(text: str) -> bool:
    text = text.strip()
    # 热门商品查询是公开的，不走登录拦截
    if _HOT_PRODUCT_INTENT_RE.search(text):
        return False
    return bool(_DB_INTENT_RE.search(text))


def _to_lc_messages(
    history: list[ChatMessage],
    message: str,
    current_user: models.User | None,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = [
        SystemMessage(content=_system_prompt(current_user))
    ]
    for item in history:
        if item.role == "user":
            messages.append(HumanMessage(content=item.content))
        else:
            messages.append(AIMessage(content=item.content))
    messages.append(HumanMessage(content=message))
    return messages


def _content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def _run_tool(name: str, args: dict[str, Any]) -> str:
    tool = _tools_by_name.get(name)
    if tool is None:
        return f"未知工具：{name}"
    try:
        result = tool.invoke(args)
        return result if isinstance(result, str) else str(result)
    except Exception as exc:
        rollback_tool_db()
        return f"工具执行失败：{exc}"


def _run_tool_blocking(name: str, args: dict[str, Any]) -> str:
    """在工作线程内用独立 Session 执行工具。"""
    return run_with_tool_session(lambda: _run_tool(name, args))


async def _run_tool_async(name: str, args: dict[str, Any]) -> str:
    """把同步工具/DB 丢到线程池，避免堵住 asyncio 事件循环。"""
    return await asyncio.to_thread(_run_tool_blocking, name, args)


def _normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for call in tool_calls or []:
        if isinstance(call, dict):
            name = call.get("name", "")
            args = call.get("args", {})
            call_id = call.get("id", name)
        else:
            name = getattr(call, "name", "") or ""
            args = getattr(call, "args", {}) or {}
            call_id = getattr(call, "id", None) or name
        if not isinstance(args, dict):
            args = {}
        normalized.append({"name": name, "args": args, "id": str(call_id)})
    return normalized


def _fallback_text() -> str:
    mutations = get_mutations()
    if "products" in mutations and "users" in mutations:
        return "操作已完成，商品和用户数据已更新。"
    if "products" in mutations:
        return "操作已完成，商品列表已更新。"
    if "users" in mutations:
        return "操作已完成，用户数据已更新。"
    return "我在的，有什么可以帮你？"


def _tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name)


def _brief_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    parts: list[str] = []
    for key, value in args.items():
        text = str(value)
        if len(text) > 40:
            text = text[:40] + "…"
        parts.append(f"{key}={text}")
    joined = "，".join(parts)
    return f"（{joined}）" if joined else ""


def _brief_result(result: str) -> str:
    text = result.strip()
    if len(text) > 160:
        return text[:160] + "…"
    return text


def _chunk_to_ai_message(chunk: AIMessageChunk) -> AIMessage:
    return AIMessage(
        content=chunk.content,
        tool_calls=list(getattr(chunk, "tool_calls", None) or []),
        id=getattr(chunk, "id", None),
    )


async def _soft_stream(
    event_key: str,
    text: str,
    *,
    chunk_size: int = 8,
    delay: float = 0.012,
) -> AsyncIterator[dict[str, Any]]:
    """把已有文本按小段推出，形成流式观感。"""
    if not text:
        return
    for i in range(0, len(text), chunk_size):
        yield {event_key: text[i : i + chunk_size]}
        await asyncio.sleep(delay)


async def chat_stream(
    message: str,
    history: list[ChatMessage],
    db: Session,
    current_user: models.User | None,
    is_cancelled: CancelCheck | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """工具调用循环；思考过程与最终回复均流式产出。"""
    llm_with_tools = get_llm().bind_tools(_tools)
    plain_llm = get_llm()
    messages = _to_lc_messages(history, message, current_user)
    db_token, user_token, mutations_token = set_tool_context(db, current_user)
    write_count = 0

    async def cancelled() -> bool:
        return bool(is_cancelled and await is_cancelled())

    try:
        # 未登录且明显是数据库操作：直接提示登录，避免模型先追问字段
        if current_user is None and _looks_like_db_intent(message):
            async for event in _soft_stream("delta", LOGIN_REQUIRED_REPLY):
                yield event
            yield {"done": True, "refresh": []}
            return

        for round_idx in range(MAX_TOOL_ROUNDS):
            if await cancelled():
                yield {"done": True, "refresh": get_mutations()}
                return

            yield {"status": "正在思考…" if round_idx == 0 else "继续分析…"}

            assembled: AIMessageChunk | None = None
            saw_tool_chunks = False
            leaked_to_delta = False

            async for chunk in llm_with_tools.astream(messages):
                if await cancelled():
                    yield {"done": True, "refresh": get_mutations()}
                    return

                assembled = chunk if assembled is None else assembled + chunk
                tool_call_chunks = getattr(chunk, "tool_call_chunks", None) or []
                if tool_call_chunks:
                    saw_tool_chunks = True
                    if leaked_to_delta:
                        # 先前误把正文流进回复区，收回并改到思考区
                        yield {"clear_delta": True}
                        leaked_to_delta = False

                piece = _content_to_str(chunk.content)
                if not piece:
                    continue

                if saw_tool_chunks:
                    yield {"status_delta": piece}
                else:
                    # 尚无工具调用迹象：先流式写入回复气泡
                    leaked_to_delta = True
                    yield {"delta": piece}

            if assembled is None:
                yield {"delta": _fallback_text()}
                yield {"done": True, "refresh": get_mutations()}
                return

            response = _chunk_to_ai_message(assembled)
            tool_calls = _normalize_tool_calls(getattr(response, "tool_calls", None))

            if not tool_calls:
                # 正文已在上方流式写入 delta；若模型只出了空内容则兜底
                if not _content_to_str(response.content).strip():
                    yield {"clear_delta": True}
                    yield {"status": "正在生成回复…"}
                    produced = False
                    async for chunk in plain_llm.astream(messages):
                        if await cancelled():
                            break
                        piece = _content_to_str(chunk.content)
                        if piece:
                            produced = True
                            yield {"delta": piece}
                    if not produced:
                        yield {"delta": _fallback_text()}
                yield {"done": True, "refresh": get_mutations()}
                return

            # 有工具：确保回复区清空，思考过程继续
            if leaked_to_delta:
                yield {"clear_delta": True}

            # 未登录时：仅允许公开工具；若混入需登录工具则直接提示登录
            if current_user is None:
                names = {call["name"] for call in tool_calls}
                if not names.issubset(PUBLIC_TOOLS):
                    async for event in _soft_stream("delta", LOGIN_REQUIRED_REPLY):
                        yield event
                    yield {"done": True, "refresh": []}
                    return
                # 只保留公开工具，去掉误带的空/未知调用后继续执行
                tool_calls = [c for c in tool_calls if c["name"] in PUBLIC_TOOLS]

            messages.append(response)
            for call in tool_calls:
                if await cancelled():
                    yield {"done": True, "refresh": get_mutations()}
                    return

                name = call["name"]
                label = _tool_label(name)
                tool_line = f"调用工具：{label}{_brief_args(call['args'])}"
                yield {"status": ""}
                async for event in _soft_stream("status_delta", tool_line):
                    yield event

                if name in WRITE_TOOLS:
                    if write_count >= MAX_WRITES_PER_REQUEST:
                        result = (
                            '{"error":"本轮最多执行 '
                            + str(MAX_WRITES_PER_REQUEST)
                            + ' 次写操作，请下一轮再继续"}'
                        )
                    else:
                        result = await _run_tool_async(name, call["args"])
                        write_count += 1
                else:
                    result = await _run_tool_async(name, call["args"])

                result_line = f"工具结果：{_brief_result(result)}"
                yield {"status": ""}
                async for event in _soft_stream("status_delta", result_line, chunk_size=12):
                    yield event

                messages.append(
                    ToolMessage(
                        content=result,
                        tool_call_id=call["id"],
                        name=name,
                    )
                )

        if await cancelled():
            yield {"done": True, "refresh": get_mutations()}
            return

        yield {"status": "正在生成回复…"}
        produced = False
        async for chunk in plain_llm.astream(messages):
            if await cancelled():
                break
            text = _content_to_str(chunk.content)
            if text:
                produced = True
                yield {"delta": text}
        if not produced:
            yield {"delta": _fallback_text()}
        yield {"done": True, "refresh": get_mutations()}
    finally:
        reset_tool_context(db_token, user_token, mutations_token)
