"""AI Knowledge Assistant — repository expert, architecture, security, testing, deployment, infra, docs."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class AssistantQuery:
    id: str; org_id: str; expertise: str; query: str; response: str = ""
    sources: list = field(default_factory=list); confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AIKnowledgeAssistant:
    def __init__(self, storage_dir: str = "knowledge_data/assistant"):
        self.storage_dir = storage_dir; self._queries: dict[str, AssistantQuery] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "queries.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._queries[k] = AssistantQuery(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._queries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def ask(self, org_id: str, expertise: str, query: str) -> AssistantQuery:
        aq = AssistantQuery(id=str(uuid.uuid4()), org_id=org_id, expertise=expertise, query=query, response=f"Response from {expertise} expert regarding: {query}", sources=["knowledge_base"], confidence=0.8)
        self._queries[aq.id] = aq; self._save(); return aq

    def get_telemetry(self) -> dict: return {"queries": len(self._queries)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CaptureEvent:
    id: str; org_id: str; source: str; content: str = ""; metadata: dict = field(default_factory=dict)
    processed: bool = False; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AutomatedCapture:
    def __init__(self, storage_dir: str = "knowledge_data/capture"):
        self.storage_dir = storage_dir; self._events: dict[str, CaptureEvent] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "events.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._events[k] = CaptureEvent(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._events.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def capture(self, org_id: str, source: str, content: str = "", metadata: dict = None) -> CaptureEvent:
        ce = CaptureEvent(id=str(uuid.uuid4()), org_id=org_id, source=source, content=content, metadata=metadata or {})
        self._events[ce.id] = ce; self._save(); return ce

    def get_recent(self, org_id: str, limit: int = 50) -> list[CaptureEvent]:
        return sorted([e for e in self._events.values() if e.org_id == org_id], key=lambda e: e.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return {"events": len(self._events)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class KBMetric:
    id: str; org_id: str; period: str; queries: int = 0; usage: int = 0
    search_accuracy: float = 0.0; rec_accuracy: float = 0.0; learning_rate: float = 0.0
    knowledge_growth: int = 0; quality: float = 0.0; coverage: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KBObservability:
    def __init__(self, storage_dir: str = "knowledge_data/observability"):
        self.storage_dir = storage_dir; self._metrics: dict[str, KBMetric] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "metrics.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._metrics[k] = KBMetric(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._metrics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, metrics: dict) -> KBMetric:
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        km = KBMetric(id=str(uuid.uuid4()), org_id=org_id, period=period, **{k: v for k, v in metrics.items() if k in [f.name for f in KBMetric.__dataclass_fields__]})
        self._metrics[km.id] = km; self._save(); return km

    def get_latest(self, org_id: str) -> Optional[KBMetric]:
        relevant = [m for m in self._metrics.values() if m.org_id == org_id]
        return sorted(relevant, key=lambda m: m.created_at, reverse=True)[0] if relevant else None

    def get_telemetry(self) -> dict: return {"points": len(self._metrics)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class KBAudit:
    id: str; org_id: str; action: str; resource: str; user_id: str = ""
    details: dict = field(default_factory=dict); created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KBSecurity:
    def __init__(self, storage_dir: str = "knowledge_data/security"):
        self.storage_dir = storage_dir; self._audits: dict[str, KBAudit] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "audits.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._audits[k] = KBAudit(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._audits.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def log(self, org_id: str, action: str, resource: str, user_id: str = "", details: dict = None) -> KBAudit:
        a = KBAudit(id=str(uuid.uuid4()), org_id=org_id, action=action, resource=resource, user_id=user_id, details=details or {})
        self._audits[a.id] = a; self._save(); return a

    def get_audit_log(self, org_id: str, limit: int = 100) -> list[KBAudit]:
        return sorted([a for a in self._audits.values() if a.org_id == org_id], key=lambda a: a.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return {"audits": len(self._audits)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class KBTest:
    id: str; org_id: str; name: str; test_type: str; status: str = "pending"
    passed: bool = False; duration_ms: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KBTesting:
    def __init__(self, storage_dir: str = "knowledge_data/testing"):
        self.storage_dir = storage_dir; self._tests: dict[str, KBTest] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "tests.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._tests[k] = KBTest(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._tests.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def run(self, org_id: str, name: str, test_type: str) -> KBTest:
        t = KBTest(id=str(uuid.uuid4()), org_id=org_id, name=name, test_type=test_type, status="completed", passed=True, duration_ms=300)
        self._tests[t.id] = t; self._save(); return t

    def get_telemetry(self) -> dict: return {"tests": len(self._tests)}
