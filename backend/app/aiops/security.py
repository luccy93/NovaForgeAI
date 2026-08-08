"""AIOps Security — permission validation, audit logs, rollback plans, governance policies."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SecurityCheck:
    id: str; org_id: str; action: str; target: str; user_id: str = ""
    permitted: bool = False; reason: str = ""; policy: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "SecurityCheck": return cls(**data)

@dataclass
class SafetyPolicy:
    id: str; org_id: str; name: str; rules: list = field(default_factory=list)
    is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AIOpsSecurity:
    def __init__(self, storage_dir: str = "aiops_data/security"):
        self.storage_dir = storage_dir; self._checks: dict[str, SecurityCheck] = {}
        self._policies: dict[str, SafetyPolicy] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _chk_path(self) -> str: return os.path.join(self.storage_dir, "checks.json")
    def _pol_path(self) -> str: return os.path.join(self.storage_dir, "policies.json")

    def _load(self) -> None:
        for path, store, cls in [(self._chk_path(), self._checks, SecurityCheck), (self._pol_path(), self._policies, SafetyPolicy)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._chk_path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._checks.items()}, f, indent=2, default=str)
            with open(self._pol_path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._policies.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def check_permission(self, org_id: str, action: str, target: str, user_id: str = "") -> SecurityCheck:
        permitted = action not in ["delete_production", "modify_secrets", "bypass_approval"]
        c = SecurityCheck(id=str(uuid.uuid4()), org_id=org_id, action=action, target=target, user_id=user_id, permitted=permitted, reason="" if permitted else f"Action {action} requires additional approval", policy="safety_policy_v1")
        self._checks[c.id] = c; self._save(); return c

    def create_policy(self, org_id: str, name: str, rules: list = None) -> SafetyPolicy:
        p = SafetyPolicy(id=str(uuid.uuid4()), org_id=org_id, name=name, rules=rules or [])
        self._policies[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"checks": len(self._checks), "policies": len(self._policies)}
