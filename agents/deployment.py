import json
from agents.base import BaseAgent


class DeploymentAgent(BaseAgent):
    name: str = "deployment"
    description: str = "Manages CI/CD, Docker, and infrastructure configuration"
    model: str = "gpt-4"

    async def run(self, input: dict) -> dict:
        project_type = input.get("project_type", "python")
        framework = input.get("framework", "fastapi")
        platform = input.get("platform", "docker")
        source = input.get("source", "")
        context = input.get("context", "")

        prompt = f"""You are a DevOps engineer. Generate deployment configuration for a {project_type} project using {framework} targeting {platform}.

Context: {context}

{"Source configuration:" if source else ""}
{source}

Return a JSON object with:
- "manifest": a dict describing the deployment manifest (Dockerfile, docker-compose, k8s manifest, CI/CD config, etc.)
- "commands": a list of shell command strings needed to deploy
- "warnings": a list of warning strings about potential issues

Example:
{{
  "manifest": {{
    "dockerfile": "FROM python:3.12-slim\\nWORKDIR /app\\nCOPY . .\\nRUN pip install -r requirements.txt\\nCMD [\\"uvicorn\\", \\"main:app\\", \\"--host\\", \\"0.0.0.0\\"]",
    "docker_compose": {{"version": "3.9", "services": {{"app": {{"build": ".", "ports": ["8000:8000"]}}}}}}
  }},
  "commands": ["docker build -t app .", "docker compose up -d"],
  "warnings": ["No health check configured"]
}}"""

        response = await self._llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"manifest": {}, "commands": [], "warnings": []}

        return {
            "manifest": result.get("manifest", {}),
            "commands": result.get("commands", []),
            "warnings": result.get("warnings", []),
        }
