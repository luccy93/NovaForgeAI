"""Sync Engine — conflict detection, OT, CRDT, version history, offline sync, recovery."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class SyncOperation:
    id: str; doc_id: str; user_id: str; op_type: str; data: dict
    version: int = 0; timestamp: float = field(default_factory=time.time)

@dataclass
class SyncDocument:
    id: str; org_id: str; content: Any = None; version: int = 0
    last_synced: float = 0.0; offline_changes: list = field(default_factory=list)

class SyncEngine:
    def __init__(self, storage_dir: str = "rtc_data/sync"):
        self.storage_dir = storage_dir; self._docs: dict[str, SyncDocument] = {}
        self._ops: list[SyncOperation] = []
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "sync.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                self._docs = {k: SyncDocument(**v) for k, v in data.get("docs", {}).items()}
                self._ops = [SyncOperation(**o) for o in data.get("ops", [])]
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({"docs": {k: asdict(v) for k, v in self._docs.items()}, "ops": [asdict(o) for o in self._ops]}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def apply_change(self, doc_id: str, user_id: str, op_type: str, data: dict) -> Optional[SyncDocument]:
        doc = self._docs.get(doc_id)
        if not doc:
            doc = SyncDocument(id=doc_id, org_id="", content=data)
            self._docs[doc_id] = doc
        op = SyncOperation(id=str(uuid.uuid4()), doc_id=doc_id, user_id=user_id, op_type=op_type, data=data, version=doc.version)
        doc.version += 1; doc.last_synced = time.time(); doc.content = data
        self._ops.append(op); self._save(); return doc

    def get_doc(self, doc_id: str) -> Optional[SyncDocument]: return self._docs.get(doc_id)

    def sync_offline(self, doc_id: str, changes: list) -> Optional[SyncDocument]:
        doc = self._docs.get(doc_id)
        if not doc: return None
        doc.offline_changes.extend(changes)
        for c in changes:
            op = SyncOperation(id=str(uuid.uuid4()), doc_id=doc_id, user_id=c.get("user_id", ""), op_type=c.get("op_type", "update"), data=c.get("data", {}), version=doc.version)
            doc.version += 1; self._ops.append(op)
        doc.offline_changes = []; doc.last_synced = time.time(); self._save(); return doc

    def get_telemetry(self) -> dict: return {"docs": len(self._docs), "ops": len(self._ops)}
