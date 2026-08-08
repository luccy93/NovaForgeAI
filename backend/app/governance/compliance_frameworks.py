import json
import uuid
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class ComplianceFramework(Enum):
    SOC2 = "soc2"
    ISO_27001 = "iso_27001"
    GDPR = "gdpr"
    CCPA = "ccpa"
    HIPAA_READY = "hipaa_ready"
    NIST = "nist"
    OWASP = "owasp"
    INTERNAL = "internal"
    CUSTOM = "custom"


class ComplianceControlStatus(Enum):
    IMPLEMENTED = "implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    NOT_IMPLEMENTED = "not_implemented"
    NOT_APPLICABLE = "not_applicable"
    IN_REVIEW = "in_review"
    EXEMPTED = "exempted"


class ComplianceSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EvidenceType(Enum):
    DOCUMENT = "document"
    LOG = "log"
    CONFIGURATION = "configuration"
    TEST_RESULT = "test_result"
    SCAN_RESULT = "scan_result"
    CERTIFICATION = "certification"
    POLICY = "policy"
    TRAINING_RECORD = "training_record"


@dataclass
class ComplianceControl:
    id: str
    org_id: str
    framework: ComplianceFramework
    control_id: str
    name: str
    description: str = ""
    category: str = ""
    severity: ComplianceSeverity = ComplianceSeverity.MEDIUM
    status: ComplianceControlStatus = ComplianceControlStatus.NOT_IMPLEMENTED
    owner: str = ""
    implementation_details: str = ""
    last_assessed: Optional[str] = None
    next_assessment_due: Optional[str] = None
    evidence: list[dict] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["framework"] = self.framework.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ComplianceControl":
        data["framework"] = ComplianceFramework(data["framework"])
        data["severity"] = ComplianceSeverity(data["severity"])
        data["status"] = ComplianceControlStatus(data["status"])
        return cls(**data)


@dataclass
class ComplianceAssessment:
    id: str
    org_id: str
    framework: ComplianceFramework
    assessor: str
    assessment_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    score: float = 0.0
    total_controls: int = 0
    implemented_controls: int = 0
    partial_controls: int = 0
    missing_controls: int = 0
    na_controls: int = 0
    controls_summary: list[dict] = field(default_factory=list)
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    overall_status: ComplianceControlStatus = ComplianceControlStatus.NOT_IMPLEMENTED
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["framework"] = self.framework.value
        d["overall_status"] = self.overall_status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ComplianceAssessment":
        data["framework"] = ComplianceFramework(data["framework"])
        data["overall_status"] = ComplianceControlStatus(data["overall_status"])
        return cls(**data)


@dataclass
class ComplianceRequirement:
    id: str
    framework: ComplianceFramework
    requirement_id: str
    title: str
    description: str = ""
    category: str = ""
    mandatory: bool = True
    controls_required: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["framework"] = self.framework.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ComplianceRequirement":
        data["framework"] = ComplianceFramework(data["framework"])
        return cls(**data)


@dataclass
class ComplianceReport:
    id: str
    org_id: str
    framework: ComplianceFramework
    period_start: str
    period_end: str
    overall_score: float = 0.0
    by_category: dict = field(default_factory=dict)
    by_severity: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    evidence_summary: list = field(default_factory=list)
    status: str = "draft"
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["framework"] = self.framework.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ComplianceReport":
        data["framework"] = ComplianceFramework(data["framework"])
        return cls(**data)


@dataclass
class FrameworkMapping:
    id: str
    org_id: str
    source_framework: ComplianceFramework
    target_framework: ComplianceFramework
    control_mappings: list[dict] = field(default_factory=list)
    mapping_notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_framework"] = self.source_framework.value
        d["target_framework"] = self.target_framework.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FrameworkMapping":
        data["source_framework"] = ComplianceFramework(data["source_framework"])
        data["target_framework"] = ComplianceFramework(data["target_framework"])
        return cls(**data)


class ComplianceManager:
    def __init__(self, storage_dir: str = "compliance_data"):
        self.storage_dir = storage_dir
        self._controls: dict[str, ComplianceControl] = {}
        self._assessments: dict[str, ComplianceAssessment] = {}
        self._requirements: dict[str, ComplianceRequirement] = {}
        self._reports: dict[str, ComplianceReport] = {}
        self._mappings: dict[str, FrameworkMapping] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _controls_path(self) -> str:
        return os.path.join(self.storage_dir, "controls.json")

    def _assessments_path(self) -> str:
        return os.path.join(self.storage_dir, "assessments.json")

    def _requirements_path(self) -> str:
        return os.path.join(self.storage_dir, "requirements.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "reports.json")

    def _mappings_path(self) -> str:
        return os.path.join(self.storage_dir, "mappings.json")

    def _save(self) -> None:
        try:
            controls_data = {cid: c.to_dict() for cid, c in self._controls.items()}
            with open(self._controls_path(), "w", encoding="utf-8") as f:
                json.dump(controls_data, f, indent=2, default=str)

            assessments_data = {aid: a.to_dict() for aid, a in self._assessments.items()}
            with open(self._assessments_path(), "w", encoding="utf-8") as f:
                json.dump(assessments_data, f, indent=2, default=str)

            requirements_data = {rid: r.to_dict() for rid, r in self._requirements.items()}
            with open(self._requirements_path(), "w", encoding="utf-8") as f:
                json.dump(requirements_data, f, indent=2, default=str)

            reports_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)

            mappings_data = {mid: m.to_dict() for mid, m in self._mappings.items()}
            with open(self._mappings_path(), "w", encoding="utf-8") as f:
                json.dump(mappings_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save compliance data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._controls_path()):
                with open(self._controls_path(), "r", encoding="utf-8") as f:
                    controls_data = json.load(f)
                for cid, data in controls_data.items():
                    try:
                        self._controls[cid] = ComplianceControl.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed control %s: %s", cid, e)

            if os.path.exists(self._assessments_path()):
                with open(self._assessments_path(), "r", encoding="utf-8") as f:
                    assessments_data = json.load(f)
                for aid, data in assessments_data.items():
                    try:
                        self._assessments[aid] = ComplianceAssessment.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed assessment %s: %s", aid, e)

            if os.path.exists(self._requirements_path()):
                with open(self._requirements_path(), "r", encoding="utf-8") as f:
                    requirements_data = json.load(f)
                for rid, data in requirements_data.items():
                    try:
                        self._requirements[rid] = ComplianceRequirement.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed requirement %s: %s", rid, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, data in reports_data.items():
                    try:
                        self._reports[rid] = ComplianceReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)

            if os.path.exists(self._mappings_path()):
                with open(self._mappings_path(), "r", encoding="utf-8") as f:
                    mappings_data = json.load(f)
                for mid, data in mappings_data.items():
                    try:
                        self._mappings[mid] = FrameworkMapping.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed mapping %s: %s", mid, e)
        except Exception as e:
            logger.error("Failed to load compliance data: %s", e, exc_info=True)

    def register_control(self, control: ComplianceControl) -> ComplianceControl:
        self._telemetry["register_control_calls"] += 1
        if control.id in self._controls:
            raise ValueError(f"Control with id '{control.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        control.created_at = now
        control.updated_at = now
        self._controls[control.id] = control
        self._save()
        logger.info("Registered control: %s (%s)", control.name, control.id)
        return control

    def get_control(self, control_id: str) -> Optional[ComplianceControl]:
        self._telemetry["get_control_calls"] += 1
        return self._controls.get(control_id)

    def update_control(self, control_id: str, updates: dict) -> Optional[ComplianceControl]:
        self._telemetry["update_control_calls"] += 1
        control = self._controls.get(control_id)
        if not control:
            logger.warning("Attempted to update unknown control: %s", control_id)
            return None
        for key, value in updates.items():
            if hasattr(control, key) and key not in ("id", "org_id", "created_at"):
                if key == "framework":
                    setattr(control, key, ComplianceFramework(value) if isinstance(value, str) else value)
                elif key == "severity":
                    setattr(control, key, ComplianceSeverity(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(control, key, ComplianceControlStatus(value) if isinstance(value, str) else value)
                else:
                    setattr(control, key, value)
        control.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated control: %s", control_id)
        return control

    def list_controls(self, org_id: str, framework: Optional[ComplianceFramework] = None, status: Optional[ComplianceControlStatus] = None) -> list[ComplianceControl]:
        self._telemetry["list_controls_calls"] += 1
        results = [c for c in self._controls.values() if c.org_id == org_id]
        if framework:
            results = [c for c in results if c.framework == framework]
        if status:
            results = [c for c in results if c.status == status]
        return results

    def run_assessment(self, org_id: str, framework: ComplianceFramework, assessor: str) -> ComplianceAssessment:
        self._telemetry["run_assessment_calls"] += 1
        controls = [c for c in self._controls.values() if c.org_id == org_id and c.framework == framework]
        total = len(controls)
        implemented = sum(1 for c in controls if c.status == ComplianceControlStatus.IMPLEMENTED)
        partial = sum(1 for c in controls if c.status == ComplianceControlStatus.PARTIALLY_IMPLEMENTED)
        missing = sum(1 for c in controls if c.status == ComplianceControlStatus.NOT_IMPLEMENTED)
        na = sum(1 for c in controls if c.status == ComplianceControlStatus.NOT_APPLICABLE)
        score = (implemented + (partial * 0.5)) / total * 100 if total > 0 else 0.0

        if score >= 90:
            overall = ComplianceControlStatus.IMPLEMENTED
        elif score >= 50:
            overall = ComplianceControlStatus.PARTIALLY_IMPLEMENTED
        else:
            overall = ComplianceControlStatus.NOT_IMPLEMENTED

        controls_summary = [c.to_dict() for c in controls]
        findings = []
        recommendations = []
        for c in controls:
            if c.status == ComplianceControlStatus.NOT_IMPLEMENTED:
                findings.append(f"Control '{c.control_id}' ({c.name}) is not implemented")
                recommendations.append(f"Implement control '{c.control_id}' - {c.name}")
            elif c.status == ComplianceControlStatus.PARTIALLY_IMPLEMENTED:
                findings.append(f"Control '{c.control_id}' ({c.name}) is partially implemented")
                recommendations.append(f"Complete implementation of control '{c.control_id}' - {c.name}")

        assessment = ComplianceAssessment(
            id=str(uuid.uuid4()),
            org_id=org_id,
            framework=framework,
            assessor=assessor,
            score=round(score, 2),
            total_controls=total,
            implemented_controls=implemented,
            partial_controls=partial,
            missing_controls=missing,
            na_controls=na,
            controls_summary=controls_summary,
            findings=findings,
            recommendations=recommendations,
            overall_status=overall,
        )
        self._assessments[assessment.id] = assessment
        self._save()
        logger.info("Ran assessment for org %s / %s: score=%.2f", org_id, framework.value, score)
        return assessment

    def get_assessment_history(self, org_id: str, framework: Optional[ComplianceFramework] = None) -> list[ComplianceAssessment]:
        self._telemetry["get_assessment_history_calls"] += 1
        results = [a for a in self._assessments.values() if a.org_id == org_id]
        if framework:
            results = [a for a in results if a.framework == framework]
        return sorted(results, key=lambda a: a.assessment_date, reverse=True)

    def generate_compliance_report(self, org_id: str, framework: ComplianceFramework, start_date: str, end_date: str) -> ComplianceReport:
        self._telemetry["generate_compliance_report_calls"] += 1
        controls = [c for c in self._controls.values() if c.org_id == org_id and c.framework == framework]
        assessments = [a for a in self._assessments.values() if a.org_id == org_id and a.framework == framework]
        latest = max(assessments, key=lambda a: a.assessment_date) if assessments else None

        by_category = defaultdict(lambda: {"total": 0, "implemented": 0, "score": 0.0})
        for c in controls:
            by_category[c.category]["total"] += 1
            if c.status == ComplianceControlStatus.IMPLEMENTED:
                by_category[c.category]["implemented"] += 1
        for cat in by_category:
            t = by_category[cat]["total"]
            imp = by_category[cat]["implemented"]
            by_category[cat]["score"] = round((imp / t * 100) if t > 0 else 0.0, 2)

        by_severity = defaultdict(lambda: {"total": 0, "implemented": 0})
        for c in controls:
            by_severity[c.severity.value]["total"] += 1
            if c.status == ComplianceControlStatus.IMPLEMENTED:
                by_severity[c.severity.value]["implemented"] += 1

        findings = []
        recommendations = []
        evidence_summary = []
        for c in controls:
            if c.status == ComplianceControlStatus.NOT_IMPLEMENTED:
                findings.append(f"Missing control: {c.control_id} - {c.name}")
                recommendations.append(f"Implement {c.control_id} ({c.name}) before next audit")
            if c.evidence:
                evidence_summary.append({
                    "control_id": c.control_id,
                    "evidence_count": len(c.evidence),
                    "last_assessed": c.last_assessed,
                })

        overall_score = latest.score if latest else 0.0
        report = ComplianceReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            framework=framework,
            period_start=start_date,
            period_end=end_date,
            overall_score=overall_score,
            by_category=dict(by_category),
            by_severity=dict(by_severity),
            findings=findings,
            recommendations=recommendations,
            evidence_summary=evidence_summary,
            status="generated",
        )
        self._reports[report.id] = report
        self._save()
        logger.info("Generated compliance report for org %s / %s", org_id, framework.value)
        return report

    def map_frameworks(self, source: ComplianceFramework, target: ComplianceFramework) -> FrameworkMapping:
        self._telemetry["map_frameworks_calls"] += 1
        key = f"{source.value}_to_{target.value}"
        existing = next((m for m in self._mappings.values() if m.source_framework == source and m.target_framework == target), None)
        if existing:
            return existing

        controls_summary = []
        for ctrl in self._controls.values():
            if ctrl.framework == source:
                controls_summary.append({
                    "source_control_id": ctrl.control_id,
                    "source_control_name": ctrl.name,
                    "mapped_to": [],
                })

        mapping = FrameworkMapping(
            id=str(uuid.uuid4()),
            org_id="",
            source_framework=source,
            target_framework=target,
            control_mappings=controls_summary,
            mapping_notes=f"Auto-generated mapping from {source.value} to {target.value}",
        )
        self._mappings[mapping.id] = mapping
        self._save()
        logger.info("Created framework mapping: %s -> %s", source.value, target.value)
        return mapping

    def get_compliance_score(self, org_id: str, framework: ComplianceFramework) -> float:
        self._telemetry["get_compliance_score_calls"] += 1
        controls = [c for c in self._controls.values() if c.org_id == org_id and c.framework == framework]
        total = len(controls)
        if total == 0:
            return 0.0
        implemented = sum(1 for c in controls if c.status == ComplianceControlStatus.IMPLEMENTED)
        partial = sum(1 for c in controls if c.status == ComplianceControlStatus.PARTIALLY_IMPLEMENTED)
        return round((implemented + (partial * 0.5)) / total * 100, 2)

    def get_missing_controls(self, org_id: str, framework: ComplianceFramework) -> list[ComplianceControl]:
        self._telemetry["get_missing_controls_calls"] += 1
        return [c for c in self._controls.values() if c.org_id == org_id and c.framework == framework and c.status == ComplianceControlStatus.NOT_IMPLEMENTED]

    def get_compliance_summary(self, org_id: str) -> dict:
        self._telemetry["get_compliance_summary_calls"] += 1
        scores = {}
        for framework in ComplianceFramework:
            score = self.get_compliance_score(org_id, framework)
            if score > 0 or any(c.org_id == org_id and c.framework == framework for c in self._controls.values()):
                scores[framework.value] = score
        return {
            "org_id": org_id,
            "scores_by_framework": scores,
            "average_score": round(sum(scores.values()) / len(scores), 2) if scores else 0.0,
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
