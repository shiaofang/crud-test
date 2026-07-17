"""LangChain create_agent 封装：多轮工具循环 + SSE 事件映射。

流程：
1. 用 create_agent 跑「模型 ↔ 工具」循环（框架负责）
2. astream 把 token / 工具进度映射成前端 SSE dict
3. 结束时 yield done（写库成功则附带 refresh）

事件字段：status / delta / done / refresh
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from langchain.agents import create_agent
from langchain.agents.middleware import InputAgentState
from langchain.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .schemas import ChatMessage
from .tools import build_tools, reset_tool_context, set_tool_context

CancelCheck = Callable[[], Awaitable[bool]]

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

# 写库工具 → 前端需刷新的资源名（与 useDataRefresh 的 DataResource 对齐）
MUTATING_TOOLS: dict[str, str] = {
    "create_product": "products",
    "update_product": "products",
    "delete_product": "products",
    "create_user": "users",
    "update_user": "users",
    "delete_user": "users",
}

_llm: ChatOllama | None = None
_tools = build_tools()


def _system_prompt(_current_user: models.User | None = None) -> str:
    # 学习阶段：工具不做登录校验；current_user 暂未参与权限
    return (
        "你是「智能商城管理系统」的智能助手，只服务本系统相关事务。\n"
        "\n"
        "【回答范围】仅可处理以下内容：\n"
        "- 本系统内的商品、用户数据的查询与管理\n"
        "- 本系统的登录 / 注册 / 功能说明\n"
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
        "4. 工具调用全部结束后，必须再给用户一句简短中文总结（如数量、是否成功、关键名称/ID），"
        "禁止只调工具不说话；不要复述原始 JSON。\n"
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
        "若上文已列出商品/用户及其 ID，后续改删时直接使用这些 ID，不要再向用户索要。"
    )


def get_llm() -> ChatOllama:
    """懒加载并缓存 ChatOllama 实例。"""
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


def _brief_result(content: Any, limit: int = 160) -> str:
    text = _content_to_str(content).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _agent_input(history: list[ChatMessage], message: str) -> InputAgentState:
    messages: list[AnyMessage | dict[str, Any]] = []
    for item in history:
        if item.role == "user":
            messages.append(HumanMessage(content=item.content))
        else:
            messages.append(AIMessage(content=item.content))
    messages.append(HumanMessage(content=message))
    return cast(InputAgentState, {"messages": messages})


def _tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name)


def _mark_refresh_if_mutated(name: str, content: Any, refresh: set[str]) -> None:
    """写库工具返回 ok 时，把对应资源记入本轮 refresh 集合。"""
    resource = MUTATING_TOOLS.get(name)
    if not resource:
        return
    try:
        data = json.loads(_content_to_str(content))
    except json.JSONDecodeError:
        return
    if isinstance(data, dict) and data.get("ok"):
        refresh.add(resource)


async def chat_stream(
    message: str,
    history: list[ChatMessage],
    db: Session,
    current_user: models.User | None,
    is_cancelled: CancelCheck | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """create_agent 流式对话，产出 SSE 用的事件 dict。"""
    agent = create_agent(
        model=get_llm(),
        tools=_tools,
        system_prompt=_system_prompt(current_user),
    )
    tokens = set_tool_context(db)

    async def client_disconnected() -> bool:
        if is_cancelled is None:
            return False
        return await is_cancelled()

    # 本轮若在吐 tool_call，正文不进回复气泡；工具结束后再收最终总结
    tool_turn = False
    replied = False
    refresh: set[str] = set()

    try:
        yield {"status": "正在思考…"}

        async for chunk in agent.astream(
            _agent_input(history, message),
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            if await client_disconnected():
                yield {"done": True, "refresh": sorted(refresh)}
                return

            kind = chunk.get("type")
            data = chunk.get("data")

            if kind == "messages":
                token, _meta = data
                if not isinstance(token, AIMessageChunk):
                    continue
                if token.tool_call_chunks:
                    # 进入工具轮：清掉可能提前流出的正文，留给结束后的总结
                    if not tool_turn and replied:
                        replied = False
                        yield {"clear_delta": True}
                    tool_turn = True
                    continue
                text = getattr(token, "text", None) or _content_to_str(token.content)
                if text and not tool_turn:
                    replied = True
                    yield {"delta": text}
                continue

            if kind != "updates" or not isinstance(data, dict):
                continue

            for _source, update in data.items():
                if not isinstance(update, dict):
                    continue
                for msg in update.get("messages") or []:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        if replied:
                            replied = False
                            yield {"clear_delta": True}
                        tool_turn = False
                        for call in msg.tool_calls:
                            name = call.get("name", "")
                            yield {"status": f"调用工具：{_tool_label(name)}"}
                    elif isinstance(msg, ToolMessage):
                        tool_turn = False
                        name = getattr(msg, "name", None) or "tool"
                        _mark_refresh_if_mutated(name, msg.content, refresh)
                        yield {
                            "status": (
                                f"工具结果（{_tool_label(name)}）："
                                f"{_brief_result(msg.content)}"
                            )
                        }
                    elif isinstance(msg, AIMessage) and not msg.tool_calls:
                        # 部分模型工具后只在 updates 给完整终稿，messages 无 token
                        text = _content_to_str(msg.content).strip()
                        if text and not replied:
                            replied = True
                            yield {"delta": text}

        yield {"done": True, "refresh": sorted(refresh)}
    finally:
        reset_tool_context(tokens)
