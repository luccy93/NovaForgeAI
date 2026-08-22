"""Payment service — process payments, refunds, webhooks, Stripe integration."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.billing.constants import PaymentStatus
from app.core.config import settings


class PaymentService:
    def __init__(self):
        self._payments: dict[str, dict] = {}
        self._invoice_payments: dict[str, list[str]] = {}
        self._org_payments: dict[str, list[str]] = {}
        self._stripe = None
        if settings.stripe_api_key:
            try:
                import stripe
                stripe.api_key = settings.stripe_api_key
                self._stripe = stripe
            except ImportError:
                pass

    @property
    def stripe_available(self) -> bool:
        return self._stripe is not None

    def process_payment(
        self,
        invoice_id: str,
        organization_id: str,
        amount_cents: int,
        currency: str = "usd",
        payment_method: str = "stripe",
        payment_method_id: Optional[str] = None,
    ) -> dict:
        payment_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        stripe_payment_intent_id = None
        if payment_method == "stripe" and self.stripe_available and payment_method_id:
            try:
                pi = self._stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency=currency,
                    payment_method=payment_method_id,
                    confirm=True,
                    metadata={"invoice_id": invoice_id, "organization_id": organization_id},
                )
                stripe_payment_intent_id = pi.id
                status = PaymentStatus.SUCCEEDED.value if pi.status == "succeeded" else PaymentStatus.PENDING.value
            except Exception:
                status = PaymentStatus.FAILED.value
        else:
            status = PaymentStatus.SUCCEEDED.value

        payment = {
            "id": payment_id,
            "invoice_id": invoice_id,
            "organization_id": organization_id,
            "amount_cents": amount_cents,
            "currency": currency,
            "status": status,
            "payment_method": payment_method,
            "stripe_payment_intent_id": stripe_payment_intent_id,
            "stripe_charge_id": None,
            "failure_reason": None,
            "refunded_at": None,
            "refund_amount_cents": 0,
            "metadata": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._payments[payment_id] = payment
        self._invoice_payments.setdefault(invoice_id, []).append(payment_id)
        self._org_payments.setdefault(organization_id, []).append(payment_id)
        return payment

    def get_payment(self, payment_id: str) -> Optional[dict]:
        return self._payments.get(payment_id)

    def list_payments(
        self,
        organization_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        if invoice_id:
            payment_ids = self._invoice_payments.get(invoice_id, [])
            results = [self._payments[pid] for pid in payment_ids if pid in self._payments]
        elif organization_id:
            payment_ids = self._org_payments.get(organization_id, [])
            results = [self._payments[pid] for pid in payment_ids if pid in self._payments]
        else:
            results = list(self._payments.values())
        if status:
            results = [p for p in results if p["status"] == status]
        return results[-limit:]

    def refund_payment(
        self,
        payment_id: str,
        amount_cents: Optional[int] = None,
        reason: str = "",
    ) -> Optional[dict]:
        payment = self._payments.get(payment_id)
        if not payment:
            return None
        now = datetime.now(timezone.utc)
        refund_amount = amount_cents if amount_cents is not None else payment["amount_cents"]
        if self.stripe_available and payment.get("stripe_payment_intent_id"):
            try:
                self._stripe.Refund.create(
                    payment_intent=payment["stripe_payment_intent_id"],
                    amount=refund_amount,
                    reason=reason if reason else "requested_by_customer",
                )
            except Exception:
                pass
        payment["status"] = PaymentStatus.REFUNDED.value
        payment["refunded_at"] = now.isoformat()
        payment["refund_amount_cents"] = refund_amount
        payment["updated_at"] = now.isoformat()
        return payment

    def mark_failed(self, payment_id: str, reason: str = "") -> Optional[dict]:
        payment = self._payments.get(payment_id)
        if not payment:
            return None
        now = datetime.now(timezone.utc)
        payment["status"] = PaymentStatus.FAILED.value
        payment["failure_reason"] = reason
        payment["updated_at"] = now.isoformat()
        return payment

    def process_webhook(self, payload: bytes, sig_header: str) -> Optional[dict]:
        if not self.stripe_available or not settings.stripe_webhook_secret:
            return None
        try:
            event = self._stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret,
            )
            return {"type": event.type, "data": event.data.object}
        except Exception:
            return None

    def get_payment_summary(self, organization_id: str) -> dict:
        payments = self.list_payments(organization_id=organization_id)
        succeeded = [p for p in payments if p["status"] == PaymentStatus.SUCCEEDED.value]
        failed = [p for p in payments if p["status"] == PaymentStatus.FAILED.value]
        refunded = [p for p in payments if p["status"] == PaymentStatus.REFUNDED.value]
        return {
            "organization_id": organization_id,
            "total_payments": len(payments),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "refunded": len(refunded),
            "total_succeeded_cents": sum(p["amount_cents"] for p in succeeded),
            "total_failed_cents": sum(p["amount_cents"] for p in failed),
            "total_refunded_cents": sum(p.get("refund_amount_cents", 0) for p in refunded),
        }

    def get_telemetry(self) -> dict:
        statuses = {}
        for p in self._payments.values():
            statuses[p["status"]] = statuses.get(p["status"], 0) + 1
        return {
            "total_payments": len(self._payments),
            "by_status": statuses,
        }


payment_service = PaymentService()
