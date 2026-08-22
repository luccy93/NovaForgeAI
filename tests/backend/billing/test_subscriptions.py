"""Subscription service tests (Volume 53)."""
import pytest
from datetime import datetime, timedelta, timezone
from app.billing.subscription_service import SubscriptionService
from app.billing.constants import SubscriptionStatus, BillingCycle


@pytest.fixture()
def svc():
    return SubscriptionService()


@pytest.fixture()
def org_id():
    return "org-test-sub-001"


@pytest.fixture()
def plan_id():
    return "plan-pro-001"


class TestSubscriptionService:
    def test_create_subscription(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        assert sub["organization_id"] == org_id
        assert sub["plan_id"] == plan_id
        assert sub["status"] == SubscriptionStatus.ACTIVE.value
        assert sub["billing_cycle"] == "monthly"

    def test_create_trial_subscription(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id, trial_days=14)
        assert sub["status"] == SubscriptionStatus.TRIALING.value
        assert sub["trial_end"] is not None
        assert sub["trial_start"] is not None

    def test_create_annual_subscription(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id, billing_cycle="annual")
        assert sub["billing_cycle"] == "annual"

    def test_get_subscription(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        got = svc.get_subscription(sub["id"])
        assert got is not None
        assert got["id"] == sub["id"]

    def test_get_subscription_not_found(self, svc):
        assert svc.get_subscription("nonexistent") is None

    def test_get_organization_subscriptions(self, svc, org_id, plan_id):
        svc.create_subscription(org_id, plan_id)
        svc.create_subscription(org_id, plan_id)
        subs = svc.get_organization_subscriptions(org_id)
        assert len(subs) == 2

    def test_get_active_subscription(self, svc, org_id, plan_id):
        svc.create_subscription(org_id, plan_id)
        active = svc.get_active_subscription(org_id)
        assert active is not None
        assert active["status"] == SubscriptionStatus.ACTIVE.value

    def test_get_active_subscription_none(self, svc, org_id):
        assert svc.get_active_subscription(org_id) is None

    def test_update_subscription(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        updated = svc.update_subscription(sub["id"], seats=5)
        assert updated["seats"] == 5

    def test_update_subscription_not_found(self, svc):
        assert svc.update_subscription("nonexistent", seats=5) is None

    def test_change_plan(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        result = svc.change_plan(sub["id"], "new-plan-id")
        assert result["new_plan_id"] == "new-plan-id"
        assert result["old_plan_id"] == plan_id

    def test_change_plan_not_found(self, svc):
        assert svc.change_plan("nonexistent", "new") is None

    def test_cancel_subscription_immediate(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        canceled = svc.cancel_subscription(sub["id"], immediate=True)
        assert canceled["status"] == SubscriptionStatus.CANCELED.value
        assert canceled["canceled_at"] is not None

    def test_cancel_subscription_at_period_end(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        canceled = svc.cancel_subscription(sub["id"], immediate=False)
        assert canceled["cancel_at_period_end"] is True
        assert canceled["status"] == SubscriptionStatus.ACTIVE.value

    def test_cancel_subscription_not_found(self, svc):
        assert svc.cancel_subscription("nonexistent") is None

    def test_reactivate_subscription(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        svc.cancel_subscription(sub["id"], immediate=True)
        react = svc.reactivate_subscription(sub["id"])
        assert react["status"] == SubscriptionStatus.ACTIVE.value
        assert react["canceled_at"] is None

    def test_reactivate_subscription_not_found(self, svc):
        assert svc.reactivate_subscription("nonexistent") is None

    def test_advance_period_monthly(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id, billing_cycle="monthly")
        original_end = sub["current_period_end"]
        advanced = svc.advance_period(sub["id"])
        assert advanced["current_period_start"] == original_end

    def test_advance_period_annual(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id, billing_cycle="annual")
        original_end = sub["current_period_end"]
        advanced = svc.advance_period(sub["id"])
        assert advanced["current_period_start"] == original_end

    def test_advance_period_cancels_at_period_end(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id)
        svc.cancel_subscription(sub["id"], immediate=False)
        advanced = svc.advance_period(sub["id"])
        assert advanced["status"] == SubscriptionStatus.CANCELED.value

    def test_advance_period_trial_to_active(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id, trial_days=1)
        assert sub["status"] == SubscriptionStatus.TRIALING.value
        sub["trial_end"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        advanced = svc.advance_period(sub["id"])
        assert advanced["status"] == SubscriptionStatus.ACTIVE.value

    def test_advance_period_not_found(self, svc):
        assert svc.advance_period("nonexistent") is None

    def test_list_subscriptions(self, svc, org_id, plan_id):
        svc.create_subscription(org_id, plan_id)
        svc.create_subscription(org_id, plan_id)
        all_subs = svc.list_subscriptions()
        assert len(all_subs) >= 2

    def test_list_subscriptions_by_status(self, svc, org_id, plan_id):
        svc.create_subscription(org_id, plan_id)
        active = svc.list_subscriptions(status="active")
        assert all(s["status"] == "active" for s in active)

    def test_subscription_analytics(self, svc, org_id, plan_id):
        svc.create_subscription(org_id, plan_id)
        svc.create_subscription(org_id, plan_id)
        svc.cancel_subscription(svc.get_organization_subscriptions(org_id)[0]["id"], immediate=True)
        analytics = svc.get_subscription_analytics(org_id)
        assert analytics["total_subscriptions"] == 2
        assert analytics["active"] >= 1
        assert analytics["canceled"] >= 1

    def test_subscription_analytics_empty(self, svc, org_id):
        analytics = svc.get_subscription_analytics(org_id)
        assert analytics["total_subscriptions"] == 0

    def test_telemetry(self, svc):
        tel = svc.get_telemetry()
        assert "total_subscriptions" in tel
        assert "by_status" in tel

    def test_create_subscription_with_seats(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id, seats=10)
        assert sub["seats"] == 10

    def test_create_subscription_with_extra(self, svc, org_id, plan_id):
        sub = svc.create_subscription(org_id, plan_id, extra={"stripe_customer_id": "cus_123"})
        assert sub["extra"]["stripe_customer_id"] == "cus_123"
