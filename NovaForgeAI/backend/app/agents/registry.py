"""Agent registry — discover, register, and resolve agents."""

from typing import Any, Optional

from app.agents.base import BaseAgent
from app.agents.schemas import AgentConfig, AgentRole


class AgentRegistry:
    """Central registry for all agent types."""

    def __init__(self):
        self._agents: dict[str, type[BaseAgent]] = {}
        self._instances: dict[str, BaseAgent] = {}
        self._configs: dict[str, AgentConfig] = {}

    def register(self, agent_class: type[BaseAgent], config: AgentConfig):
        self._agents[config.name] = agent_class
        self._configs[config.name] = config

    def get_config(self, name: str) -> Optional[AgentConfig]:
        return self._configs.get(name)

    def get_agent(self, name: str, **kwargs) -> Optional[BaseAgent]:
        cls = self._agents.get(name)
        if not cls:
            return None
        config = self._configs.get(name)
        if not config:
            return None
        return cls(config=config, **kwargs)

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "role": config.role.value,
                "version": config.version,
                "description": config.description,
                "goals": config.goals,
            }
            for name, config in self._configs.items()
        ]

    def get_agent_names(self) -> list[str]:
        return list(self._configs.keys())

    def discover(self):
        """Auto-discover and register all agent types."""
        from app.agents.agents import ALL_AGENTS
        for agent_class, config in ALL_AGENTS:
            self.register(agent_class, config)
