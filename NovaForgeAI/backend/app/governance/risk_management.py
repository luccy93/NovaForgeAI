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


class RiskCategory(Enum):
    REPOSITORY = "repository"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    AI = "ai"
    THIRD_PARTY = "third_party"
    OPERATIONAL = "operational"
    COMPLIANCE = "compliance"
    DATA = "data"
    INFRASTRUCTURE = "infrastructure"
    FINANCIAL = "financial"


class RiskLevel(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


class RiskTrend(Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    WORSENING = "worsening"
    UNKNOWN = "unknown"


class MitigationStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    WAIVED = "waived"
    EXPIRED = "expired"


@dataclass
class RiskFactor:
    id: str
    org_id: str
    category: RiskCategory
    name: str
    description: str = ""
    weight: float = 1.0
    current_score: float = 0.0
    baseline_score: float = 0.0
    target_score: float = 0.0
    trend: RiskTrend = RiskTrend.UNKNOWN
    last_assessed: Optional[str] = None
    owner: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["trend"] = self.trend.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RiskFactor":
        data["category"] = RiskCategory(data["category"])
        data["trend"] = RiskTrend(data["trend"])
        return cls(**data)


@dataclass
class RiskAssessment:
    id: str
    org_id: str
    assessor: str
    assessment_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_score: float = 0.0
    by_category: dict[RiskCategory, float] = field(default_factory=dict)
    by_severity: dict[RiskLevel, int] = field(default_factory=dict)
    top_risks: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    next_assessment_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["by_category"] = {k.value if isinstance(k, RiskCategory) else k: v for k, v in self.by_category.items()}
        d["by_severity"] = {k.value if isinstance(k, RiskLevel) else k: v for k, v in self.by_severity.items()}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RiskAssessment":
        data["by_category"] = {RiskCategory(k) if isinstance(k, str) else k: v for k, v in data.get("by_category", {}).items()}
        data["by_severity"] = {RiskLevel(k) if isinstance(k, str) else k: v for k, v in data.get("by_severity", {}).items()}
        return cls(**data)


@dataclass
class RiskMitigation:
    id: str
    risk_factor_id: str
    title: str
    description: str = ""
    action_plan: str = ""
    owner: str = ""
    status: MitigationStatus = MitigationStatus.NOT_STARTED
    target_date: Optional[str] = None
    completed_at: Optional[str] = None
    effectiveness_score: float = 0.0
    cost: float = 0.0
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RiskMitigation":
        data["status"] = MitigationStatus(data["status"])
        return cls(**data)


@dataclass
class RiskReport:
    id: str
    org_id: str
    period_start: str
    period_end: str
    overall_risk_score: float = 0.0
    overall_compliance_score: float = 0.0
    risk_distribution: dict = field(default_factory=dict)
    top_risks: list = field(default_factory=list)
    mitigations_in_progress: int = 0
    mitigations_completed: int = 0
    trend_analysis: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RiskReport":
        return cls(**data)


@dataclass
class RiskScorecard:
    id: str
    org_id: str
    repository_risk: float = 0.0
    deployment_risk: float = 0.0
    security_risk: float = 0.0
    ai_risk: float = 0.0
    third_party_risk: float = 0.0
    operational_risk: float = 0.0
    overall_risk: float = 0.0
    compliance_score: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RiskScorecard":
        return cls(**data)


class RiskManager:
    def __init__(self, storage_dir: str = "risk_management_data"):
        self.storage_dir = storage_dir
        self._risk_factors: dict[str, RiskFactor] = {}
        self._assessments: dict[str, RiskAssessment] = {}
        self._mitigations: dict[str, RiskMitigation] = {}
        self._reports: dict[str, RiskReport] = {}
        self._scorecards: dict[str, RiskScorecard] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _factors_path(self) -> str:
        return os.path.join(self.storage_dir, "risk_factors.json")

    def _assessments_path(self) -> str:
        return os.path.join(self.storage_dir, "assessments.json")

    def _mitigations_path(self) -> str:
        return os.path.join(self.storage_dir, "mitigations.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "reports.json")

    def _scorecards_path(self) -> str:
        return os.path.join(self.storage_dir, "scorecards.json")

    def _save(self) -> None:
        try:
            factors_data = {fid: f.to_dict() for fid, f in self._risk_factors.items()}
            with open(self._factors_path(), "w", encoding="utf-8") as f:
                json.dump(factors_data, f, indent=2, default=str)

            assessments_data = {aid: a.to_dict() for aid, a in self._assessments.items()}
            with open(self._assessments_path(), "w", encoding="utf-8") as f:
                json.dump(assessments_data, f, indent=2, default=str)

            mitigations_data = {mid: m.to_dict() for mid, m in self._mitigations.items()}
            with open(self._mitigations_path(), "w", encoding="utf-8") as f:
                json.dump(mitigations_data, f, indent=2, default=str)

            reports_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)

            scorecards_data = {sid: s.to_dict() for sid, s in self._scorecards.items()}
            with open(self._scorecards_path(), "w", encoding="utf-8") as f:
                json.dump(scorecards_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save risk management data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._factors_path()):
                with open(self._factors_path(), "r", encoding="utf-8") as f:
                    factors_data = json.load(f)
                for fid, data in factors_data.items():
                    try:
                        self._risk_factors[fid] = RiskFactor.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed risk factor %s: %s", fid, e)

            if os.path.exists(self._assessments_path()):
                with open(self._assessments_path(), "r", encoding="utf-8") as f:
                    assessments_data = json.load(f)
                for aid, data in assessments_data.items():
                    try:
                        self._assessments[aid] = RiskAssessment.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed assessment %s: %s", aid, e)

            if os.path.exists(self._mitigations_path()):
                with open(self._mitigations_path(), "r", encoding="utf-8") as f:
                    mitigations_data = json.load(f)
                for mid, data in mitigations_data.items():
                    try:
                        self._mitigations[mid] = RiskMitigation.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed mitigation %s: %s", mid, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, data in reports_data.items():
                    try:
                        self._reports[rid] = RiskReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)

            if os.path.exists(self._scorecards_path()):
                with open(self._scorecards_path(), "r", encoding="utf-8") as f:
                    scorecards_data = json.load(f)
                for sid, data in scorecards_data.items():
                    try:
                        self._scorecards[sid] = RiskScorecard.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed scorecard %s: %s", sid, e)
        except Exception as e:
            logger.error("Failed to load risk management data: %s", e, exc_info=True)

    def register_risk_factor(self, factor: RiskFactor) -> RiskFactor:
        self._telemetry["register_risk_factor_calls"] += 1
        if factor.id in self._risk_factors:
            raise ValueError(f"Risk factor with id '{factor.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        factor.created_at = now
        factor.updated_at = now
        self._risk_factors[factor.id] = factor
        self._save()
        logger.info("Registered risk factor: %s (%s)", factor.name, factor.id)
        return factor

    def update_risk_factor(self, factor_id: str, updates: dict) -> Optional[RiskFactor]:
        self._telemetry["update_risk_factor_calls"] += 1
        factor = self._risk_factors.get(factor_id)
        if not factor:
            logger.warning("Attempted to update unknown risk factor: %s", factor_id)
            return None
        for key, value in updates.items():
            if hasattr(factor, key) and key not in ("id", "org_id", "created_at"):
                if key == "category":
                    setattr(factor, key, RiskCategory(value) if isinstance(value, str) else value)
                elif key == "trend":
                    setattr(factor, key, RiskTrend(value) if isinstance(value, str) else value)
                else:
                    setattr(factor, key, value)
        factor.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated risk factor: %s", factor_id)
        return factor

    def list_risk_factors(self, org_id: str, category: Optional[RiskCategory] = None) -> list[RiskFactor]:
        self._telemetry["list_risk_factors_calls"] += 1
        results = [f for f in self._risk_factors.values() if f.org_id == org_id]
        if category:
            results = [f for f in results if f.category == category]
        return results

    def run_risk_assessment(self, org_id: str, assessor: str) -> RiskAssessment:
        self._telemetry["run_risk_assessment_calls"] += 1
        factors = [f for f in self._risk_factors.values() if f.org_id == org_id]
        if not factors:
            raise ValueError(f"No risk factors found for org '{org_id}'.")

        by_category: dict[RiskCategory, list[float]] = defaultdict(list)
        by_severity: dict[RiskLevel, int] = defaultdict(int)
        total_weighted = 0.0
        total_weight = 0.0
        findings = []
        recommendations = []
        top_risks = []

        for f in factors:
            by_category[f.category].append(f.current_score)
            total_weighted += f.current_score * f.weight
            total_weight += f.weight

            if f.current_score >= 80:
                level = RiskLevel.CRITICAL
            elif f.current_score >= 60:
                level = RiskLevel.HIGH
            elif f.current_score >= 40:
                level = RiskLevel.MEDIUM
            elif f.current_score >= 20:
                level = RiskLevel.LOW
            else:
                level = RiskLevel.NEGLIGIBLE
            by_severity[level] += 1

            if f.current_score >= 60:
                top_risks.append({
                    "factor_id": f.id,
                    "name": f.name,
                    "category": f.category.value,
                    "score": f.current_score,
                    "trend": f.trend.value,
                })
                findings.append(f"High risk factor '{f.name}' ({f.category.value}): score={f.current_score}")
                recommendations.append(f"Review and mitigate '{f.name}' — current score {f.current_score} exceeds threshold")

        overall_score = round(total_weighted / total_weight, 2) if total_weight > 0 else 0.0
        by_category_scores = {cat: round(sum(scores) / len(scores), 2) for cat, scores in by_category.items()}
        top_risks.sort(key=lambda r: r["score"], reverse=True)

        next_date = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()

        assessment = RiskAssessment(
            id=str(uuid.uuid4()),
            org_id=org_id,
            assessor=assessor,
            overall_score=overall_score,
            by_category=by_category_scores,
            by_severity=dict(by_severity),
            top_risks=top_risks[:10],
            findings=findings,
            recommendations=recommendations,
            next_assessment_date=next_date,
        )
        self._assessments[assessment.id] = assessment
        self._save()
        logger.info("Ran risk assessment for org %s: score=%.2f", org_id, overall_score)
        return assessment

    def get_risk_assessment_history(self, org_id: str) -> list[RiskAssessment]:
        self._telemetry["get_risk_assessment_history_calls"] += 1
        results = [a for a in self._assessments.values() if a.org_id == org_id]
        return sorted(results, key=lambda a: a.assessment_date, reverse=True)

    def create_mitigation(self, mitigation: RiskMitigation) -> RiskMitigation:
        self._telemetry["create_mitigation_calls"] += 1
        if mitigation.id in self._mitigations:
            raise ValueError(f"Mitigation with id '{mitigation.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        mitigation.created_at = now
        mitigation.updated_at = now
        self._mitigations[mitigation.id] = mitigation
        self._save()
        logger.info("Created mitigation: %s (%s)", mitigation.title, mitigation.id)
        return mitigation

    def update_mitigation(self, mitigation_id: str, updates: dict) -> Optional[RiskMitigation]:
        self._telemetry["update_mitigation_calls"] += 1
        mitigation = self._mitigations.get(mitigation_id)
        if not mitigation:
            logger.warning("Attempted to update unknown mitigation: %s", mitigation_id)
            return None
        for key, value in updates.items():
            if hasattr(mitigation, key) and key not in ("id", "risk_factor_id", "created_at"):
                if key == "status":
                    setattr(mitigation, key, MitigationStatus(value) if isinstance(value, str) else value)
                else:
                    setattr(mitigation, key, value)
        mitigation.updated_at = datetime.now(timezone.utc).isoformat()
        if mitigation.status == MitigationStatus.COMPLETED and not mitigation.completed_at:
            mitigation.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated mitigation: %s", mitigation_id)
        return mitigation

    def list_mitigations(self, risk_factor_id: Optional[str] = None, status: Optional[MitigationStatus] = None) -> list[RiskMitigation]:
        self._telemetry["list_mitigations_calls"] += 1
        results = list(self._mitigations.values())
        if risk_factor_id:
            results = [m for m in results if m.risk_factor_id == risk_factor_id]
        if status:
            results = [m for m in results if m.status == status]
        return results

    def calculate_risk_score(self, org_id: str) -> float:
        self._telemetry["calculate_risk_score_calls"] += 1
        factors = [f for f in self._risk_factors.values() if f.org_id == org_id]
        if not factors:
            return 0.0
        total_weighted = sum(f.current_score * f.weight for f in factors)
        total_weight = sum(f.weight for f in factors)
        return round(total_weighted / total_weight, 2) if total_weight > 0 else 0.0

    def _category_risk_score(self, org_id: str, category: RiskCategory) -> float:
        factors = [f for f in self._risk_factors.values() if f.org_id == org_id and f.category == category]
        if not factors:
            return 0.0
        total_weighted = sum(f.current_score * f.weight for f in factors)
        total_weight = sum(f.weight for f in factors)
        return round(total_weighted / total_weight, 2) if total_weight > 0 else 0.0

    def calculate_repository_risk(self, org_id: str) -> float:
        self._telemetry["calculate_repository_risk_calls"] += 1
        return self._category_risk_score(org_id, RiskCategory.REPOSITORY)

    def calculate_deployment_risk(self, org_id: str) -> float:
        self._telemetry["calculate_deployment_risk_calls"] += 1
        return self._category_risk_score(org_id, RiskCategory.DEPLOYMENT)

    def calculate_security_risk(self, org_id: str) -> float:
        self._telemetry["calculate_security_risk_calls"] += 1
        return self._category_risk_score(org_id, RiskCategory.SECURITY)

    def calculate_ai_risk(self, org_id: str) -> float:
        self._telemetry["calculate_ai_risk_calls"] += 1
        return self._category_risk_score(org_id, RiskCategory.AI)

    def get_risk_scorecard(self, org_id: str) -> RiskScorecard:
        self._telemetry["get_risk_scorecard_calls"] += 1
        existing = next((s for s in self._scorecards.values() if s.org_id == org_id), None)
        if existing:
            return existing

        scorecard = RiskScorecard(
            id=str(uuid.uuid4()),
            org_id=org_id,
            repository_risk=self.calculate_repository_risk(org_id),
            deployment_risk=self.calculate_deployment_risk(org_id),
            security_risk=self.calculate_security_risk(org_id),
            ai_risk=self.calculate_ai_risk(org_id),
            third_party_risk=self._category_risk_score(org_id, RiskCategory.THIRD_PARTY),
            operational_risk=self._category_risk_score(org_id, RiskCategory.OPERATIONAL),
            overall_risk=self.calculate_risk_score(org_id),
            compliance_score=self._category_risk_score(org_id, RiskCategory.COMPLIANCE),
        )
        self._scorecards[scorecard.id] = scorecard
        self._save()
        return scorecard

    def generate_risk_report(self, org_id: str, start_date: str, end_date: str) -> RiskReport:
        self._telemetry["generate_risk_report_calls"] += 1
        factors = [f for f in self._risk_factors.values() if f.org_id == org_id]
        assessments = [a for a in self._assessments.values() if a.org_id == org_id]
        mitigations = list(self._mitigations.values())

        overall_risk_score = self.calculate_risk_score(org_id)

        risk_distribution: dict[str, int] = defaultdict(int)
        for f in factors:
            if f.current_score >= 60:
                risk_distribution["high"] += 1
            elif f.current_score >= 40:
                risk_distribution["medium"] += 1
            elif f.current_score >= 20:
                risk_distribution["low"] += 1
            else:
                risk_distribution["negligible"] += 1

        top_risks = sorted(
            [{"id": f.id, "name": f.name, "category": f.category.value, "score": f.current_score, "trend": f.trend.value}
             for f in factors if f.current_score >= 40],
            key=lambda r: r["score"], reverse=True
        )[:10]

        mitigations_in_progress = sum(1 for m in mitigations if m.status in (MitigationStatus.IN_PROGRESS, MitigationStatus.NOT_STARTED))
        mitigations_completed = sum(1 for m in mitigations if m.status in (MitigationStatus.COMPLETED, MitigationStatus.VERIFIED))

        trend_analysis = {}
        if assessments:
            sorted_assessments = sorted(assessments, key=lambda a: a.assessment_date)
            scores_over_time = [{"date": a.assessment_date, "score": a.overall_score} for a in sorted_assessments]
            trend_analysis["score_trend"] = scores_over_time
            if len(scores_over_time) >= 2:
                first = scores_over_time[0]["score"]
                last = scores_over_time[-1]["score"]
                trend_analysis["direction"] = "improving" if last < first else "worsening" if last > first else "stable"
                trend_analysis["change"] = round(last - first, 2)
            else:
                trend_analysis["direction"] = "unknown"
                trend_analysis["change"] = 0.0

        recommendations = []
        for f in factors:
            if f.current_score >= 60:
                recommendations.append(f"Prioritize mitigation for '{f.name}' ({f.category.value}) — score {f.current_score}")
        if mitigations_in_progress > 0:
            recommendations.append(f"{mitigations_in_progress} mitigations still in progress — review and accelerate")

        report = RiskReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            overall_risk_score=overall_risk_score,
            overall_compliance_score=self._category_risk_score(org_id, RiskCategory.COMPLIANCE),
            risk_distribution=dict(risk_distribution),
            top_risks=top_risks,
            mitigations_in_progress=mitigations_in_progress,
            mitigations_completed=mitigations_completed,
            trend_analysis=trend_analysis,
            recommendations=recommendations,
        )
        self._reports[report.id] = report
        self._save()
        logger.info("Generated risk report for org %s", org_id)
        return report

    def get_risk_trend(self, org_id: str, months: int = 6) -> list[dict]:
        self._telemetry["get_risk_trend_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
        assessments = [
            a for a in self._assessments.values()
            if a.org_id == org_id and a.assessment_date >= cutoff.isoformat()
        ]
        assessments.sort(key=lambda a: a.assessment_date)

        trend_data = []
        for a in assessments:
            trend_data.append({
                "date": a.assessment_date,
                "overall_score": a.overall_score,
                "by_category": {k.value if isinstance(k, RiskCategory) else k: v for k, v in a.by_category.items()},
            })
        return trend_data

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
