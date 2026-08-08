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


class DashboardType(Enum):
    CEO = "ceo"
    CTO = "cto"
    ENGINEERING = "engineering"
    FINANCE = "finance"
    OPERATIONS = "operations"
    SECURITY = "security"
    PRODUCT = "product"
    CUSTOMER_SUCCESS = "customer_success"


class DashboardPeriod(Enum):
    TODAY = "today"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    THIS_QUARTER = "this_quarter"
    THIS_YEAR = "this_year"
    CUSTOM = "custom"


class ChartType(Enum):
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    AREA = "area"
    TABLE = "table"
    METRIC_CARD = "metric_card"
    TREND = "trend"
    HEATMAP = "heatmap"
    FUNNEL = "funnel"
    SCATTER = "scatter"


class DashboardSeverity(Enum):
    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"
    INFO = "info"
    PENDING = "pending"


@dataclass
class DashboardConfig:
    id: str = ""
    name: str = ""
    type: DashboardType = DashboardType.CEO
    org_id: str = ""
    owner: str = ""
    period: DashboardPeriod = DashboardPeriod.THIS_MONTH
    sections: list = field(default_factory=list)
    refresh_interval_sec: int = 300
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DashboardConfig":
        data = data.copy()
        data["type"] = DashboardType(data.get("type", "ceo"))
        data["period"] = DashboardPeriod(data.get("period", "this_month"))
        return cls(**data)


@dataclass
class DashboardSection:
    id: str = ""
    title: str = ""
    charts: list = field(default_factory=list)
    order: int = 0
    grid_position: dict = field(default_factory=dict)
    size: str = "medium"
    visible: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DashboardSection":
        return cls(**data)


@dataclass
class ChartDefinition:
    id: str = ""
    title: str = ""
    type: ChartType = ChartType.LINE
    data_source: str = ""
    metric: str = ""
    group_by: str = ""
    filters: dict = field(default_factory=dict)
    order: int = 0
    options: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChartDefinition":
        data = data.copy()
        data["type"] = ChartType(data.get("type", "line"))
        return cls(**data)


@dataclass
class DashboardData:
    id: str = ""
    dashboard_id: str = ""
    type: DashboardType = DashboardType.CEO
    period: DashboardPeriod = DashboardPeriod.THIS_MONTH
    sections_data: list = field(default_factory=list)
    summary_metrics: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_until: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DashboardData":
        data = data.copy()
        data["type"] = DashboardType(data.get("type", "ceo"))
        data["period"] = DashboardPeriod(data.get("period", "this_month"))
        return cls(**data)


@dataclass
class ExecutiveKPISummary:
    id: str = ""
    org_id: str = ""
    type: DashboardType = DashboardType.CEO
    period: DashboardPeriod = DashboardPeriod.THIS_MONTH
    total_revenue: float = 0.0
    total_costs: float = 0.0
    gross_margin: float = 0.0
    active_users: int = 0
    total_repos: int = 0
    ai_requests: int = 0
    deployments: int = 0
    security_issues: int = 0
    uptime_percent: float = 0.0
    avg_response_time: float = 0.0
    net_promoter_score: float = 0.0
    customer_count: int = 0
    mrr: float = 0.0
    arr: float = 0.0
    burn_rate: float = 0.0
    runway_months: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutiveKPISummary":
        data = data.copy()
        data["type"] = DashboardType(data.get("type", "ceo"))
        data["period"] = DashboardPeriod(data.get("period", "this_month"))
        return cls(**data)


@dataclass
class AlertSummary:
    id: str = ""
    type: DashboardType = DashboardType.CEO
    severity: DashboardSeverity = DashboardSeverity.INFO
    message: str = ""
    metric: str = ""
    current_value: float = 0.0
    threshold: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: bool = False
    resolved_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AlertSummary":
        data = data.copy()
        data["type"] = DashboardType(data.get("type", "ceo"))
        data["severity"] = DashboardSeverity(data.get("severity", "info"))
        return cls(**data)


def _period_days(period: DashboardPeriod) -> int:
    mapping = {
        DashboardPeriod.TODAY: 1,
        DashboardPeriod.THIS_WEEK: 7,
        DashboardPeriod.THIS_MONTH: 30,
        DashboardPeriod.THIS_QUARTER: 91,
        DashboardPeriod.THIS_YEAR: 365,
        DashboardPeriod.CUSTOM: 30,
    }
    return mapping.get(period, 30)


def _generate_trend_data(days: int, base: float, variance: float, seed: int = 0) -> list[dict]:
    now = datetime.now(timezone.utc)
    data = []
    val = base
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        val += (hash(str(seed + i)) % 100 - 50) / 100 * variance
        val = max(0, val)
        data.append({"date": day, "value": round(val, 2)})
    return data


class ExecutiveDashboardManager:
    def __init__(self, storage_dir: str = "executive_dashboard_data"):
        self.storage_dir = storage_dir
        self._dashboard_configs: dict[str, DashboardConfig] = {}
        self._dashboard_data: dict[str, DashboardData] = {}
        self._kpi_summaries: dict[str, ExecutiveKPISummary] = {}
        self._alerts: dict[str, AlertSummary] = {}
        self._analytics: dict[str, dict] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _configs_path(self) -> str:
        return os.path.join(self.storage_dir, "dashboard_configs.json")

    def _data_path(self) -> str:
        return os.path.join(self.storage_dir, "dashboard_data.json")

    def _kpi_path(self) -> str:
        return os.path.join(self.storage_dir, "kpi_summaries.json")

    def _alerts_path(self) -> str:
        return os.path.join(self.storage_dir, "alerts.json")

    def _analytics_path(self) -> str:
        return os.path.join(self.storage_dir, "analytics.json")

    def _save(self) -> None:
        try:
            configs_data = {cid: c.to_dict() for cid, c in self._dashboard_configs.items()}
            with open(self._configs_path(), "w", encoding="utf-8") as f:
                json.dump(configs_data, f, indent=2, default=str)

            data_data = {did: d.to_dict() for did, d in self._dashboard_data.items()}
            with open(self._data_path(), "w", encoding="utf-8") as f:
                json.dump(data_data, f, indent=2, default=str)

            kpi_data = {kid: k.to_dict() for kid, k in self._kpi_summaries.items()}
            with open(self._kpi_path(), "w", encoding="utf-8") as f:
                json.dump(kpi_data, f, indent=2, default=str)

            alerts_data = {aid: a.to_dict() for aid, a in self._alerts.items()}
            with open(self._alerts_path(), "w", encoding="utf-8") as f:
                json.dump(alerts_data, f, indent=2, default=str)

            with open(self._analytics_path(), "w", encoding="utf-8") as f:
                json.dump(self._analytics, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save executive dashboard data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._configs_path()):
                with open(self._configs_path(), "r", encoding="utf-8") as f:
                    configs_data = json.load(f)
                for cid, data in configs_data.items():
                    try:
                        self._dashboard_configs[cid] = DashboardConfig.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed dashboard config %s: %s", cid, e)

            if os.path.exists(self._data_path()):
                with open(self._data_path(), "r", encoding="utf-8") as f:
                    data_data = json.load(f)
                for did, data in data_data.items():
                    try:
                        self._dashboard_data[did] = DashboardData.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed dashboard data %s: %s", did, e)

            if os.path.exists(self._kpi_path()):
                with open(self._kpi_path(), "r", encoding="utf-8") as f:
                    kpi_data = json.load(f)
                for kid, data in kpi_data.items():
                    try:
                        self._kpi_summaries[kid] = ExecutiveKPISummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed KPI summary %s: %s", kid, e)

            if os.path.exists(self._alerts_path()):
                with open(self._alerts_path(), "r", encoding="utf-8") as f:
                    alerts_data = json.load(f)
                for aid, data in alerts_data.items():
                    try:
                        self._alerts[aid] = AlertSummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed alert %s: %s", aid, e)

            if os.path.exists(self._analytics_path()):
                with open(self._analytics_path(), "r", encoding="utf-8") as f:
                    self._analytics = json.load(f)
        except Exception as e:
            logger.error("Failed to load executive dashboard data: %s", e, exc_info=True)

    def create_dashboard_config(self, config: DashboardConfig) -> DashboardConfig:
        self._telemetry["create_dashboard_config_calls"] += 1
        if not config.id:
            config.id = str(uuid.uuid4())
        config.created_at = datetime.now(timezone.utc).isoformat()
        config.updated_at = config.created_at
        self._dashboard_configs[config.id] = config
        self._save()
        logger.info("Created dashboard config %s: %s (%s)", config.id, config.name, config.type.value)
        return config

    def get_dashboard_config(self, dashboard_id: str) -> Optional[DashboardConfig]:
        self._telemetry["get_dashboard_config_calls"] += 1
        return self._dashboard_configs.get(dashboard_id)

    def update_dashboard_config(self, dashboard_id: str, updates: dict) -> Optional[DashboardConfig]:
        self._telemetry["update_dashboard_config_calls"] += 1
        config = self._dashboard_configs.get(dashboard_id)
        if not config:
            logger.warning("Attempted to update unknown dashboard config: %s", dashboard_id)
            return None
        for key, value in updates.items():
            if hasattr(config, key) and key not in ("id", "created_at"):
                if key == "type":
                    setattr(config, key, DashboardType(value) if isinstance(value, str) else value)
                elif key == "period":
                    setattr(config, key, DashboardPeriod(value) if isinstance(value, str) else value)
                else:
                    setattr(config, key, value)
        config.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated dashboard config: %s", dashboard_id)
        return config

    def list_dashboards(self, org_id: str) -> list[DashboardConfig]:
        self._telemetry["list_dashboards_calls"] += 1
        return [c for c in self._dashboard_configs.values() if c.org_id == org_id]

    def get_dashboard_data(self, dashboard_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["get_dashboard_data_calls"] += 1
        config = self._dashboard_configs.get(dashboard_id)
        if not config:
            logger.warning("No dashboard config found for id: %s", dashboard_id)
            return DashboardData(
                id=str(uuid.uuid4()),
                dashboard_id=dashboard_id,
                type=DashboardType.CEO,
                period=period,
                sections_data=[],
                summary_metrics={},
            )

        generator_map = {
            DashboardType.CEO: self.generate_ceo_dashboard,
            DashboardType.CTO: self.generate_cto_dashboard,
            DashboardType.ENGINEERING: self.generate_engineering_dashboard,
            DashboardType.FINANCE: self.generate_finance_dashboard,
            DashboardType.OPERATIONS: self.generate_operations_dashboard,
            DashboardType.SECURITY: self.generate_security_dashboard,
            DashboardType.PRODUCT: self.generate_product_dashboard,
            DashboardType.CUSTOMER_SUCCESS: self.generate_customer_success_dashboard,
        }
        generator = generator_map.get(config.type, self.generate_ceo_dashboard)
        dashboard_data = generator(config.org_id, period)
        dashboard_data.dashboard_id = dashboard_id
        self._dashboard_data[dashboard_data.id] = dashboard_data
        self._save()
        return dashboard_data

    def get_kpi_summary(self, org_id: str, type: DashboardType, period: DashboardPeriod) -> ExecutiveKPISummary:
        self._telemetry["get_kpi_summary_calls"] += 1
        days = _period_days(period)
        now = datetime.now(timezone.utc)
        seed_val = abs(hash(f"{org_id}_{type.value}_{period.value}")) % 10000

        mrr = round(100000 + (seed_val % 50000) + (days * 100), 2)
        total_revenue = round(mrr * 1.3, 2)
        total_costs = round(total_revenue * 0.65, 2)
        gross_margin = round((total_revenue - total_costs) / total_revenue * 100, 2) if total_revenue > 0 else 0.0
        burn_rate = round(total_costs / days if days > 0 else total_costs, 2)
        runway_months = round((total_revenue * 3) / max(burn_rate, 1), 2)

        summary = ExecutiveKPISummary(
            id=str(uuid.uuid4()),
            org_id=org_id,
            type=type,
            period=period,
            total_revenue=total_revenue,
            total_costs=total_costs,
            gross_margin=gross_margin,
            active_users=1000 + (seed_val % 500),
            total_repos=50 + (seed_val % 100),
            ai_requests=50000 + (seed_val % 30000),
            deployments=20 + (seed_val % 30),
            security_issues=seed_val % 20,
            uptime_percent=round(99.5 + (seed_val % 50) / 100, 2),
            avg_response_time=round(150 + (seed_val % 200), 1),
            net_promoter_score=round(50 + (seed_val % 40), 1),
            customer_count=50 + (seed_val % 150),
            mrr=mrr,
            arr=round(mrr * 12, 2),
            burn_rate=burn_rate,
            runway_months=runway_months,
        )
        self._kpi_summaries[summary.id] = summary
        self._save()
        return summary

    def generate_ceo_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_ceo_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"ceo_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.CEO, period)

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "Revenue & Growth",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Monthly Recurring Revenue",
                        "type": ChartType.AREA.value,
                        "data": _generate_trend_data(days, kpi.mrr / days, kpi.mrr / days * 0.3, seed),
                        "summary": f"${kpi.mrr:,.2f}",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Revenue vs Costs",
                        "type": ChartType.LINE.value,
                        "data": [
                            {"date": d["date"], "revenue": d["value"] * 1.3, "costs": d["value"] * 0.85}
                            for d in _generate_trend_data(days, kpi.mrr / days, kpi.mrr / days * 0.2, seed + 1)
                        ],
                        "summary": f"Gross Margin: {kpi.gross_margin}%",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Key Metrics",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "ARR / MRR",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "ARR", "value": f"${kpi.arr:,.2f}"},
                            {"label": "MRR", "value": f"${kpi.mrr:,.2f}"},
                            {"label": "Burn Rate", "value": f"${kpi.burn_rate:,.2f}/day"},
                            {"label": "Runway", "value": f"{kpi.runway_months:.1f} months"},
                        ],
                        "summary": "",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Customer Growth",
                        "type": ChartType.BAR.value,
                        "data": _generate_trend_data(min(days, 12), kpi.customer_count / 12, kpi.customer_count * 0.1, seed + 2),
                        "summary": f"{kpi.customer_count} customers",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "NPS & User Activity",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Net Promoter Score",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [{"label": "NPS", "value": kpi.net_promoter_score}],
                        "summary": f"Score: {kpi.net_promoter_score}",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Active Users Trend",
                        "type": ChartType.TREND.value,
                        "data": _generate_trend_data(days, kpi.active_users / days, kpi.active_users * 0.15, seed + 3),
                        "summary": f"{kpi.active_users} active users",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 4, "h": 2},
                "size": "medium",
                "visible": True,
            },
        ]

        summary_metrics = {
            "total_revenue": kpi.total_revenue,
            "total_costs": kpi.total_costs,
            "gross_margin": kpi.gross_margin,
            "mrr": kpi.mrr,
            "arr": kpi.arr,
            "customer_count": kpi.customer_count,
            "active_users": kpi.active_users,
            "net_promoter_score": kpi.net_promoter_score,
            "burn_rate": kpi.burn_rate,
            "runway_months": kpi.runway_months,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.CEO,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.CEO.value,
        }
        return dashboard_data

    def generate_cto_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_cto_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"cto_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.CTO, period)

        infrastructure_cost = 45000 + (seed % 15000)
        deploy_count = kpi.deployments + (seed % 5)

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "Infrastructure Overview",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Infrastructure Cost",
                        "type": ChartType.AREA.value,
                        "data": _generate_trend_data(days, infrastructure_cost / days, 200, seed),
                        "summary": f"${infrastructure_cost:,.2f} total",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "System Uptime",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "Uptime", "value": f"{kpi.uptime_percent}%"},
                            {"label": "Avg Response", "value": f"{kpi.avg_response_time}ms"},
                            {"label": "Deployments", "value": str(deploy_count)},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Deployment Pipeline",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Deployments Over Time",
                        "type": ChartType.BAR.value,
                        "data": _generate_trend_data(days, 3, 2, seed + 1),
                        "summary": f"{deploy_count} total deployments",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Performance Metrics",
                        "type": ChartType.TABLE.value,
                        "data": [
                            {"metric": "P50 Latency", "value": f"{120 + seed % 40}ms", "status": "healthy"},
                            {"metric": "P95 Latency", "value": f"{300 + seed % 100}ms", "status": "healthy"},
                            {"metric": "P99 Latency", "value": f"{800 + seed % 400}ms", "status": "warning"},
                            {"metric": "Error Rate", "value": f"{(seed % 100) / 100:.2f}%", "status": "healthy"},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Resource Utilization",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "CPU / Memory / GPU",
                        "type": ChartType.TREND.value,
                        "data": [
                            {"date": d["date"], "cpu": round(40 + (seed + i) % 40, 1), "memory": round(50 + (seed + i * 2) % 30, 1), "gpu": round(30 + (seed + i * 3) % 50, 1)}
                            for i, d in enumerate(_generate_trend_data(days, 50, 15, seed + 2))
                        ],
                        "summary": "Resource usage over time",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 12, "h": 2},
                "size": "large",
                "visible": True,
            },
        ]

        summary_metrics = {
            "uptime_percent": kpi.uptime_percent,
            "avg_response_time": kpi.avg_response_time,
            "deployments": deploy_count,
            "infrastructure_cost": infrastructure_cost,
            "ai_requests": kpi.ai_requests,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.CTO,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.CTO.value,
        }
        return dashboard_data

    def generate_engineering_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_engineering_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"eng_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.ENGINEERING, period)

        pr_count = 40 + (seed % 60)
        reviews_count = 80 + (seed % 100)
        velocity = 15 + (seed % 20)

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "Engineering Velocity",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Pull Requests",
                        "type": ChartType.BAR.value,
                        "data": _generate_trend_data(days, pr_count / days, 1.5, seed),
                        "summary": f"{pr_count} PRs ({reviews_count} reviews)",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Deployment Velocity",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "Deployments", "value": str(kpi.deployments)},
                            {"label": "Velocity", "value": f"{velocity}/day"},
                            {"label": "Repos", "value": str(kpi.total_repos)},
                            {"label": "AI Requests", "value": str(kpi.ai_requests)},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Code Review & Quality",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Review Turnaround Time",
                        "type": ChartType.LINE.value,
                        "data": _generate_trend_data(days, 4, 2, seed + 1),
                        "summary": "Avg hours to review",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "PR Merge Rate",
                        "type": ChartType.PIE.value,
                        "data": [
                            {"label": "Merged", "value": pr_count},
                            {"label": "Open", "value": max(1, pr_count // 3)},
                            {"label": "Closed without merge", "value": max(1, pr_count // 6)},
                        ],
                        "summary": f"{round(pr_count / max(pr_count + pr_count // 3, 1) * 100, 1)}% merge rate",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "AI Contribution",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "AI Requests Trend",
                        "type": ChartType.TREND.value,
                        "data": _generate_trend_data(days, kpi.ai_requests / days, 500, seed + 2),
                        "summary": f"{kpi.ai_requests} total AI requests",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 12, "h": 2},
                "size": "large",
                "visible": True,
            },
        ]

        summary_metrics = {
            "pull_requests": pr_count,
            "reviews": reviews_count,
            "deployments": kpi.deployments,
            "velocity": velocity,
            "total_repos": kpi.total_repos,
            "ai_requests": kpi.ai_requests,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.ENGINEERING,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.ENGINEERING.value,
        }
        return dashboard_data

    def generate_finance_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_finance_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"fin_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.FINANCE, period)

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "Cost Breakdown",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Costs by Category",
                        "type": ChartType.PIE.value,
                        "data": [
                            {"label": "Infrastructure", "value": kpi.total_costs * 0.4},
                            {"label": "AI/ML Services", "value": kpi.total_costs * 0.25},
                            {"label": "Engineering", "value": kpi.total_costs * 0.15},
                            {"label": "Operations", "value": kpi.total_costs * 0.1},
                            {"label": "Other", "value": kpi.total_costs * 0.1},
                        ],
                        "summary": f"Total: ${kpi.total_costs:,.2f}",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Budget vs Actual",
                        "type": ChartType.BAR.value,
                        "data": [
                            {"category": "Infrastructure", "budget": round(kpi.total_costs * 0.35, 2), "actual": round(kpi.total_costs * 0.4, 2)},
                            {"category": "AI/ML", "budget": round(kpi.total_costs * 0.2, 2), "actual": round(kpi.total_costs * 0.25, 2)},
                            {"category": "Engineering", "budget": round(kpi.total_costs * 0.18, 2), "actual": round(kpi.total_costs * 0.15, 2)},
                            {"category": "Operations", "budget": round(kpi.total_costs * 0.12, 2), "actual": round(kpi.total_costs * 0.1, 2)},
                        ],
                        "summary": "Budget comparison",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Financial Health",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "MRR / ARR / Burn Rate",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "MRR", "value": f"${kpi.mrr:,.2f}"},
                            {"label": "ARR", "value": f"${kpi.arr:,.2f}"},
                            {"label": "Burn Rate", "value": f"${kpi.burn_rate:,.2f}/day"},
                            {"label": "Runway", "value": f"{kpi.runway_months:.1f} months"},
                        ],
                        "summary": "",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Revenue Trend",
                        "type": ChartType.TREND.value,
                        "data": _generate_trend_data(days, kpi.total_revenue / days, kpi.total_revenue / days * 0.2, seed),
                        "summary": f"${kpi.total_revenue:,.2f} total",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Forecast",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "30-Day Spend Forecast",
                        "type": ChartType.AREA.value,
                        "data": _generate_trend_data(30, kpi.total_costs / days, 100, seed + 1),
                        "summary": f"Projected: ${kpi.total_costs * 1.1:,.2f}",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 12, "h": 2},
                "size": "large",
                "visible": True,
            },
        ]

        summary_metrics = {
            "total_revenue": kpi.total_revenue,
            "total_costs": kpi.total_costs,
            "gross_margin": kpi.gross_margin,
            "mrr": kpi.mrr,
            "arr": kpi.arr,
            "burn_rate": kpi.burn_rate,
            "runway_months": kpi.runway_months,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.FINANCE,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.FINANCE.value,
        }
        return dashboard_data

    def generate_operations_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_operations_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"ops_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.OPERATIONS, period)

        incidents = 5 + (seed % 15)
        resources = {"servers": 12 + seed % 8, "containers": 45 + seed % 30, "databases": 4 + seed % 4}

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "System Health",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Incidents Over Time",
                        "type": ChartType.BAR.value,
                        "data": _generate_trend_data(days, incidents / days, 0.5, seed),
                        "summary": f"{incidents} incidents",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Resource Pool",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "Servers", "value": str(resources["servers"])},
                            {"label": "Containers", "value": str(resources["containers"])},
                            {"label": "Databases", "value": str(resources["databases"])},
                            {"label": "Uptime", "value": f"{kpi.uptime_percent}%"},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Incident Response",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "MTTR / MTBF",
                        "type": ChartType.TABLE.value,
                        "data": [
                            {"metric": "Mean Time to Resolve", "value": f"{30 + seed % 60} min", "status": "healthy"},
                            {"metric": "Mean Time Between Failures", "value": f"{72 + seed % 48} hr", "status": "healthy"},
                            {"metric": "Critical Incidents", "value": str(max(1, incidents // 4)), "status": "warning"},
                            {"metric": "Avg Response Time", "value": f"{kpi.avg_response_time}ms", "status": "healthy"},
                        ],
                        "summary": "",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Resource Utilization Heatmap",
                        "type": ChartType.HEATMAP.value,
                        "data": [
                            {"hour": h, "day": d, "value": round(30 + (seed + h + d * 3) % 50, 1)}
                            for h in range(24) for d in range(7)
                        ][:50],
                        "summary": "CPU load by hour/day",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Cost & Capacity",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Operational Costs",
                        "type": ChartType.AREA.value,
                        "data": _generate_trend_data(days, kpi.total_costs / days * 0.3, 50, seed + 1),
                        "summary": f"${kpi.total_costs * 0.3:,.2f} total",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 12, "h": 2},
                "size": "large",
                "visible": True,
            },
        ]

        summary_metrics = {
            "incidents": incidents,
            "uptime_percent": kpi.uptime_percent,
            "avg_response_time": kpi.avg_response_time,
            "resources": resources,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.OPERATIONS,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.OPERATIONS.value,
        }
        return dashboard_data

    def generate_security_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_security_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"sec_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.SECURITY, period)

        vulns = kpi.security_issues + (seed % 10)
        scans = 10 + (seed % 20)
        compliance_score = round(85 + (seed % 15), 1)

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "Vulnerability Overview",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Vulnerabilities by Severity",
                        "type": ChartType.PIE.value,
                        "data": [
                            {"label": "Critical", "value": max(1, vulns // 5)},
                            {"label": "High", "value": max(1, vulns // 3)},
                            {"label": "Medium", "value": max(1, vulns // 2)},
                            {"label": "Low", "value": max(1, vulns - vulns // 5 - vulns // 3 - vulns // 2)},
                        ],
                        "summary": f"{vulns} total vulnerabilities",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Security Scans",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "Scans Run", "value": str(scans)},
                            {"label": "Vulnerabilities", "value": str(vulns)},
                            {"label": "Compliance", "value": f"{compliance_score}%"},
                            {"label": "AI Requests", "value": str(kpi.ai_requests)},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Compliance & Scans",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Compliance Score Trend",
                        "type": ChartType.LINE.value,
                        "data": _generate_trend_data(days, compliance_score, 2, seed),
                        "summary": f"{compliance_score}% compliance",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Scan Results Over Time",
                        "type": ChartType.BAR.value,
                        "data": _generate_trend_data(days, scans / days, 0.3, seed + 1),
                        "summary": f"{scans} scans performed",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Recent Alerts",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Security Alerts",
                        "type": ChartType.TABLE.value,
                        "data": [
                            {"severity": "Critical", "title": "SQL Injection detected", "status": "open", "age": f"{seed % 5}d"},
                            {"severity": "High", "title": "Deprecated TLS version", "status": "in_progress", "age": f"{seed % 10}d"},
                            {"severity": "Medium", "title": "Missing rate limiting", "status": "open", "age": f"{seed % 15}d"},
                            {"severity": "Low", "title": "Info leak in headers", "status": "resolved", "age": f"{seed % 20}d"},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 12, "h": 2},
                "size": "large",
                "visible": True,
            },
        ]

        summary_metrics = {
            "vulnerabilities": vulns,
            "scans": scans,
            "compliance_score": compliance_score,
            "security_issues": kpi.security_issues,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.SECURITY,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.SECURITY.value,
        }
        return dashboard_data

    def generate_product_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_product_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"prod_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.PRODUCT, period)

        feature_adoption = round(35 + (seed % 50), 1)
        sessions = 5000 + (seed % 5000)

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "Feature Adoption & Usage",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Feature Adoption Rate",
                        "type": ChartType.LINE.value,
                        "data": _generate_trend_data(days, feature_adoption, 3, seed),
                        "summary": f"{feature_adoption}% adoption",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "User Engagement",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "Active Users", "value": str(kpi.active_users)},
                            {"label": "Sessions", "value": str(sessions)},
                            {"label": "AI Requests", "value": str(kpi.ai_requests)},
                            {"label": "Feature Adoption", "value": f"{feature_adoption}%"},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Engagement Metrics",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Daily Active Users",
                        "type": ChartType.AREA.value,
                        "data": _generate_trend_data(days, kpi.active_users / days, 10, seed + 1),
                        "summary": f"{kpi.active_users} DAU",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Feature Usage Distribution",
                        "type": ChartType.PIE.value,
                        "data": [
                            {"label": "Code Review", "value": 35},
                            {"label": "AI Chat", "value": 25},
                            {"label": "Search", "value": 20},
                            {"label": "Docs Gen", "value": 12},
                            {"label": "Other", "value": 8},
                        ],
                        "summary": "Usage by feature",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Product Funnel",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "User Conversion Funnel",
                        "type": ChartType.FUNNEL.value,
                        "data": [
                            {"stage": "Signed Up", "value": 1000},
                            {"stage": "Onboarded", "value": 750},
                            {"stage": "Active Day 7", "value": 500},
                            {"stage": "Active Day 30", "value": 300},
                            {"stage": "Paid", "value": 150},
                        ],
                        "summary": "Conversion funnel",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 12, "h": 2},
                "size": "large",
                "visible": True,
            },
        ]

        summary_metrics = {
            "active_users": kpi.active_users,
            "sessions": sessions,
            "feature_adoption": feature_adoption,
            "ai_requests": kpi.ai_requests,
            "net_promoter_score": kpi.net_promoter_score,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.PRODUCT,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.PRODUCT.value,
        }
        return dashboard_data

    def generate_customer_success_dashboard(self, org_id: str, period: DashboardPeriod) -> DashboardData:
        self._telemetry["generate_customer_success_dashboard_calls"] += 1
        days = _period_days(period)
        seed = abs(hash(f"cs_{org_id}_{period.value}")) % 10000
        kpi = self.get_kpi_summary(org_id, DashboardType.CUSTOMER_SUCCESS, period)

        support_tickets = 50 + (seed % 100)
        retention_rate = round(85 + (seed % 12), 1)
        csat_score = round(3.5 + (seed % 15) / 10, 1)

        sections_data = [
            {
                "id": str(uuid.uuid4()),
                "title": "Customer Health",
                "order": 1,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "NPS & CSAT",
                        "type": ChartType.METRIC_CARD.value,
                        "data": [
                            {"label": "NPS", "value": kpi.net_promoter_score},
                            {"label": "CSAT", "value": f"{csat_score}/5"},
                            {"label": "Retention", "value": f"{retention_rate}%"},
                            {"label": "Customers", "value": str(kpi.customer_count)},
                        ],
                        "summary": "",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Support Tickets",
                        "type": ChartType.BAR.value,
                        "data": _generate_trend_data(days, support_tickets / days, 2, seed),
                        "summary": f"{support_tickets} tickets",
                    },
                ],
                "grid_position": {"x": 0, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Retention & Churn",
                "order": 2,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Retention Rate Trend",
                        "type": ChartType.LINE.value,
                        "data": _generate_trend_data(days, retention_rate, 1, seed + 1),
                        "summary": f"{retention_rate}% retention",
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "title": "Ticket Resolution",
                        "type": ChartType.TABLE.value,
                        "data": [
                            {"metric": "Open Tickets", "value": str(max(1, support_tickets // 4)), "status": "warning"},
                            {"metric": "Avg Resolution", "value": f"{4 + seed % 8} hr", "status": "healthy"},
                            {"metric": "First Response", "value": f"{15 + seed % 30} min", "status": "healthy"},
                            {"metric": "SLA Breach", "value": f"{seed % 5}%", "status": "warning"},
                        ],
                        "summary": "",
                    },
                ],
                "grid_position": {"x": 6, "y": 0, "w": 6, "h": 2},
                "size": "large",
                "visible": True,
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Customer Growth",
                "order": 3,
                "charts": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": "MRR / Customer",
                        "type": ChartType.TREND.value,
                        "data": _generate_trend_data(days, kpi.mrr / max(kpi.customer_count, 1), 10, seed + 2),
                        "summary": f"${kpi.mrr / max(kpi.customer_count, 1):,.2f} per customer",
                    },
                ],
                "grid_position": {"x": 0, "y": 2, "w": 12, "h": 2},
                "size": "large",
                "visible": True,
            },
        ]

        summary_metrics = {
            "net_promoter_score": kpi.net_promoter_score,
            "csat_score": csat_score,
            "retention_rate": retention_rate,
            "support_tickets": support_tickets,
            "customer_count": kpi.customer_count,
            "mrr": kpi.mrr,
        }

        dashboard_data = DashboardData(
            id=str(uuid.uuid4()),
            dashboard_id="",
            type=DashboardType.CUSTOMER_SUCCESS,
            period=period,
            sections_data=sections_data,
            summary_metrics=summary_metrics,
        )
        self._analytics[dashboard_data.id] = {
            "views": self._analytics.get(dashboard_data.id, {}).get("views", 0) + 1,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "type": DashboardType.CUSTOMER_SUCCESS.value,
        }
        return dashboard_data

    def create_alert(self, alert: AlertSummary) -> AlertSummary:
        self._telemetry["create_alert_calls"] += 1
        if not alert.id:
            alert.id = str(uuid.uuid4())
        alert.timestamp = datetime.now(timezone.utc).isoformat()
        self._alerts[alert.id] = alert
        self._save()
        logger.info("Created alert %s: [%s] %s", alert.id, alert.severity.value, alert.message)
        return alert

    def list_alerts(self, dashboard_id: str) -> list[AlertSummary]:
        self._telemetry["list_alerts_calls"] += 1
        return [a for a in self._alerts.values() if a.type.value == dashboard_id or dashboard_id == ""]

    def dismiss_alert(self, alert_id: str) -> bool:
        self._telemetry["dismiss_alert_calls"] += 1
        alert = self._alerts.get(alert_id)
        if not alert:
            logger.warning("Attempted to dismiss unknown alert: %s", alert_id)
            return False
        alert.acknowledged = True
        alert.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Dismissed alert: %s", alert_id)
        return True

    def get_dashboard_analytics(self, dashboard_id: str) -> dict:
        self._telemetry["get_dashboard_analytics_calls"] += 1
        return self._analytics.get(dashboard_id, {
            "views": 0,
            "last_accessed": "",
            "org_id": "",
            "type": "",
        })

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
