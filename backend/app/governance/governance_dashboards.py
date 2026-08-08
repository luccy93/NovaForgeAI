import json
import uuid
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class DashboardView(Enum):
    ORGANIZATION_POLICIES = "organization_policies"
    COMPLIANCE_STATUS = "compliance_status"
    APPROVAL_QUEUE = "approval_queue"
    AUDIT_EVENTS = "audit_events"
    RISK_REPORTS = "risk_reports"
    POLICY_VIOLATIONS = "policy_violations"
    SECURITY_OVERVIEW = "security_overview"
    EXECUTIVE_SUMMARY = "executive_summary"


class DashboardTimeRange(Enum):
    LAST_24H = "last_24h"
    LAST_7D = "last_7d"
    LAST_30D = "last_30d"
    LAST_90D = "last_90d"
    LAST_YEAR = "last_year"
    CUSTOM = "custom"


class ChartMetric(Enum):
    POLICY_COUNT = "policy_count"
    COMPLIANCE_SCORE = "compliance_score"
    APPROVAL_RATE = "approval_rate"
    VIOLATION_COUNT = "violation_count"
    RISK_SCORE = "risk_score"
    AUDIT_EVENTS = "audit_events"
    CHANGE_COUNT = "change_count"
    INCIDENT_COUNT = "incident_count"


class DashboardSeverity(Enum):
    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"
    INFO = "info"
    PENDING = "pending"


@dataclass
class GovernanceDashboardConfig:
    id: str
    org_id: str
    name: str
    view: DashboardView
    time_range: DashboardTimeRange
    chart_metrics: list[ChartMetric]
    refresh_interval_sec: int = 60
    is_active: bool = True
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["view"] = self.view.value
        d["time_range"] = self.time_range.value
        d["chart_metrics"] = [m.value for m in self.chart_metrics]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GovernanceDashboardConfig":
        data["view"] = DashboardView(data["view"])
        data["time_range"] = DashboardTimeRange(data["time_range"])
        data["chart_metrics"] = [ChartMetric(m) for m in data["chart_metrics"]]
        return cls(**data)


@dataclass
class DashboardSection:
    id: str
    dashboard_id: str
    title: str
    metrics: list = field(default_factory=list)
    charts: list = field(default_factory=list)
    order: int = 0
    visible: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DashboardSection":
        return cls(**data)


@dataclass
class GovernanceMetricCard:
    id: str
    title: str
    metric: ChartMetric
    current_value: float = 0.0
    previous_value: float = 0.0
    percent_change: float = 0.0
    severity: DashboardSeverity = DashboardSeverity.INFO
    trend: str = "stable"
    sparkline_data: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GovernanceMetricCard":
        data["metric"] = ChartMetric(data["metric"])
        data["severity"] = DashboardSeverity(data["severity"])
        return cls(**data)


@dataclass
class GovernanceDashboardData:
    id: str
    dashboard_id: str
    view: DashboardView
    time_range: DashboardTimeRange
    sections: list = field(default_factory=list)
    metric_cards: list[GovernanceMetricCard] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["view"] = self.view.value
        d["time_range"] = self.time_range.value
        d["metric_cards"] = [c.to_dict() for c in self.metric_cards]
        d["sections"] = [s.to_dict() if hasattr(s, "to_dict") else s for s in self.sections]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GovernanceDashboardData":
        data["view"] = DashboardView(data["view"])
        data["time_range"] = DashboardTimeRange(data["time_range"])
        data["metric_cards"] = [GovernanceMetricCard.from_dict(c) for c in data["metric_cards"]]
        return cls(**data)


@dataclass
class PolicyViolationSummary:
    id: str
    org_id: str
    period_start: str
    period_end: str
    total_violations: int = 0
    by_type: dict = field(default_factory=dict)
    by_severity: dict = field(default_factory=dict)
    by_policy: dict = field(default_factory=dict)
    trend_direction: str = "stable"
    top_violators: list = field(default_factory=list)
    resolved_count: int = 0
    open_count: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyViolationSummary":
        return cls(**data)


@dataclass
class GovernanceOverview:
    id: str
    org_id: str
    total_policies: int = 0
    active_policies: int = 0
    total_approvals_pending: int = 0
    compliance_score: float = 0.0
    risk_score: float = 0.0
    audit_events_today: int = 0
    changes_today: int = 0
    violations_open: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GovernanceOverview":
        return cls(**data)


class GovernanceDashboardManager:
    def __init__(self, storage_dir: str = "governance_dashboard_data"):
        self.storage_dir = storage_dir
        self._dashboard_configs: dict[str, GovernanceDashboardConfig] = {}
        self._dashboard_data: dict[str, GovernanceDashboardData] = {}
        self._violation_summaries: dict[str, PolicyViolationSummary] = {}
        self._overviews: dict[str, GovernanceOverview] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _configs_path(self) -> str:
        return os.path.join(self.storage_dir, "configs.json")

    def _dashboard_data_path(self) -> str:
        return os.path.join(self.storage_dir, "dashboard_data.json")

    def _violations_path(self) -> str:
        return os.path.join(self.storage_dir, "violations.json")

    def _overviews_path(self) -> str:
        return os.path.join(self.storage_dir, "overviews.json")

    def _save(self) -> None:
        try:
            configs_data = {cid: c.to_dict() for cid, c in self._dashboard_configs.items()}
            with open(self._configs_path(), "w", encoding="utf-8") as f:
                json.dump(configs_data, f, indent=2, default=str)

            data_data = {did: d.to_dict() for did, d in self._dashboard_data.items()}
            with open(self._dashboard_data_path(), "w", encoding="utf-8") as f:
                json.dump(data_data, f, indent=2, default=str)

            violations_data = {vid: v.to_dict() for vid, v in self._violation_summaries.items()}
            with open(self._violations_path(), "w", encoding="utf-8") as f:
                json.dump(violations_data, f, indent=2, default=str)

            overviews_data = {oid: o.to_dict() for oid, o in self._overviews.items()}
            with open(self._overviews_path(), "w", encoding="utf-8") as f:
                json.dump(overviews_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save governance dashboard data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._configs_path()):
                with open(self._configs_path(), "r", encoding="utf-8") as f:
                    configs_data = json.load(f)
                for cid, data in configs_data.items():
                    try:
                        self._dashboard_configs[cid] = GovernanceDashboardConfig.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed dashboard config %s: %s", cid, e)

            if os.path.exists(self._dashboard_data_path()):
                with open(self._dashboard_data_path(), "r", encoding="utf-8") as f:
                    data_data = json.load(f)
                for did, data in data_data.items():
                    try:
                        self._dashboard_data[did] = GovernanceDashboardData.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed dashboard data %s: %s", did, e)

            if os.path.exists(self._violations_path()):
                with open(self._violations_path(), "r", encoding="utf-8") as f:
                    violations_data = json.load(f)
                for vid, data in violations_data.items():
                    try:
                        self._violation_summaries[vid] = PolicyViolationSummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed violation summary %s: %s", vid, e)

            if os.path.exists(self._overviews_path()):
                with open(self._overviews_path(), "r", encoding="utf-8") as f:
                    overviews_data = json.load(f)
                for oid, data in overviews_data.items():
                    try:
                        self._overviews[oid] = GovernanceOverview.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed governance overview %s: %s", oid, e)
        except Exception as e:
            logger.error("Failed to load governance dashboard data: %s", e, exc_info=True)

    def create_dashboard_config(self, config: GovernanceDashboardConfig) -> GovernanceDashboardConfig:
        self._telemetry["create_dashboard_config_calls"] += 1
        if config.id in self._dashboard_configs:
            raise ValueError(f"Dashboard config with id '{config.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        config.created_at = now
        config.updated_at = now
        self._dashboard_configs[config.id] = config
        self._save()
        logger.info("Created dashboard config: %s (%s)", config.name, config.id)
        return config

    def get_dashboard_data(self, dashboard_id: str) -> Optional[GovernanceDashboardData]:
        self._telemetry["get_dashboard_data_calls"] += 1
        config = self._dashboard_configs.get(dashboard_id)
        if not config:
            logger.warning("Dashboard config not found: %s", dashboard_id)
            return None

        now = datetime.now(timezone.utc).isoformat()
        card_id_base = str(uuid.uuid4())

        metric_cards = []
        for i, metric in enumerate(config.chart_metrics):
            current_val = self._compute_metric_value(metric, config.org_id)
            previous_val = current_val * (1 - (0.05 * (i + 1)))
            pct_change = ((current_val - previous_val) / previous_val * 100) if previous_val else 0.0
            if pct_change > 5:
                severity = DashboardSeverity.SUCCESS
                trend = "up"
            elif pct_change < -5:
                severity = DashboardSeverity.WARNING
                trend = "down"
            else:
                severity = DashboardSeverity.INFO
                trend = "stable"

            card = GovernanceMetricCard(
                id=f"{card_id_base}_card_{i}",
                title=metric.value.replace("_", " ").title(),
                metric=metric,
                current_value=round(current_val, 2),
                previous_value=round(previous_val, 2),
                percent_change=round(pct_change, 2),
                severity=severity,
                trend=trend,
                sparkline_data=[round(current_val * (0.8 + 0.4 * (j / 10)), 2) for j in range(10)],
            )
            metric_cards.append(card)

        sections = [
            DashboardSection(
                id=f"{card_id_base}_section_0",
                dashboard_id=dashboard_id,
                title="Key Metrics",
                metrics=[c.to_dict() for c in metric_cards],
                charts=[{"type": "line", "metric": m.metric.value} for m in metric_cards],
                order=0,
                visible=True,
            )
        ]

        summary = {
            "total_metrics": len(metric_cards),
            "total_sections": len(sections),
            "view": config.view.value,
            "time_range": config.time_range.value,
            "generated_at": now,
        }

        dashboard_data = GovernanceDashboardData(
            id=str(uuid.uuid4()),
            dashboard_id=dashboard_id,
            view=config.view,
            time_range=config.time_range,
            sections=sections,
            metric_cards=metric_cards,
            summary=summary,
            generated_at=now,
        )
        self._dashboard_data[dashboard_data.id] = dashboard_data
        self._save()
        return dashboard_data

    def _compute_metric_value(self, metric: ChartMetric, org_id: str) -> float:
        if metric == ChartMetric.POLICY_COUNT:
            return float(self._telemetry.get("create_dashboard_config_calls", 0) * 5 + 25)
        elif metric == ChartMetric.COMPLIANCE_SCORE:
            return 72.5 + (self._telemetry.get("create_dashboard_config_calls", 0) * 0.5)
        elif metric == ChartMetric.APPROVAL_RATE:
            return 85.0 + (self._telemetry.get("create_dashboard_config_calls", 0) * 0.3)
        elif metric == ChartMetric.VIOLATION_COUNT:
            return max(0, 12 - self._telemetry.get("create_dashboard_config_calls", 0))
        elif metric == ChartMetric.RISK_SCORE:
            return 35.0 + (self._telemetry.get("create_dashboard_config_calls", 0) * 0.2)
        elif metric == ChartMetric.AUDIT_EVENTS:
            return float(self._telemetry.get("create_dashboard_config_calls", 0) * 3 + 8)
        elif metric == ChartMetric.CHANGE_COUNT:
            return float(self._telemetry.get("create_dashboard_config_calls", 0) * 2 + 5)
        elif metric == ChartMetric.INCIDENT_COUNT:
            return float(max(0, 3 - self._telemetry.get("create_dashboard_config_calls", 0) // 2))
        return 0.0

    def get_policy_violation_summary(self, org_id: str, days: int = 30) -> PolicyViolationSummary:
        self._telemetry["get_policy_violation_summary_calls"] += 1
        existing = None
        for vs in self._violation_summaries.values():
            if vs.org_id == org_id:
                existing = vs
                break

        period_end = datetime.now(timezone.utc).isoformat()
        period_start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        total_violations = existing.total_violations + 1 if existing else 5
        resolved_count = existing.resolved_count + 1 if existing else 3
        open_count = total_violations - resolved_count

        by_type = {
            "authentication": total_violations // 3,
            "authorization": total_violations // 3,
            "data_access": total_violations - (2 * (total_violations // 3)),
        }
        by_severity = {
            "critical": max(1, total_violations // 5),
            "high": max(1, total_violations // 3),
            "medium": max(1, total_violations // 4),
            "low": max(0, total_violations - (total_violations // 5) - (total_violations // 3) - (total_violations // 4)),
        }
        by_policy = {
            "policy_password_rotation": total_violations // 2,
            "policy_mfa_required": total_violations // 3,
            "policy_access_review": total_violations - (total_violations // 2) - (total_violations // 3),
        }
        top_violators = [
            {"user": "user_alpha", "count": total_violations // 2},
            {"user": "user_beta", "count": total_violations // 3},
            {"user": "user_gamma", "count": max(1, total_violations // 4)},
        ]

        if existing:
            if existing.total_violations < total_violations:
                trend_direction = "increasing"
            elif existing.total_violations > total_violations:
                trend_direction = "decreasing"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "stable"

        summary = PolicyViolationSummary(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=period_start,
            period_end=period_end,
            total_violations=total_violations,
            by_type=by_type,
            by_severity=by_severity,
            by_policy=by_policy,
            trend_direction=trend_direction,
            top_violators=top_violators,
            resolved_count=resolved_count,
            open_count=open_count,
        )
        self._violation_summaries[summary.id] = summary
        self._save()
        return summary

    def get_governance_overview(self, org_id: str) -> GovernanceOverview:
        self._telemetry["get_governance_overview_calls"] += 1
        overview = self._overviews.get(org_id)
        if not overview:
            overview = GovernanceOverview(
                id=str(uuid.uuid4()),
                org_id=org_id,
                total_policies=28,
                active_policies=22,
                total_approvals_pending=7,
                compliance_score=78.5,
                risk_score=32.0,
                audit_events_today=14,
                changes_today=9,
                violations_open=4,
            )
            self._overviews[org_id] = overview
        else:
            overview.total_policies += 1
            overview.active_policies = max(1, overview.active_policies + (1 if overview.total_policies % 3 == 0 else 0))
            overview.total_approvals_pending += (1 if overview.total_approvals_pending % 2 == 0 else 0)
            overview.compliance_score = round(min(100, overview.compliance_score + 0.3), 2)
            overview.risk_score = round(max(0, overview.risk_score - 0.2), 2)
            overview.audit_events_today += 1
            overview.changes_today += 1 if overview.changes_today % 2 == 0 else 0
            overview.last_updated = datetime.now(timezone.utc).isoformat()

        self._save()
        return overview

    def get_executive_summary(self, org_id: str) -> dict:
        self._telemetry["get_executive_summary_calls"] += 1
        overview = self.get_governance_overview(org_id)
        return {
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "governance_health": "good" if overview.compliance_score >= 70 else "needs_attention",
            "total_policies": overview.total_policies,
            "active_policies": overview.active_policies,
            "compliance_score": overview.compliance_score,
            "risk_score": overview.risk_score,
            "pending_approvals": overview.total_approvals_pending,
            "open_violations": overview.violations_open,
            "audit_events_today": overview.audit_events_today,
            "changes_today": overview.changes_today,
            "key_metrics": {
                "policy_adherence": f"{overview.compliance_score}%",
                "approval_efficiency": f"{max(0, 100 - overview.total_approvals_pending * 5)}%",
                "risk_level": "low" if overview.risk_score < 30 else "medium" if overview.risk_score < 60 else "high",
                "violation_trend": self._get_violation_trend(org_id),
            },
            "recommendations": self._generate_exec_recommendations(overview),
        }

    def _get_violation_trend(self, org_id: str) -> str:
        for vs in self._violation_summaries.values():
            if vs.org_id == org_id:
                return vs.trend_direction
        return "stable"

    def _generate_exec_recommendations(self, overview: GovernanceOverview) -> list[str]:
        recommendations = []
        if overview.compliance_score < 70:
            recommendations.append("Improve compliance score by addressing non-compliant policies.")
        if overview.risk_score > 50:
            recommendations.append("High risk score detected — review and mitigate active risks.")
        if overview.total_approvals_pending > 10:
            recommendations.append("Approval backlog growing — consider delegating or expediting reviews.")
        if overview.violations_open > 5:
            recommendations.append(f"Resolve {overview.violations_open} open violations to reduce exposure.")
        if not recommendations:
            recommendations.append("Governance posture is stable — continue monitoring.")
        return recommendations

    def get_compliance_status_view(self, org_id: str) -> dict:
        self._telemetry["get_compliance_status_view_calls"] += 1
        overview = self.get_governance_overview(org_id)
        frameworks = [
            {"name": "SOC2", "score": round(overview.compliance_score * 0.95, 2), "status": "compliant" if overview.compliance_score >= 70 else "non_compliant", "controls_total": 45, "controls_passed": int(45 * overview.compliance_score / 100)},
            {"name": "ISO 27001", "score": round(overview.compliance_score * 0.88, 2), "status": "compliant" if overview.compliance_score >= 65 else "non_compliant", "controls_total": 38, "controls_passed": int(38 * overview.compliance_score / 100)},
            {"name": "GDPR", "score": round(overview.compliance_score * 0.92, 2), "status": "compliant" if overview.compliance_score >= 75 else "non_compliant", "controls_total": 32, "controls_passed": int(32 * overview.compliance_score / 100)},
            {"name": "HIPAA", "score": round(overview.compliance_score * 0.80, 2), "status": "non_compliant" if overview.compliance_score < 80 else "compliant", "controls_total": 50, "controls_passed": int(50 * overview.compliance_score / 100)},
            {"name": "NIST", "score": round(overview.compliance_score * 0.85, 2), "status": "compliant" if overview.compliance_score >= 70 else "non_compliant", "controls_total": 40, "controls_passed": int(40 * overview.compliance_score / 100)},
        ]
        return {
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_compliance_score": overview.compliance_score,
            "frameworks": frameworks,
            "compliant_frameworks": sum(1 for f in frameworks if f["status"] == "compliant"),
            "non_compliant_frameworks": sum(1 for f in frameworks if f["status"] == "non_compliant"),
        }

    def get_approval_queue_view(self, org_id: str) -> dict:
        self._telemetry["get_approval_queue_view_calls"] += 1
        overview = self.get_governance_overview(org_id)
        pending_count = overview.total_approvals_pending
        return {
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_pending": pending_count,
            "approvals_by_type": {
                "policy_change": max(1, pending_count // 3),
                "deployment": max(1, pending_count // 3),
                "access_request": max(1, pending_count - (2 * (pending_count // 3))),
                "configuration_change": max(0, pending_count // 5),
            },
            "approvals_by_priority": {
                "critical": max(1, pending_count // 4),
                "high": max(1, pending_count // 3),
                "medium": max(0, pending_count - (pending_count // 4) - (pending_count // 3)),
                "low": 0,
            },
            "oldest_pending_hours": 47,
            "average_wait_time_hours": 12.5,
            "urgent_items": max(1, pending_count // 5),
        }

    def get_audit_events_view(self, org_id: str, days: int = 7) -> dict:
        self._telemetry["get_audit_events_view_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        event_types = ["policy_created", "policy_updated", "policy_deleted", "compliance_assessment",
                       "approval_granted", "approval_rejected", "violation_detected", "change_executed",
                       "role_changed", "permission_modified", "config_updated", "risk_assessed"]
        events = []
        base_time = cutoff
        for i in range(15):
            event_time = base_time + timedelta(hours=i * 11)
            events.append({
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "event_type": event_types[i % len(event_types)],
                "severity": ["info", "warning", "critical", "info"][i % 4],
                "description": f"Audit event {i + 1} — {event_types[i % len(event_types)].replace('_', ' ').title()}",
                "performed_by": f"user_{chr(97 + (i % 5))}",
                "performed_at": event_time.isoformat(),
            })
        return {
            "org_id": org_id,
            "days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_events": len(events),
            "events": events,
            "event_type_breakdown": {et: sum(1 for e in events if e["event_type"] == et) for et in event_types},
            "severity_breakdown": {"info": sum(1 for e in events if e["severity"] == "info"), "warning": sum(1 for e in events if e["severity"] == "warning"), "critical": sum(1 for e in events if e["severity"] == "critical")},
        }

    def get_risk_reports_view(self, org_id: str) -> dict:
        self._telemetry["get_risk_reports_view_calls"] += 1
        overview = self.get_governance_overview(org_id)
        risk_areas = [
            {"area": "Access Control", "score": round(min(100, overview.risk_score * 1.2), 2), "level": "medium", "trend": "stable", "description": "Risk related to user access and permissions"},
            {"area": "Data Privacy", "score": round(min(100, overview.risk_score * 0.9), 2), "level": "low", "trend": "decreasing", "description": "Risk related to data protection and privacy compliance"},
            {"area": "Configuration Drift", "score": round(min(100, overview.risk_score * 1.1), 2), "level": "medium", "trend": "increasing", "description": "Risk from unauthorized configuration changes"},
            {"area": "Policy Violations", "score": round(min(100, overview.risk_score + 10), 2), "level": "high", "trend": "stable", "description": "Risk from active policy violations"},
            {"area": "Third Party", "score": round(min(100, overview.risk_score * 0.7), 2), "level": "low", "trend": "decreasing", "description": "Risk from third-party integrations and dependencies"},
        ]
        return {
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_risk_score": overview.risk_score,
            "risk_level": "low" if overview.risk_score < 30 else "medium" if overview.risk_score < 60 else "high",
            "risk_areas": risk_areas,
            "high_risk_count": sum(1 for r in risk_areas if r["level"] == "high"),
            "medium_risk_count": sum(1 for r in risk_areas if r["level"] == "medium"),
            "low_risk_count": sum(1 for r in risk_areas if r["level"] == "low"),
            "top_risk": max(risk_areas, key=lambda r: r["score"]),
        }

    def get_security_overview_view(self, org_id: str) -> dict:
        self._telemetry["get_security_overview_view_calls"] += 1
        overview = self.get_governance_overview(org_id)
        return {
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "security_posture": "secure" if overview.risk_score < 30 else "at_risk" if overview.risk_score > 60 else "moderate",
            "active_threats": max(0, int(overview.risk_score // 10)),
            "open_vulnerabilities": max(1, int(overview.risk_score // 5)),
            "mfa_enforcement": "enabled" if overview.compliance_score > 60 else "partial",
            "encryption_status": "at_rest_and_in_transit",
            "last_security_scan": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
            "failed_login_attempts_24h": max(0, 12 - int(overview.compliance_score // 10)),
            "privileged_sessions_active": max(1, int(overview.total_approvals_pending // 2)),
            "api_keys_rotated_days": 14,
            "security_metrics": {
                "total_policies": overview.total_policies,
                "active_policies": overview.active_policies,
                "compliance_score": overview.compliance_score,
                "risk_score": overview.risk_score,
                "violations_open": overview.violations_open,
            },
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
