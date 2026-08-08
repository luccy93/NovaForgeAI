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


class InfraResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    STORAGE = "storage"
    BANDWIDTH = "bandwidth"
    DATABASE = "database"
    REDIS = "redis"
    NEO4J = "neo4j"
    QDRANT = "qdrant"
    OBJECT_STORAGE = "object_storage"
    CONTAINER = "container"
    NETWORK = "network"
    LOAD_BALANCER = "load_balancer"
    MONITORING = "monitoring"
    LOGGING = "logging"
    CI_CD = "ci_cd"
    SERVERLESS = "serverless"
    API_GATEWAY = "api_gateway"
    CDN = "cdn"
    DNS = "dns"
    SECURITY = "security"
    BACKUP = "backup"


class InfraProvider(Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    DIGITAL_OCEAN = "digital_ocean"
    LINODE = "linode"
    VULTR = "vultr"
    HETZNER = "hetzner"
    OVH = "ovh"
    CLOUDFLARE = "cloudflare"
    FASTLY = "fastly"
    SELF_HOSTED = "self_hosted"
    CUSTOM = "custom"


class ResourceState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    PROVISIONING = "provisioning"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class AllocationMethod(Enum):
    DIRECT = "direct"
    SHARED = "shared"
    RESERVED = "reserved"
    SPOT = "spot"
    ON_DEMAND = "on_demand"
    SAVINGS_PLAN = "savings_plan"


@dataclass
class InfraResource:
    id: str
    name: str
    resource_type: InfraResourceType
    provider: InfraProvider
    region: str
    state: ResourceState
    allocation: AllocationMethod
    specifications: dict
    hourly_cost: float = 0.0
    monthly_estimate: float = 0.0
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        d["provider"] = self.provider.value
        d["state"] = self.state.value
        d["allocation"] = self.allocation.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InfraResource":
        data = data.copy()
        data["resource_type"] = InfraResourceType(data.get("resource_type", "cpu"))
        data["provider"] = InfraProvider(data.get("provider", "aws"))
        data["state"] = ResourceState(data.get("state", "unknown"))
        data["allocation"] = AllocationMethod(data.get("allocation", "on_demand"))
        return cls(**data)


@dataclass
class InfraCostEntry:
    id: str
    org_id: str
    workspace_id: str
    resource_id: str
    resource_type: InfraResourceType
    provider: InfraProvider
    cost: float = 0.0
    usage_amount: float = 0.0
    usage_unit: str = ""
    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    region: str = ""
    allocation: AllocationMethod = AllocationMethod.ON_DEMAND
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        d["provider"] = self.provider.value
        d["allocation"] = self.allocation.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InfraCostEntry":
        data = data.copy()
        data["resource_type"] = InfraResourceType(data.get("resource_type", "cpu"))
        data["provider"] = InfraProvider(data.get("provider", "aws"))
        data["allocation"] = AllocationMethod(data.get("allocation", "on_demand"))
        return cls(**data)


@dataclass
class InfraBudget:
    id: str
    org_id: str
    name: str
    resource_type: InfraResourceType
    provider: InfraProvider
    period: str
    limit: float = 0.0
    current_spend: float = 0.0
    alert_threshold: float = 80.0
    start_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_date: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InfraBudget":
        data = data.copy()
        data["resource_type"] = InfraResourceType(data.get("resource_type", "cpu"))
        data["provider"] = InfraProvider(data.get("provider", "aws"))
        return cls(**data)


@dataclass
class ResourceUtilization:
    id: str
    resource_id: str
    resource_type: InfraResourceType
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    gpu_percent: float = 0.0
    storage_percent: float = 0.0
    disk_iops: float = 0.0
    network_in_bytes: int = 0
    network_out_bytes: int = 0
    requests_per_sec: float = 0.0
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ResourceUtilization":
        data = data.copy()
        data["resource_type"] = InfraResourceType(data.get("resource_type", "cpu"))
        return cls(**data)


@dataclass
class InfraCostSummary:
    id: str
    org_id: str
    start_date: str
    end_date: str
    total_cost: float = 0.0
    by_resource_type: dict = field(default_factory=dict)
    by_provider: dict = field(default_factory=dict)
    by_region: dict = field(default_factory=dict)
    by_allocation: dict = field(default_factory=dict)
    cost_per_resource: dict = field(default_factory=dict)
    utilization_scores: dict = field(default_factory=dict)
    savings_opportunities: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "InfraCostSummary":
        return cls(**data)


class InfrastructureCostManager:
    def __init__(self, storage_dir: str = "infra_cost_data"):
        self.storage_dir = storage_dir
        self._resources: dict[str, InfraResource] = {}
        self._cost_entries: dict[str, InfraCostEntry] = {}
        self._budgets: dict[str, InfraBudget] = {}
        self._utilizations: dict[str, ResourceUtilization] = {}
        self._summaries: dict[str, InfraCostSummary] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _resources_path(self) -> str:
        return os.path.join(self.storage_dir, "resources.json")

    def _cost_entries_path(self) -> str:
        return os.path.join(self.storage_dir, "cost_entries.json")

    def _budgets_path(self) -> str:
        return os.path.join(self.storage_dir, "budgets.json")

    def _utilizations_path(self) -> str:
        return os.path.join(self.storage_dir, "utilizations.json")

    def _summaries_path(self) -> str:
        return os.path.join(self.storage_dir, "summaries.json")

    def _save(self) -> None:
        try:
            resources_data = {rid: r.to_dict() for rid, r in self._resources.items()}
            with open(self._resources_path(), "w", encoding="utf-8") as f:
                json.dump(resources_data, f, indent=2, default=str)

            entries_data = {eid: e.to_dict() for eid, e in self._cost_entries.items()}
            with open(self._cost_entries_path(), "w", encoding="utf-8") as f:
                json.dump(entries_data, f, indent=2, default=str)

            budgets_data = {bid: b.to_dict() for bid, b in self._budgets.items()}
            with open(self._budgets_path(), "w", encoding="utf-8") as f:
                json.dump(budgets_data, f, indent=2, default=str)

            utilizations_data = {uid: u.to_dict() for uid, u in self._utilizations.items()}
            with open(self._utilizations_path(), "w", encoding="utf-8") as f:
                json.dump(utilizations_data, f, indent=2, default=str)

            summaries_data = {sid: s.to_dict() for sid, s in self._summaries.items()}
            with open(self._summaries_path(), "w", encoding="utf-8") as f:
                json.dump(summaries_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save infrastructure cost data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._resources_path()):
                with open(self._resources_path(), "r", encoding="utf-8") as f:
                    resources_data = json.load(f)
                for rid, data in resources_data.items():
                    try:
                        self._resources[rid] = InfraResource.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed resource %s: %s", rid, e)

            if os.path.exists(self._cost_entries_path()):
                with open(self._cost_entries_path(), "r", encoding="utf-8") as f:
                    entries_data = json.load(f)
                for eid, data in entries_data.items():
                    try:
                        self._cost_entries[eid] = InfraCostEntry.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed cost entry %s: %s", eid, e)

            if os.path.exists(self._budgets_path()):
                with open(self._budgets_path(), "r", encoding="utf-8") as f:
                    budgets_data = json.load(f)
                for bid, data in budgets_data.items():
                    try:
                        self._budgets[bid] = InfraBudget.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed budget %s: %s", bid, e)

            if os.path.exists(self._utilizations_path()):
                with open(self._utilizations_path(), "r", encoding="utf-8") as f:
                    utilizations_data = json.load(f)
                for uid, data in utilizations_data.items():
                    try:
                        self._utilizations[uid] = ResourceUtilization.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed utilization %s: %s", uid, e)

            if os.path.exists(self._summaries_path()):
                with open(self._summaries_path(), "r", encoding="utf-8") as f:
                    summaries_data = json.load(f)
                for sid, data in summaries_data.items():
                    try:
                        self._summaries[sid] = InfraCostSummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed summary %s: %s", sid, e)
        except Exception as e:
            logger.error("Failed to load infrastructure cost data: %s", e, exc_info=True)

    def register_resource(self, resource: InfraResource) -> InfraResource:
        self._telemetry["register_resource_calls"] += 1
        if not resource.id:
            resource.id = str(uuid.uuid4())
        resource.updated_at = datetime.now(timezone.utc).isoformat()
        self._resources[resource.id] = resource
        self._save()
        logger.info("Registered infrastructure resource %s: %s (%s)", resource.id, resource.name, resource.resource_type.value)
        return resource

    def update_resource(self, resource_id: str, updates: dict) -> Optional[InfraResource]:
        self._telemetry["update_resource_calls"] += 1
        resource = self._resources.get(resource_id)
        if not resource:
            logger.warning("Attempted to update unknown resource: %s", resource_id)
            return None
        for key, value in updates.items():
            if hasattr(resource, key) and key not in ("id", "created_at"):
                if key == "resource_type":
                    setattr(resource, key, InfraResourceType(value) if isinstance(value, str) else value)
                elif key == "provider":
                    setattr(resource, key, InfraProvider(value) if isinstance(value, str) else value)
                elif key == "state":
                    setattr(resource, key, ResourceState(value) if isinstance(value, str) else value)
                elif key == "allocation":
                    setattr(resource, key, AllocationMethod(value) if isinstance(value, str) else value)
                else:
                    setattr(resource, key, value)
        resource.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated resource: %s", resource_id)
        return resource

    def list_resources(self, org_id: Optional[str] = None, resource_type: Optional[InfraResourceType] = None) -> list[InfraResource]:
        self._telemetry["list_resources_calls"] += 1
        results = []
        for resource in self._resources.values():
            if org_id is not None and org_id not in resource.id:
                continue
            if resource_type is not None and resource.resource_type != resource_type:
                continue
            results.append(resource)
        return results

    def track_cost(self, entry: InfraCostEntry) -> InfraCostEntry:
        self._telemetry["track_cost_calls"] += 1
        if not entry.id:
            entry.id = str(uuid.uuid4())
        if not entry.start_time:
            entry.start_time = datetime.now(timezone.utc).isoformat()
        if not entry.end_time:
            entry.end_time = entry.start_time
        self._cost_entries[entry.id] = entry

        # Update budget current_spend for matching org budgets
        for budget in self._budgets.values():
            if budget.org_id == entry.org_id:
                budget.current_spend = round(budget.current_spend + entry.cost, 4)

        self._save()
        logger.info("Tracked infra cost entry %s: %.4f for resource %s", entry.id, entry.cost, entry.resource_id)
        return entry

    def get_costs(self, org_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[InfraCostEntry]:
        self._telemetry["get_costs_calls"] += 1
        results = []
        for entry in self._cost_entries.values():
            if entry.org_id != org_id:
                continue
            if start_date and entry.start_time[:10] < start_date:
                continue
            if end_date and entry.start_time[:10] > end_date:
                continue
            results.append(entry)
        results.sort(key=lambda e: e.start_time)
        return results

    def get_cost_summary(self, org_id: str, start_date: str, end_date: str) -> InfraCostSummary:
        self._telemetry["get_cost_summary_calls"] += 1
        filtered = [
            e for e in self._cost_entries.values()
            if e.org_id == org_id and start_date <= e.start_time[:10] <= end_date
        ]

        total_cost = round(sum(e.cost for e in filtered), 4)

        by_resource_type: dict[str, float] = defaultdict(float)
        by_provider: dict[str, float] = defaultdict(float)
        by_region: dict[str, float] = defaultdict(float)
        by_allocation: dict[str, float] = defaultdict(float)
        cost_per_resource: dict[str, float] = defaultdict(float)
        total_utilization: dict[str, list[float]] = defaultdict(list)

        for e in filtered:
            by_resource_type[e.resource_type.value] += e.cost
            by_provider[e.provider.value] += e.cost
            by_region[e.region] += e.cost
            by_allocation[e.allocation.value] += e.cost
            cost_per_resource[e.resource_id] += e.cost

        by_resource_type = {k: round(v, 4) for k, v in by_resource_type.items()}
        by_provider = {k: round(v, 4) for k, v in by_provider.items()}
        by_region = {k: round(v, 4) for k, v in by_region.items()}
        by_allocation = {k: round(v, 4) for k, v in by_allocation.items()}
        cost_per_resource = {k: round(v, 4) for k, v in cost_per_resource.items()}

        # Compute average utilization scores for resources that have utilization data
        utilization_scores: dict[str, float] = {}
        for util in self._utilizations.values():
            if util.resource_id in cost_per_resource:
                total_utilization[util.resource_id].append(
                    (util.cpu_percent + util.memory_percent + util.gpu_percent) / 3.0
                )
        for rid, scores in total_utilization.items():
            if scores:
                utilization_scores[rid] = round(sum(scores) / len(scores), 2)

        # Identify savings opportunities from underutilized resources
        savings_opportunities = []
        for rid, avg_util in utilization_scores.items():
            if avg_util < 20.0:
                resource = self._resources.get(rid)
                if resource:
                    potential_savings = round(resource.monthly_estimate * 0.5, 4)
                    savings_opportunities.append({
                        "resource_id": rid,
                        "resource_name": resource.name,
                        "resource_type": resource.resource_type.value,
                        "avg_utilization": avg_util,
                        "monthly_cost": resource.monthly_estimate,
                        "potential_savings": potential_savings,
                        "recommendation": "Consider downsizing or terminating underutilized resource",
                    })
        savings_opportunities.sort(key=lambda x: x["potential_savings"], reverse=True)

        summary = InfraCostSummary(
            id=str(uuid.uuid4()),
            org_id=org_id,
            start_date=start_date,
            end_date=end_date,
            total_cost=total_cost,
            by_resource_type=by_resource_type,
            by_provider=by_provider,
            by_region=by_region,
            by_allocation=by_allocation,
            cost_per_resource=cost_per_resource,
            utilization_scores=utilization_scores,
            savings_opportunities=savings_opportunities,
        )
        self._summaries[summary.id] = summary
        self._save()
        return summary

    def record_utilization(self, utilization: ResourceUtilization) -> ResourceUtilization:
        self._telemetry["record_utilization_calls"] += 1
        if not utilization.id:
            utilization.id = str(uuid.uuid4())
        if not utilization.timestamp:
            utilization.timestamp = datetime.now(timezone.utc).isoformat()
        self._utilizations[utilization.id] = utilization
        self._save()
        logger.info("Recorded utilization %s for resource %s", utilization.id, utilization.resource_id)
        return utilization

    def get_utilization(self, resource_id: str, hours: int = 24) -> list[ResourceUtilization]:
        self._telemetry["get_utilization_calls"] += 1
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        results = []
        for util in self._utilizations.values():
            if util.resource_id == resource_id and util.timestamp >= cutoff:
                results.append(util)
        results.sort(key=lambda u: u.timestamp)
        return results

    def get_underutilized_resources(self, org_id: str, threshold: float = 0.2) -> list[dict]:
        self._telemetry["get_underutilized_resources_calls"] += 1
        resource_utils: dict[str, list[ResourceUtilization]] = defaultdict(list)
        for util in self._utilizations.values():
            resource_utils[util.resource_id].append(util)

        underutilized = []
        for rid, utils in resource_utils.items():
            resource = self._resources.get(rid)
            if not resource:
                continue
            if org_id and org_id not in rid:
                continue
            if not utils:
                continue
            avg_cpu = sum(u.cpu_percent for u in utils) / len(utils)
            avg_mem = sum(u.memory_percent for u in utils) / len(utils)
            avg_gpu = sum(u.gpu_percent for u in utils) / len(utils)
            avg_storage = sum(u.storage_percent for u in utils) / len(utils)

            overall = (avg_cpu + avg_mem + avg_gpu + avg_storage) / 4.0
            if overall < threshold * 100:
                underutilized.append({
                    "resource_id": rid,
                    "resource_name": resource.name,
                    "resource_type": resource.resource_type.value,
                    "provider": resource.provider.value,
                    "region": resource.region,
                    "hourly_cost": resource.hourly_cost,
                    "monthly_estimate": resource.monthly_estimate,
                    "avg_cpu_percent": round(avg_cpu, 2),
                    "avg_memory_percent": round(avg_mem, 2),
                    "avg_gpu_percent": round(avg_gpu, 2),
                    "avg_storage_percent": round(avg_storage, 2),
                    "overall_utilization_percent": round(overall, 2),
                    "savings_potential": round(resource.monthly_estimate * 0.6, 4),
                    "recommendation": "Right-size or terminate resource",
                })

        underutilized.sort(key=lambda x: x["savings_potential"], reverse=True)
        return underutilized

    def get_cost_by_resource_type(self, org_id: str) -> dict:
        self._telemetry["get_cost_by_resource_type_calls"] += 1
        type_costs: dict[str, float] = defaultdict(float)
        for entry in self._cost_entries.values():
            if entry.org_id == org_id:
                type_costs[entry.resource_type.value] += entry.cost
        total = sum(type_costs.values())
        result = {}
        for rtype, cost in sorted(type_costs.items(), key=lambda x: x[1], reverse=True):
            result[rtype] = {
                "cost": round(cost, 4),
                "percentage": round(cost / total * 100, 2) if total > 0 else 0,
            }
        return result

    def get_cost_by_provider(self, org_id: str) -> dict:
        self._telemetry["get_cost_by_provider_calls"] += 1
        provider_costs: dict[str, float] = defaultdict(float)
        for entry in self._cost_entries.values():
            if entry.org_id == org_id:
                provider_costs[entry.provider.value] += entry.cost
        total = sum(provider_costs.values())
        result = {}
        for provider, cost in sorted(provider_costs.items(), key=lambda x: x[1], reverse=True):
            result[provider] = {
                "cost": round(cost, 4),
                "percentage": round(cost / total * 100, 2) if total > 0 else 0,
            }
        return result

    def get_monthly_trend(self, org_id: str, months: int = 6) -> list[dict]:
        self._telemetry["get_monthly_trend_calls"] += 1
        now = datetime.now(timezone.utc)
        monthly_costs: dict[str, float] = defaultdict(float)

        for entry in self._cost_entries.values():
            if entry.org_id != org_id:
                continue
            dt = datetime.fromisoformat(entry.start_time)
            month_key = dt.strftime("%Y-%m")
            dt_diff = (now.year - dt.year) * 12 + (now.month - dt.month)
            if 0 <= dt_diff < months:
                monthly_costs[month_key] += entry.cost

        # Pad missing months
        trends = []
        for i in range(months - 1, -1, -1):
            month_dt = datetime(now.year, now.month, 1) - timedelta(days=30 * i)
            month_key = month_dt.strftime("%Y-%m")
            cost = round(monthly_costs.get(month_key, 0.0), 4)
            trends.append({"month": month_key, "cost": cost})

        return trends

    def create_infra_budget(self, budget: InfraBudget) -> InfraBudget:
        self._telemetry["create_infra_budget_calls"] += 1
        if not budget.id:
            budget.id = str(uuid.uuid4())
        if not budget.created_at:
            budget.created_at = datetime.now(timezone.utc).isoformat()
        if not budget.end_date:
            period_days_map = {
                "daily": 1,
                "weekly": 7,
                "monthly": 30,
                "quarterly": 91,
                "yearly": 365,
            }
            days = period_days_map.get(budget.period.lower(), 30)
            budget.end_date = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

        # Initialize current_spend from existing cost entries
        current = 0.0
        for entry in self._cost_entries.values():
            if entry.org_id == budget.org_id:
                current += entry.cost
        budget.current_spend = round(current, 4)

        self._budgets[budget.id] = budget
        self._save()
        logger.info("Created infra budget %s: %s (%.2f)", budget.id, budget.name, budget.limit)
        return budget

    def get_infra_budget_status(self, budget_id: str) -> dict:
        self._telemetry["get_infra_budget_status_calls"] += 1
        budget = self._budgets.get(budget_id)
        if not budget:
            return {"error": "Budget not found", "budget_id": budget_id}

        percentage = round((budget.current_spend / budget.limit * 100) if budget.limit > 0 else 0, 2)
        remaining = round(max(0, budget.limit - budget.current_spend), 4)

        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(budget.start_date)
        end = datetime.fromisoformat(budget.end_date) if budget.end_date else now
        elapsed_days = max(1, (now - start).days)
        total_days = max(1, (end - start).days)
        daily_rate = budget.current_spend / elapsed_days
        projected_total = daily_rate * total_days
        projected_overage = max(0, round(projected_total - budget.limit, 4))

        return {
            "budget_id": budget.id,
            "name": budget.name,
            "org_id": budget.org_id,
            "resource_type": budget.resource_type.value,
            "provider": budget.provider.value,
            "period": budget.period,
            "limit": budget.limit,
            "current_spend": budget.current_spend,
            "remaining": remaining,
            "percentage_used": percentage,
            "alert_threshold": budget.alert_threshold,
            "threshold_breached": percentage >= budget.alert_threshold,
            "projected_total": round(projected_total, 4),
            "projected_overage": projected_overage,
            "start_date": budget.start_date,
            "end_date": budget.end_date,
            "status": "exceeded" if budget.current_spend >= budget.limit else "warning" if percentage >= budget.alert_threshold else "on_track",
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
