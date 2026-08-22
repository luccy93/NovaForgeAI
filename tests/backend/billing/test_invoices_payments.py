"""Invoice and payment service tests (Volume 53)."""
import pytest
from datetime import datetime, timedelta, timezone
from app.billing.invoice_service import InvoiceService
from app.billing.payment_service import PaymentService
from app.billing.constants import InvoiceStatus, PaymentStatus


@pytest.fixture()
def inv_svc():
    return InvoiceService()


@pytest.fixture()
def pay_svc():
    return PaymentService()


@pytest.fixture()
def org_id():
    return "org-test-inv-001"


@pytest.fixture()
def sub_id():
    return "sub-test-inv-001"


@pytest.fixture()
def sample_line_items():
    return [
        {"description": "Pro plan - monthly", "amount_cents": 4900, "quantity": 1},
        {"description": "Extra seats", "amount_cents": 1000, "quantity": 3},
    ]


class TestInvoiceService:
    def test_create_invoice(self, inv_svc, sub_id, org_id, sample_line_items):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat(), sample_line_items)
        assert inv["subscription_id"] == sub_id
        assert inv["organization_id"] == org_id
        assert inv["status"] == InvoiceStatus.DRAFT.value
        assert inv["subtotal_cents"] == 7900
        assert inv["total_cents"] == 7900
        assert inv["invoice_number"].startswith("NF-")

    def test_create_invoice_no_items(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        assert inv["subtotal_cents"] == 0
        assert inv["total_cents"] == 0

    def test_get_invoice(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        got = inv_svc.get_invoice(inv["id"])
        assert got is not None
        assert got["id"] == inv["id"]

    def test_get_invoice_not_found(self, inv_svc):
        assert inv_svc.get_invoice("nonexistent") is None

    def test_get_invoice_by_number(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        by_num = inv_svc.get_invoice_by_number(inv["invoice_number"])
        assert by_num is not None
        assert by_num["id"] == inv["id"]

    def test_get_invoice_by_number_not_found(self, inv_svc):
        assert inv_svc.get_invoice_by_number("NF-000-00000000") is None

    def test_list_invoices(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=60)).isoformat())
        assert len(inv_svc.list_invoices(organization_id=org_id)) == 2

    def test_list_invoices_by_status(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        inv_svc.finalize_invoice(inv["id"])
        assert len(inv_svc.list_invoices(organization_id=org_id, status="open")) == 1

    def test_finalize_invoice(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        finalized = inv_svc.finalize_invoice(inv["id"])
        assert finalized["status"] == InvoiceStatus.OPEN.value
        assert finalized["due_date"] is not None

    def test_finalize_already_open(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        inv_svc.finalize_invoice(inv["id"])
        same = inv_svc.finalize_invoice(inv["id"])
        assert same["status"] == InvoiceStatus.OPEN.value

    def test_finalize_not_found(self, inv_svc):
        assert inv_svc.finalize_invoice("nonexistent") is None

    def test_void_invoice(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        voided = inv_svc.void_invoice(inv["id"])
        assert voided["status"] == InvoiceStatus.VOID.value
        assert voided["voided_at"] is not None
        assert voided["amount_due_cents"] == 0

    def test_void_not_found(self, inv_svc):
        assert inv_svc.void_invoice("nonexistent") is None

    def test_mark_paid(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat(), [{"description": "plan", "amount_cents": 4900, "quantity": 1}])
        inv_svc.finalize_invoice(inv["id"])
        paid = inv_svc.mark_paid(inv["id"])
        assert paid["status"] == InvoiceStatus.PAID.value
        assert paid["paid_at"] is not None
        assert paid["amount_paid_cents"] == 4900

    def test_mark_paid_partial(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat(), [{"description": "plan", "amount_cents": 4900, "quantity": 1}])
        inv_svc.finalize_invoice(inv["id"])
        paid = inv_svc.mark_paid(inv["id"], 2000)
        assert paid["amount_paid_cents"] == 2000
        assert paid["amount_due_cents"] > 0

    def test_mark_paid_not_found(self, inv_svc):
        assert inv_svc.mark_paid("nonexistent") is None

    def test_mark_uncollectible(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        uncol = inv_svc.mark_uncollectible(inv["id"])
        assert uncol["status"] == InvoiceStatus.UNCOLLECTIBLE.value

    def test_apply_discount(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat(), [{"description": "plan", "amount_cents": 4900, "quantity": 1}])
        discounted = inv_svc.apply_discount(inv["id"], 500)
        assert discounted["discount_cents"] == 500
        assert discounted["total_cents"] == 4400

    def test_apply_discount_not_found(self, inv_svc):
        assert inv_svc.apply_discount("nonexistent", 500) is None

    def test_add_line_item(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        updated = inv_svc.add_line_item(inv["id"], "Extra storage", 1000, 2)
        assert len(updated["line_items"]) == 1
        assert updated["subtotal_cents"] == 2000

    def test_add_line_item_not_found(self, inv_svc):
        assert inv_svc.add_line_item("nonexistent", "test", 100) is None

    def test_revenue_summary(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat(), [{"description": "plan", "amount_cents": 4900, "quantity": 1}])
        inv_svc.finalize_invoice(inv["id"])
        inv_svc.mark_paid(inv["id"])
        summary = inv_svc.get_org_revenue_summary(org_id)
        assert summary["total_revenue_cents"] == 4900

    def test_invoice_number_increments(self, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv1 = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        inv2 = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        assert inv1["invoice_number"] != inv2["invoice_number"]

    def test_telemetry(self, inv_svc):
        tel = inv_svc.get_telemetry()
        assert "total_invoices" in tel
        assert "by_status" in tel


class TestPaymentService:
    def test_process_payment_success(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat(), [{"description": "plan", "amount_cents": 4900, "quantity": 1}])
        payment = pay_svc.process_payment(inv["id"], org_id, 4900)
        assert payment["status"] == PaymentStatus.SUCCEEDED.value
        assert payment["amount_cents"] == 4900

    def test_get_payment(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        payment = pay_svc.process_payment(inv["id"], org_id, 4900)
        got = pay_svc.get_payment(payment["id"])
        assert got is not None
        assert got["id"] == payment["id"]

    def test_get_payment_not_found(self, pay_svc):
        assert pay_svc.get_payment("nonexistent") is None

    def test_list_payments(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        pay_svc.process_payment(inv["id"], org_id, 4900)
        pay_svc.process_payment(inv["id"], org_id, 1000)
        assert len(pay_svc.list_payments(invoice_id=inv["id"])) == 2

    def test_list_payments_by_status(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        pay_svc.process_payment(inv["id"], org_id, 4900)
        succeeded = pay_svc.list_payments(invoice_id=inv["id"], status="succeeded")
        assert len(succeeded) == 1

    def test_refund_payment(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        payment = pay_svc.process_payment(inv["id"], org_id, 4900)
        refunded = pay_svc.refund_payment(payment["id"], 2000)
        assert refunded["status"] == PaymentStatus.REFUNDED.value
        assert refunded["refund_amount_cents"] == 2000

    def test_refund_full(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        payment = pay_svc.process_payment(inv["id"], org_id, 4900)
        refunded = pay_svc.refund_payment(payment["id"])
        assert refunded["refund_amount_cents"] == 4900

    def test_refund_not_found(self, pay_svc):
        assert pay_svc.refund_payment("nonexistent") is None

    def test_mark_failed(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        payment = pay_svc.process_payment(inv["id"], org_id, 4900)
        failed = pay_svc.mark_failed(payment["id"], "insufficient funds")
        assert failed["status"] == PaymentStatus.FAILED.value
        assert failed["failure_reason"] == "insufficient funds"

    def test_mark_failed_not_found(self, pay_svc):
        assert pay_svc.mark_failed("nonexistent") is None

    def test_payment_summary(self, pay_svc, inv_svc, sub_id, org_id):
        now = datetime.now(timezone.utc)
        inv = inv_svc.create_invoice(sub_id, org_id, now.isoformat(), (now + timedelta(days=30)).isoformat())
        pay_svc.process_payment(inv["id"], org_id, 4900)
        pay_svc.process_payment(inv["id"], org_id, 1000)
        summary = pay_svc.get_payment_summary(org_id)
        assert summary["total_payments"] == 2
        assert summary["succeeded"] == 2
        assert summary["total_succeeded_cents"] == 5900

    def test_telemetry(self, pay_svc):
        tel = pay_svc.get_telemetry()
        assert "total_payments" in tel
        assert "by_status" in tel
