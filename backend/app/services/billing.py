"""Stripe billing service for NovaForge AI subscriptions."""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


PLANS = {
    "free": {
        "id": "free",
        "name": "Free",
        "description": "For individual developers",
        "price_monthly": 0,
        "price_yearly": 0,
        "features": ["1 repository", "Basic AI Chat", "Community Support"],
        "limits": {"repositories": 1, "seats": 1, "storage_gb": 1, "ai_tokens_monthly": 100_000},
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "description": "For professional developers",
        "price_monthly": 1900,
        "price_yearly": 19000,
        "features": ["10 repositories", "Advanced AI Chat", "Code Review", "Priority Support"],
        "limits": {"repositories": 10, "seats": 1, "storage_gb": 10, "ai_tokens_monthly": 1_000_000},
    },
    "team": {
        "id": "team",
        "name": "Team",
        "description": "For small teams",
        "price_monthly": 4900,
        "price_yearly": 49000,
        "features": ["50 repositories", "Team Workspaces", "Advanced Analytics", "All AI Features"],
        "limits": {"repositories": 50, "seats": 10, "storage_gb": 50, "ai_tokens_monthly": 5_000_000},
    },
    "business": {
        "id": "business",
        "name": "Business",
        "description": "For growing companies",
        "price_monthly": 14900,
        "price_yearly": 149000,
        "features": ["Unlimited repositories", "SSO/SAML", "Audit Logs", "Priority SLA"],
        "limits": {"repositories": 0, "seats": 50, "storage_gb": 200, "ai_tokens_monthly": 20_000_000},
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "description": "For large organizations",
        "price_monthly": 0,
        "price_yearly": 0,
        "features": ["Everything in Business", "Custom Deployment", "Dedicated Support", "SLA"],
        "limits": {"repositories": 0, "seats": 0, "storage_gb": 0, "ai_tokens_monthly": 0},
    },
}


def get_plan(plan_id: str) -> Optional[dict]:
    return PLANS.get(plan_id)


def get_all_plans() -> list[dict]:
    return list(PLANS.values())


class BillingService:
    def __init__(self):
        self._stripe = None
        if settings.stripe_api_key:
            try:
                import stripe
                stripe.api_key = settings.stripe_api_key
                self._stripe = stripe
            except ImportError:
                logger.warning("stripe not installed")

    @property
    def available(self) -> bool:
        return self._stripe is not None

    async def create_checkout_session(
        self,
        plan_id: str,
        organization_id: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
    ) -> Optional[dict]:
        if not self.available:
            return None
        price_field = f"stripe_price_{plan_id}"
        price_id = getattr(settings, price_field, None)
        if not price_id or price_id in ("price_free", "price_pro", "price_team", "price_business", "price_enterprise"):
            return {"url": success_url, "id": "simulated"}
        try:
            session = self._stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                customer_email=customer_email,
                client_reference_id=organization_id,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"organization_id": organization_id, "plan_id": plan_id},
            )
            return {"url": session.url, "id": session.id}
        except Exception as e:
            logger.error("Stripe checkout creation failed: %s", e)
            return None

    async def create_portal_session(self, customer_id: str, return_url: str) -> Optional[str]:
        if not self.available:
            return None
        try:
            session = self._stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url
        except Exception as e:
            logger.error("Stripe portal creation failed: %s", e)
            return None

    async def cancel_subscription(self, subscription_id: str) -> bool:
        if not self.available:
            return False
        try:
            self._stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
            return True
        except Exception as e:
            logger.error("Stripe cancellation failed: %s", e)
            return False

    async def process_webhook(self, payload: bytes, sig_header: str) -> Optional[dict]:
        if not self.available or not settings.stripe_webhook_secret:
            return None
        try:
            event = self._stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
            return {"type": event.type, "data": event.data.object}
        except Exception as e:
            logger.error("Stripe webhook verification failed: %s", e)
            return None


billing_service = BillingService()
