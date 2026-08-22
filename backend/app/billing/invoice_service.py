"""Invoice service — generate, finalize, void, list, and retrieve invoices."""
import uuid
import time
from datetime import datetime, timezone
from typing import Optional
from app.billing.constants import InvoiceStatus


class InvoiceService:
    def __init__(self):
        self._invoices: dict[str, dict] = {}
        self._sub_invoices: dict[str, list[str]] = {}
        self._org_invoices: dict[str, list[str]] = {}
        self._invoice_counter = 0

    def _next_invoice_number(self) -> str:
        self._invoice_counter += 1
        return f"NF-{int(time.time())}-{self._invoice_counter:08d}"

    def create_invoice(
        self,
        subscription_id: str,
        organization_id: str,
        period_start: str,
        period_end: str,
        line_items: Optional[list[dict]] = None,
        currency: str = "usd",
    ) -> dict:
        invoice_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        items = line_items or []
        subtotal = sum(item.get("amount_cents", 0) * item.get("quantity", 1) for item in items)
        invoice = {
            "id": invoice_id,
            "subscription_id": subscription_id,
            "organization_id": organization_id,
            "invoice_number": self._next_invoice_number(),
            "status": InvoiceStatus.DRAFT.value,
            "currency": currency,
            "subtotal_cents": subtotal,
            "tax_cents": 0,
            "discount_cents": 0,
            "total_cents": subtotal,
            "amount_due_cents": subtotal,
            "amount_paid_cents": 0,
            "period_start": period_start,
            "period_end": period_end,
            "due_date": None,
            "paid_at": None,
            "voided_at": None,
            "stripe_invoice_id": None,
            "line_items": items,
            "metadata": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._invoices[invoice_id] = invoice
        self._sub_invoices.setdefault(subscription_id, []).append(invoice_id)
        self._org_invoices.setdefault(organization_id, []).append(invoice_id)
        return invoice

    def get_invoice(self, invoice_id: str) -> Optional[dict]:
        return self._invoices.get(invoice_id)

    def get_invoice_by_number(self, invoice_number: str) -> Optional[dict]:
        for inv in self._invoices.values():
            if inv["invoice_number"] == invoice_number:
                return inv
        return None

    def list_invoices(
        self,
        organization_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        if subscription_id:
            invoice_ids = self._sub_invoices.get(subscription_id, [])
            results = [self._invoices[iid] for iid in invoice_ids if iid in self._invoices]
        elif organization_id:
            invoice_ids = self._org_invoices.get(organization_id, [])
            results = [self._invoices[iid] for iid in invoice_ids if iid in self._invoices]
        else:
            results = list(self._invoices.values())
        if status:
            results = [inv for inv in results if inv["status"] == status]
        return results[-limit:]

    def finalize_invoice(self, invoice_id: str) -> Optional[dict]:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return None
        if inv["status"] != InvoiceStatus.DRAFT.value:
            return inv
        now = datetime.now(timezone.utc)
        inv["status"] = InvoiceStatus.OPEN.value
        inv["due_date"] = (now + __import__("datetime").timedelta(days=30)).isoformat()
        inv["updated_at"] = now.isoformat()
        return inv

    def void_invoice(self, invoice_id: str) -> Optional[dict]:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return None
        now = datetime.now(timezone.utc)
        inv["status"] = InvoiceStatus.VOID.value
        inv["voided_at"] = now.isoformat()
        inv["amount_due_cents"] = 0
        inv["updated_at"] = now.isoformat()
        return inv

    def mark_paid(self, invoice_id: str, amount_cents: Optional[int] = None) -> Optional[dict]:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return None
        now = datetime.now(timezone.utc)
        paid = amount_cents if amount_cents is not None else inv["amount_due_cents"]
        inv["status"] = InvoiceStatus.PAID.value
        inv["amount_paid_cents"] = paid
        inv["amount_due_cents"] = max(0, inv["total_cents"] - inv["discount_cents"] - paid)
        inv["paid_at"] = now.isoformat()
        inv["updated_at"] = now.isoformat()
        return inv

    def mark_uncollectible(self, invoice_id: str) -> Optional[dict]:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return None
        now = datetime.now(timezone.utc)
        inv["status"] = InvoiceStatus.UNCOLLECTIBLE.value
        inv["updated_at"] = now.isoformat()
        return inv

    def apply_discount(self, invoice_id: str, discount_cents: int) -> Optional[dict]:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return None
        now = datetime.now(timezone.utc)
        inv["discount_cents"] = discount_cents
        inv["total_cents"] = inv["subtotal_cents"] - discount_cents + inv["tax_cents"]
        inv["amount_due_cents"] = max(0, inv["total_cents"] - inv["amount_paid_cents"])
        inv["updated_at"] = now.isoformat()
        return inv

    def add_line_item(self, invoice_id: str, description: str, amount_cents: int, quantity: int = 1) -> Optional[dict]:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return None
        now = datetime.now(timezone.utc)
        item = {
            "description": description,
            "amount_cents": amount_cents,
            "quantity": quantity,
            "total_cents": amount_cents * quantity,
        }
        inv["line_items"].append(item)
        inv["subtotal_cents"] = sum(i.get("amount_cents", 0) * i.get("quantity", 1) for i in inv["line_items"])
        inv["total_cents"] = inv["subtotal_cents"] - inv["discount_cents"] + inv["tax_cents"]
        inv["amount_due_cents"] = max(0, inv["total_cents"] - inv["amount_paid_cents"])
        inv["updated_at"] = now.isoformat()
        return inv

    def get_org_revenue_summary(self, organization_id: str) -> dict:
        invoices = self.list_invoices(organization_id=organization_id)
        total_revenue = sum(inv["amount_paid_cents"] for inv in invoices if inv["status"] == InvoiceStatus.PAID.value)
        outstanding = sum(inv["amount_due_cents"] for inv in invoices if inv["status"] in (InvoiceStatus.OPEN.value, InvoiceStatus.UNCOLLECTIBLE.value))
        return {
            "organization_id": organization_id,
            "total_invoices": len(invoices),
            "total_revenue_cents": total_revenue,
            "outstanding_cents": outstanding,
        }

    def get_telemetry(self) -> dict:
        statuses = {}
        for inv in self._invoices.values():
            statuses[inv["status"]] = statuses.get(inv["status"], 0) + 1
        return {
            "total_invoices": len(self._invoices),
            "by_status": statuses,
        }


invoice_service = InvoiceService()
