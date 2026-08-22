"""Billing configuration."""
from dataclasses import dataclass, field
from app.billing.constants import (
    MAX_DUNNING_RETRIES, TRIAL_DAYS, CREDIT_BALANCE_CAP, COUPON_MAX_REDEMPTIONS,
)


@dataclass
class BillingConfig:
    max_dunning_retries: int = MAX_DUNNING_RETRIES
    trial_days: int = TRIAL_DAYS
    credit_balance_cap: float = CREDIT_BALANCE_CAP
    coupon_max_redemptions: int = COUPON_MAX_REDEMPTIONS
    invoice_number_prefix: str = "NF"
    default_currency: str = "usd"
    enable_usage_alerts: bool = True
    usage_alert_warning_pct: float = 0.80
    usage_alert_critical_pct: float = 0.95
    enable_dunning: bool = True
    dunning_retry_hours: list[int] = field(default_factory=lambda: [1, 24, 72, 168, 336])
    enable_marketplace_billing: bool = True
    marketplace_revenue_share: float = 0.70
    enable_publisher_payouts: bool = True
    min_payout_amount_cents: int = 5000
    payout_schedule_days: int = 30
    stripe_webhook_tolerance_seconds: int = 300
    enable_budget_enforcement: bool = True
    budget_hard_limit_action: str = "suspend"


_billing_config: BillingConfig | None = None


def get_billing_config() -> BillingConfig:
    global _billing_config
    if _billing_config is None:
        _billing_config = BillingConfig()
    return _billing_config
