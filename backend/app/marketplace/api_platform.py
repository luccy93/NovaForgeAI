"""API Platform — marketplace, publishing, analytics, plugin, agent, prompt, workflow, template, billing APIs."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class APIEndpoint:
    id: str; org_id: str; name: str; path: str; method: str = "GET"
    rate_limit: int = 100; auth_required: bool = True; version: str = "v1"
    description: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class APIPlatform:
    def __init__(self, storage_dir: str = "marketplace_data/api"):
        self.storage_dir = storage_dir; self._endpoints: dict[str, APIEndpoint] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "endpoints.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._endpoints[k] = APIEndpoint(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._endpoints.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, path: str, method: str = "GET") -> APIEndpoint:
        e = APIEndpoint(id=str(uuid.uuid4()), org_id=org_id, name=name, path=path, method=method)
        self._endpoints[e.id] = e; self._save(); return e

    def get_telemetry(self) -> dict: return {"endpoints": len(self._endpoints)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PrivateMarketplace:
    id: str; org_id: str; name: str; is_private: bool = True
    allowed_orgs: list = field(default_factory=list); items: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class EnterpriseMarketplace:
    def __init__(self, storage_dir: str = "marketplace_data/enterprise"):
        self.storage_dir = storage_dir; self._marketplaces: dict[str, PrivateMarketplace] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "marketplaces.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._marketplaces[k] = PrivateMarketplace(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._marketplaces.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str) -> PrivateMarketplace:
        pm = PrivateMarketplace(id=str(uuid.uuid4()), org_id=org_id, name=name)
        self._marketplaces[pm.id] = pm; self._save(); return pm

    def get_telemetry(self) -> dict: return {"marketplaces": len(self._marketplaces)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MPTelemetry:
    id: str; org_id: str; period: str; marketplace_usage: int = 0; plugin_health: float = 1.0
    total_downloads: int = 0; total_revenue: float = 0.0; errors: int = 0
    publishing_activity: int = 0; security_events: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MPSecurityEntry:
    id: str; event: str; item_id: str; details: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MPTesting:
    pass

class MPObservability:
    def __init__(self, storage_dir: str = "marketplace_data/observability"):
        self.storage_dir = storage_dir; self._metrics: dict[str, MPTelemetry] = {}; self._security: dict[str, MPSecurityEntry] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _met_path(self) -> str: return os.path.join(self.storage_dir, "metrics.json")
    def _sec_path(self) -> str: return os.path.join(self.storage_dir, "security.json")

    def _load(self) -> None:
        for path, store, cls in [(self._met_path(), self._metrics, MPTelemetry), (self._sec_path(), self._security, MPSecurityEntry)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls(**v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._met_path(), "w") as f: json.dump({k: asdict(v) for k, v in self._metrics.items()}, f, indent=2, default=str)
            with open(self._sec_path(), "w") as f: json.dump({k: asdict(v) for k, v in self._security.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, metrics: dict) -> MPTelemetry:
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        m = MPTelemetry(id=str(uuid.uuid4()), org_id=org_id, period=period, **{k: v for k, v in metrics.items() if k in [f.name for f in MPTelemetry.__dataclass_fields__]})
        self._metrics[m.id] = m; self._save(); return m

    def log_security(self, event: str, item_id: str, details: str = "") -> MPSecurityEntry:
        e = MPSecurityEntry(id=str(uuid.uuid4()), event=event, item_id=item_id, details=details)
        self._security[e.id] = e; self._save(); return e

    def get_telemetry(self) -> dict: return {"metrics": len(self._metrics), "security": len(self._security)}
