"""Server-Sent Events (SSE) event bus for real-time updates.

Each board has a set of subscribers (asyncio Queues). When a mutation
occurs, the event is broadcast to all subscribers of that board.
"""

import asyncio
import json
from collections import defaultdict


class EventBus:
    def __init__(self):
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, board_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[board_id].add(queue)
        return queue

    def unsubscribe(self, board_id: int, queue: asyncio.Queue):
        self._subscribers[board_id].discard(queue)
        if not self._subscribers[board_id]:
            del self._subscribers[board_id]

    def publish(self, board_id: int, event_type: str, data: dict):
        payload = json.dumps({"type": event_type, "data": data})
        dead = []
        for queue in self._subscribers.get(board_id, set()):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(queue)
        for q in dead:
            self._subscribers[board_id].discard(q)


# Global singleton
event_bus = EventBus()
