"""In-process fan-out. One Uvicorn worker is the supported deployment for SQLite."""

from __future__ import annotations

import asyncio
from collections import deque


class EventHub:
    def __init__(self) -> None:
        self.subscribers: list[asyncio.Queue] = []
        self.recent: deque[dict] = deque(maxlen=200)
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self, event: dict) -> None:
        self.recent.append(event)
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        for queue in list(self.subscribers):
            loop.call_soon_threadsafe(self._put, queue, event)

    @staticmethod
    def _put(queue: asyncio.Queue, event: dict) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self.subscribers:
            self.subscribers.remove(queue)


hub = EventHub()
