import asyncio
from typing import Optional
from agents.base import BaseAgent


class AgentOrchestrator:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        self._agents[agent.name] = agent

    def get(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    async def run_pipeline(self, input: dict, agents: list[str]) -> dict:
        results = {}
        current_input = {**input}

        for agent_name in agents:
            agent = self.get(agent_name)
            if agent is None:
                results[agent_name] = {"error": f"Agent '{agent_name}' not found"}
                continue
            result = await agent.run(current_input)
            results[agent_name] = result
            current_input["previous_result"] = result

        return {"results": results, "final_input": current_input}

    async def run_parallel(self, input: dict, agents: list[str]) -> dict:
        tasks = {}
        for agent_name in agents:
            agent = self.get(agent_name)
            if agent is None:
                tasks[agent_name] = None
                continue
            tasks[agent_name] = agent.run(input)

        results = {}
        for agent_name, task in tasks.items():
            if task is None:
                results[agent_name] = {"error": f"Agent '{agent_name}' not found"}
            else:
                results[agent_name] = await task

        return {"results": results}

    def get_agent_descriptions(self) -> list[dict]:
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "model": agent.model,
            }
            for agent in self._agents.values()
        ]
