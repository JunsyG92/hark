"""In-process event bus.

Subscribers are plain callables invoked synchronously; a failing subscriber
is logged and never breaks the publisher. Later increments attach the SSE
stream and the webhook dispatcher as subscribers.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .models import Event, EventType

log = logging.getLogger(__name__)

Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: list[tuple[frozenset[EventType] | None, Subscriber]] = []
        self._lock = threading.Lock()

    def subscribe(
        self, handler: Subscriber, types: set[EventType] | None = None
    ) -> Callable[[], None]:
        entry = (frozenset(types) if types else None, handler)
        with self._lock:
            self._subs.append(entry)

        def unsubscribe() -> None:
            with self._lock:
                if entry in self._subs:
                    self._subs.remove(entry)

        return unsubscribe

    def publish(self, type_: EventType, data: dict[str, Any] | None = None) -> Event:
        event = Event(
            id=uuid.uuid4().hex,
            type=type_,
            occurred_at=datetime.now(UTC),
            data=data or {},
        )
        with self._lock:
            subs = list(self._subs)
        for types, handler in subs:
            if types is None or event.type in types:
                try:
                    handler(event)
                except Exception:
                    log.exception("event subscriber failed for %s", event.type)
        return event
