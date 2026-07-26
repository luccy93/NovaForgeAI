import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class GateType(Enum):
    EVALUATION = "evaluation"
    BENCHMARK = "benchmark"
    SECURITY_REVIEW = "security_review"
    LATENCY = "latency"
    COST = "cost"
    DOCUMENTATION = "documentation"
    ROLLBACK_PLAN = "rollback_plan"
    CODE_REVIEW = "code_review"
    COMPLIANCE = "compliance"
    PERFORMANCE = "performance"


class GateStatus(Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKING = "blocking"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QualityGate:
    id: str = ""
    name: str = ""
    gate_type: GateType = GateType.EVALUATION
    description: str = ""
    enabled: bool = True
    required: bool = True
    order: int = 0
    conditions: dict = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gate_type"] = self.gate_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityGate":
        if "gate_type" in data:
            data["gate_type"] = GateType(data["gate_type"])
        return cls(**data)


@dataclass
class GateResult:
    id: str = ""
    gate_id: str = ""
    target_type: str = ""
    target_id: str = ""
    status: GateStatus = GateStatus.PENDING
    score: float = 0.0
    details: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    checked_at: str = ""
    checked_by: str = ""
    duration_ms: float = 0.0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GateResult":
        if "status" in data:
            data["status"] = GateStatus(data["status"])
        return cls(**data)


@dataclass
class QualityChecklist:
    id: str = ""
    name: str = ""
    description: str = ""
    gates: list[str] = field(default_factory=list)
    target_type: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QualityChecklist":
        return cls(**data)


@dataclass
class GateReport:
    id: str = ""
    checklist_id: str = ""
    target_id: str = ""
    overall_score: float = 0.0
    passed: int = 0
    failed: int = 0
    total: int = 0
    results: list[GateResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["results"] = [r.to_dict() for r in self.results]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GateReport":
        if "results" in data:
            data["results"] = [GateResult.from_dict(r) for r in data["results"]]
        return cls(**data)


@dataclass
class RollbackPlan:
    id: str = ""
    target_type: str = ""
    target_id: str = ""
    steps: list[str] = field(default_factory=list)
    verification_steps: list[str] = field(default_factory=list)
    estimated_duration_minutes: int = 15
    rollback_script: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RollbackPlan":
        return cls(**data)


class QualityGateManager:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/quality")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.gates: dict[str, QualityGate] = {}
        self.checklists: dict[str, QualityChecklist] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_gates_path(self) -> Path:
        return self.storage_dir / "quality_gates.json"

    def _get_checklists_path(self) -> Path:
        return self.storage_dir / "quality_checklists.json"

    def _save_gates(self):
        path = self._get_gates_path()
        try:
            data = {k: v.to_dict() for k, v in self.gates.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save quality gates: %s", e)

    def _save_checklists(self):
        path = self._get_checklists_path()
        try:
            data = {k: v.to_dict() for k, v in self.checklists.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save quality checklists: %s", e)

    def _load(self):
        try:
            path = self._get_gates_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.gates = {k: QualityGate.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load quality gates: %s", e)
        try:
            path = self._get_checklists_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.checklists = {k: QualityChecklist.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load quality checklists: %s", e)

    def create_gate(self, name: str, gate_type: GateType, description: str = "",
                    enabled: bool = True, required: bool = True,
                    order: int = 0, conditions: Optional[dict] = None,
                    actions: Optional[list[str]] = None) -> QualityGate:
        gate = QualityGate(
            name=name,
            gate_type=gate_type,
            description=description,
            enabled=enabled,
            required=required,
            order=order,
            conditions=conditions or {},
            actions=actions or [],
        )
        self.gates[gate.id] = gate
        self._save_gates()
        self.telemetry["gates_created"] += 1
        logger.info("Created quality gate %s: %s [%s]", gate.id, name, gate_type.value)
        return gate

    def get_gate(self, gate_id: str) -> Optional[QualityGate]:
        return self.gates.get(gate_id)

    def update_gate(self, gate_id: str, **kwargs) -> Optional[QualityGate]:
        gate = self.gates.get(gate_id)
        if not gate:
            return None
        for key, value in kwargs.items():
            if hasattr(gate, key) and key not in ("id", "created_at"):
                if key == "gate_type":
                    setattr(gate, key, GateType(value) if isinstance(value, str) else value)
                else:
                    setattr(gate, key, value)
        gate.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_gates()
        self.telemetry["gates_updated"] += 1
        return gate

    def delete_gate(self, gate_id: str):
        if gate_id in self.gates:
            del self.gates[gate_id]
            self._save_gates()
            self.telemetry["gates_deleted"] += 1
            logger.info("Deleted quality gate %s", gate_id)

    def list_gates(self, gate_type: Optional[GateType] = None) -> list[QualityGate]:
        gates = list(self.gates.values())
        if gate_type:
            gates = [g for g in gates if g.gate_type == gate_type]
        return sorted(gates, key=lambda g: g.order)

    def get_gates_by_type(self, gate_type: GateType) -> list[QualityGate]:
        return self.list_gates(gate_type=gate_type)

    def reorder_gates(self, gate_ids: list[str]):
        for idx, gate_id in enumerate(gate_ids):
            gate = self.gates.get(gate_id)
            if gate:
                gate.order = idx
                gate.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_gates()
        self.telemetry["gates_reordered"] += 1


class GateExecutor:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/quality")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.results: dict[str, GateResult] = {}
        self.reports: dict[str, GateReport] = {}
        self.rollback_plans: dict[str, RollbackPlan] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_results_path(self) -> Path:
        return self.storage_dir / "gate_results.json"

    def _get_reports_path(self) -> Path:
        return self.storage_dir / "gate_reports.json"

    def _get_rollback_path(self) -> Path:
        return self.storage_dir / "rollback_plans.json"

    def _save_results(self):
        path = self._get_results_path()
        try:
            data = {k: v.to_dict() for k, v in self.results.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save gate results: %s", e)

    def _save_reports(self):
        path = self._get_reports_path()
        try:
            data = {k: v.to_dict() for k, v in self.reports.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save gate reports: %s", e)

    def _save_rollback_plans(self):
        path = self._get_rollback_path()
        try:
            data = {k: v.to_dict() for k, v in self.rollback_plans.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save rollback plans: %s", e)

    def _load(self):
        try:
            path = self._get_results_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.results = {k: GateResult.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load gate results: %s", e)
        try:
            path = self._get_reports_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.reports = {k: GateReport.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load gate reports: %s", e)
        try:
            path = self._get_rollback_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.rollback_plans = {k: RollbackPlan.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load rollback plans: %s", e)

    def execute_gate(self, gate_id: str, target_type: str, target_id: str,
                     evaluated_by: str = "system",
                     eval_fn: Optional[callable] = None) -> GateResult:
        result = GateResult(
            gate_id=gate_id,
            target_type=target_type,
            target_id=target_id,
            checked_by=evaluated_by,
        )
        if eval_fn:
            try:
                start = time.time()
                outcome = eval_fn()
                duration = (time.time() - start) * 1000
                result.duration_ms = duration
                if isinstance(outcome, tuple):
                    result.status = GateStatus.PASSED if outcome[0] else GateStatus.FAILED
                    result.score = outcome[1] if len(outcome) > 1 else (1.0 if outcome[0] else 0.0)
                    if len(outcome) > 2:
                        result.details = outcome[2]
                elif isinstance(outcome, bool):
                    result.status = GateStatus.PASSED if outcome else GateStatus.FAILED
                    result.score = 1.0 if outcome else 0.0
                else:
                    result.status = GateStatus.PASSED
                    result.score = float(outcome)
                self.telemetry["gates_passed" if result.status == GateStatus.PASSED else "gates_failed"] += 1
            except Exception as e:
                result.status = GateStatus.FAILED
                result.score = 0.0
                result.details = {"error": str(e)}
                self.telemetry["gates_errored"] += 1
                logger.error("Gate %s execution failed: %s", gate_id, e)
        self.results[result.id] = result
        self._save_results()
        self.telemetry["gates_executed"] += 1
        return result

    def execute_checklist(self, checklist_id: str, target_id: str,
                          evaluated_by: str = "system",
                          eval_fns: Optional[dict[str, callable]] = None) -> GateReport:
        checklist = None
        for c in self.checklists.values() if hasattr(self, 'checklists') else []:
            if c.id == checklist_id:
                checklist = c
                break

        gate_ids = checklist.gates if checklist else []
        results = []
        passed = 0
        failed = 0

        for gate_id in gate_ids:
            eval_fn = eval_fns.get(gate_id) if eval_fns else None
            result = self.execute_gate(gate_id, "checklist", target_id, evaluated_by, eval_fn)
            results.append(result)
            if result.status == GateStatus.PASSED:
                passed += 1
            elif result.status == GateStatus.FAILED:
                failed += 1

        total = len(results)
        overall_score = round(passed / total, 4) if total else 0.0

        recommendations = []
        if failed > 0:
            recommendations.append(f"Review {failed} failed gate(s)")
        if overall_score < 0.7:
            recommendations.append("Overall quality score below threshold")

        report = GateReport(
            checklist_id=checklist_id,
            target_id=target_id,
            overall_score=overall_score,
            passed=passed,
            failed=failed,
            total=total,
            results=results,
            recommendations=recommendations,
        )
        self.reports[report.id] = report
        self._save_reports()
        self.telemetry["checklists_executed"] += 1
        return report

    def get_result(self, result_id: str) -> Optional[GateResult]:
        return self.results.get(result_id)

    def get_checklist_results(self, checklist_id: str, target_id: str) -> list[GateResult]:
        return [
            r for r in self.results.values()
            if r.target_id == target_id and r.gate_id in (
                c.gates for c in (self.checklists.values() if hasattr(self, 'checklists') else [])
                if c.id == checklist_id
            )
        ]

    def evaluate_security(self, target_type: str, target_id: str,
                          evaluated_by: str = "system",
                          security_fn: Optional[callable] = None) -> GateResult:
        for gate in (self.gates.values() if hasattr(self, 'gates') else []):
            if gate.gate_type == GateType.SECURITY_REVIEW:
                return self.execute_gate(gate.id, target_type, target_id, evaluated_by, security_fn)
        result = GateResult(
            gate_id="",
            target_type=target_type,
            target_id=target_id,
            status=GateStatus.SKIPPED,
            details={"note": "No security gate configured"},
            checked_by=evaluated_by,
        )
        self.results[result.id] = result
        self._save_results()
        return result

    def evaluate_latency(self, target_type: str, target_id: str,
                         threshold_ms: float = 5000.0,
                         evaluated_by: str = "system",
                         latency_fn: Optional[callable] = None) -> GateResult:
        for gate in (self.gates.values() if hasattr(self, 'gates') else []):
            if gate.gate_type == GateType.LATENCY:
                return self.execute_gate(gate.id, target_type, target_id, evaluated_by, latency_fn)
        result = GateResult(
            gate_id="",
            target_type=target_type,
            target_id=target_id,
            status=GateStatus.SKIPPED,
            details={"note": "No latency gate configured", "threshold_ms": threshold_ms},
            checked_by=evaluated_by,
        )
        self.results[result.id] = result
        self._save_results()
        return result

    def evaluate_cost(self, target_type: str, target_id: str,
                      budget: float = 100.0,
                      evaluated_by: str = "system",
                      cost_fn: Optional[callable] = None) -> GateResult:
        for gate in (self.gates.values() if hasattr(self, 'gates') else []):
            if gate.gate_type == GateType.COST:
                return self.execute_gate(gate.id, target_type, target_id, evaluated_by, cost_fn)
        result = GateResult(
            gate_id="",
            target_type=target_type,
            target_id=target_id,
            status=GateStatus.SKIPPED,
            details={"note": "No cost gate configured", "budget": budget},
            checked_by=evaluated_by,
        )
        self.results[result.id] = result
        self._save_results()
        return result

    def evaluate_documentation(self, target_type: str, target_id: str,
                               evaluated_by: str = "system",
                               doc_fn: Optional[callable] = None) -> GateResult:
        for gate in (self.gates.values() if hasattr(self, 'gates') else []):
            if gate.gate_type == GateType.DOCUMENTATION:
                return self.execute_gate(gate.id, target_type, target_id, evaluated_by, doc_fn)
        result = GateResult(
            gate_id="",
            target_type=target_type,
            target_id=target_id,
            status=GateStatus.SKIPPED,
            details={"note": "No documentation gate configured"},
            checked_by=evaluated_by,
        )
        self.results[result.id] = result
        self._save_results()
        return result

    def evaluate_rollback_plan(self, target_type: str, target_id: str,
                               evaluated_by: str = "system",
                               rollback_fn: Optional[callable] = None) -> GateResult:
        for gate in (self.gates.values() if hasattr(self, 'gates') else []):
            if gate.gate_type == GateType.ROLLBACK_PLAN:
                return self.execute_gate(gate.id, target_type, target_id, evaluated_by, rollback_fn)
        result = GateResult(
            gate_id="",
            target_type=target_type,
            target_id=target_id,
            status=GateStatus.SKIPPED,
            details={"note": "No rollback plan gate configured"},
            checked_by=evaluated_by,
        )
        self.results[result.id] = result
        self._save_results()
        return result

    def create_rollback_plan(self, target_type: str, target_id: str,
                             steps: Optional[list[str]] = None,
                             verification_steps: Optional[list[str]] = None,
                             estimated_duration_minutes: int = 15,
                             rollback_script: str = "") -> RollbackPlan:
        plan = RollbackPlan(
            target_type=target_type,
            target_id=target_id,
            steps=steps or [],
            verification_steps=verification_steps or [],
            estimated_duration_minutes=estimated_duration_minutes,
            rollback_script=rollback_script,
        )
        self.rollback_plans[plan.id] = plan
        self._save_rollback_plans()
        self.telemetry["rollback_plans_created"] += 1
        return plan


class QualityChecker(QualityGateManager, GateExecutor):
    def __init__(self, storage_dir: str = ""):
        QualityGateManager.__init__(self, storage_dir)
        GateExecutor.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)

    def run_quality_check(self, checklist_id: str, target_id: str,
                          evaluated_by: str = "system",
                          eval_fns: Optional[dict[str, callable]] = None) -> GateReport:
        return self.execute_checklist(checklist_id, target_id, evaluated_by, eval_fns)

    def get_quality_score(self, target_id: str) -> float:
        scores = []
        for result in self.results.values():
            if result.target_id == target_id:
                scores.append(result.score)
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    def get_gate_summary(self, target_id: Optional[str] = None) -> dict:
        results = list(self.results.values())
        if target_id:
            results = [r for r in results if r.target_id == target_id]
        total = len(results)
        by_status = defaultdict(int)
        by_type = defaultdict(int)
        for r in results:
            by_status[r.status.value] += 1
            for gate in self.gates.values():
                if gate.id == r.gate_id:
                    by_type[gate.gate_type.value] += 1
                    break
        return {
            "total_checks": total,
            "by_status": dict(by_status),
            "by_gate_type": dict(by_type),
            "overall_score": self.get_quality_score(target_id) if target_id else 0.0,
        }

    def generate_report(self, checklist_id: str, target_id: str) -> GateReport:
        report = self.execute_checklist(checklist_id, target_id)
        report.recommendations = self.suggest_improvements(target_id)
        self._save_reports()
        return report

    def suggest_improvements(self, target_id: Optional[str] = None) -> list[str]:
        suggestions = []
        results = list(self.results.values())
        if target_id:
            results = [r for r in results if r.target_id == target_id]

        failed_gates = [r for r in results if r.status == GateStatus.FAILED]
        if failed_gates:
            suggestions.append(f"Address {len(failed_gates)} failed quality gate(s)")

        low_score = [r for r in results if 0 < r.score < 0.5]
        if low_score:
            suggestions.append(f"Improve {len(low_score)} gate(s) with critically low scores")

        security_results = [r for r in results if self._is_gate_type(r.gate_id, GateType.SECURITY_REVIEW)]
        if security_results and any(r.status == GateStatus.FAILED for r in security_results):
            suggestions.append("Critical: Security review failed - immediate remediation required")

        latency_results = [r for r in results if self._is_gate_type(r.gate_id, GateType.LATENCY)]
        if latency_results and any(r.status == GateStatus.FAILED for r in latency_results):
            suggestions.append("Optimize latency to meet performance thresholds")

        cost_results = [r for r in results if self._is_gate_type(r.gate_id, GateType.COST)]
        if cost_results and any(r.status == GateStatus.FAILED for r in cost_results):
            suggestions.append("Review and optimize cost efficiency")

        if not suggestions:
            suggestions.append("All quality gates passing - maintain current standards")

        return suggestions

    def _is_gate_type(self, gate_id: str, gate_type: GateType) -> bool:
        gate = self.gates.get(gate_id)
        return gate is not None and gate.gate_type == gate_type
