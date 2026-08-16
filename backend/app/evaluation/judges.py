"""LLM-as-a-judge framework and judge calibration (Volume 34).

Judges evaluate outputs against criteria (correctness, relevance, ...).
Calibration measures judge agreement, position bias, length bias, model
bias, consistency and confidence so judges are never trusted blindly.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from .metrics import cohens_kappa, agreement_rate
from .providers import EvalModel, get_model

logger = logging.getLogger(__name__)

DEFAULT_CRITERIA = [
    "correctness", "relevance", "completeness", "groundedness",
    "reasoning_quality", "code_quality", "security", "instruction_following",
    "citation_quality",
]


class LLMJudge:
    """Independent-model evaluator with criteria weights and calibration."""

    def __init__(self, judge_model: Optional[EvalModel] = None,
                 criteria: Optional[dict[str, float]] = None,
                 scorer: Optional[Callable[[str, str, str], float]] = None):
        self.model = judge_model or get_model("")
        self.criteria = criteria or {c: 1.0 for c in DEFAULT_CRITERIA}
        self.scorer = scorer  # optional external judge callback (model, prompt, output) -> score

    def judge(self, prompt: str, output: str, reference: str = "") -> dict:
        """Score an output against all criteria. Returns scores + rationale."""
        scores = {}
        for criterion in self.criteria:
            if self.scorer is not None:
                try:
                    raw = self.scorer(prompt, output, criterion)
                    score = max(0.0, min(1.0, float(raw)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("judge scorer failed: %s", exc)
                    score = 0.0
            else:
                score = self._rule_score(criterion, prompt, output, reference)
            scores[criterion] = {
                "score": round(score, 4),
                "weight": self.criteria[criterion],
                "rationale": self._rationale(criterion, score),
            }
        weighted = sum(v["score"] * v["weight"] for v in scores.values())
        total_weight = sum(self.criteria.values()) or 1.0
        overall = weighted / total_weight
        return {"judge_model": self.model.model_id(),
                "criterion_scores": scores,
                "overall": round(overall, 4),
                "confidence": self._confidence(scores)}

    def _rule_score(self, criterion: str, prompt: str, output: str,
                    reference: str) -> float:
        """Deterministic fallback scoring (offline mode, labelled)."""
        base = 0.5
        if criterion in ("groundedness", "citation_quality"):
            return base
        if reference:
            sim = self.model.score(reference, output)
            if criterion == "correctness":
                return sim
            if criterion == "relevance":
                return sim * 0.9 + 0.05
            if criterion == "completeness":
                return sim * 0.8 + 0.1
            if criterion == "reasoning_quality":
                return sim * 0.85 + 0.05
        if criterion == "instruction_following":
            return 0.8 if output.strip() else 0.0
        if criterion == "code_quality":
            return 0.7 if _looks_like_code(output) else 0.4
        if criterion == "security":
            return 0.8 if not _looks_unsafe(output) else 0.1
        return base

    @staticmethod
    def _confidence(scores: dict) -> float:
        values = [v["score"] for v in scores.values()]
        if not values:
            return 0.0
        spread = max(values) - min(values)
        return round(max(0.0, 1.0 - spread), 4)

    @staticmethod
    def _rationale(criterion: str, score: float) -> str:
        if score >= 0.8:
            return f"strong {criterion}"
        if score >= 0.5:
            return f"adequate {criterion}"
        return f"weak {criterion}"


def _looks_like_code(text: str) -> bool:
    import re
    return bool(re.search(r"def |class |function |=>|import ", text))


def _looks_unsafe(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in (
        "eval(", "exec(", "password =", "api_key =", "rm -rf", "drop table"))


# ─────────────────────────────────────────────── judge calibration ──
class JudgeCalibration:
    """Measures judge reliability: agreement, position/length/model bias."""

    def calibrate(self, judge_scores: list[dict],
                  human_scores: Optional[list[float]] = None,
                  swapped_scores: Optional[list[float]] = None,
                  short_scores: Optional[list[float]] = None,
                  long_scores: Optional[list[float]] = None) -> dict:
        """Compute calibration report from empirical observations.

        judge_scores: per-item overall judge scores.
        human_scores:  per-item human scores (same order) for agreement.
        swapped_scores: judge scores on position-swapped pairs for position bias.
        short_scores / long_scores: judge scores on short vs long answers.
        """
        report: dict = {"judge_items": len(judge_scores)}
        if human_scores and len(human_scores) == len(judge_scores):
            labels_j = [_bucket(s) for s in judge_scores]
            labels_h = [_bucket(s) for s in human_scores]
            report["human_agreement"] = round(agreement_rate(
                [[a, b] for a, b in zip(labels_j, labels_h)]), 4)
            try:
                report["cohens_kappa_judge_human"] = round(
                    cohens_kappa(labels_j, labels_h), 4)
            except ValueError:
                report["cohens_kappa_judge_human"] = None
        if swapped_scores and len(swapped_scores) == len(judge_scores):
            delta = [a - b for a, b in zip(judge_scores, swapped_scores)]
            report["position_bias"] = round(sum(delta) / len(delta), 4)
        if short_scores and long_scores:
            mean_short = sum(short_scores) / len(short_scores)
            mean_long = sum(long_scores) / len(long_scores)
            report["length_bias"] = round(mean_long - mean_short, 4)
        report["consistency"] = round(
            (max(judge_scores) - min(judge_scores)) if judge_scores else 0.0, 4)
        report["mean_confidence"] = round(
            sum(judge_scores) / len(judge_scores), 4) if judge_scores else 0.0
        return report

    def adjudicate(self, reviews: list[dict]) -> dict:
        """Adjudicate conflicting human reviews into a final decision."""
        if not reviews:
            return {"decision": "no_reviews", "reviews": 0}
        scores = [float(r.get("score", 0.0)) for r in reviews]
        return {"decision": "adjudicated", "reviews": len(reviews),
                "mean_score": round(sum(scores) / len(scores), 4),
                "agreement": round(agreement_rate(
                    [[_bucket(s)] for s in scores]), 4)}


def _bucket(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "mid"
    return "low"
