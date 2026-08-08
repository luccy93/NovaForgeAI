"""Quality Gate Engine — policies, checks, results, enforcement, automation."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class GateStatus(Enum):
    PENDING = "pending"; PASSED = "passed"; FAILED = "failed"; SKIPPED = "skipped"

class GateSeverity(Enum):
    CRITICAL = "critical"; HIGH = "high"; MEDIUM = "medium"; LOW = "low"; INFO = "info"

@dataclass
class QualityGate:
    id: str; org_id: str; name: str; description: str = ""
    category: str = "general"; severity: GateSeverity = GateSeverity.HIGH
    conditions: dict = field(default_factory=dict); auto_enforce: bool = True
    is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["severity"] = self.severity.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityGate":
        data = data.copy(); data["severity"] = GateSeverity(data.get("severity", "high"))
        return cls(**data)

@dataclass
class GateResult:
    id: str; org_id: str; gate_id: str; resource_type: str; resource_id: str
    status: GateStatus = GateStatus.PENDING; score: float = 0.0; details: dict = field(default_factory=dict)
    evaluated_at: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "GateResult":
        data = data.copy(); data["status"] = GateStatus(data.get("status", "pending"))
        return cls(**data)

class QualityGateEngine:
    def __init__(self, storage_dir: str = "release_data/gates"):
        self.storage_dir = storage_dir; self._gates: dict[str, QualityGate] = {}
        self._results: dict[str, GateResult] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _gate_path(self) -> str: return os.path.join(self.storage_dir, "gates.json")
    def _result_path(self) -> str: return os.path.join(self.storage_dir, "results.json")

    def _load(self) -> None:
        for path, store, cls in [(self._gate_path(), self._gates, QualityGate), (self._result_path(), self._results, GateResult)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._gate_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._gates.items()}, f, indent=2, default=str)
            with open(self._result_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._results.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_gate(self, org_id: str, name: str, category: str = "general", conditions: dict = None, severity: GateSeverity = GateSeverity.HIGH) -> QualityGate:
        g = QualityGate(id=str(uuid.uuid4()), org_id=org_id, name=name, category=category, conditions=conditions or {}, severity=severity)
        self._gates[g.id] = g; self._save(); return g

    def evaluate(self, org_id: str, gate_id: str, resource_type: str, resource_id: str, details: dict = None) -> GateResult:
        gate = self._gates.get(gate_id)
        if not gate: raise ValueError(f"Gate {gate_id} not found")
        passed = all(details.get(k) == v for k, v in gate.conditions.items()) if details else True
        status = GateStatus.PASSED if passed else GateStatus.FAILED
        r = GateResult(id=str(uuid.uuid4()), org_id=org_id, gate_id=gate_id, resource_type=resource_type, resource_id=resource_id, status=status, score=1.0 if passed else 0.0, details=details or {}, evaluated_at=datetime.now(timezone.utc).isoformat())
        self._results[r.id] = r; self._save(); return r

    def list_results(self, resource_type: str = "", resource_id: str = "") -> list[GateResult]:
        results = list(self._results.values())
        if resource_type: results = [r for r in results if r.resource_type == resource_type]
        if resource_id: results = [r for r in results if r.resource_id == resource_id]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
