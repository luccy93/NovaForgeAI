"""Credit, coupon, and budget service tests (Volume 53)."""
import pytest
from datetime import datetime, timedelta, timezone
from app.billing.credit_service import CreditService
from app.billing.coupon_service import CouponService
from app.billing.budget_service import BudgetService
from app.billing.constants import CouponType


@pytest.fixture()
def credit_svc():
    return CreditService()


@pytest.fixture()
def coupon_svc():
    return CouponService()


@pytest.fixture()
def budget_svc():
    return BudgetService()


@pytest.fixture()
def org_id():
    return "org-test-ccb-001"


class TestCreditService:
    def test_grant_credits(self, credit_svc, org_id):
        tx = credit_svc.grant_credits(org_id, 5000, description="Welcome bonus")
        assert tx["amount_cents"] == 5000
        assert tx["type"] == "granted"
        assert tx["balance_after_cents"] == 5000

    def test_grant_credits_updates_balance(self, credit_svc, org_id):
        credit_svc.grant_credits(org_id, 3000)
        credit_svc.grant_credits(org_id, 2000)
        balance = credit_svc.get_balance(org_id)
        assert balance["balance_cents"] == 5000
        assert balance["total_granted_cents"] == 5000

    def test_deduct_credits(self, credit_svc, org_id):
        credit_svc.grant_credits(org_id, 5000)
        tx = credit_svc.deduct_credits(org_id, 2000, description="Invoice payment")
        assert tx["amount_cents"] == -2000
        assert tx["balance_after_cents"] == 3000
        balance = credit_svc.get_balance(org_id)
        assert balance["balance_cents"] == 3000
        assert balance["total_used_cents"] == 2000

    def test_deduct_insufficient_credits(self, credit_svc, org_id):
        credit_svc.grant_credits(org_id, 1000)
        with pytest.raises(ValueError, match="Insufficient credits"):
            credit_svc.deduct_credits(org_id, 5000)

    def test_transfer_credits(self, credit_svc):
        credit_svc.grant_credits("org-from", 5000)
        result = credit_svc.transfer_credits("org-from", "org-to", 2000, description="Transfer test")
        assert result["from_deducted"] == 2000
        assert result["to_granted"]["amount_cents"] == 2000
        assert credit_svc.get_balance("org-from")["balance_cents"] == 3000
        assert credit_svc.get_balance("org-to")["balance_cents"] == 2000

    def test_get_balance(self, credit_svc, org_id):
        balance = credit_svc.get_balance(org_id)
        assert balance["balance_cents"] == 0
        assert balance["total_granted_cents"] == 0

    def test_get_transactions(self, credit_svc, org_id):
        credit_svc.grant_credits(org_id, 1000)
        credit_svc.deduct_credits(org_id, 500)
        txs = credit_svc.get_transactions(org_id)
        assert len(txs) == 2

    def test_get_transactions_empty(self, credit_svc, org_id):
        txs = credit_svc.get_transactions(org_id)
        assert len(txs) == 0

    def test_grant_with_expiry(self, credit_svc, org_id):
        exp = datetime.now(timezone.utc) + timedelta(days=30)
        credit_svc.grant_credits(org_id, 1000, expires_at=exp)
        balance = credit_svc.get_balance(org_id)
        assert balance["expires_at"] is not None

    def test_check_expired_credits(self, credit_svc):
        exp = datetime.now(timezone.utc) - timedelta(days=1)
        credit_svc.grant_credits("org-expired", 1000, expires_at=exp)
        expired = credit_svc.check_expired_credits()
        assert len(expired) == 1
        assert credit_svc.get_balance("org-expired")["balance_cents"] == 0

    def test_check_expired_credits_none_expired(self, credit_svc):
        credit_svc.grant_credits("org-active", 1000)
        expired = credit_svc.check_expired_credits()
        assert len(expired) == 0

    def test_telemetry(self, credit_svc):
        tel = credit_svc.get_telemetry()
        assert "total_organizations" in tel
        assert "total_balance_cents" in tel


class TestCouponService:
    def test_create_coupon_percentage(self, coupon_svc):
        coupon = coupon_svc.create_coupon("SAVE20", "percentage", 2000, description="20% off")
        assert coupon["code"] == "SAVE20"
        assert coupon["coupon_type"] == "percentage"
        assert coupon["value_cents"] == 2000
        assert coupon["is_active"] is True

    def test_create_coupon_fixed(self, coupon_svc):
        coupon = coupon_svc.create_coupon("FLAT10", "fixed_amount", 1000)
        assert coupon["coupon_type"] == "fixed_amount"

    def test_get_coupon(self, coupon_svc):
        coupon = coupon_svc.create_coupon("TEST", "percentage", 1000)
        got = coupon_svc.get_coupon(coupon["id"])
        assert got is not None

    def test_get_coupon_not_found(self, coupon_svc):
        assert coupon_svc.get_coupon("nonexistent") is None

    def test_get_coupon_by_code(self, coupon_svc):
        coupon_svc.create_coupon("SAVE20", "percentage", 2000)
        found = coupon_svc.get_coupon_by_code("save20")
        assert found is not None
        assert found["code"] == "SAVE20"

    def test_get_coupon_by_code_not_found(self, coupon_svc):
        assert coupon_svc.get_coupon_by_code("nonexistent") is None

    def test_list_coupons(self, coupon_svc):
        coupon_svc.create_coupon("C1", "percentage", 1000)
        coupon_svc.create_coupon("C2", "fixed_amount", 500)
        assert len(coupon_svc.list_coupons()) == 2

    def test_validate_coupon_valid(self, coupon_svc):
        coupon_svc.create_coupon("VALID", "percentage", 2000)
        result = coupon_svc.validate_coupon("VALID")
        assert result["valid"] is True

    def test_validate_coupon_not_found(self, coupon_svc):
        result = coupon_svc.validate_coupon("NOPE")
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_validate_coupon_inactive(self, coupon_svc):
        coupon = coupon_svc.create_coupon("INACTIVE", "percentage", 1000)
        coupon_svc.deactivate_coupon(coupon["id"])
        result = coupon_svc.validate_coupon("INACTIVE")
        assert result["valid"] is False
        assert "inactive" in result["error"]

    def test_validate_coupon_expired(self, coupon_svc):
        exp = datetime.now(timezone.utc) - timedelta(days=1)
        coupon_svc.create_coupon("EXPIRED", "percentage", 1000, expires_at=exp)
        result = coupon_svc.validate_coupon("EXPIRED")
        assert result["valid"] is False
        assert "expired" in result["error"]

    def test_apply_coupon_percentage(self, coupon_svc):
        coupon_svc.create_coupon("SAVE20", "percentage", 2000)
        result = coupon_svc.apply_coupon("SAVE20", "org-1", 10000)
        assert result["discount_cents"] == 2000

    def test_apply_coupon_fixed(self, coupon_svc):
        coupon_svc.create_coupon("FLAT5", "fixed_amount", 500)
        result = coupon_svc.apply_coupon("FLAT5", "org-1", 10000)
        assert result["discount_cents"] == 500

    def test_apply_coupon_fixed_capped_at_amount(self, coupon_svc):
        coupon_svc.create_coupon("BIG", "fixed_amount", 50000)
        result = coupon_svc.apply_coupon("BIG", "org-1", 1000)
        assert result["discount_cents"] == 1000

    def test_apply_coupon_invalid(self, coupon_svc):
        with pytest.raises(ValueError):
            coupon_svc.apply_coupon("NOPE", "org-1", 1000)

    def test_deactivate_coupon(self, coupon_svc):
        coupon = coupon_svc.create_coupon("TEMP", "percentage", 1000)
        deactivated = coupon_svc.deactivate_coupon(coupon["id"])
        assert deactivated["is_active"] is False

    def test_delete_coupon(self, coupon_svc):
        coupon = coupon_svc.create_coupon("DEL", "percentage", 1000)
        assert coupon_svc.delete_coupon(coupon["id"]) is True
        assert coupon_svc.get_coupon(coupon["id"]) is None

    def test_delete_coupon_not_found(self, coupon_svc):
        assert coupon_svc.delete_coupon("nonexistent") is False

    def test_get_coupon_redemptions(self, coupon_svc):
        coupon = coupon_svc.create_coupon("TRACK", "percentage", 2000)
        coupon_svc.apply_coupon("TRACK", "org-1", 10000)
        coupon_svc.apply_coupon("TRACK", "org-2", 5000)
        redemptions = coupon_svc.get_coupon_redemptions(coupon["id"])
        assert len(redemptions) == 2

    def test_telemetry(self, coupon_svc):
        coupon_svc.create_coupon("T1", "percentage", 1000)
        tel = coupon_svc.get_telemetry()
        assert tel["total_coupons"] >= 1
        assert "total_redemptions" in tel


class TestBudgetService:
    def test_create_budget(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Monthly cap", 100000)
        assert budget["organization_id"] == org_id
        assert budget["name"] == "Monthly cap"
        assert budget["limit_cents"] == 100000
        assert budget["spent_cents"] == 0
        assert budget["is_active"] is True

    def test_get_budget(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Test", 50000)
        got = budget_svc.get_budget(budget["id"])
        assert got is not None
        assert got["id"] == budget["id"]

    def test_get_budget_not_found(self, budget_svc):
        assert budget_svc.get_budget("nonexistent") is None

    def test_list_budgets(self, budget_svc, org_id):
        budget_svc.create_budget(org_id, "Budget 1", 50000)
        budget_svc.create_budget(org_id, "Budget 2", 100000)
        budgets = budget_svc.list_budgets(organization_id=org_id)
        assert len(budgets) == 2

    def test_update_budget(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Test", 50000)
        updated = budget_svc.update_budget(budget["id"], name="Updated", limit_cents=75000)
        assert updated["name"] == "Updated"
        assert updated["limit_cents"] == 75000

    def test_update_budget_not_found(self, budget_svc):
        assert budget_svc.update_budget("nonexistent", name="test") is None

    def test_record_spend(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Test", 100000)
        budget_svc.record_spend(budget["id"], 25000)
        budget_svc.record_spend(budget["id"], 10000)
        updated = budget_svc.get_budget(budget["id"])
        assert updated["spent_cents"] == 35000

    def test_check_budget_ok(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Test", 100000)
        budget_svc.record_spend(budget["id"], 50000)
        result = budget_svc.check_budget(budget["id"])
        assert result["status"] == "ok"
        assert result["percentage_used"] == 50.0

    def test_check_budget_warning(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Test", 100000)
        budget_svc.record_spend(budget["id"], 85000)
        result = budget_svc.check_budget(budget["id"])
        assert result["status"] == "warning"

    def test_check_budget_hard_limit(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Test", 100000)
        budget_svc.record_spend(budget["id"], 100000)
        result = budget_svc.check_budget(budget["id"])
        assert result["status"] == "hard_limit"

    def test_check_budget_not_found(self, budget_svc):
        result = budget_svc.check_budget("nonexistent")
        assert result["status"] == "not_found"

    def test_check_all_budgets(self, budget_svc, org_id):
        budget_svc.create_budget(org_id, "B1", 50000)
        budget_svc.create_budget(org_id, "B2", 100000)
        results = budget_svc.check_all_budgets(org_id)
        assert len(results) == 2

    def test_delete_budget(self, budget_svc, org_id):
        budget = budget_svc.create_budget(org_id, "Del", 50000)
        assert budget_svc.delete_budget(budget["id"]) is True
        assert budget_svc.get_budget(budget["id"]) is None

    def test_delete_budget_not_found(self, budget_svc):
        assert budget_svc.delete_budget("nonexistent") is False

    def test_budget_status(self, budget_svc, org_id):
        budget_svc.create_budget(org_id, "B1", 50000)
        budget_svc.create_budget(org_id, "B2", 100000)
        status = budget_svc.get_budget_status(org_id)
        assert status["total_budgets"] == 2
        assert status["total_limit_cents"] == 150000

    def test_telemetry(self, budget_svc):
        tel = budget_svc.get_telemetry()
        assert "total_budgets" in tel
        assert "active_budgets" in tel
