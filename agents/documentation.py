import json
from agents.base import BaseAgent


class DocumentationAgent(BaseAgent):
    name: str = "documentation"
    description: str = "Generates and updates project documentation from code and context"
    model: str = "gpt-4"

    async def run(self, input: dict) -> dict:
        code = input.get("code", "")
        language = input.get("language", "python")
        existing_docs = input.get("existing_docs", "")
        doc_style = input.get("doc_style", "markdown")
        context = input.get("context", "")

        action = "Generate new" if not existing_docs else "Update existing"
        prompt = f"""You are a technical writer. {action} documentation in {doc_style} format for the following {language} code.

Context: {context}

{"Existing documentation:" if existing_docs else ""}
{existing_docs}

Code:
```{language}
{code}
```

Return a JSON object with:
- "docs": the full documentation content as a string
- "changes": a list of strings describing what was changed or added

Example:
{{
  "docs": "# Module\\n\\nThis module provides...",
  "changes": ["Added API reference section", "Updated usage examples"]
}}"""

        response = await self._llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"docs": content, "changes": []}

        return {
            "docs": result.get("docs", content),
            "changes": result.get("changes", []),
        }
