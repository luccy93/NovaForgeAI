"""Research Quality — every experiment must include hypothesis, dataset, methodology, metrics, evaluation, comparison, report, versioning, rollback, documentation, tests."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class QualityCheckType(Enum):
    HYPOTHESIS = "hypothesis"
    DATASET = "dataset"
    METHODOLOGY = "methodology"
    METRICS = "metrics"
    EVALUATION = "evaluation"
    COMPARISON = "comparison"
    REPORT = "report"
    VERSIONING = "versioning"
    ROLLBACK = "rollback"
    DOCUMENTATION = "documentation"
    TESTS = "tests"
    REPRODUCIBILITY = "reproducibility"


@dataclass
class QualityChecklist:
    id: str
    org_id: str
    name: str
    description: str = ""
    required_checks: list = field(default_factory=list)
    optional_checks: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "QualityChecklist": return cls(**data)


@dataclass
class QualityCheckResult:
    id: str
    experiment_id: str
    checklist_id: str
    check_type: QualityCheckType
    check_name: str
    passed: bool = False
    score: float = 0.0
    details: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["check_type"] = self.check_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityCheckResult":
        data = data.copy()
        data["check_type"] = QualityCheckType(data.get("check_type", "hypothesis"))
        return cls(**data)


@dataclass
class QualityReport:
    id: str
    experiment_id: str
    overall_score: float = 0.0
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    checks: list = field(default_factory=list)
    passed: bool = False
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "QualityReport": return cls(**data)


class ResearchQuality:
    def __init__(self, storage_dir: str = "research_data/quality"):
        self.storage_dir = storage_dir
        self._checklists: dict[str, QualityChecklist] = {}
        self._check_results: dict[str, QualityCheckResult] = {}
        self._reports: dict[str, QualityReport] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _checklists_path(self) -> str: return os.path.join(self.storage_dir, "checklists.json")
    def _results_path(self) -> str: return os.path.join(self.storage_dir, "check_results.json")
    def _reports_path(self) -> str: return os.path.join(self.storage_dir, "quality_reports.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._checklists_path(), self._checklists, QualityChecklist),
            (self._results_path(), self._check_results, QualityCheckResult),
            (self._reports_path(), self._reports, QualityReport),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load quality data: %s", e)

    def _save(self) -> None:
        try:
            for path, store in [
                (self._checklists_path(), self._checklists),
                (self._results_path(), self._check_results),
                (self._reports_path(), self._reports),
            ]:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({k: v.to_dict() for k, v in store.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save quality data: %s", e)

    def create_checklist(self, name: str, org_id: str, description: str = "", required_checks: list = None, optional_checks: list = None) -> QualityChecklist:
        cl = QualityChecklist(id=str(uuid.uuid4()), org_id=org_id, name=name, description=description, required_checks=required_checks or [], optional_checks=optional_checks or [])
        self._checklists[cl.id] = cl
        self._save()
        return cl

    def get_checklist(self, cl_id: str) -> Optional[QualityChecklist]: return self._checklists.get(cl_id)

    def run_quality_check(self, experiment_id: str, check_type: QualityCheckType, check_name: str, passed: bool, score: float = 0.0, details: str = "") -> QualityCheckResult:
        result = QualityCheckResult(id=str(uuid.uuid4()), experiment_id=experiment_id, checklist_id="", check_type=check_type, check_name=check_name, passed=passed, score=score, details=details)
        self._check_results[result.id] = result
        self._save()
        return result

    def generate_quality_report(self, experiment_id: str) -> QualityReport:
        checks = [r for r in self._check_results.values() if r.experiment_id == experiment_id]
        total = len(checks)
        passed = sum(1 for c in checks if c.passed)
        failed = total - passed
        overall = round(passed / max(total, 1), 4)
        report = QualityReport(
            id=str(uuid.uuid4()), experiment_id=experiment_id,
            overall_score=overall, total_checks=total,
            passed_checks=passed, failed_checks=failed,
            checks=[c.to_dict() for c in checks],
            passed=overall >= 0.8,
        )
        self._reports[report.id] = report
        self._save()
        return report

    def get_report(self, report_id: str) -> Optional[QualityReport]: return self._reports.get(report_id)

    def list_reports(self, experiment_id: str = "") -> list[QualityReport]:
        results = list(self._reports.values())
        if experiment_id: results = [r for r in results if r.experiment_id == experiment_id]
        return sorted(results, key=lambda r: r.generated_at, reverse=True)

    def validate_experiment_readiness(self, experiment_id: str, checklist_id: str) -> dict:
        cl = self._checklists.get(checklist_id)
        if not cl: return {"ready": False, "reason": "Checklist not found"}
        checks = [r for r in self._check_results.values() if r.experiment_id == experiment_id]
        required_passed = all(
            any(c.check_name == req and c.passed for c in checks)
            for req in cl.required_checks
        )
        return {
            "ready": required_passed,
            "required_total": len(cl.required_checks),
            "required_passed": len([req for req in cl.required_checks if any(c.check_name == req and c.passed for c in checks)]),
            "checks_completed": len(checks),
        }

    def get_telemetry(self) -> dict: return dict(self._telemetry)
