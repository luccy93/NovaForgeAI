"""Billing integration tests (Volume 53)."""
import pytest
from datetime import datetime, timedelta, timezone
from app.billing.dunning_service import DunningService
from app.billing.reconciliation_service import ReconciliationService
from app.billing.marketplace_billing import MarketplaceBillingService
from app.billing.event_handler import (
    emit_billing_event, emit_subscription_created, emit_subscription_changed,
    emit_payment_succeeded, emit_payment_failed, emit_invoice_created,
    emit_usage_threshold_exceeded, emit_budget_alert, get_billing_event_handlers,
)
from app.billing.plan_service import PlanService
from app.billing.subscription_service import SubscriptionService
from app.billing.meter_service import MeterService
from app.billing.invoice_service import InvoiceService
from app.billing.payment_service import PaymentService
from app.core.events import EventType


@pytest.fixture()
def dunning_svc():
    return DunningService()


@pytest.fixture()
def recon_svc():
    return ReconciliationService()


@pytest.fixture()
def market_svc():
    return MarketplaceBillingService()


@pytest.fixture()
def plan_svc():
    return PlanService()


@pytest.fixture()
def sub_svc():
    return SubscriptionService()


@pytest.fixture()
def meter_svc():
    return MeterService()


@pytest.fixture()
def inv_svc():
    return InvoiceService()


@pytest.fixture()
def pay_svc():
    return PaymentService()


@pytest.fixture()
def org_id():
    return "org-test-int-001"


@pytest.fixture()
def sub_id():
    return "sub-test-int-001"


class TestDunningService:
    def test_create_dunning_record(self, dunning_svc, sub_id, org_id):
        record = dunning_svc.create_dunning_record(sub_id, org_id, "inv-001", action="email_retry")
        assert record["subscription_id"] == sub_id
        assert record["organization_id"] == org_id
        assert record["invoice_id"] == "inv-001"
        assert record["attempt_number"] == 1
        assert record["action"] == "email_retry"
        assert record["action_result"] == "pending"

    def test_create_dunning_record_increments(self, dunning_svc, sub_id, org_id):
        first = dunning_svc.create_dunning_record(sub_id, org_id, "inv-001")
        second = dunning_svc.create_dunning_record(sub_id, org_id, "inv-001")
        assert first["attempt_number"] == 1
        assert second["attempt_number"] == 2

    def test_get_dunning_record(self, dunning_svc, sub_id, org_id):
        record = dunning_svc.create_dunning_record(sub_id, org_id, "inv-001")
        got = dunning_svc.get_dunning_record(record["id"])
        assert got is not None
        assert got["id"] == record["id"]

    def test_get_dunning_record_not_found(self, dunning_svc):
        assert dunning_svc.get_dunning_record("nonexistent") is None

    def test_list_dunning_records(self, dunning_svc, sub_id, org_id):
        dunning_svc.create_dunning_record(sub_id, org_id, "inv-001")
        dunning_svc.create_dunning_record(sub_id, org_id, "inv-002")
        records = dunning_svc.list_dunning_records(organization_id=org_id)
        assert len(records) == 2

    def test_complete_dunning(self, dunning_svc, sub_id, org_id):
        record = dunning_svc.create_dunning_record(sub_id, org_id, "inv-001")
        completed = dunning_svc.complete_dunning(record["id"], result="success")
        assert completed["action_result"] == "success"
        assert completed["completed_at"] is not None

    def test_should_suspend_below_threshold(self, dunning_svc, sub_id, org_id):
        dunning_svc.create_dunning_record(sub_id, org_id, "inv-001")
        assert dunning_svc.should_suspend(sub_id) is False

    def test_telemetry(self, dunning_svc, sub_id, org_id):
        dunning_svc.create_dunning_record(sub_id, org_id, "inv-001")
        tel = dunning_svc.get_telemetry()
        assert "total_records" in tel
        assert tel["total_records"] >= 1


class TestReconciliationService:
    def test_create_reconciliation_matched(self, recon_svc, org_id):
        record = recon_svc.create_reconciliation("inv-001", org_id, 1000, actual_amount_cents=1000)
        assert record["status"] == "matched"
        assert record["discrepancy_cents"] == 0

    def test_create_reconciliation_discrepancy(self, recon_svc, org_id):
        record = recon_svc.create_reconciliation("inv-002", org_id, 1000, actual_amount_cents=900)
        assert record["status"] == "discrepancy"
        assert record["discrepancy_cents"] == 100

    def test_create_reconciliation_unmatched(self, recon_svc, org_id):
        record = recon_svc.create_reconciliation("inv-003", org_id, 1000, actual_amount_cents=None)
        assert record["status"] == "unmatched"

    def test_update_actual_amount(self, recon_svc, org_id):
        record = recon_svc.create_reconciliation("inv-004", org_id, 1000, actual_amount_cents=None)
        updated = recon_svc.update_actual_amount(record["id"], 1000)
        assert updated["actual_amount_cents"] == 1000
        assert updated["status"] == "matched"
        assert updated["discrepancy_cents"] == 0

    def test_resolve_reconciliation(self, recon_svc, org_id):
        record = recon_svc.create_reconciliation("inv-005", org_id, 1000, actual_amount_cents=900)
        resolved = recon_svc.resolve_reconciliation(record["id"], resolution_notes="waived", resolved_by="admin")
        assert resolved["status"] == "resolved"
        assert resolved["resolved_at"] is not None
        assert resolved["resolution_notes"] == "waived"

    def test_reconciliation_summary(self, recon_svc, org_id):
        recon_svc.create_reconciliation("inv-001", org_id, 1000, actual_amount_cents=1000)
        recon_svc.create_reconciliation("inv-002", org_id, 1000, actual_amount_cents=900)
        summary = recon_svc.get_reconciliation_summary(org_id)
        assert summary["total_records"] == 2
        assert summary["matched"] == 1
        assert summary["discrepancy"] == 1


class TestMarketplaceBillingService:
    def test_record_purchase(self, market_svc, org_id):
        record = market_svc.record_purchase(org_id, "pkg-001", "pub-org-001", "one_time", 1000)
        assert record["amount_cents"] == 1000
        assert record["publisher_share_cents"] == 700
        assert record["platform_share_cents"] == 300
        assert record["status"] == "completed"

    def test_get_publisher_revenue(self, market_svc, org_id):
        market_svc.record_purchase(org_id, "pkg-001", "pub-org-001", "one_time", 1000)
        market_svc.record_purchase(org_id, "pkg-002", "pub-org-001", "one_time", 2000)
        revenue = market_svc.get_publisher_revenue("pub-org-001")
        assert revenue["total_purchases"] == 2
        assert revenue["total_revenue_cents"] == 3000
        assert revenue["total_publisher_share_cents"] == 2100
        assert revenue["total_platform_share_cents"] == 900

    def test_get_package_revenue(self, market_svc, org_id):
        market_svc.record_purchase(org_id, "pkg-001", "pub-org-001", "one_time", 1000)
        market_svc.record_purchase(org_id, "pkg-001", "pub-org-002", "one_time", 2500)
        revenue = market_svc.get_package_revenue("pkg-001")
        assert revenue["package_id"] == "pkg-001"
        assert revenue["total_purchases"] == 2
        assert revenue["total_revenue_cents"] == 3500

    def test_get_marketplace_summary(self, market_svc, org_id):
        market_svc.record_purchase(org_id, "pkg-001", "pub-org-001", "one_time", 1000)
        market_svc.record_purchase(org_id, "pkg-002", "pub-org-002", "subscription", 2000)
        summary = market_svc.get_marketplace_summary()
        assert summary["total_purchases"] == 2
        assert summary["total_revenue_cents"] == 3000
        assert summary["unique_packages"] == 2
        assert summary["unique_publishers"] == 2

    def test_create_payout(self, market_svc):
        payout = market_svc.create_payout("pub-org-001", 5000, "2026-01-01", "2026-01-31")
        assert payout["publisher_org_id"] == "pub-org-001"
        assert payout["amount_cents"] == 5000
        assert payout["status"] == "pending"
        assert payout["processed_at"] is None

    def test_list_payouts(self, market_svc):
        market_svc.create_payout("pub-org-001", 5000, "2026-01-01", "2026-01-31")
        market_svc.create_payout("pub-org-001", 7500, "2026-02-01", "2026-02-28")
        payouts = market_svc.list_payouts(publisher_org_id="pub-org-001")
        assert len(payouts) == 2


class TestEventHandlers:
    @pytest.mark.asyncio
    async def test_emit_subscription_created(self, org_id):
        event = await emit_subscription_created({"organization_id": org_id, "plan_id": "plan-pro"})
        assert event.event_type == EventType.billing_subscription_changed

    @pytest.mark.asyncio
    async def test_emit_payment_failed(self, org_id):
        event = await emit_payment_failed({"organization_id": org_id, "amount_cents": 1000}, reason="card_declined")
        assert event.event_type == EventType.billing_payment_failed

    @pytest.mark.asyncio
    async def test_emit_invoice_created(self, org_id):
        event = await emit_invoice_created({"organization_id": org_id, "total_cents": 4900})
        assert event.event_type == EventType.billing_subscription_changed

    @pytest.mark.asyncio
    async def test_emit_usage_threshold_exceeded(self, org_id):
        event = await emit_usage_threshold_exceeded(org_id, "api_calls", 9500, 10000)
        assert event.event_type == EventType.billing_subscription_changed

    def test_get_billing_event_handlers(self):
        handlers = get_billing_event_handlers()
        assert isinstance(handlers, dict)
        for key in ("subscription_created", "subscription_changed", "payment_succeeded", "payment_failed", "invoice_created"):
            assert key in handlers


class TestBillingEndToEnd:
    def test_full_lifecycle(self, sub_svc, meter_svc, inv_svc, pay_svc, org_id):
        sub = sub_svc.create_subscription(org_id, "plan-pro")
        usage = meter_svc.record_usage(org_id, "api_calls", 1000, "api_calls", subscription_id=sub["id"])
        assert usage["cost_cents"] > 0
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(
            sub["id"], org_id,
            now.isoformat(), (now + timedelta(days=30)).isoformat(),
            [{"description": "Pro plan - monthly", "amount_cents": 4900, "quantity": 1}],
        )
        finalized = inv_svc.finalize_invoice(inv["id"])
        assert finalized["status"] == "open"
        payment = pay_svc.process_payment(inv["id"], org_id, inv["total_cents"])
        assert payment["status"] == "succeeded"
        paid = inv_svc.mark_paid(inv["id"], payment["amount_cents"])
        assert paid["status"] == "paid"
        assert paid["paid_at"] is not None

    def test_plan_change_lifecycle(self, sub_svc, org_id):
        sub = sub_svc.create_subscription(org_id, "plan-starter")
        result = sub_svc.change_plan(sub["id"], "plan-pro")
        assert result["new_plan_id"] == "plan-pro"
        assert result["old_plan_id"] == "plan-starter"
        updated = sub_svc.get_subscription(sub["id"])
        assert updated["plan_id"] == "plan-pro"

    def test_trial_to_active_lifecycle(self, sub_svc, org_id):
        sub = sub_svc.create_subscription(org_id, "plan-pro", trial_days=14)
        assert sub["status"] == "trialing"
        sub["trial_end"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        advanced = sub_svc.advance_period(sub["id"])
        assert advanced["status"] == "active"
