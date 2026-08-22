"""Billing Pydantic schemas — request/response models for the billing API."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.billing.constants import (
    PlanTier, BillingCycle, SubscriptionStatus, InvoiceStatus, PaymentStatus,
    MeteringUnit, CreditType, CouponType, DunningAction, ReconciliationStatus,
)


class PlanCreate(BaseModel):
    tier: PlanTier
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=100)
    description: Optional[str] = None
    price_monthly_cents: int = 0
    price_annual_cents: int = 0
    max_seats: int = 3
    max_storage_gb: int = 1
    max_tokens_millions: int = 1
    features: list[str] = []
    stripe_price_monthly_id: Optional[str] = None
    stripe_price_annual_id: Optional[str] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_monthly_cents: Optional[int] = None
    price_annual_cents: Optional[int] = None
    max_seats: Optional[int] = None
    max_storage_gb: Optional[int] = None
    max_tokens_millions: Optional[int] = None
    features: Optional[list[str]] = None
    is_active: Optional[bool] = None


class SubscriptionCreate(BaseModel):
    organization_id: str
    plan_id: str
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    trial_days: Optional[int] = None
    seats: int = 1
    coupon_code: Optional[str] = None
    payment_method_id: Optional[str] = None


class SubscriptionUpdate(BaseModel):
    plan_id: Optional[str] = None
    billing_cycle: Optional[BillingCycle] = None
    seats: Optional[int] = None
    cancel_at_period_end: Optional[bool] = None


class SubscriptionCancel(BaseModel):
    reason: Optional[str] = None
    immediate: bool = False


class UsageRecordRequest(BaseModel):
    organization_id: str
    metric_name: str = Field(..., max_length=100)
    quantity: float = Field(..., gt=0)
    unit: MeteringUnit
    source: str = "system"
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[dict] = None


class UsageSummaryRequest(BaseModel):
    organization_id: str
    metric_name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class InvoiceCreate(BaseModel):
    subscription_id: str
    period_start: datetime
    period_end: datetime
    line_items: Optional[list[dict]] = None


class InvoiceFinalize(BaseModel):
    invoice_id: str


class PaymentProcess(BaseModel):
    invoice_id: str
    amount_cents: Optional[int] = None
    payment_method: str = "stripe"
    payment_method_id: Optional[str] = None


class PaymentRefund(BaseModel):
    payment_id: str
    amount_cents: Optional[int] = None
    reason: Optional[str] = None


class CreditGrant(BaseModel):
    organization_id: str
    amount_cents: int = Field(..., gt=0)
    credit_type: CreditType = CreditType.GRANTED
    description: Optional[str] = None
    expires_at: Optional[datetime] = None


class CreditDeduct(BaseModel):
    organization_id: str
    amount_cents: int = Field(..., gt=0)
    invoice_id: Optional[str] = None
    description: Optional[str] = None


class CouponCreate(BaseModel):
    code: str = Field(..., max_length=100)
    description: Optional[str] = None
    coupon_type: CouponType
    value_cents: int = Field(..., gt=0)
    currency: str = "usd"
    max_redemptions: int = 10000
    applies_to_plans: Optional[list[str]] = None
    min_subscription_cents: int = 0
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class CouponApply(BaseModel):
    coupon_code: str
    subscription_id: Optional[str] = None
    invoice_id: Optional[str] = None


class BudgetCreate(BaseModel):
    organization_id: str
    name: str = Field(..., max_length=255)
    scope: str = "organization"
    scope_value: Optional[str] = None
    limit_cents: int = Field(..., gt=0)
    period: str = "monthly"
    warning_threshold: float = 0.80
    hard_limit_threshold: float = 1.0


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    limit_cents: Optional[int] = None
    warning_threshold: Optional[float] = None
    hard_limit_threshold: Optional[float] = None
    is_active: Optional[bool] = None


class MarketplacePurchaseRequest(BaseModel):
    organization_id: str
    package_id: str
    publisher_org_id: str
    pricing_type: str = "subscription"
    amount_cents: int = 0
    billing_period: str = "monthly"


class DunningActionRequest(BaseModel):
    subscription_id: str
    invoice_id: str
    action: DunningAction
    reason: Optional[str] = None


class ReconciliationCreate(BaseModel):
    invoice_id: str
    expected_amount_cents: int
    actual_amount_cents: Optional[int] = None


class ReconciliationResolve(BaseModel):
    reconciliation_id: str
    resolution_notes: str
    resolved_by: str


class CheckoutSessionRequest(BaseModel):
    plan_id: str
    organization_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    customer_email: Optional[str] = None
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
