"""Cross-Organization — partner/vendor/customer collaboration, guest access, secure sharing."""
import json, uuid, os, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CrossOrgCollaboration:
    id: str; org_id: str; partner_org_id: str; collaboration_type: str  # partner, vendor, customer, guest
    name: str = ""; description: str = ""; permissions: dict = field(default_factory=dict)
    shared_resources: list = field(default_factory=list); is_active: bool = True
    expires_at: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "CrossOrgCollaboration": return cls(**data)

@dataclass
class GuestAccess:
    id: str; collab_id: str; guest_email: str; guest_name: str = ""
    permissions: dict = field(default_factory=dict); access_token: str = ""
    expires_at: str = ""; is_active: bool = True; last_accessed: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "GuestAccess": return cls(**data)

class CrossOrg:
    def __init__(self, storage_dir: str = "rtc_data/cross_org"):
        self.storage_dir = storage_dir; self._collabs: dict[str, CrossOrgCollaboration] = {}
        self._guests: dict[str, GuestAccess] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _col_path(self) -> str: return os.path.join(self.storage_dir, "collaborations.json")
    def _guest_path(self) -> str: return os.path.join(self.storage_dir, "guests.json")

    def _load(self) -> None:
        for path, store, cls in [(self._col_path(), self._collabs, CrossOrgCollaboration), (self._guest_path(), self._guests, GuestAccess)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._col_path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._collabs.items()}, f, indent=2, default=str)
            with open(self._guest_path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._guests.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_collaboration(self, org_id: str, partner_org_id: str, collab_type: str, name: str = "") -> CrossOrgCollaboration:
        c = CrossOrgCollaboration(id=str(uuid.uuid4()), org_id=org_id, partner_org_id=partner_org_id, collaboration_type=collab_type, name=name)
        self._collabs[c.id] = c; self._save(); return c

    def grant_guest_access(self, collab_id: str, email: str, name: str = "", ttl_hours: int = 72) -> Optional[GuestAccess]:
        collab = self._collabs.get(collab_id)
        if not collab: return None
        g = GuestAccess(id=str(uuid.uuid4()), collab_id=collab_id, guest_email=email, guest_name=name, access_token=str(uuid.uuid4()), expires_at=(datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat())
        self._guests[g.id] = g; self._save(); return g

    def get_telemetry(self) -> dict: return {"collaborations": len(self._collabs), "guests": len(self._guests)}
