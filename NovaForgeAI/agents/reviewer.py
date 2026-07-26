import json
from agents.base import BaseAgent


class ReviewerAgent(BaseAgent):
    name: str = "reviewer"
    description: str = "Reviews code for bugs, style issues, and improvements"
    model: str = "gpt-4"

    async def run(self, input: dict) -> dict:
        code = input.get("code", "")
        language = input.get("language", "python")
        context = input.get("context", "")

        prompt = f"""You are a senior code reviewer. Review the following {language} code and find issues.

Context: {context}

Code:
```{language}
{code}
```

Return a JSON object with:
- "issues": a list of issues, each with "severity" ("critical", "high", "medium", "low", "info"), "line" (int), "message" (str), "suggestion" (str)
- "score": an integer from 0 to 100 representing code quality

Example:
{{
  "issues": [
    {{"severity": "high", "line": 42, "message": "Unhandled exception", "suggestion": "Wrap in try/except"}}
  ],
  "score": 85
}}"""

        response = await self._llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"issues": [], "score": 0}

        return {
            "issues": result.get("issues", []),
            "score": result.get("score", 0),
        }
