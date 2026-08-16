"""Agent evaluation (Volume 34).

Objective success criteria, trajectory storage (structured reasoning
summaries and tool traces only — never private chain-of-thought), tool use
evaluation and efficiency/cost-per-success metrics.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SUCCESS_CRITERIA = {
    "expected_file_changed": "expected file was modified",
    "expected_behavior": "expected behavior was achieved",
    "tests_pass": "tests pass after the change",
    "no_unrelated_changes": "no unrelated files changed",
    "security_maintained": "security invariants still hold",
}


class AgentEvaluator:
    """Evaluates agent runs: success, trajectory, tool use, efficiency."""

    def evaluate_success(self, expected: dict, actual: dict) -> dict:
        """Score objective success criteria against observed outcomes."""
        results = {}
        for criterion in SUCCESS_CRITERIA:
            if criterion in expected:
                results[criterion] = 1.0 if bool(actual.get(criterion, False)) else 0.0
        passed = all(v == 1.0 for v in results.values()) if results else False
        return {
            "criteria": results,
            "task_completed": passed,
            "success_rate": round(sum(results.values()) / len(results), 4) if results else 0.0,
        }

    def evaluate_trajectory(self, steps: list[dict]) -> dict:
        """Score a trajectory of structured agent steps.

        Each step: {tool, ok, error, retry, decision}. No chain-of-thought
        is stored or evaluated — only structured summaries and outcomes.
        """
        total = len(steps)
        if not total:
            return {"steps": 0, "error_rate": 0.0, "retry_rate": 0.0,
                    "decision_quality": 0.0}
        errors = sum(1 for s in steps if s.get("error"))
        retries = sum(1 for s in steps if s.get("retry"))
        good_decisions = sum(1 for s in steps if s.get("decision") is True)
        decided = sum(1 for s in steps if "decision" in s)
        return {
            "steps": total,
            "error_rate": round(errors / total, 4),
            "retry_rate": round(retries / total, 4),
            "decision_quality": round(good_decisions / decided, 4) if decided else 0.0,
        }

    def evaluate_tool_use(self, expected_sequence: list[str],
                          used_sequence: list[str]) -> dict:
        """Tool selection accuracy: correct/wrong/missing/unnecessary tools."""
        expected = list(expected_sequence)
        used = list(used_sequence)
        correct = sum(1 for tool in used if tool in expected)
        wrong = sum(1 for tool in used if tool not in expected)
        missing = [tool for tool in expected if tool not in used]
        unnecessary = [tool for tool in used if tool not in expected]
        precision = correct / len(used) if used else 0.0
        recall = correct / len(expected) if expected else 0.0
        return {
            "correct_tools": correct,
            "wrong_tools": wrong,
            "missing_tools": missing,
            "unnecessary_tools": unnecessary,
            "tool_precision": round(precision, 4),
            "tool_recall": round(recall, 4),
            "sequence_followed": expected == used,
        }

    def evaluate_efficiency(self, successful: int, total: int,
                            steps: int = 0, tokens: int = 0,
                            latency_ms: float = 0.0, tool_calls: int = 0,
                            retries: int = 0, failures: int = 0,
                            cost: float = 0.0) -> dict:
        """Efficiency + cost-per-success metrics for an agent batch."""
        return {
            "steps": steps,
            "tokens": tokens,
            "latency_ms": latency_ms,
            "tool_calls": tool_calls,
            "retries": retries,
            "failures": failures,
            "successful_tasks": successful,
            "success_rate": round(successful / total, 4) if total else 0.0,
            "cost_per_successful_task": round(cost / successful, 4) if successful else None,
            "steps_per_successful_task": round(steps / successful, 4) if successful else None,
            "tokens_per_successful_task": round(tokens / successful, 4) if successful else None,
        }
