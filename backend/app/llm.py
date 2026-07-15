"""LangChain + Ollama Cloud LLM 封装（含工具调用）。

本模块职责：
1. 构造系统提示词与对话消息
2. 用 astream 从云端模型流式取 token（LLM 侧流式）
3. 多轮工具调用循环（查/增/改/删商品与用户）
4. 把过程整理成事件 dict，交给 chat 路由再用 SSE 推给前端

常见事件字段：
- status / status_delta：思考过程、工具调用说明
- delta：最终回复正文（流式增量）
- clear_delta：清空前端回复气泡（改道或兜底时用）
- done + refresh：结束，并告知前端要刷新哪些列表
- error：由路由层捕获异常后包装
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

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

# ---------------------------------------------------------------------------
# 系统提示词
# ---------------------------------------------------------------------------


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
        "- 本系统内的商品、用户数据的查询与管理\n"
        "- 本系统的登录 / 注册 / 权限说明\n"
        "- 本系统功能怎么用（首页、商品管理、智能助手等）\n"
        "- 与上述直接相关的简短确认或追问\n"
        "\n"
        "【禁止范围】与本商城系统无关的问题一律拒绝，例如但不限于：\n"
        "天气、新闻、娱乐、旅游、医疗、投资、写诗/作文、通用编程、数学题、"
        "翻译、闲聊八卦、其他网站/App、与本项目无关的知识问答等。\n"
        "拒绝时：用一两句中文说明你只能协助本智能商城管理系统相关问题，并简要提示可问什么"
        "（如管理商品/用户）；不要回答无关内容，不要调用工具，不要延伸发挥。\n"
        "\n"
        "规则：\n"
        "1. 始终用简体中文面对用户；思考过程可写简短中文步骤，但最终回复禁止英文独白，"
        "禁止把工具参数 / JSON 发给用户。\n"
        "2. 用户寒暄、确认在线（如「在吗」「你好」）时：直接简短中文回复并说明可协助的范围，"
        "不要调用任何工具，也不要继续执行历史对话里未完成的批量任务。\n"
        "3. 只有用户明确要求查/增/改/删本系统数据时才调用工具；你只能通过工具读写数据库。\n"
        "\n"
        "【数据操作方法】可用工具即全部能力：\n"
        "- 商品：list_products / get_product / create_product / update_product / delete_product\n"
        "- 用户：list_users / get_user / create_user / update_user / delete_user\n"
        "\n"
        "复杂任务允许边想边调用工具边改，推荐节奏：\n"
        "① 先复述用户目标（一句话）\n"
        "② 先查后列：用 list_* 查出候选（page_size 建议 100）；若 total 大于本页数量，"
        "必须继续 page=2,3…翻页直到拿全。在思考中列出将处理的项并核对是否符合条件\n"
        "③ 再改：对核对通过的目标，自己算出新值，并在同一轮尽量并行多次调用 update_*；"
        "不要每次只改 1～2 个；没改完禁止总结，必须继续下一轮改剩余项\n"
        "④ 收尾前必须再 list 一次，确认没有遗漏符合条件的项；确认没有后才中文总结"
        "（名称、ID、旧值→新值）\n"
        "\n"
        "示例：「把价格超过100的改成100以下随机价」→ 先 list 全部商品（含翻页）→ "
        "筛出 price>100 的列出来核对 → 再对它们并行 update → 再 list 确认已无 price>100 → 中文总结。\n"
        "\n"
        "创建商品：名称必填；描述/价格/库存缺省时可自行补合理值。"
        "商品名称必须唯一，已存在同名时不要重复创建。\n"
        "\n"
        "4. 权限：\n"
        "   - 商品/用户的查询、创建、更新、删除必须已登录。\n"
        "   - 若当前为「未登录」且用户意图是需登录的数据库操作（即使信息不全，如只说「添加商品肥皂」），"
        "立刻直接回复请先去导航栏登录，禁止追问价格、库存、描述等字段，禁止调用需登录的工具，"
        "禁止承诺稍后帮其添加或继续收集信息。\n"
        "   - 若工具返回未登录，同样提示先去导航栏登录。\n"
        "5. 若上文已列出商品/用户及其 ID，后续改删时直接使用这些 ID，不要再向用户索要。"
    )


# ---------------------------------------------------------------------------
# 常量与全局缓存
# ---------------------------------------------------------------------------

MAX_TOOL_ROUNDS = 20
MAX_WRITES_PER_REQUEST = 40
LLM_STREAM_RETRIES = 2
MAX_AUTO_CONTINUES = 6

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

# 无需登录即可调用的公开工具（当前无公开业务工具）
PUBLIC_TOOLS: frozenset[str] = frozenset()

# 未登录时用于短路拦截的数据库操作意图（避免模型先追问字段）
_DB_INTENT_RE = re.compile(
    r"(添加|创建|新增|删除|删掉|修改|更新|查询|查看|列出|搜索|找).{0,12}(商品|产品|用户)"
    r"|(商品|产品|用户).{0,12}(添加|创建|新增|删除|修改|更新|列表|库存|价格|详情)"
    r"|增删改查|数据库操作"
)

LOGIN_REQUIRED_REPLY = (
    "当前未登录。请先在导航栏登录后，再进行商品或用户的查询与管理操作。"
)

_llm: ChatOllama | None = None
_tools = build_tools()
_tools_by_name = {tool.name: tool for tool in _tools}

# 客户端断开检测：无参异步函数，返回 True 表示已取消
CancelCheck = Callable[[], Awaitable[bool]]


# ---------------------------------------------------------------------------
# LLM 实例
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 消息与内容转换
# ---------------------------------------------------------------------------


def _looks_like_db_intent(text: str) -> bool:
    """判断用户这句话是否像「要操作商品/用户数据库」。"""
    return bool(_DB_INTENT_RE.search(text.strip()))


def _to_lc_messages(
    history: list[ChatMessage],
    message: str,
    current_user: models.User | None,
) -> list[BaseMessage]:
    """把前端的 history + 当前 message 转成 LangChain 消息列表。"""
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
    """把模型 content（可能是 str / list / 其它）统一转成纯文本。"""
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


# ---------------------------------------------------------------------------
# 工具执行
# ---------------------------------------------------------------------------


def _run_tool(name: str, args: dict[str, Any]) -> str:
    """按名称调用已注册工具，返回字符串结果。"""
    tool = _tools_by_name.get(name)
    if tool is None:
        return f"未知工具：{name}"
    try:
        result = tool.invoke(args)
        if isinstance(result, str):
            return result
        return str(result)
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
    """把模型返回的 tool_calls 统一成 [{name, args, id}, ...]。"""
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


def _parse_tool_json(result: str) -> dict[str, Any] | None:
    """尝试把工具返回的 JSON 字符串解析成 dict；失败返回 None。"""
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict):
        return data
    return None


def _format_product_line(
    product: dict[str, Any],
    *,
    changed: dict[str, Any] | None = None,
) -> str:
    """把商品信息格式化成一句中文摘要，供操作笔记使用。"""
    name = product.get("name") or f"ID {product.get('id')}"
    product_id = product.get("id")
    parts = [f"「{name}」(ID {product_id})"]

    field_labels = (
        ("price", "价格"),
        ("stock", "库存"),
        ("description", "描述"),
        ("name", "名称"),
    )
    if changed:
        for key, label in field_labels:
            if key in changed and changed[key] is not None:
                parts.append(f"{label}→{changed[key]}")
    else:
        if "price" in product:
            parts.append(f"价格 {product['price']}")
        if "stock" in product:
            parts.append(f"库存 {product['stock']}")

    return "，".join(parts)


# ---------------------------------------------------------------------------
# 从工具结果提炼操作笔记（给用户看的中文摘要）
# ---------------------------------------------------------------------------


def _note_from_tool_result(name: str, args: dict[str, Any], result: str) -> str | None:
    """从写操作工具结果提炼一条中文摘要；失败或不相关则返回 None。"""
    data = _parse_tool_json(result)
    if data is None:
        return None
    if data.get("error"):
        return f"{_tool_label(name)}失败：{data['error']}"

    if name == "create_product" and data.get("ok"):
        product = data.get("product") or {}
        return f"已创建商品 {_format_product_line(product)}"

    if name == "update_product" and data.get("ok"):
        product = data.get("product") or {}
        changed = {k: args[k] for k in ("name", "description", "price", "stock") if k in args}
        return f"已更新商品 {_format_product_line(product, changed=changed)}"

    if name == "delete_product" and data.get("ok"):
        deleted_id = data.get("deleted_id")
        return f"已删除商品 ID {deleted_id}"

    if name == "create_user" and data.get("ok"):
        user = data.get("user") or {}
        return f"已创建用户「{user.get('username')}」(ID {user.get('id')})"

    if name == "update_user" and data.get("ok"):
        user = data.get("user") or {}
        return f"已更新用户「{user.get('username')}」(ID {user.get('id')})"

    if name == "delete_user" and data.get("ok"):
        return f"已删除用户 ID {data.get('deleted_id')}"

    return None


# ---------------------------------------------------------------------------
# 回复质量：弱总结检测与兜底文案
# ---------------------------------------------------------------------------


def _is_weak_summary(text: str) -> bool:
    """判断模型最终回复是否过于空泛或误把工具参数当回复。"""
    cleaned = text.strip()
    if cleaned.startswith("{") or cleaned.startswith("["):
        return True
    compact = re.sub(r"\s+", "", cleaned)
    if len(compact) > 40:
        return False
    weak_phrases = (
        "操作已完成",
        "商品列表已更新",
        "用户数据已更新",
        "已更新",
        "完成了",
        "好的",
    )
    return any(p in compact for p in weak_phrases)


def _summary_from_notes(notes: list[str], *, interrupted: bool = False) -> str:
    """根据操作笔记 / mutations 生成兜底中文总结。"""
    if notes:
        body = "\n".join(notes)
        if interrupted:
            return (
                f"{body}\n\n"
                "以上为已完成部分；后续处理因模型异常中断，可能尚未全部完成。"
                "请重新发送同一指令以继续处理剩余数据。"
            )
        return f"操作结果如下：\n{body}"

    mutations = get_mutations()
    if interrupted and mutations:
        return (
            "部分操作已执行，但后续处理因模型异常中断，可能尚未全部完成。"
            "请重新发送同一指令以继续处理剩余数据。"
        )
    if "products" in mutations and "users" in mutations:
        return "操作已完成，商品和用户数据已更新。"
    if "products" in mutations:
        return "操作已完成，商品列表已更新。"
    if "users" in mutations:
        return "操作已完成，用户数据已更新。"
    return "我在的，有什么可以帮你？"


def _fallback_text(notes: list[str] | None = None, *, interrupted: bool = False) -> str:
    """模型没给出合格回复时，用操作笔记生成兜底文案。"""
    return _summary_from_notes(notes or [], interrupted=interrupted)


def _tool_label(name: str) -> str:
    """工具英文名 → 中文展示名。"""
    return TOOL_LABELS.get(name, name)


def _brief_args(args: dict[str, Any]) -> str:
    """把工具参数压成短中文，用于 status 展示。"""
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
    """截断工具结果，避免 status 区过长。"""
    text = result.strip()
    if len(text) > 160:
        return text[:160] + "…"
    return text


def _compact_tool_result_for_llm(name: str, result: str) -> str:
    """压缩写入对话历史的工具结果，减轻后续轮次请求体积。"""
    data = _parse_tool_json(result)
    if data is None:
        return result[:1200] if len(result) > 1200 else result

    if name == "list_products" and isinstance(data.get("items"), list):
        items = []
        for item in data["items"]:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "price": item.get("price"),
                    "stock": item.get("stock"),
                }
            )
        return json.dumps({"total": data.get("total", len(items)), "items": items}, ensure_ascii=False)

    if name in {"create_product", "update_product"} and isinstance(data.get("product"), dict):
        p = data["product"]
        return json.dumps(
            {
                "ok": True,
                "product": {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "price": p.get("price"),
                    "stock": p.get("stock"),
                },
            },
            ensure_ascii=False,
        )

    text = json.dumps(data, ensure_ascii=False)
    return text[:1200] + "…" if len(text) > 1200 else text


def _chunk_to_ai_message(chunk: AIMessageChunk) -> AIMessage:
    tool_calls = list(getattr(chunk, "tool_calls", None) or [])
    # 带 tool_calls 时丢掉冗长思考正文，避免下一轮请求体过大触发云端 500
    content: Any = "" if tool_calls else chunk.content
    return AIMessage(
        content=content,
        tool_calls=tool_calls,
        id=getattr(chunk, "id", None),
    )


def _is_transient_llm_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "500",
            "502",
            "503",
            "504",
            "internal server error",
            "timeout",
            "temporar",
            "rate limit",
            "overloaded",
        )
    )


# ---------------------------------------------------------------------------
# 假流式输出（已有完整文本时，切成小段推给前端）
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 主入口：对话流
# ---------------------------------------------------------------------------


async def chat_stream(
    message: str,
    history: list[ChatMessage],
    db: Session,
    current_user: models.User | None,
    is_cancelled: CancelCheck | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """智能助手主循环：流式思考 + 工具调用 + 流式最终回复。

    Args:
        message: 用户当前输入。
        history: 前端传来的历史对话。
        db: 当前请求的数据库 Session。
        current_user: 已登录用户；未登录为 None。
        is_cancelled: 可选的取消检查（通常传 request.is_disconnected）。

    Yields:
        事件字典，由 chat 路由格式化成 SSE 推给前端。
    """
    llm_with_tools = get_llm().bind_tools(_tools)
    plain_llm = get_llm()
    messages = _to_lc_messages(history, message, current_user)
    db_token, user_token, mutations_token = set_tool_context(db, current_user)
    write_count = 0
    action_notes: list[str] = []
    auto_continues = 0
    completion_checks = 0

    async def client_disconnected() -> bool:
        """前端是否已断开（例如用户关闭页面）。"""
        if is_cancelled is None:
            return False
        return await is_cancelled()

    try:
        # 未登录且明显是数据库操作：直接提示登录，避免模型先追问字段
        if current_user is None and _looks_like_db_intent(message):
            async for event in _soft_stream("delta", LOGIN_REQUIRED_REPLY):
                yield event
            yield {"done": True, "refresh": []}
            return

        for round_idx in range(MAX_TOOL_ROUNDS):
            if await client_disconnected():
                yield {"done": True, "refresh": get_mutations()}
                return

            yield {"status": "正在思考…" if round_idx == 0 else "继续分析…"}

            assembled: AIMessageChunk | None = None
            saw_tool_chunks = False
            leaked_to_delta = False
            stream_error: Exception | None = None

            for attempt in range(LLM_STREAM_RETRIES):
                assembled = None
                saw_tool_chunks = False
                leaked_to_delta = False
                stream_error = None
                try:
                    async for chunk in llm_with_tools.astream(messages):
                        if await client_disconnected():
                            yield {"done": True, "refresh": get_mutations()}
                            return

                        # bind_tools 后 astream 的静态类型偏宽（AIMessage|…），运行时仍是 AIMessageChunk
                        piece_chunk = cast(AIMessageChunk, chunk)
                        assembled = (
                            piece_chunk
                            if assembled is None
                            else cast(AIMessageChunk, assembled + piece_chunk)
                        )
                        tool_call_chunks = (
                            getattr(piece_chunk, "tool_call_chunks", None) or []
                        )
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
                    break
                except Exception as exc:
                    stream_error = exc
                    if leaked_to_delta:
                        yield {"clear_delta": True}
                        leaked_to_delta = False
                    if attempt + 1 < LLM_STREAM_RETRIES and _is_transient_llm_error(exc):
                        yield {"status": "模型暂时异常，正在重试…"}
                        await asyncio.sleep(0.6 * (attempt + 1))
                        continue
                    break

            if stream_error is not None:
                # 云端多轮抖动时：自动注入「继续」提示，让模型用已有查询结果接着改
                can_auto_continue = (
                    auto_continues < MAX_AUTO_CONTINUES
                    and _is_transient_llm_error(stream_error)
                    and (action_notes or any(
                        isinstance(m, ToolMessage) for m in messages
                    ))
                )
                if can_auto_continue:
                    auto_continues += 1
                    yield {"clear_delta": True}
                    yield {
                        "status": (
                            f"模型中断，自动继续剩余任务"
                            f"（{auto_continues}/{MAX_AUTO_CONTINUES}）…"
                        )
                    }
                    messages.append(
                        HumanMessage(
                            content=(
                                "上一轮模型调用中断。请根据对话中已有的查询结果与工具结果，"
                                "继续完成用户尚未做完的剩余操作；不要重复已经成功的写操作。"
                                "尽量在同一轮并行发起多个 update/create/delete。"
                                "改完前不要总结；可先再 list 核对是否还有遗漏，再继续改。"
                                "全部完成后用中文总结具体改动，不要输出 JSON。"
                            )
                        )
                    )
                    continue

                if get_mutations() or action_notes:
                    yield {"clear_delta": True}
                    async for event in _soft_stream(
                        "delta", _fallback_text(action_notes, interrupted=True)
                    ):
                        yield event
                    yield {"done": True, "refresh": get_mutations()}
                    return
                raise stream_error

            if assembled is None:
                yield {"delta": _fallback_text(action_notes)}
                yield {"done": True, "refresh": get_mutations()}
                return

            response = _chunk_to_ai_message(assembled)
            tool_calls = _normalize_tool_calls(getattr(response, "tool_calls", None))

            if not tool_calls:
                # 写操作后最多强制收尾核对 2 次，避免只改一部分就提前总结
                if action_notes and completion_checks < 2:
                    completion_checks += 1
                    yield {"clear_delta": True}
                    yield {"status": "收尾核对中，检查是否还有遗漏…"}
                    if _content_to_str(response.content).strip():
                        messages.append(response)
                    messages.append(
                        HumanMessage(
                            content=(
                                "请先再调用 list_products（page_size=100，必要时翻页）核对："
                                "是否还有符合用户条件、尚未改完的商品。"
                                "若有，立即在同一轮并行 update 剩余项，不要总结；"
                                "若确认没有遗漏了，再用中文总结本次全部改动。"
                            )
                        )
                    )
                    continue

                # 正文已在上方流式写入 delta；空内容 / JSON / 空泛总结 → 用明细兜底
                final_text = _content_to_str(response.content).strip()
                if not final_text:
                    yield {"clear_delta": True}
                    yield {"status": "正在生成回复…"}
                    produced_parts = list[str]()
                    try:
                        async for chunk in plain_llm.astream(messages):
                            if await client_disconnected():
                                break
                            piece = _content_to_str(chunk.content)
                            if piece:
                                produced_parts.append(piece)
                                yield {"delta": piece}
                    except Exception:
                        produced_parts = []
                    produced_text = "".join(produced_parts).strip()
                    if not produced_text or _is_weak_summary(produced_text):
                        yield {"clear_delta": True}
                        async for event in _soft_stream(
                            "delta", _fallback_text(action_notes)
                        ):
                            yield event
                elif _is_weak_summary(final_text):
                    yield {"clear_delta": True}
                    async for event in _soft_stream(
                        "delta", _fallback_text(action_notes)
                    ):
                        yield event
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
                if await client_disconnected():
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

                note = _note_from_tool_result(name, call["args"], result)
                if note:
                    action_notes.append(note)

                result_line = f"工具结果：{_brief_result(result)}"
                yield {"status": ""}
                async for event in _soft_stream("status_delta", result_line, chunk_size=12):
                    yield event

                messages.append(
                    ToolMessage(
                        content=_compact_tool_result_for_llm(name, result),
                        tool_call_id=call["id"],
                        name=name,
                    )
                )

        if await client_disconnected():
            yield {"done": True, "refresh": get_mutations()}
            return

        yield {"status": "正在生成回复…"}
        produced_parts = list[str]()
        try:
            async for chunk in plain_llm.astream(messages):
                if await client_disconnected():
                    break
                text = _content_to_str(chunk.content)
                if text:
                    produced_parts.append(text)
                    yield {"delta": text}
        except Exception:
            produced_parts = []
        produced_text = "".join(produced_parts).strip()
        if not produced_text or _is_weak_summary(produced_text):
            yield {"clear_delta": True}
            async for event in _soft_stream("delta", _fallback_text(action_notes)):
                yield event
        yield {"done": True, "refresh": get_mutations()}
    finally:
        reset_tool_context(db_token, user_token, mutations_token)
