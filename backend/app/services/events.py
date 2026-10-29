"""In-memory live event bus: backend -> browser.

Every live update (transcript bubble, status, tool call, form state, turn
metrics, errors) is published here and sent to the UI over the WebSocket
/api/calls/{call_id}/events. Simulate mode publishes the same events, so the
UI code path is identical. Late subscribers get the history replayed first.

All publishing happens on the asyncio event loop thread (async routes and the
pipeline), so plain asyncio.Queues are safe.
"""

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone

MAX_HISTORY = 3000


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._history: dict[str, list[dict]] = defaultdict(list)

    def publish(self, call_id: str, event_type: str, data: dict | None = None) -> dict:
        event = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "t_ms": round(time.time() * 1000),
            "data": data or {},
        }
        history = self._history[call_id]
        history.append(event)
        if len(history) > MAX_HISTORY:
            del history[: len(history) - MAX_HISTORY]
        for queue in list(self._subscribers[call_id]):
            queue.put_nowait(event)
        return event

    def subscribe(self, call_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        for event in self._history[call_id]:
            queue.put_nowait(event)
        self._subscribers[call_id].add(queue)
        return queue

    def unsubscribe(self, call_id: str, queue: asyncio.Queue):
        self._subscribers[call_id].discard(queue)

    def history(self, call_id: str) -> list[dict]:
        return list(self._history[call_id])


bus = EventBus()
