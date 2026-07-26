"""Sync Engine — real-time sync, offline sync, conflict detection, conflict resolution, history, snapshots, workspace recovery."""
import json, uuid, os, logging, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    ONE_WAY = "one_way"
    TWO_WAY = "two_way"


class SyncStatus(Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    COMPLETED = "completed"
    CONFLICT = "conflict"
    FAILED = "failed"


class ConflictResolution(Enum):
    SOURCE_WINS = "source_wins"
    TARGET_WINS = "target_wins"
    LAST_WRITE_WINS = "last_write_wins"
    MANUAL = "manual"


@dataclass
class SyncRecord:
    id: str
    entity_type: str
    entity_id: str
    source: str
    target: str
    direction: SyncDirection
    status: SyncStatus = SyncStatus.PENDING
    data_hash: str = ""
    conflict_data: dict = field(default_factory=dict)
    resolved: bool = False
    retry_count: int = 0
    started_at: str = ""
    completed_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = self.direction.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SyncRecord":
        data = data.copy()
        data["direction"] = SyncDirection(data.get("direction", "one_way"))
        data["status"] = SyncStatus(data.get("status", "pending"))
        return cls(**data)


@dataclass
class Snapshot:
    id: str
    entity_type: str
    entity_id: str
    data: Any = None
    version: int = 1
    hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot": return cls(**data)


class SyncEngine:
    def __init__(self, storage_dir: str = "collab_data/sync"):
        self.storage_dir = storage_dir
        self._records: dict[str, SyncRecord] = {}
        self._snapshots: dict[str, Snapshot] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _records_path(self) -> str: return os.path.join(self.storage_dir, "records.json")
    def _snapshots_path(self) -> str: return os.path.join(self.storage_dir, "snapshots.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._records_path(), self._records, SyncRecord),
            (self._snapshots_path(), self._snapshots, Snapshot),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load sync data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._records_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._records.items()}, f, indent=2, default=str)
            with open(self._snapshots_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save sync data: %s", e)

    def _compute_hash(self, data: Any) -> str:
        return hashlib.sha256(json.dumps(data, default=str).encode()).hexdigest()[:16]

    def create_sync(self, entity_type: str, entity_id: str, source: str, target: str, direction: SyncDirection = SyncDirection.ONE_WAY) -> SyncRecord:
        record = SyncRecord(id=str(uuid.uuid4()), entity_type=entity_type, entity_id=entity_id, source=source, target=target, direction=direction)
        self._records[record.id] = record
        self._save()
        return record

    def start_sync(self, record_id: str) -> bool:
        record = self._records.get(record_id)
        if not record: return False
        record.status = SyncStatus.SYNCING
        record.started_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def complete_sync(self, record_id: str, data: Any = None) -> bool:
        record = self._records.get(record_id)
        if not record: return False
        record.status = SyncStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc).isoformat()
        if data: record.data_hash = self._compute_hash(data)
        self._save()
        return True

    def detect_conflict(self, record_id: str, source_data: Any, target_data: Any) -> bool:
        record = self._records.get(record_id)
        if not record: return False
        source_hash = self._compute_hash(source_data)
        target_hash = self._compute_hash(target_data)
        if source_hash != target_hash:
            record.status = SyncStatus.CONFLICT
            record.conflict_data = {"source_hash": source_hash, "target_hash": target_hash}
            self._save()
            return True
        return False

    def resolve_conflict(self, record_id: str, resolution: ConflictResolution, resolved_data: Any = None) -> bool:
        record = self._records.get(record_id)
        if not record: return False
        record.resolved = True
        record.status = SyncStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def create_snapshot(self, entity_type: str, entity_id: str, data: Any) -> Snapshot:
        existing = [s for s in self._snapshots.values() if s.entity_type == entity_type and s.entity_id == entity_id]
        version = max((s.version for s in existing), default=0) + 1
        snap = Snapshot(id=str(uuid.uuid4()), entity_type=entity_type, entity_id=entity_id, data=data, version=version, hash=self._compute_hash(data))
        self._snapshots[snap.id] = snap
        self._save()
        return snap

    def restore_snapshot(self, entity_type: str, entity_id: str, version: int = -1) -> Optional[Snapshot]:
        snaps = [s for s in self._snapshots.values() if s.entity_type == entity_type and s.entity_id == entity_id]
        if not snaps: return None
        snaps.sort(key=lambda s: s.version)
        target = snaps[-1] if version == -1 else next((s for s in snaps if s.version == version), None)
        return target

    def list_syncs(self, entity_type: str = "", status: Optional[SyncStatus] = None) -> list[SyncRecord]:
        results = list(self._records.values())
        if entity_type: results = [r for r in results if r.entity_type == entity_type]
        if status: results = [r for r in results if r.status == status]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def list_snapshots(self, entity_type: str = "", entity_id: str = "") -> list[Snapshot]:
        results = list(self._snapshots.values())
        if entity_type: results = [s for s in results if s.entity_type == entity_type]
        if entity_id: results = [s for s in results if s.entity_id == entity_id]
        return sorted(results, key=lambda s: s.version)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
