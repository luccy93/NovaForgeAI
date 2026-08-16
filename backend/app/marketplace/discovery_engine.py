"""Discovery Engine — popular, trending, recommended, personalized, AI suggestions."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class DiscoveryResult:
    id: str; org_id: str; item_id: str; reason: str; score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DiscoveryEngine:
    def __init__(self, storage_dir: str = "marketplace_data/discovery"):
        self.storage_dir = storage_dir; self._results: dict[str, DiscoveryResult] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "results.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._results[k] = DiscoveryResult(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._results.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def recommend(self, org_id: str, item_id: str, reason: str, score: float = 0.5) -> DiscoveryResult:
        r = DiscoveryResult(id=str(uuid.uuid4()), org_id=org_id, item_id=item_id, reason=reason, score=score)
        self._results[r.id] = r; self._save(); return r

    def get_recommendations(self, org_id: str, limit: int = 20) -> list[DiscoveryResult]:
        return sorted([r for r in self._results.values() if r.org_id == org_id], key=lambda r: r.score, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return {"results": len(self._results)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PluginSecurityCheck:
    id: str; plugin_id: str; sandboxed: bool = True; code_signed: bool = False
    malware_scan: bool = False; dep_scan: bool = False; license_valid: bool = False
    overall_score: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PluginSecurity:
    def __init__(self, storage_dir: str = "marketplace_data/security"):
        self.storage_dir = storage_dir; self._checks: dict[str, PluginSecurityCheck] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "checks.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._checks[k] = PluginSecurityCheck(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._checks.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def scan(self, plugin_id: str) -> PluginSecurityCheck:
        score = 0.8  # simulated scan
        c = PluginSecurityCheck(id=str(uuid.uuid4()), plugin_id=plugin_id, sandboxed=True, code_signed=True, malware_scan=True, dep_scan=True, license_valid=True, overall_score=score)
        self._checks[c.id] = c; self._save(); return c

    def get_by_plugin(self, plugin_id: str) -> Optional[PluginSecurityCheck]:
        for c in self._checks.values():
            if c.plugin_id == plugin_id: return c
        return None

    def get_telemetry(self) -> dict: return {"checks": len(self._checks)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PluginAnalytic:
    id: str; plugin_id: str; period: str; installations: int = 0; active_users: int = 0
    failures: int = 0; avg_memory_mb: float = 0.0; avg_cpu_percent: float = 0.0
    revenue_generated: float = 0.0; rating: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PluginAnalytics:
    def __init__(self, storage_dir: str = "marketplace_data/analytics"):
        self.storage_dir = storage_dir; self._analytics: dict[str, PluginAnalytic] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "analytics.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._analytics[k] = PluginAnalytic(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._analytics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, plugin_id: str, installations: int = 0, active: int = 0) -> PluginAnalytic:
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        a = PluginAnalytic(id=str(uuid.uuid4()), plugin_id=plugin_id, period=period, installations=installations, active_users=active)
        self._analytics[a.id] = a; self._save(); return a

    def get_by_plugin(self, plugin_id: str) -> list[PluginAnalytic]:
        return sorted([a for a in self._analytics.values() if a.plugin_id == plugin_id], key=lambda a: a.created_at, reverse=True)

    def get_telemetry(self) -> dict: return {"analytics": len(self._analytics)}
