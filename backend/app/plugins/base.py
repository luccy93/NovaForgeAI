from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING


class PluginType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    INTEGRATION = "integration"
    ANALYZER = "analyzer"
    EXPORTER = "exporter"
    UI = "ui"
    HOOK = "hook"


class PluginStatus(str, Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"


@dataclass
class PluginMetadata:
    name: str
    version: str
    description: str
    author: str
    plugin_type: PluginType
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    entry_point: Optional[str] = None
    homepage: Optional[str] = None
    repository: Optional[str] = None
    license: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    min_novaforge_version: str = "0.1.0"
    max_novaforge_version: Optional[str] = None


class BasePlugin(abc.ABC):
    metadata: PluginMetadata
    _status: PluginStatus = PluginStatus.UNLOADED
    _context: Optional["PluginContext"] = None

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._event_handlers: Dict[str, List[Callable]] = {}

    @property
    def status(self) -> PluginStatus:
        return self._status

    @property
    def context(self):
        return self._context

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version

    @abc.abstractmethod
    async def initialize(self, context: "PluginContext") -> None:
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        ...

    async def on_load(self) -> None:
        self._status = PluginStatus.LOADING

    async def on_ready(self) -> None:
        self._status = PluginStatus.READY

    async def on_error(self, error: Exception) -> None:
        self._status = PluginStatus.ERROR

    def on_event(self, event_name: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            if event_name not in self._event_handlers:
                self._event_handlers[event_name] = []
            self._event_handlers[event_name].append(func)
            return func
        return decorator

    async def emit_event(self, event_name: str, data: Any) -> None:
        if self._context:
            await self._context.publish_event(event_name, data)
