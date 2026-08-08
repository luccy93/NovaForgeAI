from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class PluginContext:
    config: Dict[str, Any] = field(default_factory=dict)
    _registered_agents: Dict[str, Any] = field(default_factory=dict)
    _registered_tools: Dict[str, Any] = field(default_factory=dict)
    _plugins: Dict[str, Any] = field(default_factory=dict)

    def register_agent(self, name: str, agent: Any) -> None:
        self._registered_agents[name] = agent

    def register_tool(self, name: str, tool: Any) -> None:
        self._registered_tools[name] = tool

    def get_agent(self, name: str) -> Optional[Any]:
        return self._registered_agents.get(name)

    def get_tool(self, name: str) -> Optional[Any]:
        return self._registered_tools.get(name)

    def list_agents(self) -> List[str]:
        return list(self._registered_agents.keys())

    def list_tools(self) -> List[str]:
        return list(self._registered_tools.keys())

    async def publish_event(self, event_name: str, data: Any) -> None:
        pass

    async def shutdown(self) -> None:
        pass
