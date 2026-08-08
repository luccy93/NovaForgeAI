"""Decision Pipeline — problem detection, context, analysis, reasoning, recommendation, validation, risk."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PipelineRun:
    id: str; org_id: str; problem: str; context: dict = field(default_factory=dict)
    stages: list = field(default_factory=list); current_stage: str = ""
    status: str = "pending"; decision_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "PipelineRun": return cls(**data)

@dataclass
class PipelineStage:
    id: str; run_id: str; name: str; order: int; status: str = "pending"
    result: dict = field(default_factory=dict); duration_ms: float = 0.0
    started_at: str = ""; completed_at: str = ""

class DecisionPipeline:
    def __init__(self, storage_dir: str = "decision_data/pipeline"):
        self.storage_dir = storage_dir; self._runs: dict[str, PipelineRun] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "runs.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._runs[k] = PipelineRun.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._runs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def start(self, org_id: str, problem: str) -> PipelineRun:
        r = PipelineRun(id=str(uuid.uuid4()), org_id=org_id, problem=problem)
        self._runs[r.id] = r; self._save(); return r

    def complete(self, run_id: str, decision_id: str) -> Optional[PipelineRun]:
        r = self._runs.get(run_id)
        if not r: return None
        r.status = "completed"; r.decision_id = decision_id; self._save(); return r

    def get_telemetry(self) -> dict: return {"runs": len(self._runs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Tradeoff:
    id: str; decision_id: str; dimension: str  # performance, maintainability, security, complexity, scalability, reliability, cost, tech_debt, effort, dx, business_value
    primary_value: float = 0.0; alternative_value: float = 0.0
    primary_label: str = ""; alternative_label: str = ""
    weight: float = 1.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TradeoffAnalysis:
    def __init__(self, storage_dir: str = "decision_data/tradeoffs"):
        self.storage_dir = storage_dir; self._tradeoffs: dict[str, Tradeoff] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "tradeoffs.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._tradeoffs[k] = Tradeoff(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._tradeoffs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def compare(self, decision_id: str, dimension: str, primary_val: float, alt_val: float, primary_label: str = "", alt_label: str = "") -> Tradeoff:
        t = Tradeoff(id=str(uuid.uuid4()), decision_id=decision_id, dimension=dimension, primary_value=primary_val, alternative_value=alt_val, primary_label=primary_label, alternative_label=alt_label)
        self._tradeoffs[t.id] = t; self._save(); return t

    def get_by_decision(self, decision_id: str) -> list[Tradeoff]:
        return [t for t in self._tradeoffs.values() if t.decision_id == decision_id]

    def summary(self, decision_id: str) -> dict:
        dims = self.get_by_decision(decision_id)
        if not dims: return {}
        primary_total = sum(t.primary_value * t.weight for t in dims)
        alt_total = sum(t.alternative_value * t.weight for t in dims)
        return {"primary_total": round(primary_total, 2), "alternative_total": round(alt_total, 2), "recommended": "primary" if primary_total >= alt_total else "alternative", "dimensions": len(dims)}

    def get_telemetry(self) -> dict: return {"tradeoffs": len(self._tradeoffs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ArchitectureFinding:
    id: str; org_id: str; repository_id: str; finding_type: str  # layer_violation, dependency_cycle, coupling, boundary, domain_separation
    severity: str = "medium"; description: str = ""
    locations: list = field(default_factory=list); recommendation: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ArchitectureAdvisor:
    def __init__(self, storage_dir: str = "decision_data/arch"):
        self.storage_dir = storage_dir; self._findings: dict[str, ArchitectureFinding] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "findings.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._findings[k] = ArchitectureFinding.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._findings.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def report(self, org_id: str, repo_id: str, finding_type: str, description: str, severity: str = "medium") -> ArchitectureFinding:
        f = ArchitectureFinding(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, finding_type=finding_type, severity=severity, description=description)
        self._findings[f.id] = f; self._save(); return f

    def get_by_repo(self, org_id: str, repo_id: str) -> list[ArchitectureFinding]:
        return [f for f in self._findings.values() if f.org_id == org_id and f.repository_id == repo_id]

    def get_telemetry(self) -> dict: return {"findings": len(self._findings)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SecurityFinding:
    id: str; org_id: str; repository_id: str; finding_type: str  # auth, encryption, secrets, dependency, owasp, compliance
    severity: str = "medium"; description: str = ""
    locations: list = field(default_factory=list); recommendation: str = ""
    cvss_score: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class SecurityAdvisor:
    def __init__(self, storage_dir: str = "decision_data/security"):
        self.storage_dir = storage_dir; self._findings: dict[str, SecurityFinding] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "findings.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._findings[k] = SecurityFinding.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._findings.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def report(self, org_id: str, repo_id: str, finding_type: str, description: str, severity: str = "medium", cvss: float = 0.0) -> SecurityFinding:
        f = SecurityFinding(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, finding_type=finding_type, severity=severity, description=description, cvss_score=cvss)
        self._findings[f.id] = f; self._save(); return f

    def get_by_repo(self, org_id: str, repo_id: str) -> list[SecurityFinding]:
        return [f for f in self._findings.values() if f.org_id == org_id and f.repository_id == repo_id]

    def get_telemetry(self) -> dict: return {"findings": len(self._findings)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PerformanceFinding:
    id: str; org_id: str; repository_id: str; finding_type: str  # caching, query, parallel, memory, cpu, gpu, scaling
    severity: str = "medium"; description: str = ""
    locations: list = field(default_factory=list); recommendation: str = ""
    estimated_improvement: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PerformanceAdvisor:
    def __init__(self, storage_dir: str = "decision_data/perf"):
        self.storage_dir = storage_dir; self._findings: dict[str, PerformanceFinding] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "findings.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._findings[k] = PerformanceFinding.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._findings.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def report(self, org_id: str, repo_id: str, finding_type: str, description: str, severity: str = "medium", improvement: float = 0.0) -> PerformanceFinding:
        f = PerformanceFinding(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, finding_type=finding_type, severity=severity, description=description, estimated_improvement=improvement)
        self._findings[f.id] = f; self._save(); return f

    def get_by_repo(self, org_id: str, repo_id: str) -> list[PerformanceFinding]:
        return [f for f in self._findings.values() if f.org_id == org_id and f.repository_id == repo_id]

    def get_telemetry(self) -> dict: return {"findings": len(self._findings)}
