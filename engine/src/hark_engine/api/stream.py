"""Server-Sent Events: fan-out of the internal event bus to local clients."""

from __future__ import annotations

import asyncio
import json
import threading

from ..events import EventBus
from ..models import Event


def format_sse(event: Event) -> str:
    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f"id: {event.id}\nevent: {event.type.value}\ndata: {payload}\n\n"


class EventBroker:
    def __init__(self, bus: EventBus) -> None:
        self._subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[Event]]] = []
        self._lock = threading.Lock()
        bus.subscribe(self._on_event)

    def _on_event(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subs)
        for loop, queue in subs:
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        with self._lock:
            self._subs = [s for s in self._subs if s[1] is not queue]
