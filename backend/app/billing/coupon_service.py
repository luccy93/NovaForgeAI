"""Coupon service — create, validate, apply, and track coupon redemptions."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.billing.constants import CouponType
from app.billing.config import get_billing_config


class CouponService:
    def __init__(self):
        self._coupons: dict[str, dict] = {}
        self._redemptions: list[dict] = []

    def create_coupon(
        self,
        code: str,
        coupon_type: str,
        value_cents: int,
        description: str = "",
        currency: str = "usd",
        max_redemptions: int = 10000,
        applies_to_plans: Optional[list[str]] = None,
        min_subscription_cents: int = 0,
        starts_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> dict:
        coupon_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        coupon = {
            "id": coupon_id,
            "code": code.upper(),
            "description": description,
            "coupon_type": coupon_type,
            "value_cents": value_cents,
            "currency": currency,
            "max_redemptions": max_redemptions,
            "redemptions_count": 0,
            "applies_to_plans": applies_to_plans or [],
            "min_subscription_cents": min_subscription_cents,
            "starts_at": starts_at.isoformat() if isinstance(starts_at, datetime) else starts_at,
            "expires_at": expires_at.isoformat() if isinstance(expires_at, datetime) else expires_at,
            "is_active": True,
            "metadata": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._coupons[coupon_id] = coupon
        return coupon

    def get_coupon(self, coupon_id: str) -> Optional[dict]:
        return self._coupons.get(coupon_id)

    def get_coupon_by_code(self, code: str) -> Optional[dict]:
        for coupon in self._coupons.values():
            if coupon["code"] == code.upper():
                return coupon
        return None

    def list_coupons(self, active_only: bool = True) -> list[dict]:
        coupons = list(self._coupons.values())
        if active_only:
            coupons = [c for c in coupons if c["is_active"]]
        return coupons

    def validate_coupon(
        self,
        code: str,
        plan_id: Optional[str] = None,
        subscription_amount_cents: int = 0,
    ) -> dict:
        coupon = self.get_coupon_by_code(code)
        if not coupon:
            return {"valid": False, "error": "Coupon not found"}
        now = datetime.now(timezone.utc)
        if not coupon["is_active"]:
            return {"valid": False, "error": "Coupon is inactive"}
        if coupon.get("starts_at"):
            starts = datetime.fromisoformat(coupon["starts_at"])
            if now < starts:
                return {"valid": False, "error": "Coupon not yet active"}
        if coupon.get("expires_at"):
            expires = datetime.fromisoformat(coupon["expires_at"])
            if now > expires:
                return {"valid": False, "error": "Coupon has expired"}
        if coupon["redemptions_count"] >= coupon["max_redemptions"]:
            return {"valid": False, "error": "Coupon redemption limit reached"}
        if coupon["min_subscription_cents"] > 0 and subscription_amount_cents < coupon["min_subscription_cents"]:
            return {"valid": False, "error": f"Minimum subscription amount ${coupon['min_subscription_cents']/100:.2f} not met"}
        if coupon["applies_to_plans"] and plan_id and plan_id not in coupon["applies_to_plans"]:
            return {"valid": False, "error": "Coupon does not apply to this plan"}
        return {"valid": True, "coupon": coupon}

    def apply_coupon(
        self,
        code: str,
        organization_id: str,
        amount_cents: int,
        subscription_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
    ) -> dict:
        validation = self.validate_coupon(code)
        if not validation["valid"]:
            raise ValueError(validation["error"])
        coupon = validation["coupon"]
        if coupon["coupon_type"] == CouponType.PERCENTAGE.value:
            discount = int(amount_cents * coupon["value_cents"] / 10000)
        elif coupon["coupon_type"] == CouponType.FIXED_AMOUNT.value:
            discount = min(coupon["value_cents"], amount_cents)
        else:
            discount = amount_cents
        now = datetime.now(timezone.utc)
        coupon["redemptions_count"] += 1
        coupon["updated_at"] = now.isoformat()
        redemption = {
            "id": str(uuid.uuid4()),
            "coupon_id": coupon["id"],
            "organization_id": organization_id,
            "subscription_id": subscription_id,
            "invoice_id": invoice_id,
            "discount_cents": discount,
            "created_at": now.isoformat(),
        }
        self._redemptions.append(redemption)
        return {"discount_cents": discount, "redemption": redemption, "coupon": coupon}

    def deactivate_coupon(self, coupon_id: str) -> Optional[dict]:
        coupon = self._coupons.get(coupon_id)
        if not coupon:
            return None
        coupon["is_active"] = False
        coupon["updated_at"] = datetime.now(timezone.utc).isoformat()
        return coupon

    def delete_coupon(self, coupon_id: str) -> bool:
        if coupon_id in self._coupons:
            del self._coupons[coupon_id]
            return True
        return False

    def get_coupon_redemptions(self, coupon_id: str) -> list[dict]:
        return [r for r in self._redemptions if r["coupon_id"] == coupon_id]

    def get_telemetry(self) -> dict:
        return {
            "total_coupons": len(self._coupons),
            "active_coupons": sum(1 for c in self._coupons.values() if c["is_active"]),
            "total_redemptions": len(self._redemptions),
        }


coupon_service = CouponService()
