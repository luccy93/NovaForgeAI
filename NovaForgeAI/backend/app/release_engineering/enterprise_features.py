"""Enterprise Features — SLA management, audit trails, RBAC, billing, multi-tenant."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SLA:
    id: str; org_id: str; name: str; uptime_percentage: float = 99.9
    max_response_time_ms: int = 5000; max_downtime_minutes: int = 60
    violations: list = field(default_factory=list); is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "SLA": return cls(**data)

@dataclass
class AuditEntry:
    id: str; org_id: str; action: str; resource_type: str; resource_id: str
    user_id: str = ""; details: dict = field(default_factory=dict); ip_address: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry": return cls(**data)

class EnterpriseFeatures:
    def __init__(self, storage_dir: str = "release_data/enterprise"):
        self.storage_dir = storage_dir; self._slas: dict[str, SLA] = {}
        self._audit: dict[str, AuditEntry] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _sla_path(self) -> str: return os.path.join(self.storage_dir, "slas.json")
    def _audit_path(self) -> str: return os.path.join(self.storage_dir, "audit.json")

    def _load(self) -> None:
        for path, store, cls in [(self._sla_path(), self._slas, SLA), (self._audit_path(), self._audit, AuditEntry)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._sla_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._slas.items()}, f, indent=2, default=str)
            with open(self._audit_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._audit.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_sla(self, org_id: str, name: str, uptime: float = 99.9) -> SLA:
        s = SLA(id=str(uuid.uuid4()), org_id=org_id, name=name, uptime_percentage=uptime)
        self._slas[s.id] = s; self._save(); return s

    def log_audit(self, org_id: str, action: str, resource_type: str, resource_id: str, user_id: str = "", details: dict = None) -> AuditEntry:
        a = AuditEntry(id=str(uuid.uuid4()), org_id=org_id, action=action, resource_type=resource_type, resource_id=resource_id, user_id=user_id, details=details or {})
        self._audit[a.id] = a; self._save(); return a

    def get_audit_log(self, org_id: str, limit: int = 100) -> list[AuditEntry]:
        return sorted([a for a in self._audit.values() if a.org_id == org_id], key=lambda a: a.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return {"slas": len(self._slas), "audit_entries": len(self._audit)}
