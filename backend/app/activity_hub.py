"""进程内动态扇出：Kafka Consumer 写入后，推给所有 SSE 订阅者。

最近 N 条以 MySQL 为准；本 Hub 只做在线连接广播与短缓存回放。
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any


class ActivityHub:
    """短缓存最近 N 条动态，并向订阅队列广播。"""

    def __init__(self, maxlen: int = 50) -> None:
        self._recent: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def warm(self, events: list[dict[str, Any]]) -> None:
        """用持久化历史填充短缓存（不广播）。events 应为从旧到新。"""
        self._recent.clear()
        for event in events:
            self._recent.append(event)

    def publish(self, event: dict[str, Any]) -> None:
        self._recent.append(event)
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            self._subscribers.discard(queue)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        for event in self._recent:
            queue.put_nowait(event)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)


activity_hub = ActivityHub()
