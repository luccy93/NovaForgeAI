"""Billing SDK mixin — Production-Grade Billing Platform (Volume 53)."""
from __future__ import annotations


class BillingMixin:
    def billing_list_plans(self):
        return self._get("/billing/plans")

    def billing_get_plan(self, plan_id):
        return self._get(f"/billing/plans/{plan_id}")

    def billing_create_plan(self, tier, name, slug, description="", price_monthly=0, price_annual=0, max_seats=3, max_storage_gb=1, max_tokens_millions=1, features=None):
        return self._post("/billing/plans", json={"tier": tier, "name": name, "slug": slug, "description": description, "price_monthly_cents": price_monthly, "price_annual_cents": price_annual, "max_seats": max_seats, "max_storage_gb": max_storage_gb, "max_tokens_millions": max_tokens_millions, "features": features or []})

    def billing_update_plan(self, plan_id, **kwargs):
        return self._put(f"/billing/plans/{plan_id}", json=kwargs)

    def billing_delete_plan(self, plan_id):
        return self._delete(f"/billing/plans/{plan_id}")

    def billing_create_subscription(self, organization_id, plan_id, billing_cycle="monthly", trial_days=None, seats=1, coupon_code=None):
        return self._post("/billing/subscriptions", json={"organization_id": organization_id, "plan_id": plan_id, "billing_cycle": billing_cycle, "trial_days": trial_days, "seats": seats, "coupon_code": coupon_code})

    def billing_get_subscription(self, subscription_id):
        return self._get(f"/billing/subscriptions/{subscription_id}")

    def billing_list_org_subscriptions(self, organization_id):
        return self._get(f"/billing/subscriptions/organization/{organization_id}")

    def billing_get_active_subscription(self, organization_id):
        return self._get(f"/billing/subscriptions/active/{organization_id}")

    def billing_update_subscription(self, subscription_id, **kwargs):
        return self._put(f"/billing/subscriptions/{subscription_id}", json=kwargs)

    def billing_cancel_subscription(self, subscription_id, reason="", immediate=False):
        return self._post(f"/billing/subscriptions/{subscription_id}/cancel", json={"reason": reason, "immediate": immediate})

    def billing_reactivate_subscription(self, subscription_id):
        return self._post(f"/billing/subscriptions/{subscription_id}/reactivate")

    def billing_advance_subscription(self, subscription_id):
        return self._post(f"/billing/subscriptions/{subscription_id}/advance")

    def billing_subscription_analytics(self, organization_id):
        return self._get(f"/billing/subscriptions/analytics/{organization_id}")

    def billing_record_usage(self, organization_id, metric_name, quantity, unit, source="system", resource_id=None, resource_type=None):
        return self._post("/billing/usage/record", json={"organization_id": organization_id, "metric_name": metric_name, "quantity": quantity, "unit": unit, "source": source, "resource_id": resource_id, "resource_type": resource_type})

    def billing_usage_summary(self, organization_id, metric=""):
        return self._get(f"/billing/usage/summary/{organization_id}", params={"metric": metric} if metric else {})

    def billing_usage_check_limit(self, organization_id, metric, limit):
        return self._get(f"/billing/usage/check-limit/{organization_id}", params={"metric": metric, "limit": limit})

    def billing_create_invoice(self, subscription_id, period_start, period_end, line_items=None):
        return self._post("/billing/invoices", json={"subscription_id": subscription_id, "period_start": period_start, "period_end": period_end, "line_items": line_items})

    def billing_get_invoice(self, invoice_id):
        return self._get(f"/billing/invoices/{invoice_id}")

    def billing_list_invoices(self, organization_id="", subscription_id="", status=""):
        return self._get("/billing/invoices", params={"organization_id": organization_id, "subscription_id": subscription_id, "status": status})

    def billing_finalize_invoice(self, invoice_id):
        return self._post(f"/billing/invoices/{invoice_id}/finalize")

    def billing_void_invoice(self, invoice_id):
        return self._post(f"/billing/invoices/{invoice_id}/void")

    def billing_pay_invoice(self, invoice_id, amount_cents=0):
        return self._post(f"/billing/invoices/{invoice_id}/pay", params={"amount_cents": amount_cents})

    def billing_revenue_summary(self, organization_id):
        return self._get(f"/billing/revenue/{organization_id}")

    def billing_process_payment(self, invoice_id, amount_cents=0, payment_method="stripe"):
        return self._post("/billing/payments", json={"invoice_id": invoice_id, "amount_cents": amount_cents, "payment_method": payment_method})

    def billing_get_payment(self, payment_id):
        return self._get(f"/billing/payments/{payment_id}")

    def billing_refund_payment(self, payment_id, amount_cents=None, reason=""):
        return self._post(f"/billing/payments/{payment_id}/refund", json={"amount_cents": amount_cents, "reason": reason})

    def billing_payment_summary(self, organization_id):
        return self._get(f"/billing/payments/summary/{organization_id}")

    def billing_grant_credits(self, organization_id, amount_cents, credit_type="granted", description="", expires_at=None):
        return self._post("/billing/credits/grant", json={"organization_id": organization_id, "amount_cents": amount_cents, "credit_type": credit_type, "description": description, "expires_at": expires_at})

    def billing_deduct_credits(self, organization_id, amount_cents, invoice_id=None, description=""):
        return self._post("/billing/credits/deduct", json={"organization_id": organization_id, "amount_cents": amount_cents, "invoice_id": invoice_id, "description": description})

    def billing_credit_balance(self, organization_id):
        return self._get(f"/billing/credits/balance/{organization_id}")

    def billing_create_coupon(self, code, coupon_type, value_cents, description="", max_redemptions=10000, applies_to_plans=None):
        return self._post("/billing/coupons", json={"code": code, "coupon_type": coupon_type, "value_cents": value_cents, "description": description, "max_redemptions": max_redemptions, "applies_to_plans": applies_to_plans})

    def billing_list_coupons(self, active_only=True):
        return self._get("/billing/coupons", params={"active_only": active_only})

    def billing_validate_coupon(self, code, plan_id="", amount=0):
        return self._post("/billing/coupons/validate", params={"code": code, "plan_id": plan_id, "amount": amount})

    def billing_apply_coupon(self, coupon_code, subscription_id=None, invoice_id=None):
        return self._post("/billing/coupons/apply", json={"coupon_code": coupon_code, "subscription_id": subscription_id, "invoice_id": invoice_id})

    def billing_create_budget(self, organization_id, name, limit_cents, scope="organization", period="monthly"):
        return self._post("/billing/budgets", json={"organization_id": organization_id, "name": name, "limit_cents": limit_cents, "scope": scope, "period": period})

    def billing_get_budget(self, budget_id):
        return self._get(f"/billing/budgets/{budget_id}")

    def billing_list_budgets(self, organization_id):
        return self._get(f"/billing/budgets/organization/{organization_id}")

    def billing_check_budget(self, budget_id):
        return self._get(f"/billing/budgets/{budget_id}/check")

    def billing_budget_status(self, organization_id):
        return self._get(f"/billing/budgets/status/{organization_id}")

    def billing_marketplace_purchase(self, organization_id, package_id, publisher_org_id, amount_cents, pricing_type="subscription"):
        return self._post("/billing/marketplace/purchase", json={"organization_id": organization_id, "package_id": package_id, "publisher_org_id": publisher_org_id, "amount_cents": amount_cents, "pricing_type": pricing_type})

    def billing_marketplace_summary(self):
        return self._get("/billing/marketplace/summary")

    def billing_publisher_revenue(self, publisher_org_id):
        return self._get(f"/billing/marketplace/publisher/{publisher_org_id}")

    def billing_telemetry(self):
        return self._get("/billing/telemetry")


class AsyncBillingMixin:
    async def billing_list_plans(self):
        return await self._get("/billing/plans")

    async def billing_get_plan(self, plan_id):
        return await self._get(f"/billing/plans/{plan_id}")

    async def billing_create_subscription(self, organization_id, plan_id, billing_cycle="monthly", trial_days=None, seats=1):
        return await self._post("/billing/subscriptions", json={"organization_id": organization_id, "plan_id": plan_id, "billing_cycle": billing_cycle, "trial_days": trial_days, "seats": seats})

    async def billing_get_subscription(self, subscription_id):
        return await self._get(f"/billing/subscriptions/{subscription_id}")

    async def billing_cancel_subscription(self, subscription_id, reason="", immediate=False):
        return await self._post(f"/billing/subscriptions/{subscription_id}/cancel", json={"reason": reason, "immediate": immediate})

    async def billing_reactivate_subscription(self, subscription_id):
        return await self._post(f"/billing/subscriptions/{subscription_id}/reactivate")

    async def billing_record_usage(self, organization_id, metric_name, quantity, unit):
        return await self._post("/billing/usage/record", json={"organization_id": organization_id, "metric_name": metric_name, "quantity": quantity, "unit": unit})

    async def billing_usage_summary(self, organization_id):
        return await self._get(f"/billing/usage/summary/{organization_id}")

    async def billing_create_invoice(self, subscription_id, period_start, period_end, line_items=None):
        return await self._post("/billing/invoices", json={"subscription_id": subscription_id, "period_start": period_start, "period_end": period_end, "line_items": line_items})

    async def billing_get_invoice(self, invoice_id):
        return await self._get(f"/billing/invoices/{invoice_id}")

    async def billing_finalize_invoice(self, invoice_id):
        return await self._post(f"/billing/invoices/{invoice_id}/finalize")

    async def billing_grant_credits(self, organization_id, amount_cents, credit_type="granted"):
        return await self._post("/billing/credits/grant", json={"organization_id": organization_id, "amount_cents": amount_cents, "credit_type": credit_type})

    async def billing_credit_balance(self, organization_id):
        return await self._get(f"/billing/credits/balance/{organization_id}")

    async def billing_create_coupon(self, code, coupon_type, value_cents, max_redemptions=10000):
        return await self._post("/billing/coupons", json={"code": code, "coupon_type": coupon_type, "value_cents": value_cents, "max_redemptions": max_redemptions})

    async def billing_create_budget(self, organization_id, name, limit_cents, scope="organization"):
        return await self._post("/billing/budgets", json={"organization_id": organization_id, "name": name, "limit_cents": limit_cents, "scope": scope})

    async def billing_check_budget(self, budget_id):
        return await self._get(f"/billing/budgets/{budget_id}/check")

    async def billing_telemetry(self):
        return await self._get("/billing/telemetry")
