"""Billing SQLAlchemy models — subscriptions, invoicing, payments, metering, credits, coupons, budgets, marketplace billing."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Table, Column,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class BillingPlan(Base, TimestampMixin):
    __tablename__ = "billing_plans"

    tier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price_monthly_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_annual_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_seats: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_tokens_millions: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stripe_price_monthly_id: Mapped[Optional[str]] = mapped_column(String(255))
    stripe_price_annual_id: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_billing_plans_tier", "tier"),
    )


class BillingSubscription(Base, TimestampMixin):
    __tablename__ = "billing_subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_plans.id"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trial_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    organization = relationship("Organization")
    plan = relationship("BillingPlan")
    invoices = relationship("BillingInvoice", back_populates="subscription", cascade="all, delete-orphan")
    metering_records = relationship("UsageMetering", back_populates="subscription")

    __table_args__ = (
        Index("ix_billing_subscriptions_org_id", "organization_id"),
        Index("ix_billing_subscriptions_org_status", "organization_id", "status"),
    )


class BillingInvoice(Base, TimestampMixin):
    __tablename__ = "billing_invoices"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_subscriptions.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="usd", nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_due_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stripe_invoice_id: Mapped[Optional[str]] = mapped_column(String(255))
    line_items: Mapped[dict] = mapped_column(JSONB, default=list)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    subscription = relationship("BillingSubscription", back_populates="invoices")
    organization = relationship("Organization")
    payments = relationship("BillingPayment", back_populates="invoice", cascade="all, delete-orphan")
    reconciliations = relationship("ReconciliationRecord", back_populates="invoice")

    __table_args__ = (
        Index("ix_billing_invoices_org_id", "organization_id"),
        Index("ix_billing_invoices_sub_id", "subscription_id"),
        Index("ix_billing_invoices_status", "status"),
        Index("ix_billing_invoices_number", "invoice_number"),
    )


class BillingPayment(Base, TimestampMixin):
    __tablename__ = "billing_payments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="usd", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), default="stripe", nullable=False)
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255))
    stripe_charge_id: Mapped[Optional[str]] = mapped_column(String(255))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refund_amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    invoice = relationship("BillingInvoice", back_populates="payments")
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_billing_payments_invoice_id", "invoice_id"),
        Index("ix_billing_payments_org_id", "organization_id"),
        Index("ix_billing_payments_status", "status"),
    )


class UsageMetering(Base, TimestampMixin):
    __tablename__ = "billing_usage_metering"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_subscriptions.id"), nullable=True,
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    rate_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    resource_type: Mapped[Optional[str]] = mapped_column(String(100))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    subscription = relationship("BillingSubscription", back_populates="metering_records")
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_billing_metering_org_id", "organization_id"),
        Index("ix_billing_metering_metric", "metric_name"),
        Index("ix_billing_metering_org_metric", "organization_id", "metric_name"),
        Index("ix_billing_metering_period", "period_start", "period_end"),
    )


class CreditBalance(Base, TimestampMixin):
    __tablename__ = "billing_credits"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    balance_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_granted_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_used_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="usd", nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    organization = relationship("Organization")
    transactions = relationship("CreditTransaction", back_populates="balance", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_billing_credits_org_id", "organization_id"),
    )


class CreditTransaction(Base, TimestampMixin):
    __tablename__ = "billing_credit_transactions"

    credit_balance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_credits.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_invoices.id"), nullable=True,
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    balance = relationship("CreditBalance", back_populates="transactions")
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_billing_credit_tx_org_id", "organization_id"),
        Index("ix_billing_credit_tx_balance_id", "credit_balance_id"),
    )


class BillingCoupon(Base, TimestampMixin):
    __tablename__ = "billing_coupons"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    coupon_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="usd", nullable=False)
    max_redemptions: Mapped[int] = mapped_column(Integer, default=10000, nullable=False)
    redemptions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    applies_to_plans: Mapped[dict] = mapped_column(JSONB, default=list)
    min_subscription_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    redemptions = relationship("CouponRedemption", back_populates="coupon", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_billing_coupons_code", "code"),
    )


class CouponRedemption(Base, TimestampMixin):
    __tablename__ = "billing_coupon_redemptions"

    coupon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_coupons.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_subscriptions.id"), nullable=True,
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_invoices.id"), nullable=True,
    )
    discount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    coupon = relationship("BillingCoupon", back_populates="redemptions")
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_billing_coupon_red_org_id", "organization_id"),
        Index("ix_billing_coupon_red_coupon_id", "coupon_id"),
    )


class BillingBudget(Base, TimestampMixin):
    __tablename__ = "billing_budgets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), default="organization", nullable=False)
    scope_value: Mapped[Optional[str]] = mapped_column(String(255))
    limit_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    spent_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    warning_threshold: Mapped[float] = mapped_column(Float, default=0.80, nullable=False)
    hard_limit_threshold: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_billing_budgets_org_id", "organization_id"),
    )


class MarketplaceBillingRecord(Base, TimestampMixin):
    __tablename__ = "billing_marketplace_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    package_id: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    pricing_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    publisher_share_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_share_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="usd", nullable=False)
    billing_period: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_invoices.id"), nullable=True,
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    organization = relationship("Organization", foreign_keys=[organization_id])
    publisher = relationship("Organization", foreign_keys=[publisher_org_id])

    __table_args__ = (
        Index("ix_billing_marketplace_org_id", "organization_id"),
        Index("ix_billing_marketplace_pkg_id", "package_id"),
        Index("ix_billing_marketplace_publisher_id", "publisher_org_id"),
    )


class DunningRecord(Base, TimestampMixin):
    __tablename__ = "billing_dunning_records"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_subscriptions.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    action_result: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    subscription = relationship("BillingSubscription")
    organization = relationship("Organization")
    invoice = relationship("BillingInvoice")

    __table_args__ = (
        Index("ix_billing_dunning_sub_id", "subscription_id"),
        Index("ix_billing_dunning_org_id", "organization_id"),
    )


class ReconciliationRecord(Base, TimestampMixin):
    __tablename__ = "billing_reconciliation"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), default="unmatched", nullable=False)
    expected_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_amount_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    discrepancy_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[Optional[str]] = mapped_column(String(255))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    invoice = relationship("BillingInvoice", back_populates="reconciliations")
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_billing_recon_invoice_id", "invoice_id"),
        Index("ix_billing_recon_org_id", "organization_id"),
        Index("ix_billing_recon_status", "status"),
    )
