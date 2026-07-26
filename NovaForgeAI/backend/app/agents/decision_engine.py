"""Decision engine — analyzes agent output for evidence, confidence, risk, and recommendations."""

import re
from typing import Any, Optional

from app.agents.schemas import AgentDecision, RiskLevel, ToolResult


class DecisionEngine:
    """Analyzes agent output to produce structured decisions."""

    async def analyze(
        self,
        task_input: str,
        agent_output: str,
        tool_calls: list[ToolResult],
        context: Optional[dict] = None,
    ) -> AgentDecision:
        evidence = self._extract_evidence(agent_output)
        confidence = self._calculate_confidence(agent_output, tool_calls)
        files_affected = self._extract_files(agent_output)
        risk = self._assess_risk(agent_output, tool_calls)
        impact = self._estimate_impact(agent_output, risk)
        validation = self._suggest_validation(agent_output, risk)
        rollback = self._suggest_rollback(risk, files_affected)
        reasoning = self._extract_reasoning(agent_output)

        return AgentDecision(
            evidence=evidence,
            confidence=confidence,
            files_affected=files_affected,
            risk_level=risk,
            estimated_impact=impact,
            suggested_validation=validation,
            rollback_strategy=rollback,
            reasoning=reasoning,
        )

    def _extract_evidence(self, output: str) -> list[str]:
        evidence = []
        patterns = [
            r"(?:Evidence|Source|Reference|Citation)[:\s]+(.+)$",
            r"(?:Based on|According to|Found in)[:\s]+(.+)$",
            r"`([^`]+)`",
        ]
        for p in patterns:
            matches = re.findall(p, output, re.MULTILINE | re.IGNORECASE)
            evidence.extend(m.strip() for m in matches if len(m.strip()) > 10)
        return evidence[:10]

    def _calculate_confidence(self, output: str, tool_calls: list[ToolResult]) -> float:
        confidence = 0.7
        if re.search(r"(?:I am|I'm)\s+(?:highly|very|extremely)\s+confident", output, re.IGNORECASE):
            confidence += 0.15
        if re.search(r"(?:I am|I'm)\s+(?:somewhat|moderately)\s+confident", output, re.IGNORECASE):
            confidence += 0.05
        if re.search(r"(?:uncertain|not sure|maybe|possibly|might)", output, re.IGNORECASE):
            confidence -= 0.2
        success_rate = sum(1 for t in tool_calls if t.success) / max(len(tool_calls), 1)
        confidence = (confidence + success_rate) / 2
        return max(0.0, min(1.0, confidence))

    def _extract_files(self, output: str) -> list[str]:
        files = re.findall(r'(?:file|path)[:\s]+`?([^`\n,]+(?:\.\w+)+)`?', output, re.IGNORECASE)
        files.extend(re.findall(r'`([^`]+\.\w+)`', output))
        return list(set(files))[:10]

    def _assess_risk(self, output: str, tool_calls: list[ToolResult]) -> RiskLevel:
        high_risk_patterns = ["delete", "drop", "truncate", "rm -rf", "format", "overwrite"]
        mid_risk_patterns = ["update", "modify", "change", "alter", "migrate"]

        output_lower = output.lower()
        for p in high_risk_patterns:
            if p in output_lower:
                return RiskLevel.high
        for p in mid_risk_patterns:
            if p in output_lower:
                return RiskLevel.medium

        if not tool_calls:
            return RiskLevel.none
        if any(not t.success for t in tool_calls):
            return RiskLevel.medium
        return RiskLevel.low

    def _estimate_impact(self, output: str, risk: RiskLevel) -> str:
        if risk == RiskLevel.high:
            return "This change affects core functionality. Review thoroughly before applying."
        if risk == RiskLevel.medium:
            return "Moderate impact. Test in staging environment first."
        if risk == RiskLevel.low:
            return "Low impact change. Safe to apply with standard review."
        return "Informational only. No code changes proposed."

    def _suggest_validation(self, output: str, risk: RiskLevel) -> str:
        if risk in (RiskLevel.high, RiskLevel.critical):
            return "Requires human review, full test suite run, and staging deployment verification."
        if risk == RiskLevel.medium:
            return "Run related unit tests and perform code review."
        return "Quick validation via existing test suite."

    def _suggest_rollback(self, risk: RiskLevel, files: list[str]) -> str:
        if not files:
            return "No files to rollback."
        if risk in (RiskLevel.high, RiskLevel.critical):
            return f"Revert via `git checkout HEAD -- {' '.join(files)}` and verify."
        return f"Use `git checkout HEAD -- {' '.join(files[:3] + (['...'] if len(files) > 3 else []))}` if needed."

    def _extract_reasoning(self, output: str) -> str:
        reasoning_match = re.search(
            r"(?:Reasoning|Rationale|Analysis|Explanation)[:\s]*\n?(.+?)(?:\n\n|\Z)",
            output, re.DOTALL | re.IGNORECASE,
        )
        if reasoning_match:
            return reasoning_match.group(1).strip()[:1000]
        return output[:500]
