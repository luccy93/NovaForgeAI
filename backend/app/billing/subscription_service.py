"""Subscription service — manages subscriptions: create, upgrade, downgrade, cancel, reactivate."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.billing.constants import (
    SubscriptionStatus, BillingCycle, PlanTier, PLAN_PRICING,
)
from app.billing.config import get_billing_config


class SubscriptionService:
    def __init__(self):
        self._subscriptions: dict[str, dict] = {}
        self._org_sub_index: dict[str, list[str]] = {}

    def create_subscription(
        self,
        organization_id: str,
        plan_id: str,
        billing_cycle: str = "monthly",
        trial_days: Optional[int] = None,
        seats: int = 1,
        extra: Optional[dict] = None,
    ) -> dict:
        sub_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        config = get_billing_config()

        is_trial = trial_days is not None and trial_days > 0
        trial_end = None
        if is_trial:
            effective_trial = trial_days if trial_days else config.trial_days
            trial_end = now + timedelta(days=effective_trial)
            status = SubscriptionStatus.TRIALING.value
            period_end = trial_end
        else:
            status = SubscriptionStatus.ACTIVE.value
            if billing_cycle == BillingCycle.ANNUAL.value:
                period_end = now + timedelta(days=365)
            else:
                period_end = now + timedelta(days=30)

        sub = {
            "id": sub_id,
            "organization_id": organization_id,
            "plan_id": plan_id,
            "status": status,
            "billing_cycle": billing_cycle,
            "current_period_start": now.isoformat(),
            "current_period_end": period_end.isoformat(),
            "trial_start": now.isoformat() if is_trial else None,
            "trial_end": trial_end.isoformat() if trial_end else None,
            "canceled_at": None,
            "cancel_at_period_end": False,
            "seats": seats,
            "extra": extra or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._subscriptions[sub_id] = sub
        self._org_sub_index.setdefault(organization_id, []).append(sub_id)
        return sub

    def get_subscription(self, subscription_id: str) -> Optional[dict]:
        return self._subscriptions.get(subscription_id)

    def get_organization_subscriptions(self, organization_id: str) -> list[dict]:
        sub_ids = self._org_sub_index.get(organization_id, [])
        return [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]

    def get_active_subscription(self, organization_id: str) -> Optional[dict]:
        for sub_id in self._org_sub_index.get(organization_id, []):
            sub = self._subscriptions.get(sub_id)
            if sub and sub["status"] in (
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value,
            ):
                return sub
        return None

    def update_subscription(self, subscription_id: str, **kwargs) -> Optional[dict]:
        sub = self._subscriptions.get(subscription_id)
        if not sub:
            return None
        for key in ("plan_id", "billing_cycle", "seats", "cancel_at_period_end", "extra"):
            if key in kwargs and kwargs[key] is not None:
                sub[key] = kwargs[key]
        sub["updated_at"] = datetime.now(timezone.utc).isoformat()
        return sub

    def change_plan(self, subscription_id: str, new_plan_id: str) -> Optional[dict]:
        sub = self._subscriptions.get(subscription_id)
        if not sub:
            return None
        old_plan = sub["plan_id"]
        sub["plan_id"] = new_plan_id
        sub["updated_at"] = datetime.now(timezone.utc).isoformat()
        return {"subscription": sub, "old_plan_id": old_plan, "new_plan_id": new_plan_id, "changed_at": sub["updated_at"]}

    def cancel_subscription(self, subscription_id: str, immediate: bool = False, reason: str = "") -> Optional[dict]:
        sub = self._subscriptions.get(subscription_id)
        if not sub:
            return None
        now = datetime.now(timezone.utc)
        if immediate:
            sub["status"] = SubscriptionStatus.CANCELED.value
            sub["canceled_at"] = now.isoformat()
        else:
            sub["cancel_at_period_end"] = True
            sub["canceled_at"] = now.isoformat()
        sub["updated_at"] = now.isoformat()
        return sub

    def reactivate_subscription(self, subscription_id: str) -> Optional[dict]:
        sub = self._subscriptions.get(subscription_id)
        if not sub:
            return None
        now = datetime.now(timezone.utc)
        if sub["status"] in (SubscriptionStatus.CANCELED.value, SubscriptionStatus.PAUSED.value, SubscriptionStatus.UNPAID.value):
            sub["status"] = SubscriptionStatus.ACTIVE.value
            sub["canceled_at"] = None
            sub["cancel_at_period_end"] = False
            sub["updated_at"] = now.isoformat()
        return sub

    def advance_period(self, subscription_id: str) -> Optional[dict]:
        sub = self._subscriptions.get(subscription_id)
        if not sub:
            return None
        now = datetime.now(timezone.utc)
        if sub["cancel_at_period_end"] and sub["status"] == SubscriptionStatus.ACTIVE.value:
            sub["status"] = SubscriptionStatus.CANCELED.value
        elif sub["status"] == SubscriptionStatus.TRIALING.value and sub.get("trial_end"):
            trial_end = datetime.fromisoformat(sub["trial_end"])
            if now >= trial_end:
                sub["status"] = SubscriptionStatus.ACTIVE.value
        if sub["billing_cycle"] == BillingCycle.ANNUAL.value:
            sub["current_period_start"] = sub["current_period_end"]
            end = datetime.fromisoformat(sub["current_period_end"]) + timedelta(days=365)
            sub["current_period_end"] = end.isoformat()
        else:
            sub["current_period_start"] = sub["current_period_end"]
            end = datetime.fromisoformat(sub["current_period_end"]) + timedelta(days=30)
            sub["current_period_end"] = end.isoformat()
        sub["updated_at"] = now.isoformat()
        return sub

    def list_subscriptions(self, status: Optional[str] = None) -> list[dict]:
        subs = list(self._subscriptions.values())
        if status:
            subs = [s for s in subs if s["status"] == status]
        return subs

    def get_subscription_analytics(self, organization_id: str) -> dict:
        subs = self.get_organization_subscriptions(organization_id)
        active = sum(1 for s in subs if s["status"] == SubscriptionStatus.ACTIVE.value)
        trialing = sum(1 for s in subs if s["status"] == SubscriptionStatus.TRIALING.value)
        canceled = sum(1 for s in subs if s["status"] == SubscriptionStatus.CANCELED.value)
        total_seats = sum(s.get("seats", 1) for s in subs if s["status"] != SubscriptionStatus.CANCELED.value)
        return {
            "organization_id": organization_id,
            "total_subscriptions": len(subs),
            "active": active,
            "trialing": trialing,
            "canceled": canceled,
            "total_seats": total_seats,
        }

    def get_telemetry(self) -> dict:
        statuses = {}
        for sub in self._subscriptions.values():
            statuses[sub["status"]] = statuses.get(sub["status"], 0) + 1
        return {
            "total_subscriptions": len(self._subscriptions),
            "by_status": statuses,
        }


subscription_service = SubscriptionService()
