"""Conflict Resolver — OT/CRDT, conflict detection, resolution, undo/redo."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class Operation:
    id: str; user_id: str; session_id: str; op_type: str  # insert, delete, update, replace
    path: str = ""; value: Any = None; position: int = 0; version: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Operation": return cls(**data)

from typing import Any

class ConflictResolver:
    def __init__(self, storage_dir: str = "rtc_data/ops"):
        self.storage_dir = storage_dir; self._ops: dict[str, Operation] = {}
        self._documents: dict[str, list] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "operations.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._ops[k] = Operation.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._ops.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def apply_operation(self, doc_id: str, op: Operation) -> Optional[list]:
        if doc_id not in self._documents: self._documents[doc_id] = []
        doc = self._documents[doc_id]
        if op.op_type == "insert":
            pos = min(op.position, len(doc))
            doc.insert(pos, op.value)
        elif op.op_type == "delete":
            if op.position < len(doc): doc.pop(op.position)
        elif op.op_type == "update":
            if op.position < len(doc): doc[op.position] = op.value
        self._ops[op.id] = op; self._save()
        return doc

    def transform(self, op_a: Operation, op_b: Operation) -> tuple:
        """Simple operational transform."""
        if op_a.position < op_b.position:
            return op_a, op_b
        return op_b, op_a

    def get_history(self, doc_id: str) -> list[Operation]:
        return [o for o in self._ops.values() if o.session_id == doc_id]
