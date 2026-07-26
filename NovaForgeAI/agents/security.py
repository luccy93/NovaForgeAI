import json
from agents.base import BaseAgent


class SecurityAgent(BaseAgent):
    name: str = "security"
    description: str = "Scans code for OWASP Top 10 vulnerabilities, secrets, and dependency risks"
    model: str = "gpt-4"

    async def run(self, input: dict) -> dict:
        code = input.get("code", "")
        language = input.get("language", "python")
        dependencies = input.get("dependencies", "")
        context = input.get("context", "")

        prompt = f"""You are a security expert. Scan the following {language} code for security vulnerabilities.

Context: {context}

Code:
```{language}
{code}
```

Dependencies: {dependencies}

Check for: OWASP Top 10 vulnerabilities, hardcoded secrets/credentials, dependency risks, insecure configurations, injection flaws, broken authentication, sensitive data exposure, XXE, broken access control, security misconfigurations, XSS, insecure deserialization, known vulnerable components, insufficient logging.

Return a JSON object with:
- "vulnerabilities": a list of objects, each with "type" (str), "severity" ("critical", "high", "medium", "low"), "location" (str), "description" (str), "cwe" (str or null)
- "risk_level": "critical", "high", "medium", "low", or "none"
- "recommendations": a list of recommendation strings

Example:
{{
  "vulnerabilities": [
    {{"type": "SQL Injection", "severity": "critical", "location": "db.py:15", "description": "Raw SQL query with string interpolation", "cwe": "CWE-89"}}
  ],
  "risk_level": "high",
  "recommendations": ["Use parameterized queries instead of string formatting"]
}}"""

        response = await self._llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"vulnerabilities": [], "risk_level": "unknown", "recommendations": []}

        return {
            "vulnerabilities": result.get("vulnerabilities", []),
            "risk_level": result.get("risk_level", "unknown"),
            "recommendations": result.get("recommendations", []),
        }
