from __future__ import annotations

from typing import Any, Callable, Dict, List
from dataclasses import dataclass, field


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable) -> None:
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Callable) -> None:
        if event_name in self._handlers:
            self._handlers[event_name] = [h for h in self._handlers[event_name] if h != handler]

    async def publish(self, event_name: str, data: Any) -> None:
        handlers = self._handlers.get(event_name, [])
        for handler in handlers:
            await handler(data)

    def clear(self) -> None:
        self._handlers.clear()
