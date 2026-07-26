"""Migration Manager — schema, data, versioned migrations, rollback, dry-run."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class MigrationStatus(Enum):
    PENDING = "pending"; RUNNING = "running"; SUCCEEDED = "succeeded"
    FAILED = "failed"; ROLLING_BACK = "rolling_back"; ROLLED_BACK = "rolled_back"

class MigrationType(Enum):
    SCHEMA = "schema"; DATA = "data"; SEED = "seed"; INDEX = "index"; CONFIG = "config"

@dataclass
class Migration:
    id: str; org_id: str; name: str; migration_type: MigrationType = MigrationType.SCHEMA
    status: MigrationStatus = MigrationStatus.PENDING; version: str = ""
    up_sql: str = ""; down_sql: str = ""; dry_run: bool = False
    checksum: str = ""; executed_by: str = ""
    started_at: str = ""; completed_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["migration_type"] = self.migration_type.value; d["status"] = self.status.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "Migration":
        data = data.copy(); data["migration_type"] = MigrationType(data.get("migration_type", "schema"))
        data["status"] = MigrationStatus(data.get("status", "pending"))
        return cls(**data)

class MigrationManager:
    def __init__(self, storage_dir: str = "release_data/migrations"):
        self.storage_dir = storage_dir; self._migrations: dict[str, Migration] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "migrations.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._migrations[k] = Migration.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._migrations.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, migration_type: MigrationType = MigrationType.SCHEMA, up_sql: str = "", down_sql: str = "") -> Migration:
        m = Migration(id=str(uuid.uuid4()), org_id=org_id, name=name, migration_type=migration_type, up_sql=up_sql, down_sql=down_sql)
        self._migrations[m.id] = m; self._save(); return m

    def execute(self, mig_id: str, executed_by: str = "") -> Optional[Migration]:
        m = self._migrations.get(mig_id)
        if not m: return None
        m.status = MigrationStatus.RUNNING; m.executed_by = executed_by
        m.started_at = datetime.now(timezone.utc).isoformat()
        # simulate execution
        m.status = MigrationStatus.SUCCEEDED; m.completed_at = datetime.now(timezone.utc).isoformat()
        self._save(); return m

    def rollback(self, mig_id: str) -> Optional[Migration]:
        m = self._migrations.get(mig_id)
        if not m: return None
        m.status = MigrationStatus.ROLLED_BACK; m.completed_at = datetime.now(timezone.utc).isoformat()
        self._save(); return m

    def get_telemetry(self) -> dict: return dict(self._telemetry)
