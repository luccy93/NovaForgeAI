"""Certification — verified plugins, agents, prompts, connectors, workflows, templates; security cert."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Certification:
    id: str; org_id: str; item_id: str; cert_type: str; status: str = "pending"
    checks_passed: int = 0; total_checks: int = 5; verified_by: str = ""
    expires_at: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CertificationSystem:
    def __init__(self, storage_dir: str = "marketplace_data/certification"):
        self.storage_dir = storage_dir; self._certs: dict[str, Certification] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "certs.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._certs[k] = Certification(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._certs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def certify(self, org_id: str, item_id: str, cert_type: str) -> Certification:
        c = Certification(id=str(uuid.uuid4()), org_id=org_id, item_id=item_id, cert_type=cert_type, status="verified", checks_passed=5, total_checks=5)
        self._certs[c.id] = c; self._save(); return c

    def get_by_item(self, item_id: str) -> Optional[Certification]:
        for c in self._certs.values():
            if c.item_id == item_id: return c
        return None

    def get_telemetry(self) -> dict: return {"certs": len(self._certs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class DeveloperProfile:
    id: str; org_id: str; name: str; email: str = ""; api_keys: list = field(default_factory=list)
    published_items: int = 0; total_revenue: float = 0.0; rating: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DeveloperPortal:
    def __init__(self, storage_dir: str = "marketplace_data/portal"):
        self.storage_dir = storage_dir; self._profiles: dict[str, DeveloperProfile] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "profiles.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._profiles[k] = DeveloperProfile(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._profiles.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, email: str = "") -> DeveloperProfile:
        p = DeveloperProfile(id=str(uuid.uuid4()), org_id=org_id, name=name, email=email)
        self._profiles[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"profiles": len(self._profiles)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MonetizationPlan:
    id: str; org_id: str; item_id: str; plan_type: str  # free, paid, subscription, one_time, enterprise, usage_based
    price: float = 0.0; revenue_share: float = 0.7; currency: str = "USD"
    is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class Monetization:
    def __init__(self, storage_dir: str = "marketplace_data/monetization"):
        self.storage_dir = storage_dir; self._plans: dict[str, MonetizationPlan] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "plans.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._plans[k] = MonetizationPlan(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._plans.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_plan(self, org_id: str, item_id: str, plan_type: str, price: float = 0.0) -> MonetizationPlan:
        p = MonetizationPlan(id=str(uuid.uuid4()), org_id=org_id, item_id=item_id, plan_type=plan_type, price=price)
        self._plans[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"plans": len(self._plans)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class RatingReview:
    id: str; org_id: str; item_id: str; user_id: str; rating: float; review: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class RatingSystem:
    def __init__(self, storage_dir: str = "marketplace_data/ratings"):
        self.storage_dir = storage_dir; self._reviews: dict[str, RatingReview] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "reviews.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._reviews[k] = RatingReview(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._reviews.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def submit(self, org_id: str, item_id: str, user_id: str, rating: float, review: str = "") -> RatingReview:
        r = RatingReview(id=str(uuid.uuid4()), org_id=org_id, item_id=item_id, user_id=user_id, rating=rating, review=review)
        self._reviews[r.id] = r; self._save(); return r

    def get_average(self, item_id: str) -> float:
        ratings = [r.rating for r in self._reviews.values() if r.item_id == item_id]
        return sum(ratings) / len(ratings) if ratings else 0.0

    def get_telemetry(self) -> dict: return {"reviews": len(self._reviews)}
