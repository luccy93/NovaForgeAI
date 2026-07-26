"""Confidence Engine — confidence score, evidence strength, coverage, model agreement, reliability."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ConfidenceScore:
    id: str; decision_id: str; overall: float = 0.0
    evidence_strength: float = 0.0; coverage: float = 0.0; knowledge_completeness: float = 0.0
    model_agreement: float = 0.0; agent_agreement: float = 0.0; historical_accuracy: float = 0.0
    reliability: float = 0.0; stability: float = 0.0; components: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ConfidenceEngine:
    def __init__(self, storage_dir: str = "decision_data/confidence"):
        self.storage_dir = storage_dir; self._scores: dict[str, ConfidenceScore] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "scores.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._scores[k] = ConfidenceScore(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._scores.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def calculate(self, decision_id: str, evidence_strength: float = 0.7, coverage: float = 0.7) -> ConfidenceScore:
        overall = (evidence_strength * 0.4 + coverage * 0.3 + 0.8 * 0.3)
        cs = ConfidenceScore(id=str(uuid.uuid4()), decision_id=decision_id, overall=round(overall, 2), evidence_strength=evidence_strength, coverage=coverage, knowledge_completeness=coverage, model_agreement=0.85, agent_agreement=0.8, historical_accuracy=0.75, reliability=0.8, stability=0.85)
        self._scores[cs.id] = cs; self._save(); return cs

    def get_by_decision(self, decision_id: str) -> Optional[ConfidenceScore]:
        for s in self._scores.values():
            if s.decision_id == decision_id: return s
        return None

    def get_telemetry(self) -> dict: return {"scores": len(self._scores)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class Recommendation:
    id: str; decision_id: str; title: str; description: str = ""
    priority: str = "medium"; category: str = "general"
    confidence: float = 0.0; effort_hours: int = 0; risk: str = "low"
    evidence: list = field(default_factory=list); alternatives: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class RecommendationEngine:
    def __init__(self, storage_dir: str = "decision_data/recommendations"):
        self.storage_dir = storage_dir; self._recs: dict[str, Recommendation] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "recommendations.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._recs[k] = Recommendation(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._recs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, decision_id: str, title: str, description: str = "", priority: str = "medium", confidence: float = 0.0) -> Recommendation:
        r = Recommendation(id=str(uuid.uuid4()), decision_id=decision_id, title=title, description=description, priority=priority, confidence=confidence)
        self._recs[r.id] = r; self._save(); return r

    def get_by_decision(self, decision_id: str) -> list[Recommendation]:
        return sorted([r for r in self._recs.values() if r.decision_id == decision_id], key=lambda r: r.created_at, reverse=True)

    def get_telemetry(self) -> dict: return {"recommendations": len(self._recs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Alternative:
    id: str; decision_id: str; title: str; description: str = ""
    solution_type: str = "primary"  # primary, alternative, low_risk, high_perf, low_cost, enterprise, fast, long_term
    pros: list = field(default_factory=list); cons: list = field(default_factory=list)
    effort_hours: int = 0; risk_score: float = 0.0; confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AlternativeEngine:
    def __init__(self, storage_dir: str = "decision_data/alternatives"):
        self.storage_dir = storage_dir; self._alternatives: dict[str, Alternative] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "alternatives.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._alternatives[k] = Alternative(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._alternatives.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def generate(self, decision_id: str, title: str, solution_type: str = "alternative") -> Alternative:
        a = Alternative(id=str(uuid.uuid4()), decision_id=decision_id, title=title, solution_type=solution_type)
        self._alternatives[a.id] = a; self._save(); return a

    def get_by_decision(self, decision_id: str) -> list[Alternative]:
        return [a for a in self._alternatives.values() if a.decision_id == decision_id]

    def get_telemetry(self) -> dict: return {"alternatives": len(self._alternatives)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class RiskAssessment:
    id: str; decision_id: str; overall_risk: float = 0.0
    security_risk: float = 0.0; performance_risk: float = 0.0; deployment_risk: float = 0.0
    dependency_risk: float = 0.0; migration_risk: float = 0.0; compliance_risk: float = 0.0
    risk_factors: list = field(default_factory=list); mitigations: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class RiskEngine:
    def __init__(self, storage_dir: str = "decision_data/risks"):
        self.storage_dir = storage_dir; self._assessments: dict[str, RiskAssessment] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "assessments.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._assessments[k] = RiskAssessment(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._assessments.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def assess(self, decision_id: str, factors: list = None) -> RiskAssessment:
        ra = RiskAssessment(id=str(uuid.uuid4()), decision_id=decision_id, overall_risk=0.3, risk_factors=factors or ["default_risk"], mitigations=["monitor", "rollback_plan"])
        self._assessments[ra.id] = ra; self._save(); return ra

    def get_by_decision(self, decision_id: str) -> Optional[RiskAssessment]:
        for r in self._assessments.values():
            if r.decision_id == decision_id: return r
        return None

    def get_telemetry(self) -> dict: return {"assessments": len(self._assessments)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class BusinessImpact:
    id: str; decision_id: str; engineering_hours_saved: int = 0
    operational_cost_savings: float = 0.0; risk_reduction: float = 0.0
    performance_gain: float = 0.0; maintainability_improvement: float = 0.0
    deployment_risk: float = 0.0; security_improvement: float = 0.0
    developer_productivity_gain: float = 0.0; roi: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class BusinessImpactEngine:
    def __init__(self, storage_dir: str = "decision_data/impact"):
        self.storage_dir = storage_dir; self._impacts: dict[str, BusinessImpact] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "impacts.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._impacts[k] = BusinessImpact(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._impacts.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def estimate(self, decision_id: str, hours_saved: int = 0, cost_savings: float = 0.0) -> BusinessImpact:
        bi = BusinessImpact(id=str(uuid.uuid4()), decision_id=decision_id, engineering_hours_saved=hours_saved, operational_cost_savings=cost_savings, roi=hours_saved * 150 + cost_savings)
        self._impacts[bi.id] = bi; self._save(); return bi

    def get_by_decision(self, decision_id: str) -> Optional[BusinessImpact]:
        for b in self._impacts.values():
            if b.decision_id == decision_id: return b
        return None

    def get_telemetry(self) -> dict: return {"impacts": len(self._impacts)}
