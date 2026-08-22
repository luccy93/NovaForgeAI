"""Plan service tests (Volume 53)."""
import pytest
from app.billing.plan_service import PlanService
from app.billing.constants import PlanTier


@pytest.fixture()
def svc():
    return PlanService()


class TestPlanService:
    def test_seed_plans_created(self, svc):
        plans = svc.list_plans()
        assert len(plans) >= 6

    def test_list_plans_active_only(self, svc):
        plans = svc.list_plans(active_only=True)
        assert all(p["is_active"] for p in plans)

    def test_get_plan(self, svc):
        plans = svc.list_plans()
        plan = svc.get_plan(plans[0]["id"])
        assert plan is not None
        assert plan["id"] == plans[0]["id"]

    def test_get_plan_not_found(self, svc):
        assert svc.get_plan("nonexistent") is None

    def test_get_plan_by_tier(self, svc):
        plan = svc.get_plan_by_tier("free")
        assert plan is not None
        assert plan["tier"] == "free"

    def test_get_plan_by_tier_not_found(self, svc):
        assert svc.get_plan_by_tier("nonexistent") is None

    def test_get_plan_by_slug(self, svc):
        plan = svc.get_plan_by_slug("professional")
        assert plan is not None
        assert plan["slug"] == "professional"

    def test_get_plan_by_slug_not_found(self, svc):
        assert svc.get_plan_by_slug("nonexistent") is None

    def test_create_plan(self, svc):
        plan = svc.create_plan("custom", "Custom Plan", "custom", "A custom plan", 9900, 99000, 10, 50, 10)
        assert plan["tier"] == "custom"
        assert plan["name"] == "Custom Plan"
        assert plan["price_monthly_cents"] == 9900
        assert plan["price_annual_cents"] == 99000

    def test_create_plan_with_features(self, svc):
        plan = svc.create_plan("test", "Test", "test", features=["feature1", "feature2"])
        assert len(plan["features"]) == 2

    def test_update_plan(self, svc):
        plans = svc.list_plans()
        updated = svc.update_plan(plans[0]["id"], name="Updated Plan", price_monthly_cents=9999)
        assert updated["name"] == "Updated Plan"
        assert updated["price_monthly_cents"] == 9999

    def test_update_plan_not_found(self, svc):
        assert svc.update_plan("nonexistent", name="test") is None

    def test_update_plan_ignores_invalid_keys(self, svc):
        plans = svc.list_plans()
        updated = svc.update_plan(plans[0]["id"], invalid_key="should be ignored")
        assert updated is not None

    def test_delete_plan(self, svc):
        plan = svc.create_plan("temp", "Temp", "temp")
        assert svc.delete_plan(plan["id"]) is True
        assert svc.get_plan(plan["id"]) is None

    def test_delete_plan_not_found(self, svc):
        assert svc.delete_plan("nonexistent") is False

    def test_telemetry(self, svc):
        tel = svc.get_telemetry()
        assert "total_plans" in tel
        assert "active_plans" in tel
        assert tel["total_plans"] >= 6

    def test_plan_has_correct_pricing(self, svc):
        plan = svc.get_plan_by_tier("starter")
        assert plan["price_monthly_cents"] == 1900
        assert plan["price_annual_cents"] == 19000

    def test_free_plan_has_zero_price(self, svc):
        plan = svc.get_plan_by_tier("free")
        assert plan["price_monthly_cents"] == 0
        assert plan["price_annual_cents"] == 0

    def test_enterprise_plan_has_unlimited(self, svc):
        plan = svc.get_plan_by_tier("enterprise")
        assert plan["max_seats"] == -1
        assert plan["max_storage_gb"] == -1
        assert plan["max_tokens_millions"] == -1

    def test_create_plan_with_stripe_ids(self, svc):
        plan = svc.create_plan("stripe_plan", "Stripe", "stripe", stripe_price_monthly_id="price_month", stripe_price_annual_id="price_year")
        assert plan["stripe_price_monthly_id"] == "price_month"
        assert plan["stripe_price_annual_id"] == "price_year"
