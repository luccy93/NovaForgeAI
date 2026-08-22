"""Billing constants — enums, plan definitions, limits, pricing."""
import enum


class PlanTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    TEAM = "team"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    PAUSED = "paused"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class MeteringUnit(str, enum.Enum):
    TOKENS = "tokens"
    API_CALLS = "api_calls"
    COMPUTE_SECONDS = "compute_seconds"
    STORAGE_GB_HOURS = "storage_gb_hours"
    EMBEDDING_CALLS = "embedding_calls"
    SEARCH_QUERIES = "search_queries"
    AGENT_RUNS = "agent_runs"
    REPOSITORY_READS = "repository_reads"


class CreditType(str, enum.Enum):
    GRANTED = "granted"
    EARNED = "earned"
    PURCHASED = "purchased"
    REFUND = "refund"


class CouponType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    FREE_TRIAL = "free_trial"


class DunningAction(str, enum.Enum):
    EMAIL_RETRY = "email_retry"
    RETRY_PAYMENT = "retry_payment"
    DOWNGRADE = "downgrade"
    SUSPEND = "suspend"
    CANCEL = "cancel"


class ReconciliationStatus(str, enum.Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    DISCREPANCY = "discrepancy"
    RESOLVED = "resolved"


PLAN_PRICING = {
    PlanTier.FREE: {"monthly": 0, "annual": 0, "seats": 3, "storage_gb": 1, "tokens_millions": 1},
    PlanTier.STARTER: {"monthly": 1900, "annual": 19000, "seats": 5, "storage_gb": 10, "tokens_millions": 10},
    PlanTier.PROFESSIONAL: {"monthly": 4900, "annual": 49000, "seats": 20, "storage_gb": 50, "tokens_millions": 50},
    PlanTier.TEAM: {"monthly": 9900, "annual": 99000, "seats": 50, "storage_gb": 200, "tokens_millions": 200},
    PlanTier.BUSINESS: {"monthly": 24900, "annual": 249000, "seats": 100, "storage_gb": 500, "tokens_millions": 500},
    PlanTier.ENTERPRISE: {"monthly": 0, "annual": 0, "seats": -1, "storage_gb": -1, "tokens_millions": -1},
}

METER_RATES = {
    MeteringUnit.TOKENS: 0.00001,
    MeteringUnit.API_CALLS: 0.0001,
    MeteringUnit.COMPUTE_SECONDS: 0.001,
    MeteringUnit.STORAGE_GB_HOURS: 0.01,
    MeteringUnit.EMBEDDING_CALLS: 0.00005,
    MeteringUnit.SEARCH_QUERIES: 0.00002,
    MeteringUnit.AGENT_RUNS: 0.01,
    MeteringUnit.REPOSITORY_READS: 0.00001,
}

MAX_DUNNING_RETRIES = 5
TRIAL_DAYS = 14
INVOICE_NUMBER_PREFIX = "NF"
CREDIT_BALANCE_CAP = 10000.00
COUPON_MAX_REDEMPTIONS = 10000
BILLING_PLAN_FEATURES = {
    PlanTier.FREE: ["1 repository", "Basic AI Chat", "Community Support"],
    PlanTier.STARTER: ["10 repositories", "Standard AI", "Email Support"],
    PlanTier.PROFESSIONAL: ["50 repositories", "Advanced AI", "Code Review", "Priority Support"],
    PlanTier.TEAM: ["Unlimited repositories", "Team Workspaces", "Advanced Analytics", "All AI Features"],
    PlanTier.BUSINESS: ["Everything in Team", "SSO/SAML", "Audit Logs", "Priority SLA"],
    PlanTier.ENTERPRISE: ["Everything in Business", "Custom Deployment", "Dedicated Support", "Custom SLA"],
}
