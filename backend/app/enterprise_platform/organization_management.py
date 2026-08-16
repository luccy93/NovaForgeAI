import os, uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class Organization:
    id: str
    name: str = ""
    domain: str = ""
    plan: str = "free"
    owner_id: str = ""
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class OrganizationManagement:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)

    def create(self, name, domain, plan, owner_id=""):
        return Organization(id=uuid.uuid4().hex, name=name, domain=domain, plan=plan, owner_id=owner_id)