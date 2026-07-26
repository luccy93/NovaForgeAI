import json
from agents.base import BaseAgent


class TestingAgent(BaseAgent):
    name: str = "testing"
    description: str = "Generates unit, integration, and E2E tests from source code"
    model: str = "gpt-4"

    async def run(self, input: dict) -> dict:
        code = input.get("code", "")
        language = input.get("language", "python")
        framework = input.get("framework", "pytest")
        test_type = input.get("test_type", "unit")

        prompt = f"""You are a QA engineer. Generate {test_type} tests using {framework} for the following {language} code.

Code:
```{language}
{code}
```

Return a JSON object with:
- "tests": a list of objects, each with "name" (str), "type" ("unit", "integration", or "e2e"), "code" (str containing the full test code)
- "coverage_estimate": a float between 0.0 and 1.0 estimating statement coverage

Example:
{{
  "tests": [
    {{"name": "test_add_function", "type": "unit", "code": "def test_add_function():\\n    assert add(2, 3) == 5"}}
  ],
  "coverage_estimate": 0.85
}}"""

        response = await self._llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"tests": [], "coverage_estimate": 0.0}

        return {
            "tests": result.get("tests", []),
            "coverage_estimate": result.get("coverage_estimate", 0.0),
        }
