"""Plan service — manages billing plans (static seed data + CRUD)."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.billing.constants import (
    PlanTier, PLAN_PRICING, BILLING_PLAN_FEATURES,
)


class PlanService:
    def __init__(self):
        self._plans: dict[str, dict] = {}
        self._seed_plans()

    def _seed_plans(self):
        for tier in PlanTier:
            pricing = PLAN_PRICING[tier]
            features = BILLING_PLAN_FEATURES.get(tier, [])
            plan_id = str(uuid.uuid4())
            self._plans[plan_id] = {
                "id": plan_id,
                "tier": tier.value,
                "name": tier.value.replace("_", " ").title(),
                "slug": tier.value,
                f"description": f"{tier.value.replace('_', ' ').title()} plan",
                "price_monthly_cents": pricing["monthly"],
                "price_annual_cents": pricing["annual"],
                "max_seats": pricing["seats"],
                "max_storage_gb": pricing["storage_gb"],
                "max_tokens_millions": pricing["tokens_millions"],
                "features": features,
                "is_active": True,
                "stripe_price_monthly_id": None,
                "stripe_price_annual_id": None,
                "metadata": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    def list_plans(self, active_only: bool = True) -> list[dict]:
        plans = list(self._plans.values())
        if active_only:
            plans = [p for p in plans if p["is_active"]]
        return plans

    def get_plan(self, plan_id: str) -> Optional[dict]:
        return self._plans.get(plan_id)

    def get_plan_by_tier(self, tier: str) -> Optional[dict]:
        for plan in self._plans.values():
            if plan["tier"] == tier:
                return plan
        return None

    def get_plan_by_slug(self, slug: str) -> Optional[dict]:
        for plan in self._plans.values():
            if plan["slug"] == slug:
                return plan
        return None

    def create_plan(
        self,
        tier: str,
        name: str,
        slug: str,
        description: str = "",
        price_monthly_cents: int = 0,
        price_annual_cents: int = 0,
        max_seats: int = 3,
        max_storage_gb: int = 1,
        max_tokens_millions: int = 1,
        features: Optional[list[str]] = None,
        stripe_price_monthly_id: Optional[str] = None,
        stripe_price_annual_id: Optional[str] = None,
    ) -> dict:
        plan_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        plan = {
            "id": plan_id,
            "tier": tier,
            "name": name,
            "slug": slug,
            "description": description,
            "price_monthly_cents": price_monthly_cents,
            "price_annual_cents": price_annual_cents,
            "max_seats": max_seats,
            "max_storage_gb": max_storage_gb,
            "max_tokens_millions": max_tokens_millions,
            "features": features or [],
            "is_active": True,
            "stripe_price_monthly_id": stripe_price_monthly_id,
            "stripe_price_annual_id": stripe_price_annual_id,
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }
        self._plans[plan_id] = plan
        return plan

    def update_plan(self, plan_id: str, **kwargs) -> Optional[dict]:
        plan = self._plans.get(plan_id)
        if not plan:
            return None
        for key, value in kwargs.items():
            if value is not None and key in (
                "name", "description", "price_monthly_cents", "price_annual_cents",
                "max_seats", "max_storage_gb", "max_tokens_millions",
                "features", "is_active", "stripe_price_monthly_id", "stripe_price_annual_id",
            ):
                plan[key] = value
        plan["updated_at"] = datetime.now(timezone.utc).isoformat()
        return plan

    def delete_plan(self, plan_id: str) -> bool:
        if plan_id in self._plans:
            del self._plans[plan_id]
            return True
        return False

    def get_telemetry(self) -> dict:
        return {
            "total_plans": len(self._plans),
            "active_plans": sum(1 for p in self._plans.values() if p["is_active"]),
            "plans_by_tier": {p["tier"]: p["id"] for p in self._plans.values()},
        }


plan_service = PlanService()
