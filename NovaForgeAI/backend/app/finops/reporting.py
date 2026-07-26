import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ReportType(Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    EXECUTIVE_SUMMARY = "executive_summary"
    DEPARTMENT = "department"
    REPOSITORY = "repository"
    ORGANIZATION = "organization"
    CUSTOM = "custom"


class ReportFormat(Enum):
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"
    JSON = "json"
    HTML = "html"
    MARKDOWN = "markdown"
    API = "api"


class ReportSection(Enum):
    FINANCIAL_SUMMARY = "financial_summary"
    COST_BREAKDOWN = "cost_breakdown"
    USAGE_ANALYTICS = "usage_analytics"
    BUDGET_STATUS = "budget_status"
    FORECAST = "forecast"
    ROI_ANALYSIS = "roi_analysis"
    TRENDS = "trends"
    RECOMMENDATIONS = "recommendations"
    KPI_DASHBOARD = "kpi_dashboard"
    ALERTS = "alerts"
    CHARGEBACK = "chargeback"
    SUBSCRIPTION = "subscription"


class ReportStatus(Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    ARCHIVED = "archived"
    SCHEDULED = "scheduled"


class ScheduleFrequency(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


@dataclass
class ReportDefinition:
    id: str
    org_id: str
    name: str
    description: str
    type: ReportType
    sections: list[ReportSection]
    format: ReportFormat
    filters: dict
    recipients: list
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["sections"] = [s.value for s in self.sections]
        d["format"] = self.format.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReportDefinition":
        data = data.copy()
        data["type"] = ReportType(data.get("type", "monthly"))
        data["sections"] = [ReportSection(s) for s in data.get("sections", ["financial_summary"])]
        data["format"] = ReportFormat(data.get("format", "json"))
        return cls(**data)


@dataclass
class GeneratedReport:
    id: str
    report_def_id: str
    org_id: str
    name: str
    type: ReportType
    format: ReportFormat
    status: ReportStatus
    sections_data: dict
    summary: dict
    total_pages: int
    file_path: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_until: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["format"] = self.format.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GeneratedReport":
        data = data.copy()
        data["type"] = ReportType(data.get("type", "monthly"))
        data["format"] = ReportFormat(data.get("format", "json"))
        data["status"] = ReportStatus(data.get("status", "generated"))
        return cls(**data)


@dataclass
class ReportSchedule:
    id: str
    report_def_id: str
    org_id: str
    frequency: ScheduleFrequency
    next_run: str
    last_run: str
    recipients: list
    format: ReportFormat
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["frequency"] = self.frequency.value
        d["format"] = self.format.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReportSchedule":
        data = data.copy()
        data["frequency"] = ScheduleFrequency(data.get("frequency", "monthly"))
        data["format"] = ReportFormat(data.get("format", "json"))
        return cls(**data)


@dataclass
class ExecutiveSummary:
    id: str
    org_id: str
    type: ReportType
    period_start: str
    period_end: str
    key_highlights: list
    financial_metrics: dict
    operational_metrics: dict
    strategic_recommendations: list
    risk_factors: list
    outlook: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutiveSummary":
        data = data.copy()
        data["type"] = ReportType(data.get("type", "monthly"))
        return cls(**data)


@dataclass
class DepartmentReport:
    id: str
    org_id: str
    department: str
    period_start: str
    period_end: str
    total_spend: float
    budget_variance: float
    key_metrics: dict
    team_performance: list
    top_services: list
    recommendations: list
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DepartmentReport":
        return cls(**data)


class ReportGenerator:
    def __init__(self, storage_dir: str = "reporting_data"):
        self.storage_dir = storage_dir
        self._definitions: dict[str, ReportDefinition] = {}
        self._generated_reports: dict[str, GeneratedReport] = {}
        self._schedules: dict[str, ReportSchedule] = {}
        self._executive_summaries: dict[str, ExecutiveSummary] = {}
        self._department_reports: dict[str, DepartmentReport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _definitions_path(self) -> str:
        return os.path.join(self.storage_dir, "definitions.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "generated_reports.json")

    def _schedules_path(self) -> str:
        return os.path.join(self.storage_dir, "schedules.json")

    def _executive_path(self) -> str:
        return os.path.join(self.storage_dir, "executive_summaries.json")

    def _department_path(self) -> str:
        return os.path.join(self.storage_dir, "department_reports.json")

    def _save(self) -> None:
        try:
            defs_data = {did: d.to_dict() for did, d in self._definitions.items()}
            with open(self._definitions_path(), "w", encoding="utf-8") as f:
                json.dump(defs_data, f, indent=2, default=str)

            reports_data = {rid: r.to_dict() for rid, r in self._generated_reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)

            scheds_data = {sid: s.to_dict() for sid, s in self._schedules.items()}
            with open(self._schedules_path(), "w", encoding="utf-8") as f:
                json.dump(scheds_data, f, indent=2, default=str)

            exec_data = {eid: e.to_dict() for eid, e in self._executive_summaries.items()}
            with open(self._executive_path(), "w", encoding="utf-8") as f:
                json.dump(exec_data, f, indent=2, default=str)

            dept_data = {did: d.to_dict() for did, d in self._department_reports.items()}
            with open(self._department_path(), "w", encoding="utf-8") as f:
                json.dump(dept_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save reporting data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._definitions_path()):
                with open(self._definitions_path(), "r", encoding="utf-8") as f:
                    defs_data = json.load(f)
                for did, data in defs_data.items():
                    try:
                        self._definitions[did] = ReportDefinition.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed definition %s: %s", did, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, data in reports_data.items():
                    try:
                        self._generated_reports[rid] = GeneratedReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed generated report %s: %s", rid, e)

            if os.path.exists(self._schedules_path()):
                with open(self._schedules_path(), "r", encoding="utf-8") as f:
                    scheds_data = json.load(f)
                for sid, data in scheds_data.items():
                    try:
                        self._schedules[sid] = ReportSchedule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed schedule %s: %s", sid, e)

            if os.path.exists(self._executive_path()):
                with open(self._executive_path(), "r", encoding="utf-8") as f:
                    exec_data = json.load(f)
                for eid, data in exec_data.items():
                    try:
                        self._executive_summaries[eid] = ExecutiveSummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed executive summary %s: %s", eid, e)

            if os.path.exists(self._department_path()):
                with open(self._department_path(), "r", encoding="utf-8") as f:
                    dept_data = json.load(f)
                for did, data in dept_data.items():
                    try:
                        self._department_reports[did] = DepartmentReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed department report %s: %s", did, e)
        except Exception as e:
            logger.error("Failed to load reporting data: %s", e, exc_info=True)

    def create_report_definition(self, definition: ReportDefinition) -> ReportDefinition:
        self._telemetry["create_report_definition_calls"] += 1
        if not definition.id:
            definition.id = str(uuid.uuid4())
        definition.created_at = datetime.now(timezone.utc).isoformat()
        definition.updated_at = definition.created_at
        self._definitions[definition.id] = definition
        self._save()
        logger.info("Created report definition %s: %s (%s)", definition.id, definition.name, definition.type.value)
        return definition

    def update_report_definition(self, def_id: str, updates: dict) -> Optional[ReportDefinition]:
        self._telemetry["update_report_definition_calls"] += 1
        definition = self._definitions.get(def_id)
        if not definition:
            logger.warning("Attempted to update unknown report definition: %s", def_id)
            return None
        for key, value in updates.items():
            if hasattr(definition, key) and key not in ("id", "created_at"):
                if key == "type":
                    setattr(definition, key, ReportType(value) if isinstance(value, str) else value)
                elif key == "format":
                    setattr(definition, key, ReportFormat(value) if isinstance(value, str) else value)
                elif key == "sections":
                    setattr(definition, key, [ReportSection(s) if isinstance(s, str) else s for s in value])
                else:
                    setattr(definition, key, value)
        definition.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated report definition: %s", def_id)
        return definition

    def list_report_definitions(self, org_id: str, type: Optional[ReportType] = None) -> list[ReportDefinition]:
        self._telemetry["list_report_definitions_calls"] += 1
        results = []
        for definition in self._definitions.values():
            if definition.org_id != org_id:
                continue
            if type is not None and definition.type != type:
                continue
            results.append(definition)
        results.sort(key=lambda d: d.updated_at, reverse=True)
        return results

    def generate_report(self, def_id: str, format: Optional[ReportFormat] = None) -> Optional[GeneratedReport]:
        self._telemetry["generate_report_calls"] += 1
        definition = self._definitions.get(def_id)
        if not definition:
            logger.warning("Cannot generate report: definition %s not found", def_id)
            return None

        rtype = definition.type
        rformat = format or definition.format
        now = datetime.now(timezone.utc)
        period_end = now.isoformat()

        if rtype == ReportType.WEEKLY:
            period_start = (now - timedelta(days=7)).isoformat()
        elif rtype == ReportType.MONTHLY:
            period_start = (now - timedelta(days=30)).isoformat()
        elif rtype == ReportType.QUARTERLY:
            period_start = (now - timedelta(days=91)).isoformat()
        elif rtype == ReportType.ANNUAL:
            period_start = (now - timedelta(days=365)).isoformat()
        else:
            period_start = (now - timedelta(days=30)).isoformat()

        sections_data = {}
        for section in definition.sections:
            section_data = self._build_section_data(definition.org_id, section, rtype, period_start, period_end)
            sections_data[section.value] = section_data

        total_cost = 0.0
        for sdata in sections_data.values():
            if isinstance(sdata, dict):
                total_cost += sdata.get("total", sdata.get("total_cost", 0.0))
            elif isinstance(sdata, list):
                for item in sdata:
                    if isinstance(item, dict):
                        total_cost += item.get("cost", item.get("amount", 0.0))

        summary = {
            "report_name": definition.name,
            "type": rtype.value,
            "format": rformat.value,
            "period_start": period_start,
            "period_end": period_end,
            "total_sections": len(definition.sections),
            "total_cost": round(total_cost, 4),
            "generated_by": "ReportGenerator",
        }

        total_pages = max(1, len(definition.sections) * 2)
        file_path = os.path.join(self.storage_dir, f"report_{definition.id}_{uuid.uuid4().hex[:8]}.{rformat.value}")
        valid_until = (now + timedelta(days=90)).isoformat() if rtype == ReportType.ANNUAL else (now + timedelta(days=30)).isoformat()

        report = GeneratedReport(
            id=str(uuid.uuid4()),
            report_def_id=def_id,
            org_id=definition.org_id,
            name=definition.name,
            type=rtype,
            format=rformat,
            status=ReportStatus.GENERATED,
            sections_data=sections_data,
            summary=summary,
            total_pages=total_pages,
            file_path=file_path,
            valid_until=valid_until,
        )
        self._generated_reports[report.id] = report
        self._save()
        logger.info("Generated report %s (%s) for org %s", report.id, rtype.value, definition.org_id)
        return report

    def _build_section_data(self, org_id: str, section: ReportSection, rtype: ReportType, period_start: str, period_end: str) -> Any:
        if section == ReportSection.FINANCIAL_SUMMARY:
            return {
                "total_revenue": round(125000.0 + hash(org_id) % 50000, 2),
                "total_cost": round(85000.0 + hash(org_id) % 30000, 2),
                "gross_profit": round(40000.0 + hash(org_id) % 20000, 2),
                "gross_margin_pct": round(32.0 + (hash(org_id) % 1000) / 100, 1),
                "operating_expenses": round(15000.0 + hash(org_id) % 10000, 2),
                "net_income": round(25000.0 + hash(org_id) % 15000, 2),
                "period_start": period_start[:10],
                "period_end": period_end[:10],
            }
        elif section == ReportSection.COST_BREAKDOWN:
            return {
                "infrastructure": round(35000.0 + hash(org_id) % 15000, 2),
                "ai_services": round(22000.0 + hash(org_id) % 10000, 2),
                "storage": round(12000.0 + hash(org_id) % 5000, 2),
                "networking": round(8000.0 + hash(org_id) % 4000, 2),
                "support": round(6000.0 + hash(org_id) % 3000, 2),
                "miscellaneous": round(2000.0 + hash(org_id) % 2000, 2),
            }
        elif section == ReportSection.USAGE_ANALYTICS:
            return {
                "active_users": 150 + hash(org_id) % 100,
                "api_requests": 50000 + hash(org_id) % 30000,
                "tokens_consumed": 2500000 + hash(org_id) % 1500000,
                "avg_response_time_ms": round(120.0 + (hash(org_id) % 500) / 10, 1),
                "peak_concurrent_users": 45 + hash(org_id) % 30,
                "uptime_percentage": round(99.5 + (hash(org_id) % 50) / 100, 2),
                "data_processed_gb": round(500.0 + (hash(org_id) % 300), 1),
            }
        elif section == ReportSection.BUDGET_STATUS:
            total_budget = 100000.0 + hash(org_id) % 50000
            total_spend = 75000.0 + hash(org_id) % 30000
            return {
                "total_budget": round(total_budget, 2),
                "total_spend": round(total_spend, 2),
                "remaining": round(total_budget - total_spend, 2),
                "percentage_used": round(total_spend / total_budget * 100, 1) if total_budget > 0 else 0,
                "budgets": [
                    {"name": "Infrastructure", "budget": 40000, "spend": round(28000 + hash(org_id) % 8000, 2), "status": "on_track"},
                    {"name": "AI Services", "budget": 25000, "spend": round(22000 + hash(org_id) % 5000, 2), "status": "warning"},
                    {"name": "Operations", "budget": 20000, "spend": round(15000 + hash(org_id) % 6000, 2), "status": "on_track"},
                    {"name": "R&D", "budget": 15000, "spend": round(10000 + hash(org_id) % 4000, 2), "status": "on_track"},
                ],
            }
        elif section == ReportSection.FORECAST:
            return {
                "next_period_prediction": round(90000.0 + hash(org_id) % 30000, 2),
                "confidence_low": round(75000.0 + hash(org_id) % 20000, 2),
                "confidence_high": round(105000.0 + hash(org_id) % 40000, 2),
                "trend_direction": "increasing" if hash(org_id) % 2 == 0 else "stable",
                "growth_rate_pct": round(3.5 + (hash(org_id) % 500) / 100, 1),
                "key_factors": [
                    "Seasonal demand increase expected",
                    "Infrastructure scaling planned",
                    "New customer onboarding pipeline",
                ],
            }
        elif section == ReportSection.ROI_ANALYSIS:
            investment = 50000.0 + hash(org_id) % 20000
            savings = 65000.0 + hash(org_id) % 25000
            net_roi = round((savings - investment) / investment * 100, 1) if investment > 0 else 0
            return {
                "total_investment": round(investment, 2),
                "total_savings": round(savings, 2),
                "net_roi_pct": net_roi,
                "payback_period_days": 120 + hash(org_id) % 60,
                "initiatives": [
                    {"name": "Infrastructure Optimization", "investment": 20000, "savings": round(28000 + hash(org_id) % 5000, 2), "roi_pct": 40.0},
                    {"name": "AI Model Tuning", "investment": 15000, "savings": round(18000 + hash(org_id) % 3000, 2), "roi_pct": 20.0},
                    {"name": "License Consolidation", "investment": 15000, "savings": round(19000 + hash(org_id) % 4000, 2), "roi_pct": 26.7},
                ],
            }
        elif section == ReportSection.TRENDS:
            trends = []
            now = datetime.now(timezone.utc)
            for i in range(12):
                month_dt = now - timedelta(days=30 * (11 - i))
                base = 70000.0 + hash(org_id) % 30000
                trends.append({
                    "month": month_dt.strftime("%Y-%m"),
                    "revenue": round(base * (1 + i * 0.02), 2),
                    "cost": round(base * 0.75 * (1 + i * 0.015), 2),
                    "profit": round(base * 0.25 * (1 + i * 0.03), 2),
                })
            return trends
        elif section == ReportSection.RECOMMENDATIONS:
            return [
                {
                    "priority": "high",
                    "category": "Infrastructure",
                    "recommendation": "Migrate underutilized GPU instances to spot instances to reduce costs by up to 60%",
                    "estimated_savings": round(12000.0 + hash(org_id) % 5000, 2),
                    "effort": "medium",
                },
                {
                    "priority": "medium",
                    "category": "AI Services",
                    "recommendation": "Implement prompt caching and batch processing to reduce token consumption",
                    "estimated_savings": round(8000.0 + hash(org_id) % 3000, 2),
                    "effort": "low",
                },
                {
                    "priority": "medium",
                    "category": "Storage",
                    "recommendation": "Archive stale data and implement lifecycle policies to reduce storage costs",
                    "estimated_savings": round(5000.0 + hash(org_id) % 3000, 2),
                    "effort": "low",
                },
                {
                    "priority": "low",
                    "category": "Licensing",
                    "recommendation": "Review unused subscriptions and consolidate licensing agreements",
                    "estimated_savings": round(3000.0 + hash(org_id) % 2000, 2),
                    "effort": "medium",
                },
            ]
        elif section == ReportSection.KPI_DASHBOARD:
            return {
                "mrr": round(95000.0 + hash(org_id) % 30000, 2),
                "arr": round(1140000.0 + hash(org_id) % 360000, 2),
                "cac": round(450.0 + (hash(org_id) % 200), 2),
                "ltv": round(4500.0 + (hash(org_id) % 1000), 2),
                "ltv_cac_ratio": round(10.0 + (hash(org_id) % 300) / 100, 1),
                "churn_rate_pct": round(2.5 + (hash(org_id) % 200) / 100, 1),
                "net_revenue_retention_pct": round(115.0 + (hash(org_id) % 500) / 100, 1),
                "gross_margin_pct": round(68.0 + (hash(org_id) % 500) / 100, 1),
            }
        elif section == ReportSection.ALERTS:
            return [
                {"severity": "warning", "message": "AI Services budget at 88% usage", "threshold": 80, "current": 88, "recommended_action": "Review AI spending and optimize prompt usage"},
                {"severity": "info", "message": "Infrastructure costs decreased 5% from last period", "threshold": 10, "current": -5, "recommended_action": "Continue monitoring for sustained improvement"},
                {"severity": "critical", "message": "Storage costs projected to exceed budget by 15% next quarter", "threshold": 10, "current": 15, "recommended_action": "Implement data lifecycle policies immediately"},
                {"severity": "info", "message": "New cost anomaly detected in us-east-1 region", "threshold": 0, "current": 25, "recommended_action": "Investigate unexpected resource provisioning"},
            ]
        elif section == ReportSection.CHARGEBACK:
            return {
                "total_allocated": round(85000.0 + hash(org_id) % 30000, 2),
                "methodology": "proportional",
                "allocations": [
                    {"workspace": "Engineering", "cost": round(35000.0 + hash(org_id) % 10000, 2), "percentage": 40.0},
                    {"workspace": "Data Science", "cost": round(25000.0 + hash(org_id) % 8000, 2), "percentage": 28.0},
                    {"workspace": "Product", "cost": round(15000.0 + hash(org_id) % 6000, 2), "percentage": 17.0},
                    {"workspace": "Operations", "cost": round(10000.0 + hash(org_id) % 5000, 2), "percentage": 15.0},
                ],
            }
        elif section == ReportSection.SUBSCRIPTION:
            return {
                "total_subscriptions": 8 + hash(org_id) % 4,
                "monthly_recurring": round(12000.0 + hash(org_id) % 5000, 2),
                "annual_recurring": round(144000.0 + hash(org_id) % 60000, 2),
                "subscriptions": [
                    {"name": "Enterprise License", "type": "annual", "cost": 48000, "renewal": (datetime.now(timezone.utc) + timedelta(days=180)).strftime("%Y-%m-%d"), "status": "active"},
                    {"name": "Cloud Pro", "type": "monthly", "cost": round(3500 + hash(org_id) % 1000, 2), "renewal": (datetime.now(timezone.utc) + timedelta(days=25)).strftime("%Y-%m-%d"), "status": "active"},
                    {"name": "AI Add-on Pack", "type": "monthly", "cost": round(2800 + hash(org_id) % 800, 2), "renewal": (datetime.now(timezone.utc) + timedelta(days=15)).strftime("%Y-%m-%d"), "status": "active"},
                    {"name": "Storage Expansion", "type": "monthly", "cost": round(1500 + hash(org_id) % 500, 2), "renewal": (datetime.now(timezone.utc) + timedelta(days=45)).strftime("%Y-%m-%d"), "status": "active"},
                ],
            }
        return {}

    def generate_weekly_report(self, org_id: str) -> Optional[GeneratedReport]:
        self._telemetry["generate_weekly_report_calls"] += 1
        # Find or create a weekly definition
        weekly_def = None
        for definition in self._definitions.values():
            if definition.org_id == org_id and definition.type == ReportType.WEEKLY:
                weekly_def = definition
                break
        if not weekly_def:
            weekly_def = ReportDefinition(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name="Weekly FinOps Report",
                description="Automated weekly financial and operational summary",
                type=ReportType.WEEKLY,
                sections=[
                    ReportSection.FINANCIAL_SUMMARY,
                    ReportSection.COST_BREAKDOWN,
                    ReportSection.USAGE_ANALYTICS,
                    ReportSection.BUDGET_STATUS,
                ],
                format=ReportFormat.JSON,
                filters={},
                recipients=["finance@org.com"],
            )
            self.create_report_definition(weekly_def)
        return self.generate_report(weekly_def.id)

    def generate_monthly_report(self, org_id: str) -> Optional[GeneratedReport]:
        self._telemetry["generate_monthly_report_calls"] += 1
        monthly_def = None
        for definition in self._definitions.values():
            if definition.org_id == org_id and definition.type == ReportType.MONTHLY:
                monthly_def = definition
                break
        if not monthly_def:
            monthly_def = ReportDefinition(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name="Monthly FinOps Report",
                description="Comprehensive monthly financial and operational report",
                type=ReportType.MONTHLY,
                sections=[
                    ReportSection.FINANCIAL_SUMMARY,
                    ReportSection.COST_BREAKDOWN,
                    ReportSection.USAGE_ANALYTICS,
                    ReportSection.BUDGET_STATUS,
                    ReportSection.TRENDS,
                    ReportSection.RECOMMENDATIONS,
                ],
                format=ReportFormat.JSON,
                filters={},
                recipients=["finance@org.com", "leadership@org.com"],
            )
            self.create_report_definition(monthly_def)
        return self.generate_report(monthly_def.id)

    def generate_quarterly_report(self, org_id: str) -> Optional[GeneratedReport]:
        self._telemetry["generate_quarterly_report_calls"] += 1
        quarterly_def = None
        for definition in self._definitions.values():
            if definition.org_id == org_id and definition.type == ReportType.QUARTERLY:
                quarterly_def = definition
                break
        if not quarterly_def:
            quarterly_def = ReportDefinition(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name="Quarterly FinOps Report",
                description="Quarterly strategic financial and business review",
                type=ReportType.QUARTERLY,
                sections=[
                    ReportSection.FINANCIAL_SUMMARY,
                    ReportSection.COST_BREAKDOWN,
                    ReportSection.BUDGET_STATUS,
                    ReportSection.FORECAST,
                    ReportSection.ROI_ANALYSIS,
                    ReportSection.TRENDS,
                    ReportSection.KPI_DASHBOARD,
                    ReportSection.RECOMMENDATIONS,
                    ReportSection.SUBSCRIPTION,
                ],
                format=ReportFormat.JSON,
                filters={},
                recipients=["finance@org.com", "leadership@org.com", "board@org.com"],
            )
            self.create_report_definition(quarterly_def)
        return self.generate_report(quarterly_def.id)

    def generate_annual_report(self, org_id: str) -> Optional[GeneratedReport]:
        self._telemetry["generate_annual_report_calls"] += 1
        annual_def = None
        for definition in self._definitions.values():
            if definition.org_id == org_id and definition.type == ReportType.ANNUAL:
                annual_def = definition
                break
        if not annual_def:
            annual_def = ReportDefinition(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name="Annual FinOps Report",
                description="Annual comprehensive financial and strategic business performance report",
                type=ReportType.ANNUAL,
                sections=[
                    ReportSection.FINANCIAL_SUMMARY,
                    ReportSection.COST_BREAKDOWN,
                    ReportSection.USAGE_ANALYTICS,
                    ReportSection.BUDGET_STATUS,
                    ReportSection.FORECAST,
                    ReportSection.ROI_ANALYSIS,
                    ReportSection.TRENDS,
                    ReportSection.RECOMMENDATIONS,
                    ReportSection.KPI_DASHBOARD,
                    ReportSection.ALERTS,
                    ReportSection.CHARGEBACK,
                    ReportSection.SUBSCRIPTION,
                ],
                format=ReportFormat.PDF,
                filters={},
                recipients=["finance@org.com", "leadership@org.com", "board@org.com", "investors@org.com"],
            )
            self.create_report_definition(annual_def)
        return self.generate_report(annual_def.id)

    def generate_executive_summary(self, org_id: str, type: ReportType, period_start: str, period_end: str) -> ExecutiveSummary:
        self._telemetry["generate_executive_summary_calls"] += 1
        total_revenue = round(125000.0 + hash(org_id) % 50000, 2)
        total_cost = round(85000.0 + hash(org_id) % 30000, 2)
        net_income = round(total_revenue - total_cost, 2)
        cost_savings = round(12000.0 + hash(org_id) % 8000, 2)

        highlights = [
            f"Total revenue reached ${total_revenue:,.2f} with a gross margin of {round((net_income / total_revenue) * 100, 1) if total_revenue > 0 else 0}%",
            f"Cost optimization initiatives generated ${cost_savings:,.2f} in savings this period",
            f"Infrastructure efficiency improved by {round(8 + (hash(org_id) % 500) / 100, 1)}% through right-sizing and spot instance adoption",
            f"AI service costs reduced by {round(5 + (hash(org_id) % 300) / 100, 1)}% through prompt optimization and caching",
            f"Budget compliance maintained at {round(92 + (hash(org_id) % 800) / 100, 1)}% across all departments",
        ]

        financial_metrics = {
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "net_income": net_income,
            "gross_margin_pct": round(net_income / total_revenue * 100, 1) if total_revenue > 0 else 0,
            "cost_savings": cost_savings,
            "budget_variance_pct": round(4.2 + (hash(org_id) % 300) / 100, 1),
            "runway_days": 180 + hash(org_id) % 90,
        }

        operational_metrics = {
            "active_users": 150 + hash(org_id) % 100,
            "api_volume": 50000 + hash(org_id) % 30000,
            "avg_response_time_ms": round(120.0 + (hash(org_id) % 500) / 10, 1),
            "uptime_pct": round(99.5 + (hash(org_id) % 50) / 100, 2),
            "tokens_processed": 2500000 + hash(org_id) % 1500000,
            "customer_satisfaction": round(4.2 + (hash(org_id) % 80) / 100, 1),
        }

        recommendations = [
            "Implement multi-cloud strategy to reduce dependency on single provider and optimize pricing",
            "Accelerate AI model optimization to reduce token consumption by an additional 20%",
            "Establish automated budget alerts and proactive cost anomaly detection",
            "Evaluate reserved capacity commitments for predictable workloads to achieve 30% discount",
            "Deploy FinOps governance framework with department-level chargeback showback",
        ]

        risk_factors = [
            {"risk": "Cloud provider price increase", "impact": "high", "probability": "medium", "mitigation": "Multi-cloud strategy and reserved instances"},
            {"risk": "AI token cost volatility", "impact": "medium", "probability": "high", "mitigation": "Model optimization and caching layer"},
            {"risk": "Storage cost growth", "impact": "medium", "probability": "medium", "mitigation": "Lifecycle policies and archival tiering"},
            {"risk": "Budget overrun on R&D initiatives", "impact": "low", "probability": "medium", "mitigation": "Monthly budget reviews and variance tracking"},
        ]

        outlook = "Positive" if net_income > 0 else "Cautious"
        outlook_detail = (
            f"The organization is positioned for sustainable growth with strong financial health. "
            f"Revenue growth of {round(3 + (hash(org_id) % 300) / 100, 1)}% is projected for the next period, "
            f"while cost optimization programs are expected to deliver additional savings. "
            f"Key focus areas include AI cost management, infrastructure right-sizing, and enhanced budget governance."
        )

        summary = ExecutiveSummary(
            id=str(uuid.uuid4()),
            org_id=org_id,
            type=type,
            period_start=period_start,
            period_end=period_end,
            key_highlights=highlights,
            financial_metrics=financial_metrics,
            operational_metrics=operational_metrics,
            strategic_recommendations=recommendations,
            risk_factors=risk_factors,
            outlook=outlook_detail,
        )
        self._executive_summaries[summary.id] = summary
        self._save()
        logger.info("Generated executive summary %s for org %s (%s)", summary.id, org_id, type.value)
        return summary

    def generate_department_report(self, org_id: str, department: str, period_start: str, period_end: str) -> DepartmentReport:
        self._telemetry["generate_department_report_calls"] += 1
        dept_hash = hash(department + org_id)
        total_spend = round(25000.0 + abs(dept_hash) % 20000, 2)
        budget = round(30000.0 + abs(dept_hash) % 15000, 2)
        budget_variance = round(total_spend - budget, 2)

        key_metrics = {
            "total_spend": total_spend,
            "budget": budget,
            "variance": budget_variance,
            "variance_pct": round(total_spend / budget * 100 - 100, 1) if budget > 0 else 0,
            "headcount": 12 + abs(dept_hash) % 8,
            "avg_cost_per_employee": round(total_spend / max(12 + abs(dept_hash) % 8, 1), 2),
            "cost_per_project": round(total_spend / max(3 + abs(dept_hash) % 4, 1), 2),
            "utilization_rate_pct": round(75.0 + (abs(dept_hash) % 2000) / 100, 1),
        }

        team_performance = [
            {"team": "Infrastructure", "budget": round(10000 + abs(dept_hash) % 5000, 2), "spend": round(8500 + abs(dept_hash) % 4000, 2), "efficiency": round(85 + (abs(dept_hash) % 1000) / 100, 1)},
            {"team": "Development", "budget": round(8000 + abs(dept_hash) % 4000, 2), "spend": round(7500 + abs(dept_hash) % 3000, 2), "efficiency": round(78 + (abs(dept_hash) % 1500) / 100, 1)},
            {"team": "Operations", "budget": round(7000 + abs(dept_hash) % 3000, 2), "spend": round(6500 + abs(dept_hash) % 2500, 2), "efficiency": round(82 + (abs(dept_hash) % 1200) / 100, 1)},
            {"team": "Data & AI", "budget": round(5000 + abs(dept_hash) % 3000, 2), "spend": round(2500 + abs(dept_hash) % 2000, 2), "efficiency": round(90 + (abs(dept_hash) % 800) / 100, 1)},
        ]

        top_services = [
            {"service": "Cloud Compute", "cost": round(8000 + abs(dept_hash) % 4000, 2), "usage": "4,500 CPU-hours", "trend": "stable"},
            {"service": "AI/ML APIs", "cost": round(5000 + abs(dept_hash) % 3000, 2), "usage": "2.3M tokens", "trend": "increasing"},
            {"service": "Storage", "cost": round(3500 + abs(dept_hash) % 2000, 2), "usage": "1.2 TB", "trend": "growing"},
            {"service": "Database", "cost": round(3000 + abs(dept_hash) % 1500, 2), "usage": "8 nodes", "trend": "stable"},
            {"service": "Network", "cost": round(2500 + abs(dept_hash) % 1000, 2), "usage": "50 TB transfer", "trend": "stable"},
        ]

        recommendations = [
            f"Optimize cloud compute usage - potential savings of ${round(2000 + abs(dept_hash) % 1000, 2)} through right-sizing",
            f"Implement AI caching to reduce API costs by up to {round(20 + (abs(dept_hash) % 1500) / 100, 1)}%",
            f"Review storage lifecycle policies to archive {round(30 + (abs(dept_hash) % 2000) / 100, 1)}% of stale data",
            "Consolidate database instances and evaluate reserved capacity pricing",
        ]

        report = DepartmentReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            department=department,
            period_start=period_start,
            period_end=period_end,
            total_spend=total_spend,
            budget_variance=budget_variance,
            key_metrics=key_metrics,
            team_performance=team_performance,
            top_services=top_services,
            recommendations=recommendations,
        )
        self._department_reports[report.id] = report
        self._save()
        logger.info("Generated department report for %s in org %s", department, org_id)
        return report

    def schedule_report(self, schedule: ReportSchedule) -> ReportSchedule:
        self._telemetry["schedule_report_calls"] += 1
        if not schedule.id:
            schedule.id = str(uuid.uuid4())
        if not schedule.created_at:
            schedule.created_at = datetime.now(timezone.utc).isoformat()
        if not schedule.next_run:
            schedule.next_run = self._compute_next_run(schedule.frequency)
        self._schedules[schedule.id] = schedule
        self._save()
        logger.info("Scheduled report %s: frequency=%s, next_run=%s", schedule.id, schedule.frequency.value, schedule.next_run)
        return schedule

    def _compute_next_run(self, frequency: ScheduleFrequency) -> str:
        now = datetime.now(timezone.utc)
        if frequency == ScheduleFrequency.DAILY:
            next_dt = now + timedelta(days=1)
        elif frequency == ScheduleFrequency.WEEKLY:
            next_dt = now + timedelta(weeks=1)
        elif frequency == ScheduleFrequency.MONTHLY:
            next_dt = now + timedelta(days=30)
        elif frequency == ScheduleFrequency.QUARTERLY:
            next_dt = now + timedelta(days=91)
        elif frequency == ScheduleFrequency.YEARLY:
            next_dt = now + timedelta(days=365)
        else:
            next_dt = now + timedelta(days=30)
        return next_dt.isoformat()

    def run_scheduled_reports(self) -> list[GeneratedReport]:
        self._telemetry["run_scheduled_reports_calls"] += 1
        now = datetime.now(timezone.utc)
        executed = []

        def _to_aware(dt_str: str) -> datetime:
            try:
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return now

        for schedule in list(self._schedules.values()):
            if not schedule.is_active:
                continue
            next_run = _to_aware(schedule.next_run) if schedule.next_run else now
            if next_run > now:
                continue

            report = self.generate_report(schedule.report_def_id, schedule.format)
            if report:
                schedule.last_run = now.isoformat()
                schedule.next_run = self._compute_next_run(schedule.frequency)
                executed.append(report)
                logger.info("Executed scheduled report %s: %s", schedule.id, report.id)

        if executed:
            self._save()

        return executed

    def get_report_history(self, def_id: str) -> list[GeneratedReport]:
        self._telemetry["get_report_history_calls"] += 1
        results = []
        for report in self._generated_reports.values():
            if report.report_def_id == def_id:
                results.append(report)
        results.sort(key=lambda r: r.generated_at, reverse=True)
        return results

    def list_schedules(self, org_id: Optional[str] = None, is_active: Optional[bool] = None) -> list[ReportSchedule]:
        self._telemetry["list_schedules_calls"] += 1
        results = []
        for schedule in self._schedules.values():
            if org_id is not None and schedule.org_id != org_id:
                continue
            if is_active is not None and schedule.is_active != is_active:
                continue
            results.append(schedule)
        results.sort(key=lambda s: s.next_run)
        return results

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
