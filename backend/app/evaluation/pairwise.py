"""Pairwise (A/B) evaluation (Volume 34).

Compares two candidates — models, prompts, agents, RAG configs, workflows —
over the same examples and reports win rate, tie rate and confidence.
""" 
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from ..common.storage import JsonFileStorage
from .metrics import win_rate
from .models import PairwiseResult

logger = logging.getLogger(__name__)


class PairwiseEvaluator:
    """Runs candidate A vs candidate B on a shared set of examples."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/evaluation/pairwise.json")

    def compare(self, a_label: str, b_label: str, examples: list[dict],
                evaluate: Optional[Callable[[str, dict], float]] = None,
                prefer: Optional[Callable[[float, float], str]] = None,
                dataset_id: str = "") -> dict:
        """Evaluate both candidates per example; winner = higher score.

        evaluate(candidate_label, example) -> 0..1 quality score.
        prefer(score_a, score_b) -> 'a' | 'b' | 'tie' (default by scores).
        """
        if not examples:
            raise ValueError("no examples to compare")
        if evaluate is None:
            from .providers import get_model
            model = get_model("")
            evaluate = lambda label, example: (  # noqa: E731
                model.score(example.get("expected_output", ""),
                            example.get("input", "")))
        a_wins = b_wins = ties = 0
        preferences = []
        for index, example in enumerate(examples):
            score_a = float(evaluate(a_label, example))
            score_b = float(evaluate(b_label, example))
            if prefer is not None:
                verdict = prefer(score_a, score_b)
            else:
                verdict = "a" if score_a > score_b else ("b" if score_b > score_a else "tie")
            if verdict == "a":
                a_wins += 1
            elif verdict == "b":
                b_wins += 1
            else:
                ties += 1
            preferences.append({"example": index, "score_a": score_a,
                                "score_b": score_b, "winner": verdict})
        stats = win_rate(a_wins, b_wins, ties)
        result = PairwiseResult(
            id=uuid.uuid4().hex[:12],
            a_label=a_label, b_label=b_label,
            a_win=a_wins, b_win=b_wins, ties=ties,
            preferences=preferences,
            win_rate_a=stats["win_rate_a"], win_rate_b=stats["win_rate_b"],
            tie_rate=stats["tie_rate"], confidence=stats["confidence"],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        record = result.to_dict()
        if dataset_id:
            record["dataset_id"] = dataset_id
        self.storage.set(result.id, record)
        return record

    def list_pairwise(self, limit: int = 50) -> list[dict]:
        records = list(self.storage.get_all().values())
        records = [r for r in records if isinstance(r, dict)]
        return sorted(records, key=lambda r: r.get("created_at", ""), reverse=True)[:limit]
