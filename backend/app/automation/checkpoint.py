"""Execution checkpoints (Volume 33).

Checkpoints let a failed or interrupted run resume from the last completed
step instead of restarting. Checkpoints are persisted JSON (tenant-scoped)
with execution_id + step_id + output snapshot.
"""
import logging, time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    execution_id: str
    step_id: str
    completed_at: str
    outputs: dict = field(default_factory=dict)
    sequence: int = 0


class CheckpointStore:
    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self._storage = storage or JsonFileStorage(
            "data/automation/checkpoints.json")

    def save(self, execution_id: str, step_id: str, outputs: dict,
             sequence: int = 0) -> Checkpoint:
        entry = Checkpoint(execution_id=execution_id, step_id=step_id,
                           completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                      time.gmtime()),
                           outputs=outputs, sequence=sequence)
        self._storage.set(f"{execution_id}:{step_id}", entry.__dict__)
        return entry

    def get(self, execution_id: str, step_id: str) -> Optional[Checkpoint]:
        raw = self._storage.get(f"{execution_id}:{step_id}")
        if not raw:
            return None
        return Checkpoint(**raw)

    def resume_point(self, execution_id: str,
                     ordered_step_ids: list[str]) -> Optional[Checkpoint]:
        """Latest completed checkpoint for this execution, in order."""
        for step_id in reversed(ordered_step_ids):
            cp = self.get(execution_id, step_id)
            if cp is not None:
                return cp
        return None

    def list(self, execution_id: str) -> list[Checkpoint]:
        prefix = f"{execution_id}:"
        entries = []
        for key, raw in self._storage.get_all().items():
            if key.startswith(prefix):
                entries.append(Checkpoint(**raw))
        entries.sort(key=lambda c: c.sequence)
        return entries

    def clear(self, execution_id: str) -> int:
        removed = 0
        for key in list(self._storage.get_all().keys()):
            if key.startswith(f"{execution_id}:"):
                self._storage.delete(key)
                removed += 1
        return removed

    def count(self) -> int:
        return len(self._storage.get_all())


def build_resume_plan(execution_id: str, ordered_step_ids: list[str],
                      checkpoint: Optional[Checkpoint]) -> list[str]:
    """Steps to (re)run: everything after the resume checkpoint."""
    if checkpoint is None:
        return ordered_step_ids
    try:
        idx = ordered_step_ids.index(checkpoint.step_id)
    except ValueError:
        return ordered_step_ids
    return ordered_step_ids[idx + 1:]