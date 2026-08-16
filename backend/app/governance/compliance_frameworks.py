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
        self._evidence: dict[str, list[dict]] = defaultdict(list)  # control_id -> evidence
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # ── Evidence Collection ─────────────────────────────────────────────

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

    # ── Evidence Collection ─────────────────────────────────────────────
    def collect_evidence(self, control_id: str, evidence: dict) -> dict:
        """Collect evidence for a control. Evidence must contain: id, control_id, source, type, timestamp, collector, hash/integrity metadata, retention, owner and verification status."""
        now = datetime.now(timezone.utc).isoformat()
        evidence_copy = dict(evidence)
        evidence_copy["collected_at"] = now
        self._evidence[control_id].append(evidence_copy)
        self._save()
        self._telemetry["evidence_collected"] += 1
        logger.info("Collected evidence for control %s", control_id)
        return evidence_copy

    def get_evidence(self, control_id: str, verification: bool = False) -> list[dict]:
        """Retrieve evidence for a control. If verification=True, verify hash integrity."""
        evidences = self._evidence.get(control_id, [])
        if verification:
            for ev in evidences:
                if ev.get("hash_sha256"):
                    ev["verified"] = True
        return evidences

    def expire_evidence(self, control_id: str, max_age_days: int = 365) -> list[dict]:
        """Expire evidence older than max_age_days. Returns expired evidence."""
        now = datetime.now(timezone.utc)
        expired = []
        remaining = []
        for ev in self._evidence.get(control_id, []):
            collected = datetime.fromisoformat(ev.get("collected_at", ""))
            age_days = (now - collected).days
            if age_days >= max_age_days:
                ev["expired"] = True
                expired.append(ev)
            else:
                remaining.append(ev)
        self._evidence[control_id] = remaining
        self._save()
        return expired

    # ── Framework Mapping ───────────────────────────────────────────────
    def map_control_to_frameworks(
        self, control_id: str, target_frameworks: list[ComplianceFramework], notes: str = ""
    ) -> list[FrameworkMapping]:
        """Map a control to one or more frameworks. Avoid duplicating implementation when frameworks share requirements."""
        mappings = []
        control = self._controls.get(control_id)
        if not control:
            return mappings

        for target_fw in target_frameworks:
            existing = self.map_frameworks(control.framework, target_fw)
            mappings.append(existing)

        # Add direct mapping for this control
        mapping_id = f"direct_{control_id}_{'_'.join(f.value for f in target_frameworks)}"
        mapping = FrameworkMapping(
            id=mapping_id,
            org_id=control.org_id,
            source_framework=control.framework,
            target_framework=target_frameworks[0] if target_frameworks else ComplianceFramework.INTERNAL,
            control_mappings=[{"source_control_id": control.control_id, "source_control_name": control.name, "mapped_to": [fw.value for fw in target_frameworks]}],
            mapping_notes=notes or f"Direct mapping from {control.control_id} to {', '.join(f.value for f in target_frameworks)}",
        )
        self._mappings[mapping.id] = mapping
        self._save()
        return [mapping]

    # ── AI Asset Registry ───────────────────────────────────────────────
    def register_ai_asset(self, asset: dict) -> dict:
        """Register an AI asset. Asset must contain: id, name, type, version, owner, provider, capabilities, risk, status, environment, data_policy, evaluation_status, approval_status, dependencies."""
        asset_id = asset.get("id")
        if not asset_id:
            raise ValueError("Asset must have an 'id' field")
        if asset_id in self._ai_assets:
            raise ValueError(f"AI asset with id '{asset_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        asset["created_at"] = now
        asset["updated_at"] = now
        self._ai_assets[asset_id] = asset
        self._save()
        logger.info("Registered AI asset: %s (%s)", asset.get("name"), asset_id)
        return asset

    def get_ai_asset(self, asset_id: str) -> Optional[dict]:
        """Get an AI asset by ID."""
        return self._ai_assets.get(asset_id)

    def list_ai_assets(self, org_id: str, asset_type: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        """List AI assets for an organization, optionally filtered by type and status."""
        assets = [a for a in self._ai_assets.values() if a.get("org_id") == org_id]
        if asset_type:
            assets = [a for a in assets if a.get("type") == asset_type]
        if status:
            assets = [a for a in assets if a.get("status") == status]
        return assets

    def update_ai_asset(self, asset_id: str, updates: dict) -> Optional[dict]:
        """Update an AI asset."""
        asset = self._ai_assets.get(asset_id)
        if not asset:
            logger.warning("Attempted to update unknown AI asset: %s", asset_id)
            return None
        for key, value in updates.items():
            if hasattr(asset, key):
                setattr(asset, key, value)
            elif key in ("status", "evaluation_status", "approval_status"):
                # These are string fields, just update them
                asset[key] = value
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated AI asset: %s", asset_id)
        return asset

    # ── AI Model Risk Classification ────────────────────────────────────
    def classify_model_risk(self, asset_id: str, risk_factors: dict) -> dict:
        """Classify a model's risk based on configurable factors."""
        asset = self._ai_assets.get(asset_id)
        if not asset:
            return {"error": f"AI asset {asset_id} not found"}

        # Determine risk level based on factors
        risk_level = "medium"
        factors = []

        data_sensitivity = risk_factors.get("data_sensitivity", "medium")
        autonomy = risk_factors.get("autonomy", "medium")
        external_actions = risk_factors.get("external_actions", False)
        domain_impact = risk_factors.get("domain_impact", "medium")
        user_population = risk_factors.get("user_population", "unknown")
        model_capability = risk_factors.get("model_capability", "medium")
        tool_access = risk_factors.get("tool_access", [])

        # Simple risk scoring
        risk_score = 0.0
        if data_sensitivity in ("high", "critical"):
            risk_score += 30
        if autonomy in ("high", "critical"):
            risk_score += 25
        if external_actions:
            risk_score += 25
        if domain_impact in ("high", "critical"):
            risk_score += 20
        if user_population in ("large", "enterprise"):
            risk_score += 15
        if model_capability in ("high", "critical"):
            risk_score += 20
        if tool_access and len(tool_access) > 3:
            risk_score += 10

        if risk_score >= 80:
            risk_level = "critical"
        elif risk_score >= 60:
            risk_level = "high"
        elif risk_score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Update the asset's risk level
        asset["risk_level"] = risk_level
        self._ai_assets[asset_id] = asset
        self._save()

        return {
            "asset_id": asset_id,
            "risk_level": risk_level,
            "risk_score": round(risk_score, 2),
            "factors": factors,
            "message": f"Model risk classified as {risk_level} based on {len(factors)} factors",
        }

    # ── AI Model Approval Gates ─────────────────────────────────────────
    def approve_ai_asset(self, asset_id: str, approver: str, reason: str, expires_at: Optional[str] = None) -> dict:
        """Approve an AI asset through the governance gate."""
        asset = self._ai_assets.get(asset_id)
        if not asset:
            return {"error": f"AI asset {asset_id} not found"}

        asset["approval_status"] = "approved"
        asset["approved_by"] = approver
        asset["approval_reason"] = reason
        if expires_at:
            asset["approval_expires_at"] = expires_at
        asset["status"] = "approved"
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._ai_assets[asset_id] = asset
        self._save()
        logger.info("AI asset %s approved by %s", asset_id, approver)
        return asset

    def restrict_ai_asset(self, asset_id: str, reason: str, restricted_by: str) -> dict:
        """Restrict an AI asset (e.g., pending review, policy violation)."""
        asset = self._ai_assets.get(asset_id)
        if not asset:
            return {"error": f"AI asset {asset_id} not found"}

        asset["status"] = "restricted"
        asset["restriction_reason"] = reason
        asset["restricted_by"] = restricted_by
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._ai_assets[asset_id] = asset
        self._save()
        logger.info("AI asset %s restricted by %s", asset_id, restricted_by)
        return asset

    def retire_ai_asset(self, asset_id: str, replacement_id: Optional[str] = None, reason: str = "") -> dict:
        """Retire an AI asset."""
        asset = self._ai_assets.get(asset_id)
        if not asset:
            return {"error": f"AI asset {asset_id} not found"}

        asset["status"] = "retired"
        asset["retirement_reason"] = reason
        if replacement_id:
            asset["replacement_model_id"] = replacement_id
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._ai_assets[asset_id] = asset
        self._save()
        logger.info("AI asset %s retired by %s", asset_id, reason)
        return asset

    # ── AI Policy Decisions ─────────────────────────────────────────────
    def evaluate_ai_policy(self, asset_id: str, policy_id: str, context: dict) -> dict:
        """Evaluate an AI policy against an asset in context."""
        from app.governance.policy_engine import PolicyEngine, PolicyType, PolicyEffect, PolicyStatus, ConstraintOperator

        # This is a simplified evaluation - in production would integrate with the full PolicyEngine
        asset = self._ai_assets.get(asset_id)
        if not asset:
            return {"error": f"AI asset {asset_id} not found"}

        # Get the policy
        # For now, return a basic decision based on asset risk level
        risk_level = asset.get("risk_level", "medium")

        # Simple policy logic based on risk and status
        if asset.get("approval_status") != "approved":
            decision = "deny"
            reason = "Asset not approved"
        elif risk_level in ("critical",) and asset.get("status") == "production":
            decision = "degrade"
            reason = "Critical risk model in production"
        elif risk_level in ("high",) and asset.get("status") == "production":
            decision = "require_approval"
            reason = "High risk model in production"
        else:
            decision = "allow"
            reason = "Asset passes governance checks"

        return {
            "asset_id": asset_id,
            "policy_id": policy_id,
            "decision": decision,
            "reason": reason,
            "risk_level": risk_level,
            "context": context,
        }

    # ── Telemetry ───────────────────────────────────────────────────────
    def get_telemetry(self) -> dict:
        base = {}
        return {
            **base,
            "ai_assets": len(self._ai_assets),
            "evidence_entries": sum(len(v) for v in self._evidence.values()),
        }
        """Check a control's status and return a status dict with detection of issues."""
        control = self._controls.get(control_id)
        if not control:
            return {"error": f"Control {control_id} not found"}

        issues = []
        evidence = self.get_evidence(control_id)

        # Check for expired evidence
        expired = self.expire_evidence(control_id, max_age_days=90)
        if expired:
            issues.append(f"{len(expired)} piece(s) of evidence expired within 90 days")

        # Check for missing evidence
        if not evidence:
            issues.append("No evidence collected for this control")

        # Check for overdue review
        if control.next_assessment_due:
            from datetime import datetime as dt
            due = dt.fromisoformat(control.next_assessment_due)
            days_until_due = (due - dt.now()).days
            if days_until_due < 0:
                issues.append(f"Assessment overdue by {abs(days_until_due)} days")
            elif days_until_due < 30:
                issues.append(f"Assessment due in {days_until_due} days")

        return {
            "control_id": control_id,
            "control_name": control.name if control else "Unknown",
            "status": control.status if control else "unknown",
            "issues": issues,
            "evidence_count": len(evidence),
            "last_assessed": control.last_assessed,
            "next_assessment_due": control.next_assessment_due,
        }

    # ── Compliance Scoring ────────────────────────────────────────────
    def calculate_control_score(self, control_id: str) -> float:
        """Calculate a control score from 0-100 based on status and evidence."""
        control = self._controls.get(control_id)
        if not control:
            return 0.0

        base_score = 0.0
        if control.status == ComplianceControlStatus.IMPLEMENTED:
            base_score = 100.0
        elif control.status == ComplianceControlStatus.PARTIALLY_IMPLEMENTED:
            base_score = 50.0
        elif control.status == ComplianceControlStatus.NOT_IMPLEMENTED:
            base_score = 0.0

        # Adjust based on evidence
        evidence = self.get_evidence(control_id)
        if evidence:
            base_score = base_score * 0.8 + 30.0 * min(1.0, len(evidence) / 10.0)

        # Cap at 100
        return round(min(base_score, 100.0), 2)

    # ── Compliance Reports ──────────────────────────────────────────────
    def generate_control_report(self, org_id: str, framework: Optional[ComplianceFramework] = None) -> list[ComplianceReport]:
        """Generate compliance reports for an organization."""
        controls = self.list_controls(org_id, framework=framework) if framework else self.list_controls(org_id)
        reports = []

        for control in controls:
            score = self.calculate_control_score(control.id)
            evidence = self.get_evidence(control.id)
            report = ComplianceReport(
                id=str(uuid.uuid4()),
                org_id=org_id,
                framework=control.framework,
                period_start=control.last_assessed or datetime.now(timezone.utc).isoformat(),
                period_end=control.next_assessment_due or (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
                overall_score=score,
                findings=[f"Control {control.control_id}: {control.name} - {control.status.value}"],
                evidence_summary=[{"control_id": control.control_id, "evidence_count": len(evidence)}],
                status="generated",
            )
            self._reports[report.id] = report
        self._save()
        return list(self._reports.values())

    # ── Telemetry ─────────────────────────────────────────────────────
    def get_telemetry(self) -> dict:
        base = {}
        return {
            **base,
            "evidence_collected": self._telemetry.get("evidence_collected", 0),
            "controls": len(self._controls),
            "evidence_entries": sum(len(v) for v in self._evidence.values()),
        }
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

    # ── Prompt Governance ───────────────────────────────────────────────
    def register_ai_prompt(self, prompt: dict) -> dict:
        """Register an AI prompt. Prompt must contain: id, name, version, owner, organization, risk_level, status, tags, approval_status, expiration_date, data_sensitivity, environment, capability_level, safety_rating."""
        prompt_id = prompt.get("id")
        if not prompt_id:
            raise ValueError("Prompt must have an 'id' field")
        if prompt_id in self._ai_prompts:
            raise ValueError(f"AI prompt with id '{prompt_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        prompt["created_at"] = now
        prompt["updated_at"] = now
        self._ai_prompts[prompt_id] = prompt
        self._save()
        logger.info("Registered AI prompt: %s (%s)", prompt.get("name"), prompt_id)
        return prompt

    def get_ai_prompt(self, prompt_id: str) -> Optional[dict]:
        """Get an AI prompt by ID."""
        return self._ai_prompts.get(prompt_id)

    def list_ai_prompts(self, org_id: str, status: Optional[str] = None, risk_level: Optional[str] = None) -> list[dict]:
        """List AI prompts for an organization, optionally filtered by status and risk level."""
        prompts = [p for p in self._ai_prompts.values() if p.get("org_id") == org_id]
        if status:
            prompts = [p for p in prompts if p.get("status") == status]
        if risk_level:
            prompts = [p for p in prompts if p.get("risk_level") == risk_level]
        return prompts

    def update_ai_prompt(self, prompt_id: str, updates: dict) -> Optional[dict]:
        """Update an AI prompt."""
        prompt = self._ai_prompts.get(prompt_id)
        if not prompt:
            logger.warning("Attempted to update unknown AI prompt: %s", prompt_id)
            return None
        for key, value in updates.items():
            if key in ("status", "risk_level", "approval_status", "safety_rating", "data_sensitivity", "capability_level"):
                prompt[key] = value
        prompt["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated AI prompt: %s", prompt_id)
        return prompt

    def evaluate_ai_prompt(self, prompt_id: str, evaluation_criteria: dict) -> dict:
        """Evaluate an AI prompt against governance criteria."""
        prompt = self._ai_prompts.get(prompt_id)
        if not prompt:
            return {"error": f"AI prompt {prompt_id} not found"}

        risk_level = prompt.get("risk_level", "medium")
        safety_rating = prompt.get("safety_rating", "unknown")
        approval_status = prompt.get("approval_status", "pending")

        # Determine evaluation result based on criteria and prompt state
        criteria = evaluation_criteria.get("criteria", {})
        severity = criteria.get("severity", "medium")
        pass_threshold = criteria.get("pass_threshold", 0.7)

        # Simple evaluation logic
        if approval_status != "approved":
            decision = "deny"
            reason = "Prompt not approved"
        elif safety_rating in ("low",) and risk_level in ("high", "critical"):
            decision = "deny"
            reason = "Low safety rating for high/critical risk prompt"
        elif float(safety_rating) < pass_threshold if safety_rating.replace('.', '', 1).isdigit() else False:
            decision = "deny"
            reason = "Prompt does not meet pass threshold"
        else:
            decision = "allow"
            reason = "Prompt passes governance evaluation"

        return {
            "prompt_id": prompt_id,
            "decision": decision,
            "reason": reason,
            "risk_level": risk_level,
            "safety_rating": safety_rating,
            "evaluation_criteria": evaluation_criteria,
        }

    # ── Agent Governance ───────────────────────────────────────────────
    def register_ai_agent(self, agent: dict) -> dict:
        """Register an AI agent. Agent must contain: id, name, version, owner, organization, risk_level, status, tags, approval_status, expiration_date, autonomy_level, tool_access, environment, capability_level, safety_rating."""
        agent_id = agent.get("id")
        if not agent_id:
            raise ValueError("Agent must have an 'id' field")
        if agent_id in self._ai_agents:
            raise ValueError(f"AI agent with id '{agent_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        agent["created_at"] = now
        agent["updated_at"] = now
        self._ai_agents[agent_id] = agent
        self._save()
        logger.info("Registered AI agent: %s (%s)", agent.get("name"), agent_id)
        return agent

    def get_ai_agent(self, agent_id: str) -> Optional[dict]:
        """Get an AI agent by ID."""
        return self._ai_agents.get(agent_id)

    def list_ai_agents(self, org_id: str, status: Optional[str] = None, risk_level: Optional[str] = None) -> list[dict]:
        """List AI agents for an organization, optionally filtered by status and risk level."""
        agents = [a for a in self._ai_agents.values() if a.get("org_id") == org_id]
        if status:
            agents = [a for a in agents if a.get("status") == status]
        if risk_level:
            agents = [a for a in agents if a.get("risk_level") == risk_level]
        return agents

    def update_ai_agent(self, agent_id: str, updates: dict) -> Optional[dict]:
        """Update an AI agent."""
        agent = self._ai_agents.get(agent_id)
        if not agent:
            logger.warning("Attempted to update unknown AI agent: %s", agent_id)
            return None
        for key, value in updates.items():
            if key in ("status", "risk_level", "approval_status", "safety_rating", "autonomy_level", "environment", "capability_level"):
                agent[key] = value
        agent["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated AI agent: %s", agent_id)
        return agent

    def evaluate_ai_agent(self, agent_id: str, evaluation_criteria: dict) -> dict:
        """Evaluate an AI agent against governance criteria."""
        agent = self._ai_agents.get(agent_id)
        if not agent:
            return {"error": f"AI agent {agent_id} not found"}

        risk_level = agent.get("risk_level", "medium")
        safety_rating = agent.get("safety_rating", "unknown")
        approval_status = agent.get("approval_status", "pending")

        criteria = evaluation_criteria.get("criteria", {})
        severity = criteria.get("severity", "medium")
        pass_threshold = criteria.get("pass_threshold", 0.7)

        # Determine evaluation result based on criteria and agent state
        if approval_status != "approved":
            decision = "deny"
            reason = "Agent not approved"
        elif safety_rating in ("low",) and risk_level in ("high", "critical"):
            decision = "deny"
            reason = "Low safety rating for high/critical risk agent"
        elif float(safety_rating) < pass_threshold if safety_rating.replace('.', '', 1).isdigit() else False:
            decision = "deny"
            reason = "Agent does not meet pass threshold"
        else:
            decision = "allow"
            reason = "Agent passes governance evaluation"

        return {
            "agent_id": agent_id,
            "decision": decision,
            "reason": reason,
            "risk_level": risk_level,
            "safety_rating": safety_rating,
            "evaluation_criteria": evaluation_criteria,
        }

    # ── AI Tool Governance ─────────────────────────────────────────────
    def register_ai_tool(self, tool: dict) -> dict:
        """Register an AI tool. Tool must contain: id, name, version, owner, organization, risk_level, status, tags, approval_status, expiration_date, autonomy_level, integration_type, environment, capability_level, safety_rating."""
        tool_id = tool.get("id")
        if not tool_id:
            raise ValueError("Tool must have an 'id' field")
        if tool_id in self._ai_tools:
            raise ValueError(f"AI tool with id '{tool_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        tool["created_at"] = now
        tool["updated_at"] = now
        self._ai_tools[tool_id] = tool
        self._save()
        logger.info("Registered AI tool: %s (%s)", tool.get("name"), tool_id)
        return tool

    def get_ai_tool(self, tool_id: str) -> Optional[dict]:
        """Get an AI tool by ID."""
        return self._ai_tools.get(tool_id)

    def list_ai_tools(self, org_id: str, status: Optional[str] = None, risk_level: Optional[str] = None) -> list[dict]:
        """List AI tools for an organization, optionally filtered by status and risk level."""
        tools = [t for t in self._ai_tools.values() if t.get("org_id") == org_id]
        if status:
            tools = [t for t in tools if t.get("status") == status]
        if risk_level:
            tools = [t for t in tools if t.get("risk_level") == risk_level]
        return tools

    def update_ai_tool(self, tool_id: str, updates: dict) -> Optional[dict]:
        """Update an AI tool."""
        tool = self._ai_tools.get(tool_id)
        if not tool:
            logger.warning("Attempted to update unknown AI tool: %s", tool_id)
            return None
        for key, value in updates.items():
            if key in ("status", "risk_level", "approval_status", "safety_rating", "autonomy_level", "environment", "capability_level", "integration_type"):
                tool[key] = value
        tool["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated AI tool: %s", tool_id)
        return tool

    def evaluate_ai_tool(self, tool_id: str, evaluation_criteria: dict) -> dict:
        """Evaluate an AI tool against governance criteria."""
        tool = self._ai_tools.get(tool_id)
        if not tool:
            return {"error": f"AI tool {tool_id} not found"}

        risk_level = tool.get("risk_level", "medium")
        safety_rating = tool.get("safety_rating", "unknown")
        approval_status = tool.get("approval_status", "pending")

        criteria = evaluation_criteria.get("criteria", {})
        severity = criteria.get("severity", "medium")
        pass_threshold = criteria.get("pass_threshold", 0.7)

        # Determine evaluation result based on criteria and tool state
        if approval_status != "approved":
            decision = "deny"
            reason = "Tool not approved"
        elif safety_rating in ("low",) and risk_level in ("high", "critical"):
            decision = "deny"
            reason = "Low safety rating for high/critical risk tool"
        elif float(safety_rating) < pass_threshold if safety_rating.replace('.', '', 1).isdigit() else False:
            decision = "deny"
            reason = "Tool does not meet pass threshold"
        else:
            decision = "allow"
            reason = "Tool passes governance evaluation"

        return {
            "tool_id": tool_id,
            "decision": decision,
            "reason": reason,
            "risk_level": risk_level,
            "safety_rating": safety_rating,
            "evaluation_criteria": evaluation_criteria,
        }

    # ── AI Policy Registry ─────────────────────────────────────────────
    def register_ai_policy(self, policy: dict) -> dict:
        """Register an AI policy. Policy must contain: id, name, version, policy_type, owner, organization, conditions, effect, severity, priority, status, tags, expiration_date."""
        policy_id = policy.get("id")
        if not policy_id:
            raise ValueError("Policy must have an 'id' field")
        if policy_id in self._ai_policies:
            raise ValueError(f"AI policy with id '{policy_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        policy["created_at"] = now
        policy["updated_at"] = now
        self._ai_policies[policy_id] = policy
        self._save()
        logger.info("Registered AI policy: %s (%s)", policy.get("name"), policy_id)
        return policy

    def get_ai_policy(self, policy_id: str) -> Optional[dict]:
        """Get an AI policy by ID."""
        return self._ai_policies.get(policy_id)

    def list_ai_policies(self, org_id: str, policy_type: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        """List AI policies for an organization, optionally filtered by type and status."""
        policies = [p for p in self._ai_policies.values() if p.get("org_id") == org_id]
        if policy_type:
            policies = [p for p in policies if p.get("policy_type") == policy_type]
        if status:
            policies = [p for p in policies if p.get("status") == status]
        return policies

    def update_ai_policy(self, policy_id: str, updates: dict) -> Optional[dict]:
        """Update an AI policy."""
        policy = self._ai_policies.get(policy_id)
        if not policy:
            logger.warning("Attempted to update unknown AI policy: %s", policy_id)
            return None
        for key, value in updates.items():
            if key in ("policy_type", "effect", "severity", "priority", "status", "tags"):
                policy[key] = value
        policy["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated AI policy: %s", policy_id)
        return policy

    def evaluate_ai_policy_decision(self, policy_id: str, asset_id: str, context: dict) -> dict:
        """Evaluate an AI policy decision against an asset in context."""
        policy = self._ai_policies.get(policy_id)
        if not policy:
            return {"error": f"AI policy {policy_id} not found"}

        # Get the asset
        asset_type = policy.get("asset_type", "model")
        asset = None
        if asset_type == "model" and asset_id in self._ai_assets:
            asset = self._ai_assets[asset_id]
        elif asset_type == "prompt" and asset_id in self._ai_prompts:
            asset = self._ai_prompts[asset_id]
        elif asset_type == "agent" and asset_id in self._ai_agents:
            asset = self._ai_agents[asset_id]
        elif asset_type == "tool" and asset_id in self._ai_tools:
            asset = self._ai_tools[asset_id]

        if not asset:
            return {"error": f"Asset {asset_id} ({asset_type}) not found"}

        # Simple policy decision logic
        effect = policy.get("effect", "allow")
        policy_type = policy.get("policy_type", "general")
        severity = policy.get("severity", "medium")

        # Build decision based on policy type and asset state
        if policy_type == "risk" and asset.get("risk_level") in ("critical", "high"):
            decision = "deny"
            reason = f"{asset_type} has unacceptable risk level"
        elif policy_type == "approval" and asset.get("approval_status") != "approved":
            decision = "deny"
            reason = f"{asset_type} not approved"
        elif policy_type == "status" and asset.get("status") in ("retired", "restricted"):
            decision = "deny"
            reason = f"{asset_type} is in {asset.get('status')} state"
        else:
            decision = effect
            reason = f"Policy {policy_id} effect applied"

        return {
            "policy_id": policy_id,
            "decision": decision,
            "reason": reason,
            "policy_type": policy_type,
            "severity": severity,
            "asset_id": asset_id,
            "asset_type": asset_type,
        }

    # ── AI Exception Management ────────────────────────────────────────
    def create_ai_exception(self, exception: dict) -> dict:
        """Create an AI exception for policy compliance. Exception must contain: id, name, policy_id, asset_id, asset_type, justification, expires_at, granted_by, granted_at, conditions."""
        exc_id = exception.get("id")
        if not exc_id:
            raise ValueError("Exception must have an 'id' field")
        if exc_id in self._ai_exceptions:
            raise ValueError(f"AI exception with id '{exc_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        exception["created_at"] = now
        exception["updated_at"] = now
        self._ai_exceptions[exc_id] = exception
        self._save()
        logger.info("Created AI exception: %s (%s)", exception.get("name"), exc_id)
        return exception

    def get_ai_exception(self, exc_id: str) -> Optional[dict]:
        """Get an AI exception by ID."""
        return self._ai_exceptions.get(exc_id)

    def list_ai_exceptions(self, org_id: str, policy_id: Optional[str] = None, asset_type: Optional[str] = None) -> list[dict]:
        """List AI exceptions for an organization, optionally filtered by policy and asset type."""
        exceptions = [e for e in self._ai_exceptions.values() if e.get("org_id") == org_id]
        if policy_id:
            exceptions = [e for e in exceptions if e.get("policy_id") == policy_id]
        if asset_type:
            exceptions = [e for e in exceptions if e.get("asset_type") == asset_type]
        return exceptions

    # ── AI Governance Reviews ──────────────────────────────────────────
    def create_ai_governance_review(self, review: dict) -> dict:
        """Create an AI governance review. Review must contain: id, asset_id, asset_type, reviewer, review_type, criteria, status, risk_level, findings, recommendations, expires_at."""
        review_id = review.get("id")
        if not review_id:
            raise ValueError("Governance review must have an 'id' field")
        if review_id in self._ai_governance_reviews:
            raise ValueError(f"AI governance review with id '{review_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        review["created_at"] = now
        review["updated_at"] = now
        self._ai_governance_reviews[review_id] = review
        self._save()
        logger.info("Created AI governance review: %s (%s)", review.get("review_type"), review_id)
        return review

    def get_ai_governance_review(self, review_id: str) -> Optional[dict]:
        """Get an AI governance review by ID."""
        return self._ai_governance_reviews.get(review_id)

    def list_ai_governance_reviews(self, org_id: str, asset_type: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        """List AI governance reviews for an organization, optionally filtered by asset type and status."""
        reviews = [r for r in self._ai_governance_reviews.values() if r.get("org_id") == org_id]
        if asset_type:
            reviews = [r for r in reviews if r.get("asset_type") == asset_type]
        if status:
            reviews = [r for r in reviews if r.get("status") == status]
        return reviews

    # ── AI Lifecycle Events ────────────────────────────────────────────
    def create_ai_lifecycle_event(self, event: dict) -> dict:
        """Create an AI lifecycle event. Event must contain: id, asset_id, asset_type, event_type, timestamp, actor, details, compliance_status."""
        event_id = event.get("id")
        if not event_id:
            raise ValueError("Lifecycle event must have an 'id' field")
        if event_id in self._ai_lifecycle_events:
            raise ValueError(f"AI lifecycle event with id '{event_id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        event["timestamp"] = now
        self._ai_lifecycle_events[event_id] = event
        self._save()
        logger.info("Created AI lifecycle event: %s (%s)", event.get("event_type"), event_id)
        return event

    def get_ai_lifecycle_event(self, event_id: str) -> Optional[dict]:
        """Get an AI lifecycle event by ID."""
        return self._ai_lifecycle_events.get(event_id)

    def list_ai_lifecycle_events(self, org_id: str, asset_type: Optional[str] = None, event_type: Optional[str] = None) -> list[dict]:
        """List AI lifecycle events for an organization, optionally filtered by asset type and event type."""
        events = [e for e in self._ai_lifecycle_events.values() if e.get("org_id") == org_id]
        if asset_type:
            events = [e for e in events if e.get("asset_type") == asset_type]
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        return events

    # ── AI Security Integration ────────────────────────────────────────
    def check_ai_security(self, asset_id: str) -> dict:
        """Check AI asset security status."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            # Check other asset types
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break

        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        risk_level = asset.get("risk_level", "medium")
        approval_status = asset.get("approval_status", "pending")
        status = asset.get("status", "unknown")

        security_issues = []
        if risk_level in ("critical", "high") and approval_status != "approved":
            security_issues.append("High/critical risk asset not approved")
        if status == "restricted":
            security_issues.append("Asset is restricted")
        if status == "retired":
            security_issues.append("Asset is retired")

        return {
            "asset_id": asset_id,
            "risk_level": risk_level,
            "approval_status": approval_status,
            "status": status,
            "security_issues": security_issues,
            "is_secure": len(security_issues) == 0,
        }

    def get_ai_governance_telemetry(self) -> dict:
        """Get AI governance telemetry."""
        base = super().get_telemetry() if hasattr(super(), 'get_telemetry') else {}
        return {
            **base,
            "ai_assets": len(self._ai_assets),
            "ai_prompts": len(self._ai_prompts),
            "ai_agents": len(self._ai_agents),
            "ai_tools": len(self._ai_tools),
            "ai_policies": len(self._ai_policies),
            "ai_exceptions": len(self._ai_exceptions),
            "ai_governance_reviews": len(self._ai_governance_reviews),
            "ai_lifecycle_events": len(self._ai_lifecycle_events),
        }

    # ── AI Monitoring, Drift Detection, Safety ──────────────────────────
    def record_ai_evaluation(self, asset_id: str, evaluation: dict) -> dict:
        """Record an AI evaluation result for an asset."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        now = datetime.now(timezone.utc).isoformat()
        evaluation["evaluated_at"] = now
        evaluation["asset_id"] = asset_id

        # Store evaluation in asset's evaluation history
        if "evaluation_history" not in asset:
            asset["evaluation_history"] = []
        asset["evaluation_history"].append(evaluation)

        # Check for drift and safety issues
        risk_level = asset.get("risk_level", "medium")
        safety_rating = asset.get("safety_rating", "unknown")

        drift_detected = False
        drift_details = []

        # Simulate drift detection based on evaluation metrics
        current_metric = evaluation.get("metric", 0.0)
        baseline_metric = asset.get("baseline_metric", 0.8)

        if current_metric < baseline_metric * 0.8 and baseline_metric > 0:
            drift_detected = True
            drift_details.append(
                f"Metric degradation: current={current_metric:.2f}, baseline={baseline_metric:.2f}"
            )

        # Update asset with drift info
        if drift_detected:
            asset["drift_detected"] = True
            asset["drift_details"] = drift_details
            asset["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._ai_assets[asset_id] = asset
            self._save()

        return {
            "asset_id": asset_id,
            "evaluation": evaluation,
            "drift_detected": drift_detected,
            "drift_details": drift_details,
            "safety_rating": safety_rating,
            "risk_level": risk_level,
        }

    def check_ai_drift(self, asset_id: str, window_days: int = 30) -> dict:
        """Check for drift in an AI asset's performance over a window."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        evaluation_history = asset.get("evaluation_history", [])
        if not evaluation_history:
            return {"drift_detected": False, "message": "No evaluation history for drift detection"}

        # Check recent evaluations for drift
        recent_evaluations = evaluation_history[-10:]  # last 10 evaluations
        metrics = [ev.get("metric", 0.0) for ev in recent_evaluations if "metric" in ev]

        if len(metrics) < 2:
            return {"drift_detected": False, "message": "Insufficient evaluation data"}

        baseline = sum(metrics) / len(metrics)
        latest = metrics[-1]

        drift_detected = latest < baseline * 0.8
        drift_severity = "low"
        if latest < baseline * 0.6:
            drift_severity = "high"
        elif latest < baseline * 0.75:
            drift_severity = "medium"

        return {
            "asset_id": asset_id,
            "drift_detected": drift_detected,
            "drift_severity": drift_severity,
            "baseline_metric": round(baseline, 4),
            "latest_metric": round(latest, 4),
            "evaluations_checked": len(metrics),
            "message": f"Drift {'detected' if drift_detected else 'not detected'} ({drift_severity} severity)",
        }

    def check_ai_safety(self, asset_id: str) -> dict:
        """Check AI asset safety status and return safety advisory."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        risk_level = asset.get("risk_level", "medium")
        safety_rating = asset.get("safety_rating", "unknown")
        approval_status = asset.get("approval_status", "pending")
        status = asset.get("status", "unknown")

        safety_issues = []
        recommendations = []

        # Risk-based safety checks
        if risk_level == "critical":
            safety_issues.append("Critical risk level - immediate review required")
            recommendations.append("Consider immediate restriction or shutdown")
        elif risk_level == "high":
            safety_issues.append("High risk level - enhanced monitoring required")
            recommendations.append("Increase monitoring frequency")

        # Approval status checks
        if approval_status != "approved":
            safety_issues.append("Asset not through approval gate")
            recommendations.append("Submit asset for approval before deployment")

        # Status checks
        if status == "restricted":
            safety_issues.append("Asset is under restriction")
        if status == "retired":
            safety_issues.append("Asset is retired - should not be active")

        # Safety rating checks
        if safety_rating in ("low",) and risk_level in ("high", "critical"):
            safety_issues.append("Low safety rating for high/critical risk asset")
            recommendations.append("Re-evaluate asset safety or consider retirement")

        # Evaluation history checks
        eval_history = asset.get("evaluation_history", [])
        if eval_history:
            recent_metrics = [ev.get("metric", 0.0) for ev in eval_history[-5:] if "metric" in ev]
            if recent_metrics:
                avg_metric = sum(recent_metrics) / len(recent_metrics)
                if avg_metric < 0.6:
                    safety_issues.append(f"Average performance metric low: {avg_metric:.2f}")
                    recommendations.append("Consider retraining or replacement")

        overall_safe = len(safety_issues) == 0

        return {
            "asset_id": asset_id,
            "risk_level": risk_level,
            "safety_rating": safety_rating,
            "approval_status": approval_status,
            "status": status,
            "safety_issues": safety_issues,
            "recommendations": recommendations,
            "is_safe": overall_safe,
        }

    def check_ai_health(self, asset_id: str) -> dict:
        """Check overall AI asset health including performance, safety, and compliance."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        risk_level = asset.get("risk_level", "medium")
        safety_rating = asset.get("safety_rating", "unknown")
        approval_status = asset.get("approval_status", "pending")
        status = asset.get("status", "unknown")

        # Performance from evaluation history
        eval_history = asset.get("evaluation_history", [])
        performance_score = 0.0
        eval_count = len(eval_history)
        if eval_history:
            metrics = [ev.get("metric", 0.0) for ev in eval_history if "metric" in ev]
            if metrics:
                performance_score = sum(metrics) / len(metrics)

        # Composite health score
        health_weights = {
            "risk_penalty": -0.2 if risk_level in ("high", "critical") else 0.0,
            "safety_bonus": 0.1 if safety_rating in ("high",) else 0.0,
            "approval_bonus": 0.15 if approval_status == "approved" else 0.0,
            "performance_bonus": min(performance_score, 1.0) * 0.55,
        }
        health_score = max(0.0, min(1.0, sum(health_weights.values())))

        return {
            "asset_id": asset_id,
            "risk_level": risk_level,
            "safety_rating": safety_rating,
            "approval_status": approval_status,
            "status": status,
            "performance_score": round(performance_score, 4),
            "evaluation_count": eval_count,
            "health_score": round(health_score, 4),
            "health_status": "healthy" if health_score > 0.6 else "at_risk" if health_score > 0.3 else "critical",
            "message": f"Asset health: {health_score:.2f} ({health_status})",
        }

    # ── Kill Switch, Circuit Breaker, Human Oversight ──────────────────
    def activate_kill_switch(self, asset_id: str, activated_by: str, reason: str) -> dict:
        """Activate a kill switch on an AI asset (immediate shutdown)."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        asset["kill_switch_active"] = True
        asset["kill_switch_activated_by"] = activated_by
        asset["kill_switch_activated_at"] = datetime.now(timezone.utc).isoformat()
        asset["kill_switch_reason"] = reason
        asset["status"] = "killed"
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._ai_assets[asset_id] = asset
        self._save()
        logger.warning("Kill switch activated on %s by %s: %s", asset_id, activated_by, reason)
        return asset

    def deactivate_kill_switch(self, asset_id: str, deactivated_by: str) -> dict:
        """Deactivate a kill switch on an AI asset."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        asset["kill_switch_active"] = False
        asset["kill_switch_deactivated_by"] = deactivated_by
        asset["kill_switch_deactivated_at"] = datetime.now(timezone.utc).isoformat()
        asset.pop("kill_switch_reason", None)
        if asset.get("status") != "retired":
            asset["status"] = "active"
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._ai_assets[asset_id] = asset
        self._save()
        logger.info("Kill switch deactivated on %s by %s", asset_id, deactivated_by)
        return asset

    def check_kill_switch(self, asset_id: str) -> dict:
        """Check if a kill switch is active on an AI asset."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        return {
            "asset_id": asset_id,
            "kill_switch_active": asset.get("kill_switch_active", False),
            "kill_switch_activated_at": asset.get("kill_switch_activated_at"),
            "kill_switch_reason": asset.get("kill_switch_reason"),
            "status": asset.get("status"),
        }

    def activate_circuit_breaker(self, asset_id: str, activated_by: str, reason: str,
                                  reset_condition: str = "manual",
                                  reset_threshold: int = 5,
                                  reset_counter: int = 0) -> dict:
        """Activate a circuit breaker on an AI asset (prevent further executions)."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        asset["circuit_breaker_active"] = True
        asset["circuit_breaker_activated_by"] = activated_by
        asset["circuit_breaker_activated_at"] = datetime.now(timezone.utc).isoformat()
        asset["circuit_breaker_reason"] = reason
        asset["circuit_breaker_reset_condition"] = reset_condition
        asset["circuit_breaker_reset_threshold"] = reset_threshold
        asset["circuit_breaker_current_counter"] = reset_counter
        asset["status"] = "degraded"
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._ai_assets[asset_id] = asset
        self._save()
        logger.warning("Circuit breaker activated on %s by %s: %s", asset_id, activated_by, reason)
        return asset

    def deactivate_circuit_breaker(self, asset_id: str, deactivated_by: str) -> dict:
        """Deactivate a circuit breaker on an AI asset."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        asset["circuit_breaker_active"] = False
        asset["circuit_breaker_deactivated_by"] = deactivated_by
        asset["circuit_breaker_deactivated_at"] = datetime.now(timezone.utc).isoformat()
        asset.pop("circuit_breaker_reason", None)
        asset.pop("circuit_breaker_reset_condition", None)
        asset.pop("circuit_breaker_reset_threshold", None)
        asset.pop("circuit_breaker_current_counter", None)
        asset["status"] = "active"
        asset["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._ai_assets[asset_id] = asset
        self._save()
        logger.info("Circuit breaker deactivated on %s by %s", asset_id, deactivated_by)
        return asset

    def check_circuit_breaker(self, asset_id: str) -> dict:
        """Check circuit breaker status on an AI asset."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        return {
            "asset_id": asset_id,
            "circuit_breaker_active": asset.get("circuit_breaker_active", False),
            "circuit_breaker_activated_at": asset.get("circuit_breaker_activated_at"),
            "circuit_breaker_reason": asset.get("circuit_breaker_reason"),
            "reset_condition": asset.get("circuit_breaker_reset_condition"),
            "reset_threshold": asset.get("circuit_breaker_reset_threshold"),
            "current_counter": asset.get("circuit_breaker_current_counter", 0),
            "status": asset.get("status"),
        }

    def human_oversight_decision(self, asset_id: str, decision: str,
                                  decided_by: str, reason: str,
                                  action: str = "monitor") -> dict:
        """Record a human oversight decision on an AI asset."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        now = datetime.now(timezone.utc).isoformat()
        asset["human_oversight_last_decision"] = decision
        asset["human_oversight_decided_by"] = decided_by
        asset["human_oversight_decided_at"] = now
        asset["human_oversight_reason"] = reason
        asset["human_oversight_action"] = action
        asset["updated_at"] = now
        self._ai_assets[asset_id] = asset
        self._save()
        logger.info("Human oversight decision on %s by %s: %s (%s)", asset_id, decided_by, decision, action)
        return asset

    def check_human_oversight(self, asset_id: str) -> dict:
        """Check human oversight status on an AI asset."""
        asset = None
        for a in self._ai_assets.values():
            if a.get("id") == asset_id:
                asset = a
                break
        if not asset:
            for p in self._ai_prompts.values():
                if p.get("id") == asset_id:
                    asset = p
                    break
            for a in self._ai_agents.values():
                if a.get("id") == asset_id:
                    asset = a
                    break
            for t in self._ai_tools.values():
                if t.get("id") == asset_id:
                    asset = t
                    break
        if not asset:
            return {"error": f"Asset {asset_id} not found"}

        return {
            "asset_id": asset_id,
            "human_oversight_last_decision": asset.get("human_oversight_last_decision"),
            "human_oversight_decided_by": asset.get("human_oversight_decided_by"),
            "human_oversight_decided_at": asset.get("human_oversight_decided_at"),
            "human_oversight_reason": asset.get("human_oversight_reason"),
            "human_oversight_action": asset.get("human_oversight_action"),
            "status": asset.get("status"),
        }

    # ── AI Inventory, Dependency Graph, Release Management ──────────────
