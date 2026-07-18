"""Kafka 商品动态总线：Producer 发事件，Consumer 落库并扇出到 ActivityHub。

必须连上 Kafka 才能发/收动态，不做本机 hub 降级。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from . import crud
from .activity_hub import activity_hub
from .config import settings
from .database import SessionLocal

logger = logging.getLogger(__name__)

ActivityAction = Literal["created", "updated", "deleted"]
ActivitySource = Literal["admin", "ai"]

_loop: asyncio.AbstractEventLoop | None = None
_producer: AIOKafkaProducer | None = None
_consumer_task: asyncio.Task[None] | None = None
_started = False


def _who(source: ActivitySource, actor: str | None) -> str:
    if source == "ai":
        return "AI 助手"
    if actor:
        return f"管理员 {actor}"
    return "管理员"


def build_activity_message(
    *,
    action: ActivityAction,
    product_name: str,
    source: ActivitySource,
    actor: str | None = None,
    changes: dict[str, Any] | None = None,
) -> str:
    """生成首页展示用的中文文案。"""
    who = _who(source, actor)
    name = product_name or "未知商品"

    if action == "created":
        return f"{who}刚刚创建了商品「{name}」"
    if action == "deleted":
        return f"{who}删除了商品「{name}」"

    if changes:
        parts: list[str] = []
        if "stock" in changes:
            old, new = changes["stock"]
            parts.append(f"库存 {old} → {new}")
        if "price" in changes:
            old, new = changes["price"]
            parts.append(f"价格 {old} → {new}")
        if "name" in changes:
            old, new = changes["name"]
            parts.append(f"名称「{old}」→「{new}」")
        if "description" in changes:
            parts.append("描述")
        if parts:
            return f"{who}更新了商品「{name}」的{'、'.join(parts)}"
    return f"{who}更新了商品「{name}」"


def build_activity_event(
    *,
    action: ActivityAction,
    product_id: int | None,
    product_name: str,
    source: ActivitySource,
    actor: str | None = None,
    changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": f"product.{action}",
        "action": action,
        "source": source,
        "message": build_activity_message(
            action=action,
            product_name=product_name,
            source=source,
            actor=actor,
            changes=changes,
        ),
        "product_id": product_id,
        "product_name": product_name,
        "actor": actor,
        "changes": changes,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def _send(event: dict[str, Any]) -> None:
    if _producer is None:
        raise RuntimeError("Kafka producer 未就绪，无法发布商品动态")
    payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
    await _producer.send_and_wait(settings.kafka_activity_topic, payload)


def publish_activity(event: dict[str, Any]) -> None:
    """从同步路由/工具中发事件到 Kafka（线程安全）。失败只打日志，不影响主业务写库。"""
    try:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        # 已在主事件循环中：不能 result() 等待，否则会死锁
        if running is not None and running is _loop:
            running.create_task(_send(event))
            return

        if _loop is not None and _loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_send(event), _loop)
            future.result(timeout=3)
            return

        raise RuntimeError("事件循环未就绪，无法发布商品动态到 Kafka")
    except Exception:
        logger.exception("发布商品动态到 Kafka 失败（已忽略，不影响写库）")


def emit_product_activity(
    *,
    action: ActivityAction,
    product_id: int | None,
    product_name: str,
    source: ActivitySource,
    actor: str | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    """业务侧统一入口：拼事件并发布到 Kafka。"""
    event = build_activity_event(
        action=action,
        product_id=product_id,
        product_name=product_name,
        source=source,
        actor=actor,
        changes=changes,
    )
    publish_activity(event)


def _persist_and_fanout(event: dict[str, Any]) -> dict[str, Any]:
    """写入 MySQL 后返回带 id 的事件，供 Hub 扇出。"""
    db = SessionLocal()
    try:
        row = crud.create_activity(db, event)
        return crud.activity_to_event(row)
    finally:
        db.close()


def _warm_hub_from_db(limit: int = 50) -> None:
    """启动时从 MySQL 回填最近动态到内存 Hub。"""
    db = SessionLocal()
    try:
        rows = crud.list_recent_activities(db, limit=limit)
        # DB 为最新在前，Hub 回放需要从旧到新
        events = [crud.activity_to_event(row) for row in reversed(rows)]
        activity_hub.warm(events)
        logger.info("已从 MySQL 回填 %s 条动态到 ActivityHub", len(events))
    finally:
        db.close()


async def _consume_forever() -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_activity_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="activity-hub",
        enable_auto_commit=True,
        auto_offset_reset="latest",
    )
    await consumer.start()
    logger.info(
        "Kafka consumer 已启动 topic=%s servers=%s",
        settings.kafka_activity_topic,
        settings.kafka_bootstrap_servers,
    )
    try:
        async for msg in consumer:
            try:
                if msg.value is None:
                    continue
                event = json.loads(msg.value.decode("utf-8"))
                if not isinstance(event, dict):
                    continue
                persisted = await asyncio.to_thread(_persist_and_fanout, event)
                activity_hub.publish(persisted)
            except Exception:
                logger.exception("处理 Kafka 动态消息失败")
    finally:
        await consumer.stop()


async def start_kafka() -> None:
    """应用启动时调用：必须连上 Kafka，失败则阻止启动。"""
    global _loop, _producer, _consumer_task, _started
    if _started:
        return
    _loop = asyncio.get_running_loop()

    await asyncio.to_thread(_warm_hub_from_db)

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
    )
    await producer.start()
    _producer = producer
    _consumer_task = asyncio.create_task(
        _consume_forever(),
        name="kafka-activity-consumer",
    )
    _started = True
    logger.info(
        "Kafka producer 已启动 servers=%s topic=%s",
        settings.kafka_bootstrap_servers,
        settings.kafka_activity_topic,
    )


async def stop_kafka() -> None:
    """应用关闭时调用。"""
    global _producer, _consumer_task, _started, _loop
    if _consumer_task is not None:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
        _consumer_task = None
    if _producer is not None:
        await _producer.stop()
        _producer = None
    _loop = None
    _started = False
