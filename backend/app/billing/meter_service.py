"""Meter service — usage metering, aggregation, and reporting."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.billing.constants import MeteringUnit, METER_RATES


class MeterService:
    def __init__(self):
        self._records: list[dict] = []
        self._aggregated: dict[str, dict] = {}

    def record_usage(
        self,
        organization_id: str,
        metric_name: str,
        quantity: float,
        unit: str,
        source: str = "system",
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        subscription_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        now = timestamp or datetime.now(timezone.utc)
        if isinstance(now, str):
            now = datetime.fromisoformat(now)
        rate = METER_RATES.get(unit, 0)
        cost_cents = int(quantity * rate * 100)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1)

        record = {
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "subscription_id": subscription_id,
            "metric_name": metric_name,
            "quantity": quantity,
            "unit": unit,
            "rate_cents": int(rate * 100),
            "cost_cents": cost_cents,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "is_estimated": False,
            "source": source,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "metadata": metadata or {},
            "created_at": now.isoformat(),
        }
        self._records.append(record)
        self._update_aggregation(record)
        return record

    def _update_aggregation(self, record: dict):
        key = f"{record['organization_id']}:{record['metric_name']}:{record['period_start']}"
        if key not in self._aggregated:
            self._aggregated[key] = {
                "organization_id": record["organization_id"],
                "metric_name": record["metric_name"],
                "period_start": record["period_start"],
                "period_end": record["period_end"],
                "total_quantity": 0.0,
                "total_cost_cents": 0,
                "record_count": 0,
                "unit": record["unit"],
            }
        agg = self._aggregated[key]
        agg["total_quantity"] += record["quantity"]
        agg["total_cost_cents"] += record["cost_cents"]
        agg["record_count"] += 1

    def get_usage(
        self,
        organization_id: str,
        metric_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[dict]:
        results = [r for r in self._records if r["organization_id"] == organization_id]
        if metric_name:
            results = [r for r in results if r["metric_name"] == metric_name]
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date)
            results = [r for r in results if datetime.fromisoformat(r["created_at"]) >= start_date]
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date)
            results = [r for r in results if datetime.fromisoformat(r["created_at"]) <= end_date]
        return results[-limit:]

    def get_usage_summary(
        self,
        organization_id: str,
        metric_name: Optional[str] = None,
    ) -> dict:
        records = self.get_usage(organization_id, metric_name=metric_name)
        if not records:
            return {
                "organization_id": organization_id,
                "total_quantity": 0.0,
                "total_cost_cents": 0,
                "record_count": 0,
                "by_metric": {},
            }
        by_metric: dict[str, dict] = {}
        total_quantity = 0.0
        total_cost = 0
        for r in records:
            mn = r["metric_name"]
            if mn not in by_metric:
                by_metric[mn] = {"quantity": 0.0, "cost_cents": 0, "unit": r["unit"], "count": 0}
            by_metric[mn]["quantity"] += r["quantity"]
            by_metric[mn]["cost_cents"] += r["cost_cents"]
            by_metric[mn]["count"] += 1
            total_quantity += r["quantity"]
            total_cost += r["cost_cents"]
        return {
            "organization_id": organization_id,
            "total_quantity": total_quantity,
            "total_cost_cents": total_cost,
            "record_count": len(records),
            "by_metric": by_metric,
        }

    def get_aggregated_usage(
        self,
        organization_id: str,
        metric_name: Optional[str] = None,
    ) -> list[dict]:
        results = [v for v in self._aggregated.values() if v["organization_id"] == organization_id]
        if metric_name:
            results = [r for r in results if r["metric_name"] == metric_name]
        return results

    def get_usage_by_resource(
        self,
        organization_id: str,
        resource_type: str,
    ) -> list[dict]:
        records = [r for r in self._records if r["organization_id"] == organization_id and r["resource_type"] == resource_type]
        by_resource: dict[str, dict] = {}
        for r in records:
            rid = r.get("resource_id", "unknown")
            if rid not in by_resource:
                by_resource[rid] = {"resource_id": rid, "resource_type": resource_type, "total_quantity": 0.0, "total_cost_cents": 0}
            by_resource[rid]["total_quantity"] += r["quantity"]
            by_resource[rid]["total_cost_cents"] += r["cost_cents"]
        return list(by_resource.values())

    def check_usage_limit(
        self,
        organization_id: str,
        metric_name: str,
        limit_quantity: float,
    ) -> dict:
        summary = self.get_usage_summary(organization_id, metric_name=metric_name)
        current = summary["total_quantity"]
        percentage = (current / limit_quantity * 100) if limit_quantity > 0 else 0
        return {
            "organization_id": organization_id,
            "metric_name": metric_name,
            "current_usage": current,
            "limit": limit_quantity,
            "percentage_used": round(percentage, 2),
            "exceeded": current >= limit_quantity,
        }

    def get_telemetry(self) -> dict:
        return {
            "total_records": len(self._records),
            "aggregated_keys": len(self._aggregated),
            "unique_organizations": len(set(r["organization_id"] for r in self._records)),
        }


meter_service = MeterService()
