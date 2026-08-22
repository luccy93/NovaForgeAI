"""Marketplace billing — track package purchases, publisher revenue splits, payout tracking."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.billing.config import get_billing_config


class MarketplaceBillingService:
    def __init__(self):
        self._records: dict[str, dict] = {}
        self._org_records: dict[str, list[str]] = {}
        self._publisher_records: dict[str, list[str]] = {}
        self._package_records: dict[str, list[str]] = {}
        self._payouts: list[dict] = []

    def record_purchase(
        self,
        organization_id: str,
        package_id: str,
        publisher_org_id: str,
        pricing_type: str,
        amount_cents: int,
        billing_period: str = "monthly",
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        invoice_id: Optional[str] = None,
    ) -> dict:
        config = get_billing_config()
        publisher_share_pct = config.marketplace_revenue_share
        platform_share_pct = 1.0 - publisher_share_pct
        publisher_share = int(amount_cents * publisher_share_pct)
        platform_share = amount_cents - publisher_share
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = {
            "id": record_id,
            "organization_id": organization_id,
            "package_id": package_id,
            "publisher_org_id": publisher_org_id,
            "pricing_type": pricing_type,
            "amount_cents": amount_cents,
            "publisher_share_cents": publisher_share,
            "platform_share_cents": platform_share,
            "currency": "usd",
            "billing_period": billing_period,
            "period_start": (period_start or now).isoformat(),
            "period_end": (period_end or now).isoformat(),
            "status": "completed",
            "invoice_id": invoice_id,
            "metadata": {},
            "created_at": now.isoformat(),
        }
        self._records[record_id] = record
        self._org_records.setdefault(organization_id, []).append(record_id)
        self._publisher_records.setdefault(publisher_org_id, []).append(record_id)
        self._package_records.setdefault(package_id, []).append(record_id)
        return record

    def get_record(self, record_id: str) -> Optional[dict]:
        return self._records.get(record_id)

    def list_records(
        self,
        organization_id: Optional[str] = None,
        publisher_org_id: Optional[str] = None,
        package_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        if organization_id:
            ids = self._org_records.get(organization_id, [])
        elif publisher_org_id:
            ids = self._publisher_records.get(publisher_org_id, [])
        elif package_id:
            ids = self._package_records.get(package_id, [])
        else:
            ids = list(self._records.keys())
        results = [self._records[rid] for rid in ids if rid in self._records]
        return results[-limit:]

    def get_publisher_revenue(self, publisher_org_id: str) -> dict:
        ids = self._publisher_records.get(publisher_org_id, [])
        records = [self._records[rid] for rid in ids if rid in self._records]
        total_revenue = sum(r["amount_cents"] for r in records)
        total_publisher_share = sum(r["publisher_share_cents"] for r in records)
        total_platform_share = sum(r["platform_share_cents"] for r in records)
        return {
            "publisher_org_id": publisher_org_id,
            "total_purchases": len(records),
            "total_revenue_cents": total_revenue,
            "total_publisher_share_cents": total_publisher_share,
            "total_platform_share_cents": total_platform_share,
        }

    def get_package_revenue(self, package_id: str) -> dict:
        ids = self._package_records.get(package_id, [])
        records = [self._records[rid] for rid in ids if rid in self._records]
        total = sum(r["amount_cents"] for r in records)
        return {
            "package_id": package_id,
            "total_purchases": len(records),
            "total_revenue_cents": total,
        }

    def create_payout(
        self,
        publisher_org_id: str,
        amount_cents: int,
        period_start: str,
        period_end: str,
    ) -> dict:
        config = get_billing_config()
        now = datetime.now(timezone.utc)
        payout = {
            "id": str(uuid.uuid4()),
            "publisher_org_id": publisher_org_id,
            "amount_cents": amount_cents,
            "currency": "usd",
            "status": "pending",
            "period_start": period_start,
            "period_end": period_end,
            "processed_at": None,
            "created_at": now.isoformat(),
        }
        self._payouts.append(payout)
        return payout

    def list_payouts(
        self,
        publisher_org_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        payouts = self._payouts
        if publisher_org_id:
            payouts = [p for p in payouts if p["publisher_org_id"] == publisher_org_id]
        return payouts[-limit:]

    def get_marketplace_summary(self) -> dict:
        total_revenue = sum(r["amount_cents"] for r in self._records.values())
        total_purchases = len(self._records)
        unique_packages = len(set(r["package_id"] for r in self._records.values()))
        unique_publishers = len(set(r["publisher_org_id"] for r in self._records.values()))
        return {
            "total_purchases": total_purchases,
            "total_revenue_cents": total_revenue,
            "unique_packages": unique_packages,
            "unique_publishers": unique_publishers,
        }

    def get_telemetry(self) -> dict:
        return {
            "total_records": len(self._records),
            "total_payouts": len(self._payouts),
        }


marketplace_billing_service = MarketplaceBillingService()
