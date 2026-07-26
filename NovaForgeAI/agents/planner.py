import json
from typing import Any
from agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    name: str = "planner"
    description: str = "Analyzes requirements and generates a multi-step implementation plan"
    model: str = "gpt-4"

    async def run(self, input: dict) -> dict:
        requirement = input.get("requirement", input.get("input", ""))
        context = input.get("context", "")

        prompt = f"""You are a software architect. Analyze the following requirement and generate a detailed multi-step implementation plan.

Requirement: {requirement}

Context: {context}

Return a JSON object with:
- "plan": a list of steps, each with "step" (int), "action" (str), "files" (list of str), "dependencies" (list of step ints that this step depends on)
- "summary": a concise summary of the overall plan

Example:
{{
  "plan": [
    {{"step": 1, "action": "Create the main entry point", "files": ["main.py"], "dependencies": []}},
    {{"step": 2, "action": "Implement business logic", "files": ["services/core.py"], "dependencies": [1]}}
  ],
  "summary": "Two-step plan to build the application."
}}"""

        response = await self._llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"plan": [], "summary": content}

        return {
            "plan": result.get("plan", []),
            "summary": result.get("summary", content),
        }
