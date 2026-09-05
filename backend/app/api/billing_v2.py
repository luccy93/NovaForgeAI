"""Billing V2 API — Production-Grade Billing Platform (Volume 53)"""
import asyncio
from fastapi import APIRouter, HTTPException
from app.billing.schemas import (
    PlanCreate, PlanUpdate, SubscriptionCreate, SubscriptionUpdate, SubscriptionCancel,
    UsageRecordRequest, UsageSummaryRequest, InvoiceCreate, InvoiceFinalize,
    PaymentProcess, PaymentRefund, CreditGrant, CreditDeduct,
    CouponCreate, CouponApply, BudgetCreate, BudgetUpdate,
    MarketplacePurchaseRequest, DunningActionRequest,
    ReconciliationCreate, ReconciliationResolve, CheckoutSessionRequest,
)

router = APIRouter()


# ─── Plans ───────────────────────────────────────────────────────────────────
#
# NOTE (V72): GET /billing/plans and GET /billing/plans/{plan_id} are served
# by the legacy billing router (registered first); the twins that lived here
# were unreachable dead code and have been removed. POST/PUT/DELETE below
# remain the managed write surface.

@router.post("/billing/plans")
async def create_plan(body: PlanCreate):
    from app.billing.plan_service import plan_service
    plan = await asyncio.to_thread(
        plan_service.create_plan, body.tier.value, body.name, body.slug,
        body.description or "", body.price_monthly_cents, body.price_annual_cents,
        body.max_seats, body.max_storage_gb, body.max_tokens_millions,
        body.features, body.stripe_price_monthly_id, body.stripe_price_annual_id,
    )
    return plan


@router.put("/billing/plans/{plan_id}")
async def update_plan(plan_id: str, body: PlanUpdate):
    from app.billing.plan_service import plan_service
    kwargs = body.model_dump(exclude_none=True)
    plan = await asyncio.to_thread(plan_service.update_plan, plan_id, **kwargs)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.delete("/billing/plans/{plan_id}")
async def delete_plan(plan_id: str):
    from app.billing.plan_service import plan_service
    deleted = await asyncio.to_thread(plan_service.delete_plan, plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"deleted": True}


# ─── Subscriptions ───────────────────────────────────────────────────────────

@router.post("/billing/subscriptions")
async def create_subscription(body: SubscriptionCreate):
    from app.billing.subscription_service import subscription_service
    sub = await asyncio.to_thread(
        subscription_service.create_subscription,
        body.organization_id, body.plan_id, body.billing_cycle.value,
        body.trial_days, body.seats, None,
    )
    return sub


@router.get("/billing/subscriptions/{subscription_id}")
async def get_subscription(subscription_id: str):
    from app.billing.subscription_service import subscription_service
    sub = await asyncio.to_thread(subscription_service.get_subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.get("/billing/subscriptions/organization/{organization_id}")
async def list_org_subscriptions(organization_id: str):
    from app.billing.subscription_service import subscription_service
    return await asyncio.to_thread(subscription_service.get_organization_subscriptions, organization_id)


@router.get("/billing/subscriptions/active/{organization_id}")
async def get_active_subscription(organization_id: str):
    from app.billing.subscription_service import subscription_service
    sub = await asyncio.to_thread(subscription_service.get_active_subscription, organization_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription")
    return sub


@router.put("/billing/subscriptions/{subscription_id}")
async def update_subscription(subscription_id: str, body: SubscriptionUpdate):
    from app.billing.subscription_service import subscription_service
    kwargs = body.model_dump(exclude_none=True)
    if "billing_cycle" in kwargs:
        kwargs["billing_cycle"] = kwargs["billing_cycle"].value if kwargs["billing_cycle"] else None
    sub = await asyncio.to_thread(subscription_service.update_subscription, subscription_id, **kwargs)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.post("/billing/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(subscription_id: str, body: SubscriptionCancel):
    from app.billing.subscription_service import subscription_service
    sub = await asyncio.to_thread(
        subscription_service.cancel_subscription, subscription_id, body.immediate, body.reason or "",
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.post("/billing/subscriptions/{subscription_id}/reactivate")
async def reactivate_subscription(subscription_id: str):
    from app.billing.subscription_service import subscription_service
    sub = await asyncio.to_thread(subscription_service.reactivate_subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.post("/billing/subscriptions/{subscription_id}/advance")
async def advance_subscription_period(subscription_id: str):
    from app.billing.subscription_service import subscription_service
    sub = await asyncio.to_thread(subscription_service.advance_period, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.get("/billing/subscriptions/analytics/{organization_id}")
async def subscription_analytics(organization_id: str):
    from app.billing.subscription_service import subscription_service
    return await asyncio.to_thread(subscription_service.get_subscription_analytics, organization_id)


# ─── Usage Metering ──────────────────────────────────────────────────────────

@router.post("/billing/usage/record")
async def record_usage(body: UsageRecordRequest):
    from app.billing.meter_service import meter_service
    return await asyncio.to_thread(
        meter_service.record_usage,
        body.organization_id, body.metric_name, body.quantity, body.unit.value,
        body.source, body.resource_id, body.resource_type, None, body.timestamp, body.metadata,
    )


@router.post("/billing/usage/query")
async def query_usage(body: UsageSummaryRequest):
    from app.billing.meter_service import meter_service
    return await asyncio.to_thread(
        meter_service.get_usage, body.organization_id, body.metric_name,
        body.start_date, body.end_date,
    )


@router.get("/billing/usage/summary/{organization_id}")
async def usage_summary(organization_id: str, metric: str = ""):
    from app.billing.meter_service import meter_service
    return await asyncio.to_thread(meter_service.get_usage_summary, organization_id, metric or None)


@router.get("/billing/usage/aggregated/{organization_id}")
async def aggregated_usage(organization_id: str, metric: str = ""):
    from app.billing.meter_service import meter_service
    return await asyncio.to_thread(meter_service.get_aggregated_usage, organization_id, metric or None)


@router.get("/billing/usage/by-resource/{organization_id}/{resource_type}")
async def usage_by_resource(organization_id: str, resource_type: str):
    from app.billing.meter_service import meter_service
    return await asyncio.to_thread(meter_service.get_usage_by_resource, organization_id, resource_type)


@router.get("/billing/usage/check-limit/{organization_id}")
async def check_usage_limit(organization_id: str, metric: str, limit: float):
    from app.billing.meter_service import meter_service
    return await asyncio.to_thread(meter_service.check_usage_limit, organization_id, metric, limit)


# ─── Invoices ────────────────────────────────────────────────────────────────

@router.post("/billing/invoices")
async def create_invoice(body: InvoiceCreate):
    from app.billing.invoice_service import invoice_service
    return await asyncio.to_thread(
        invoice_service.create_invoice,
        body.subscription_id, "", body.period_start.isoformat(),
        body.period_end.isoformat(), body.line_items,
    )


@router.get("/billing/invoices/{invoice_id}")
async def get_invoice(invoice_id: str):
    from app.billing.invoice_service import invoice_service
    inv = await asyncio.to_thread(invoice_service.get_invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.get("/billing/invoices")
async def list_invoices(organization_id: str = "", subscription_id: str = "", status: str = ""):
    from app.billing.invoice_service import invoice_service
    return await asyncio.to_thread(
        invoice_service.list_invoices, organization_id or None, subscription_id or None, status or None,
    )


@router.post("/billing/invoices/{invoice_id}/finalize")
async def finalize_invoice(invoice_id: str):
    from app.billing.invoice_service import invoice_service
    inv = await asyncio.to_thread(invoice_service.finalize_invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/billing/invoices/{invoice_id}/void")
async def void_invoice(invoice_id: str):
    from app.billing.invoice_service import invoice_service
    inv = await asyncio.to_thread(invoice_service.void_invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/billing/invoices/{invoice_id}/pay")
async def mark_invoice_paid(invoice_id: str, amount_cents: int = 0):
    from app.billing.invoice_service import invoice_service
    inv = await asyncio.to_thread(invoice_service.mark_paid, invoice_id, amount_cents or None)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/billing/invoices/{invoice_id}/discount")
async def apply_invoice_discount(invoice_id: str, discount_cents: int):
    from app.billing.invoice_service import invoice_service
    inv = await asyncio.to_thread(invoice_service.apply_discount, invoice_id, discount_cents)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.get("/billing/revenue/{organization_id}")
async def revenue_summary(organization_id: str):
    from app.billing.invoice_service import invoice_service
    return await asyncio.to_thread(invoice_service.get_org_revenue_summary, organization_id)


# ─── Payments ────────────────────────────────────────────────────────────────

@router.post("/billing/payments")
async def process_payment(body: PaymentProcess):
    from app.billing.payment_service import payment_service
    return await asyncio.to_thread(
        payment_service.process_payment,
        body.invoice_id, "", body.amount_cents, "usd",
        body.payment_method, body.payment_method_id,
    )


@router.get("/billing/payments/{payment_id}")
async def get_payment(payment_id: str):
    from app.billing.payment_service import payment_service
    pay = await asyncio.to_thread(payment_service.get_payment, payment_id)
    if not pay:
        raise HTTPException(status_code=404, detail="Payment not found")
    return pay


@router.get("/billing/payments")
async def list_payments(organization_id: str = "", invoice_id: str = "", status: str = ""):
    from app.billing.payment_service import payment_service
    return await asyncio.to_thread(
        payment_service.list_payments, organization_id or None, invoice_id or None, status or None,
    )


@router.post("/billing/payments/{payment_id}/refund")
async def refund_payment(payment_id: str, body: PaymentRefund):
    from app.billing.payment_service import payment_service
    pay = await asyncio.to_thread(
        payment_service.refund_payment, payment_id, body.amount_cents, body.reason or "",
    )
    if not pay:
        raise HTTPException(status_code=404, detail="Payment not found")
    return pay


@router.get("/billing/payments/summary/{organization_id}")
async def payment_summary(organization_id: str):
    from app.billing.payment_service import payment_service
    return await asyncio.to_thread(payment_service.get_payment_summary, organization_id)


# ─── Credits ─────────────────────────────────────────────────────────────────

@router.post("/billing/credits/grant")
async def grant_credits(body: CreditGrant):
    from app.billing.credit_service import credit_service
    return await asyncio.to_thread(
        credit_service.grant_credits,
        body.organization_id, body.amount_cents, body.credit_type.value,
        body.description or "", body.expires_at,
    )


@router.post("/billing/credits/deduct")
async def deduct_credits(body: CreditDeduct):
    from app.billing.credit_service import credit_service
    return await asyncio.to_thread(
        credit_service.deduct_credits,
        body.organization_id, body.amount_cents, body.invoice_id, body.description or "",
    )


@router.get("/billing/credits/balance/{organization_id}")
async def credit_balance(organization_id: str):
    from app.billing.credit_service import credit_service
    return await asyncio.to_thread(credit_service.get_balance, organization_id)


@router.get("/billing/credits/transactions/{organization_id}")
async def credit_transactions(organization_id: str):
    from app.billing.credit_service import credit_service
    return await asyncio.to_thread(credit_service.get_transactions, organization_id)


# ─── Coupons ─────────────────────────────────────────────────────────────────

@router.post("/billing/coupons")
async def create_coupon(body: CouponCreate):
    from app.billing.coupon_service import coupon_service
    return await asyncio.to_thread(
        coupon_service.create_coupon,
        body.code, body.coupon_type.value, body.value_cents,
        body.description or "", body.currency, body.max_redemptions,
        body.applies_to_plans, body.min_subscription_cents,
        body.starts_at, body.expires_at,
    )


@router.get("/billing/coupons")
async def list_coupons(active_only: bool = True):
    from app.billing.coupon_service import coupon_service
    return await asyncio.to_thread(coupon_service.list_coupons, active_only)


@router.get("/billing/coupons/{coupon_id}")
async def get_coupon(coupon_id: str):
    from app.billing.coupon_service import coupon_service
    coupon = await asyncio.to_thread(coupon_service.get_coupon, coupon_id)
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    return coupon


@router.post("/billing/coupons/validate")
async def validate_coupon(code: str, plan_id: str = "", amount: int = 0):
    from app.billing.coupon_service import coupon_service
    return await asyncio.to_thread(coupon_service.validate_coupon, code, plan_id or None, amount)


@router.post("/billing/coupons/apply")
async def apply_coupon(body: CouponApply):
    from app.billing.coupon_service import coupon_service
    try:
        return await asyncio.to_thread(
            coupon_service.apply_coupon,
            body.coupon_code, "", 0, body.subscription_id, body.invoice_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/billing/coupons/{coupon_id}")
async def delete_coupon(coupon_id: str):
    from app.billing.coupon_service import coupon_service
    deleted = await asyncio.to_thread(coupon_service.delete_coupon, coupon_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Coupon not found")
    return {"deleted": True}


# ─── Budgets ─────────────────────────────────────────────────────────────────

@router.post("/billing/budgets")
async def create_budget(body: BudgetCreate):
    from app.billing.budget_service import budget_service
    return await asyncio.to_thread(
        budget_service.create_budget,
        body.organization_id, body.name, body.limit_cents,
        body.scope, body.scope_value, body.period,
        body.warning_threshold, body.hard_limit_threshold,
    )


@router.get("/billing/budgets/{budget_id}")
async def get_budget(budget_id: str):
    from app.billing.budget_service import budget_service
    budget = await asyncio.to_thread(budget_service.get_budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("/billing/budgets/organization/{organization_id}")
async def list_budgets(organization_id: str):
    from app.billing.budget_service import budget_service
    return await asyncio.to_thread(budget_service.list_budgets, organization_id)


@router.put("/billing/budgets/{budget_id}")
async def update_budget(budget_id: str, body: BudgetUpdate):
    from app.billing.budget_service import budget_service
    kwargs = body.model_dump(exclude_none=True)
    budget = await asyncio.to_thread(budget_service.update_budget, budget_id, **kwargs)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("/billing/budgets/{budget_id}/check")
async def check_budget(budget_id: str):
    from app.billing.budget_service import budget_service
    return await asyncio.to_thread(budget_service.check_budget, budget_id)


@router.get("/billing/budgets/status/{organization_id}")
async def budget_status(organization_id: str):
    from app.billing.budget_service import budget_service
    return await asyncio.to_thread(budget_service.get_budget_status, organization_id)


@router.delete("/billing/budgets/{budget_id}")
async def delete_budget(budget_id: str):
    from app.billing.budget_service import budget_service
    deleted = await asyncio.to_thread(budget_service.delete_budget, budget_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"deleted": True}


# ─── Marketplace Billing ─────────────────────────────────────────────────────

@router.post("/billing/marketplace/purchase")
async def marketplace_purchase(body: MarketplacePurchaseRequest):
    from app.billing.marketplace_billing import marketplace_billing_service
    return await asyncio.to_thread(
        marketplace_billing_service.record_purchase,
        body.organization_id, body.package_id, body.publisher_org_id,
        body.pricing_type, body.amount_cents, body.billing_period,
    )


@router.get("/billing/marketplace/summary")
async def marketplace_summary():
    from app.billing.marketplace_billing import marketplace_billing_service
    return await asyncio.to_thread(marketplace_billing_service.get_marketplace_summary)


@router.get("/billing/marketplace/publisher/{publisher_org_id}")
async def publisher_revenue(publisher_org_id: str):
    from app.billing.marketplace_billing import marketplace_billing_service
    return await asyncio.to_thread(marketplace_billing_service.get_publisher_revenue, publisher_org_id)


@router.get("/billing/marketplace/package/{package_id}")
async def package_revenue(package_id: str):
    from app.billing.marketplace_billing import marketplace_billing_service
    return await asyncio.to_thread(marketplace_billing_service.get_package_revenue, package_id)


# ─── Dunning ─────────────────────────────────────────────────────────────────

@router.post("/billing/dunning")
async def create_dunning(body: DunningActionRequest):
    from app.billing.dunning_service import dunning_service
    return await asyncio.to_thread(
        dunning_service.create_dunning_record,
        body.subscription_id, "", body.invoice_id, body.action.value, body.reason or "",
    )


@router.get("/billing/dunning/subscription/{subscription_id}")
async def subscription_dunning(subscription_id: str):
    from app.billing.dunning_service import dunning_service
    return await asyncio.to_thread(dunning_service.get_subscription_dunning, subscription_id)


@router.get("/billing/dunning/check/{subscription_id}")
async def should_suspend(subscription_id: str):
    from app.billing.dunning_service import dunning_service
    return {"should_suspend": await asyncio.to_thread(dunning_service.should_suspend, subscription_id)}


# ─── Reconciliation ──────────────────────────────────────────────────────────

@router.post("/billing/reconciliation")
async def create_reconciliation(body: ReconciliationCreate):
    from app.billing.reconciliation_service import reconciliation_service
    return await asyncio.to_thread(
        reconciliation_service.create_reconciliation,
        body.invoice_id, "", body.expected_amount_cents, body.actual_amount_cents,
    )


@router.get("/billing/reconciliation/summary/{organization_id}")
async def reconciliation_summary(organization_id: str):
    from app.billing.reconciliation_service import reconciliation_service
    return await asyncio.to_thread(reconciliation_service.get_reconciliation_summary, organization_id)


@router.post("/billing/reconciliation/resolve")
async def resolve_reconciliation(body: ReconciliationResolve):
    from app.billing.reconciliation_service import reconciliation_service
    rec = await asyncio.to_thread(
        reconciliation_service.resolve_reconciliation,
        body.reconciliation_id, body.resolution_notes, body.resolved_by,
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Reconciliation record not found")
    return rec


# ─── Telemetry ───────────────────────────────────────────────────────────────

@router.get("/billing/telemetry")
async def billing_telemetry():
    from app.billing.plan_service import plan_service
    from app.billing.subscription_service import subscription_service
    from app.billing.meter_service import meter_service
    from app.billing.invoice_service import invoice_service
    from app.billing.payment_service import payment_service
    from app.billing.credit_service import credit_service
    from app.billing.coupon_service import coupon_service
    from app.billing.budget_service import budget_service
    from app.billing.marketplace_billing import marketplace_billing_service
    from app.billing.dunning_service import dunning_service
    from app.billing.reconciliation_service import reconciliation_service
    return {
        "plans": await asyncio.to_thread(plan_service.get_telemetry),
        "subscriptions": await asyncio.to_thread(subscription_service.get_telemetry),
        "metering": await asyncio.to_thread(meter_service.get_telemetry),
        "invoices": await asyncio.to_thread(invoice_service.get_telemetry),
        "payments": await asyncio.to_thread(payment_service.get_telemetry),
        "credits": await asyncio.to_thread(credit_service.get_telemetry),
        "coupons": await asyncio.to_thread(coupon_service.get_telemetry),
        "budgets": await asyncio.to_thread(budget_service.get_telemetry),
        "marketplace": await asyncio.to_thread(marketplace_billing_service.get_telemetry),
        "dunning": await asyncio.to_thread(dunning_service.get_telemetry),
        "reconciliation": await asyncio.to_thread(reconciliation_service.get_telemetry),
    }
