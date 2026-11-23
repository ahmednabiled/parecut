import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from fastapi import Request

from parecut_engine.schemas import JobEvent


class EventBroker(Protocol):
    async def publish(self, job_id: str, event: JobEvent) -> None: ...

    def subscribe(self, job_id: str) -> AsyncIterator[JobEvent]: ...


class _Subscription:
    def __init__(self, broker: "InMemoryEventBroker", job_id: str) -> None:
        self._broker = broker
        self._job_id = job_id
        self._queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=512)
        broker._subscribers.setdefault(job_id, set()).add(self._queue)

    def __aiter__(self) -> "_Subscription":
        return self

    async def __anext__(self) -> JobEvent:
        return await self._queue.get()

    async def close(self) -> None:
        subscribers = self._broker._subscribers.get(self._job_id)
        if subscribers is not None:
            subscribers.discard(self._queue)
            if not subscribers:
                self._broker._subscribers.pop(self._job_id, None)


class InMemoryEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[JobEvent]]] = {}

    async def publish(self, job_id: str, event: JobEvent) -> None:
        for queue in list(self._subscribers.get(job_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self, job_id: str) -> AsyncIterator[JobEvent]:
        return _Subscription(self, job_id)


def get_broker(request: Request) -> EventBroker:
    return request.app.state.broker
