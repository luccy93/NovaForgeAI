"""Human evaluation platform (Volume 34).

Single/multi-reviewer scoring, blind and pairwise review, adjudication and
inter-rater reliability (Cohen's Kappa for 2 raters, Fleiss' Kappa for 3+,
agreement rate always). Kappa-family metrics are only reported when the
data type supports them (categorical labels).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..common.storage import JsonFileStorage
from .metrics import inter_rater_report
from .models import HumanReview

logger = logging.getLogger(__name__)

DEFAULT_CRITERIA = [
    "correctness", "quality", "usefulness", "security",
    "groundedness", "completeness", "preference",
]


class HumanReviewManager:
    """Review workflow: create reviews, aggregate, adjudicate, reliability."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/evaluation/reviews.json")

    def add(self, run_id: str, example_id: str, reviewer: str = "",
            scores: Optional[dict] = None, preference: str = "",
            comment: str = "", blind: bool = True) -> dict:
        review = HumanReview(
            id=uuid.uuid4().hex[:12],
            run_id=run_id,
            example_id=example_id,
            reviewer=reviewer,
            scores=scores or {},
            preference=preference,
            comment=comment,
            blind=blind,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.storage.set(review.id, review.to_dict())
        return review.to_dict()

    def list_reviews(self, run_id: str = "", example_id: str = "") -> list[dict]:
        reviews = []
        for record in self.storage.get_all().values():
            if not isinstance(record, dict):
                continue
            if run_id and record.get("run_id") != run_id:
                continue
            if example_id and record.get("example_id") != example_id:
                continue
            reviews.append(record)
        return sorted(reviews, key=lambda r: r.get("created_at", ""))

    def aggregate(self, run_id: str) -> dict:
        """Aggregate all reviews for a run into per-criterion stats."""
        reviews = self.list_reviews(run_id=run_id)
        if not reviews:
            return {"run_id": run_id, "reviews": 0}
        criteria: dict[str, list[float]] = {}
        for review in reviews:
            for criterion, value in review.get("scores", {}).items():
                criteria.setdefault(criterion, []).append(float(value))
        summary = {}
        for criterion, values in criteria.items():
            summary[criterion] = {
                "mean": round(sum(values) / len(values), 4),
                "count": len(values),
            }
        overall_values = [v for vals in criteria.values() for v in vals]
        overall = round(sum(overall_values) / len(overall_values), 4) if overall_values else 0.0
        return {"run_id": run_id, "reviews": len(reviews),
                "criteria": summary, "overall": overall}

    def pairwise_verdict(self, run_id: str) -> dict:
        """Aggregate pairwise preference votes (A/B review)."""
        reviews = self.list_reviews(run_id=run_id)
        votes = {"a": 0, "b": 0, "tie": 0}
        for review in reviews:
            pref = review.get("preference", "")
            if pref in votes:
                votes[pref] += 1
        total = sum(votes.values())
        return {
            "run_id": run_id, "votes": votes,
            "prefer_a": round(votes["a"] / total, 4) if total else 0.0,
            "prefer_b": round(votes["b"] / total, 4) if total else 0.0,
        }

    def reliability(self, run_id: str) -> dict:
        """Inter-rater reliability over categorical review buckets."""
        reviews = self.list_reviews(run_id=run_id)
        if not reviews:
            return {"run_id": run_id, "reviews": 0,
                    "notes": ["no reviews to compute reliability"]}
        per_reviewer: dict[str, dict[str, float]] = {}
        for review in reviews:
            per_reviewer.setdefault(review.get("reviewer", "?"), {})[review["example_id"]] = \
                review.get("scores", {}).get("overall",
                sum(review.get("scores", {}).values()) / max(1, len(review.get("scores", {}))))
        reviewers = sorted(per_reviewer)
        labels = []
        for example_id in sorted({e for m in per_reviewer.values() for e in m}):
            row = [bucket(per_reviewer[r].get(example_id, 0.0)) for r in reviewers]
            labels.append(row)
        report = inter_rater_report(labels)
        report["run_id"] = run_id
        report["reviewers"] = reviewers
        report["examples"] = len(labels)
        report["reviews"] = len(reviews)
        return report


def bucket(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "mid"
    return "low"
