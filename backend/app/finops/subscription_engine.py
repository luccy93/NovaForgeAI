import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class PlanType(Enum):
    FREE = "free"
    PROFESSIONAL = "professional"
    TEAM = "team"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"
    CUSTOM_ENTERPRISE = "custom_enterprise"


class BillingCycle(Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    WEEKLY = "weekly"


class SubscriptionStatus(Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    PENDING = "pending"
    SUSPENDED = "suspended"


class PaymentMethod(Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    INVOICE = "invoice"
    ACH = "ach"
    WIRE_TRANSFER = "wire_transfer"
    CREDITS = "credits"


class FeatureCode(Enum):
    UNLIMITED_REPOS = "unlimited_repos"
    UNLIMITED_USERS = "unlimited_users"
    AI_REVIEW = "ai_review"
    SECURITY_SCAN = "security_scan"
    DOCS_GEN = "docs_gen"
    TEST_GEN = "test_gen"
    ADVANCED_ANALYTICS = "advanced_analytics"
    API_ACCESS = "api_access"
    SSO = "sso"
    AUDIT_LOG = "audit_log"
    CUSTOM_RULES = "custom_rules"
    PRIORITY_SUPPORT = "priority_support"
    DEDICATED_INFRA = "dedicated_infra"
    WHITE_LABEL = "white_label"


@dataclass
class Plan:
    id: str
    name: str
    type: PlanType
    billing_cycle: BillingCycle
    base_price: float
    price_per_seat: float
    max_seats: int
    max_repos: int
    max_users: int
    included_tokens: int
    included_storage_gb: int
    features: list[FeatureCode]
    rate_limits: dict
    metadata: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["billing_cycle"] = self.billing_cycle.value
        d["features"] = [f.value for f in self.features]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        data["type"] = PlanType(data.get("type", "free"))
        data["billing_cycle"] = BillingCycle(data.get("billing_cycle", "monthly"))
        features_raw = data.get("features", [])
        data["features"] = [FeatureCode(f) if isinstance(f, str) else f for f in features_raw]
        return cls(**data)


@dataclass
class Subscription:
    id: str
    org_id: str
    plan_id: str
    plan_type: PlanType
    status: SubscriptionStatus
    billing_cycle: BillingCycle
    seats: int
    start_date: str
    end_date: str
    trial_end_date: str
    auto_renew: bool
    payment_method: PaymentMethod
    coupon_code: str
    discount_percent: float
    current_bill: float
    total_billed: float
    metadata: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["plan_type"] = self.plan_type.value
        d["status"] = self.status.value
        d["billing_cycle"] = self.billing_cycle.value
        d["payment_method"] = self.payment_method.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Subscription":
        data["plan_type"] = PlanType(data.get("plan_type", "free"))
        data["status"] = SubscriptionStatus(data.get("status", "pending"))
        data["billing_cycle"] = BillingCycle(data.get("billing_cycle", "monthly"))
        data["payment_method"] = PaymentMethod(data.get("payment_method", "credit_card"))
        return cls(**data)


@dataclass
class Invoice:
    id: str
    org_id: str
    subscription_id: str
    invoice_number: str
    amount: float
    currency: str
    status: str
    period_start: str
    period_end: str
    issued_at: str
    paid_at: str
    items: list
    payment_method: PaymentMethod
    metadata: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        d["payment_method"] = self.payment_method.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Invoice":
        data["payment_method"] = PaymentMethod(data.get("payment_method", "credit_card"))
        return cls(**data)


@dataclass
class UsageRecord:
    id: str
    org_id: str
    subscription_id: str
    workspace_id: str
    metric_name: str
    metric_value: float
    unit: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UsageRecord":
        return cls(**data)


@dataclass
class CreditTransaction:
    id: str
    org_id: str
    amount: float
    balance_after: float
    transaction_type: str
    description: str
    reference_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CreditTransaction":
        return cls(**data)


@dataclass
class Coupon:
    id: str
    code: str
    discount_percent: float
    discount_amount: float
    max_uses: int
    current_uses: int
    valid_from: str
    valid_until: str
    applicable_plans: list[PlanType]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["applicable_plans"] = [p.value for p in self.applicable_plans]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Coupon":
        plans_raw = data.get("applicable_plans", [])
        data["applicable_plans"] = [PlanType(p) if isinstance(p, str) else p for p in plans_raw]
        return cls(**data)


BASE_PLAN_PRICING = {
    PlanType.FREE: {"base_price": 0.0, "price_per_seat": 0.0, "max_seats": 5, "max_repos": 3, "max_users": 5, "included_tokens": 10000, "included_storage_gb": 1},
    PlanType.PROFESSIONAL: {"base_price": 29.0, "price_per_seat": 10.0, "max_seats": 20, "max_repos": 50, "max_users": 20, "included_tokens": 100000, "included_storage_gb": 10},
    PlanType.TEAM: {"base_price": 99.0, "price_per_seat": 15.0, "max_seats": 100, "max_repos": 200, "max_users": 100, "included_tokens": 500000, "included_storage_gb": 50},
    PlanType.BUSINESS: {"base_price": 299.0, "price_per_seat": 20.0, "max_seats": 500, "max_repos": 1000, "max_users": 500, "included_tokens": 2000000, "included_storage_gb": 200},
    PlanType.ENTERPRISE: {"base_price": 999.0, "price_per_seat": 25.0, "max_seats": 2000, "max_repos": 5000, "max_users": 2000, "included_tokens": 10000000, "included_storage_gb": 1000},
    PlanType.CUSTOM_ENTERPRISE: {"base_price": 0.0, "price_per_seat": 0.0, "max_seats": 99999, "max_repos": 99999, "max_users": 99999, "included_tokens": 0, "included_storage_gb": 0},
}

BILLING_MULTIPLIER = {
    BillingCycle.WEEKLY: 4,
    BillingCycle.MONTHLY: 1,
    BillingCycle.QUARTERLY: 3,
    BillingCycle.ANNUAL: 12,
}


class SubscriptionManager:
    def __init__(self, storage_dir: str = "subscription_data"):
        self.storage_dir = storage_dir
        self._plans: dict[str, Plan] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._invoices: dict[str, Invoice] = {}
        self._usage_records: dict[str, UsageRecord] = {}
        self._credit_transactions: dict[str, CreditTransaction] = {}
        self._coupons: dict[str, Coupon] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _plans_path(self) -> str:
        return os.path.join(self.storage_dir, "plans.json")

    def _subscriptions_path(self) -> str:
        return os.path.join(self.storage_dir, "subscriptions.json")

    def _invoices_path(self) -> str:
        return os.path.join(self.storage_dir, "invoices.json")

    def _usage_records_path(self) -> str:
        return os.path.join(self.storage_dir, "usage_records.json")

    def _credit_transactions_path(self) -> str:
        return os.path.join(self.storage_dir, "credit_transactions.json")

    def _coupons_path(self) -> str:
        return os.path.join(self.storage_dir, "coupons.json")

    def _save(self) -> None:
        try:
            plans_data = {pid: p.to_dict() for pid, p in self._plans.items()}
            with open(self._plans_path(), "w", encoding="utf-8") as f:
                json.dump(plans_data, f, indent=2, default=str)

            subs_data = {sid: s.to_dict() for sid, s in self._subscriptions.items()}
            with open(self._subscriptions_path(), "w", encoding="utf-8") as f:
                json.dump(subs_data, f, indent=2, default=str)

            invoices_data = {iid: i.to_dict() for iid, i in self._invoices.items()}
            with open(self._invoices_path(), "w", encoding="utf-8") as f:
                json.dump(invoices_data, f, indent=2, default=str)

            usage_data = {uid: u.to_dict() for uid, u in self._usage_records.items()}
            with open(self._usage_records_path(), "w", encoding="utf-8") as f:
                json.dump(usage_data, f, indent=2, default=str)

            credit_data = {cid: c.to_dict() for cid, c in self._credit_transactions.items()}
            with open(self._credit_transactions_path(), "w", encoding="utf-8") as f:
                json.dump(credit_data, f, indent=2, default=str)

            coupons_data = {cid: c.to_dict() for cid, c in self._coupons.items()}
            with open(self._coupons_path(), "w", encoding="utf-8") as f:
                json.dump(coupons_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save subscription data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._plans_path()):
                with open(self._plans_path(), "r", encoding="utf-8") as f:
                    plans_data = json.load(f)
                for pid, data in plans_data.items():
                    try:
                        self._plans[pid] = Plan.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed plan %s: %s", pid, e)

            if os.path.exists(self._subscriptions_path()):
                with open(self._subscriptions_path(), "r", encoding="utf-8") as f:
                    subs_data = json.load(f)
                for sid, data in subs_data.items():
                    try:
                        self._subscriptions[sid] = Subscription.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed subscription %s: %s", sid, e)

            if os.path.exists(self._invoices_path()):
                with open(self._invoices_path(), "r", encoding="utf-8") as f:
                    invoices_data = json.load(f)
                for iid, data in invoices_data.items():
                    try:
                        self._invoices[iid] = Invoice.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed invoice %s: %s", iid, e)

            if os.path.exists(self._usage_records_path()):
                with open(self._usage_records_path(), "r", encoding="utf-8") as f:
                    usage_data = json.load(f)
                for uid, data in usage_data.items():
                    try:
                        self._usage_records[uid] = UsageRecord.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed usage record %s: %s", uid, e)

            if os.path.exists(self._credit_transactions_path()):
                with open(self._credit_transactions_path(), "r", encoding="utf-8") as f:
                    credit_data = json.load(f)
                for cid, data in credit_data.items():
                    try:
                        self._credit_transactions[cid] = CreditTransaction.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed credit transaction %s: %s", cid, e)

            if os.path.exists(self._coupons_path()):
                with open(self._coupons_path(), "r", encoding="utf-8") as f:
                    coupons_data = json.load(f)
                for cid, data in coupons_data.items():
                    try:
                        self._coupons[cid] = Coupon.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed coupon %s: %s", cid, e)
        except Exception as e:
            logger.error("Failed to load subscription data: %s", e, exc_info=True)

    def create_plan(self, plan: Plan) -> Plan:
        self._telemetry["create_plan_calls"] += 1
        if not plan.id:
            plan.id = str(uuid.uuid4())
        plan.created_at = datetime.now(timezone.utc).isoformat()
        plan.updated_at = plan.created_at
        self._plans[plan.id] = plan
        self._save()
        logger.info("Created plan %s: %s (%s)", plan.id, plan.name, plan.type.value)
        return plan

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        self._telemetry["get_plan_calls"] += 1
        return self._plans.get(plan_id)

    def list_plans(self, plan_type: Optional[PlanType] = None) -> list[Plan]:
        self._telemetry["list_plans_calls"] += 1
        if plan_type:
            return [p for p in self._plans.values() if p.type == plan_type]
        return list(self._plans.values())

    def create_subscription(self, subscription: Subscription) -> Subscription:
        self._telemetry["create_subscription_calls"] += 1
        if not subscription.id:
            subscription.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        subscription.created_at = now.isoformat()
        subscription.updated_at = subscription.created_at
        if not subscription.start_date:
            subscription.start_date = now.isoformat()
        if not subscription.end_date:
            cycle_days = {
                BillingCycle.WEEKLY: 7,
                BillingCycle.MONTHLY: 30,
                BillingCycle.QUARTERLY: 91,
                BillingCycle.ANNUAL: 365,
            }
            days = cycle_days.get(subscription.billing_cycle, 30)
            subscription.end_date = (now + timedelta(days=days)).isoformat()
        if not subscription.trial_end_date and subscription.status == SubscriptionStatus.TRIAL:
            subscription.trial_end_date = (now + timedelta(days=14)).isoformat()

        # Calculate initial current_bill
        subscription.current_bill = self.get_current_bill(subscription.id)
        self._subscriptions[subscription.id] = subscription
        self._save()
        logger.info("Created subscription %s for org %s (plan: %s)", subscription.id, subscription.org_id, subscription.plan_type.value)
        return subscription

    def get_subscription(self, sub_id: str) -> Optional[Subscription]:
        self._telemetry["get_subscription_calls"] += 1
        return self._subscriptions.get(sub_id)

    def update_subscription(self, sub_id: str, updates: dict) -> Optional[Subscription]:
        self._telemetry["update_subscription_calls"] += 1
        sub = self._subscriptions.get(sub_id)
        if not sub:
            logger.warning("Attempted to update unknown subscription: %s", sub_id)
            return None
        for key, value in updates.items():
            if hasattr(sub, key) and key not in ("id", "org_id", "created_at"):
                if key == "plan_type":
                    setattr(sub, key, PlanType(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(sub, key, SubscriptionStatus(value) if isinstance(value, str) else value)
                elif key == "billing_cycle":
                    setattr(sub, key, BillingCycle(value) if isinstance(value, str) else value)
                elif key == "payment_method":
                    setattr(sub, key, PaymentMethod(value) if isinstance(value, str) else value)
                else:
                    setattr(sub, key, value)
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        sub.current_bill = self.get_current_bill(sub.id)
        self._save()
        logger.info("Updated subscription: %s", sub_id)
        return sub

    def cancel_subscription(self, sub_id: str) -> Optional[Subscription]:
        self._telemetry["cancel_subscription_calls"] += 1
        sub = self._subscriptions.get(sub_id)
        if not sub:
            logger.warning("Attempted to cancel unknown subscription: %s", sub_id)
            return None
        sub.status = SubscriptionStatus.CANCELLED
        sub.auto_renew = False
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Cancelled subscription: %s", sub_id)
        return sub

    def activate_subscription(self, sub_id: str) -> Optional[Subscription]:
        self._telemetry["activate_subscription_calls"] += 1
        sub = self._subscriptions.get(sub_id)
        if not sub:
            logger.warning("Attempted to activate unknown subscription: %s", sub_id)
            return None
        sub.status = SubscriptionStatus.ACTIVE
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Activated subscription: %s", sub_id)
        return sub

    def list_subscriptions(self, org_id: Optional[str] = None, status: Optional[SubscriptionStatus] = None) -> list[Subscription]:
        self._telemetry["list_subscriptions_calls"] += 1
        results = []
        for sub in self._subscriptions.values():
            if org_id is not None and sub.org_id != org_id:
                continue
            if status is not None and sub.status != status:
                continue
            results.append(sub)
        return results

    def get_current_bill(self, sub_id: str) -> float:
        self._telemetry["get_current_bill_calls"] += 1
        sub = self._subscriptions.get(sub_id)
        if not sub:
            return 0.0

        plan = self._plans.get(sub.plan_id)

        # Base price
        if plan:
            base_price = plan.base_price
            price_per_seat = plan.price_per_seat
        else:
            pricing = BASE_PLAN_PRICING.get(sub.plan_type, BASE_PLAN_PRICING[PlanType.FREE])
            base_price = pricing["base_price"]
            price_per_seat = pricing["price_per_seat"]

        multiplier = BILLING_MULTIPLIER.get(sub.billing_cycle, 1)
        seat_cost = price_per_seat * max(0, sub.seats - 1) if sub.seats > 0 else 0
        bill = (base_price + seat_cost) * multiplier

        # Add usage-based overage
        usage_metrics = self._get_usage_aggregates(sub.org_id)
        if plan and plan.included_tokens > 0:
            overage_tokens = max(0, usage_metrics.get("total_tokens", 0) - plan.included_tokens)
            bill += (overage_tokens / 1000) * 0.01

        if plan and plan.included_storage_gb > 0:
            overage_storage = max(0, usage_metrics.get("total_storage_gb", 0) - plan.included_storage_gb)
            bill += overage_storage * 0.50

        # Apply discount from coupon
        if sub.coupon_code:
            coupon = self._find_coupon_by_code(sub.coupon_code)
            if coupon:
                bill -= coupon.discount_amount
                if coupon.discount_percent > 0:
                    bill -= bill * (coupon.discount_percent / 100.0)

        if sub.discount_percent > 0:
            bill -= bill * (sub.discount_percent / 100.0)

        return round(max(0, bill), 4)

    def _get_usage_aggregates(self, org_id: str) -> dict:
        total_tokens = 0.0
        total_storage_gb = 0.0
        now = datetime.now(timezone.utc)
        month_start = now - timedelta(days=30)
        for record in self._usage_records.values():
            if record.org_id != org_id:
                continue
            if record.timestamp < month_start.isoformat():
                continue
            if record.metric_name == "tokens":
                total_tokens += record.metric_value
            elif record.metric_name == "storage_gb":
                total_storage_gb += record.metric_value
        return {"total_tokens": total_tokens, "total_storage_gb": total_storage_gb}

    def create_invoice(self, invoice: Invoice) -> Invoice:
        self._telemetry["create_invoice_calls"] += 1
        if not invoice.id:
            invoice.id = str(uuid.uuid4())
        if not invoice.issued_at:
            invoice.issued_at = datetime.now(timezone.utc).isoformat()
        if not invoice.invoice_number:
            invoice.invoice_number = f"INV-{int(time.time())}-{invoice.org_id[:8]}"
        self._invoices[invoice.id] = invoice
        self._save()
        logger.info("Created invoice %s: %.2f for org %s", invoice.invoice_number, invoice.amount, invoice.org_id)
        return invoice

    def list_invoices(self, org_id: str) -> list[Invoice]:
        self._telemetry["list_invoices_calls"] += 1
        return [inv for inv in self._invoices.values() if inv.org_id == org_id]

    def record_usage(self, record: UsageRecord) -> UsageRecord:
        self._telemetry["record_usage_calls"] += 1
        if not record.id:
            record.id = str(uuid.uuid4())
        if not record.timestamp:
            record.timestamp = datetime.now(timezone.utc).isoformat()
        self._usage_records[record.id] = record

        # Update subscription current_bill
        sub = self._subscriptions.get(record.subscription_id)
        if sub:
            sub.current_bill = self.get_current_bill(sub.id)
            sub.updated_at = datetime.now(timezone.utc).isoformat()

        self._save()
        logger.info("Recorded usage %s: %.2f %s for org %s", record.id, record.metric_value, record.unit, record.org_id)
        return record

    def get_usage(self, org_id: str, metric_name: str, start_date: str, end_date: str) -> list[UsageRecord]:
        self._telemetry["get_usage_calls"] += 1
        results = []
        for record in self._usage_records.values():
            if record.org_id == org_id and record.metric_name == metric_name and start_date <= record.timestamp[:10] <= end_date:
                results.append(record)
        results.sort(key=lambda r: r.timestamp)
        return results

    def add_credits(self, org_id: str, amount: float, description: str) -> CreditTransaction:
        self._telemetry["add_credits_calls"] += 1
        current_balance = self.get_credit_balance(org_id)
        new_balance = current_balance + amount
        transaction = CreditTransaction(
            id=str(uuid.uuid4()),
            org_id=org_id,
            amount=amount,
            balance_after=new_balance,
            transaction_type="credit" if amount >= 0 else "debit",
            description=description,
            reference_id="",
        )
        self._credit_transactions[transaction.id] = transaction
        self._save()
        logger.info("Added %.2f credits for org %s: %s", amount, org_id, description)
        return transaction

    def get_credit_balance(self, org_id: str) -> float:
        self._telemetry["get_credit_balance_calls"] += 1
        balance = 0.0
        for tx in self._credit_transactions.values():
            if tx.org_id == org_id:
                balance += tx.amount
        return round(balance, 4)

    def validate_subscription(self, org_id: str) -> dict:
        self._telemetry["validate_subscription_calls"] += 1
        subs = [s for s in self._subscriptions.values() if s.org_id == org_id and s.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)]
        if not subs:
            return {
                "valid": False,
                "org_id": org_id,
                "reason": "No active subscription found",
                "status": "none",
                "remaining_tokens": 0,
                "remaining_storage_gb": 0,
                "plan_type": None,
            }

        sub = max(subs, key=lambda s: 0 if s.status == SubscriptionStatus.TRIAL else 1)
        now = datetime.now(timezone.utc)
        def _parse_dt(s: str) -> datetime:
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return now

        if sub.status == SubscriptionStatus.EXPIRED or (sub.end_date and now > _parse_dt(sub.end_date)):
            return {
                "valid": False,
                "org_id": org_id,
                "reason": "Subscription has expired",
                "status": "expired",
                "remaining_tokens": 0,
                "remaining_storage_gb": 0,
                "plan_type": sub.plan_type.value,
            }

        if sub.status == SubscriptionStatus.TRIAL and sub.trial_end_date:
            if now > _parse_dt(sub.trial_end_date):
                return {
                    "valid": False,
                    "org_id": org_id,
                    "reason": "Trial period has ended",
                    "status": "trial_ended",
                    "remaining_tokens": 0,
                    "remaining_storage_gb": 0,
                    "plan_type": sub.plan_type.value,
                }

        if sub.status == SubscriptionStatus.SUSPENDED:
            return {
                "valid": False,
                "org_id": org_id,
                "reason": "Subscription is suspended",
                "status": "suspended",
                "remaining_tokens": 0,
                "remaining_storage_gb": 0,
                "plan_type": sub.plan_type.value,
            }

        if sub.status == SubscriptionStatus.CANCELLED:
            return {
                "valid": False,
                "org_id": org_id,
                "reason": "Subscription is cancelled",
                "status": "cancelled",
                "remaining_tokens": 0,
                "remaining_storage_gb": 0,
                "plan_type": sub.plan_type.value,
            }

        plan = self._plans.get(sub.plan_id)
        included_tokens = plan.included_tokens if plan else BASE_PLAN_PRICING.get(sub.plan_type, BASE_PLAN_PRICING[PlanType.FREE])["included_tokens"]
        included_storage_gb = plan.included_storage_gb if plan else BASE_PLAN_PRICING.get(sub.plan_type, BASE_PLAN_PRICING[PlanType.FREE])["included_storage_gb"]

        usage = self._get_usage_aggregates(org_id)
        remaining_tokens = max(0, included_tokens - usage["total_tokens"])
        remaining_storage_gb = max(0, included_storage_gb - usage["total_storage_gb"])

        return {
            "valid": True,
            "org_id": org_id,
            "status": sub.status.value,
            "plan_type": sub.plan_type.value,
            "remaining_tokens": int(remaining_tokens),
            "remaining_storage_gb": int(remaining_storage_gb),
            "subscription_id": sub.id,
            "auto_renew": sub.auto_renew,
            "start_date": sub.start_date,
            "end_date": sub.end_date,
            "seats": sub.seats,
            "current_bill": sub.current_bill,
        }

    def create_coupon(self, coupon: Coupon) -> Coupon:
        self._telemetry["create_coupon_calls"] += 1
        if not coupon.id:
            coupon.id = str(uuid.uuid4())
        coupon.created_at = datetime.now(timezone.utc).isoformat()
        self._coupons[coupon.id] = coupon
        self._save()
        logger.info("Created coupon %s: code=%s", coupon.id, coupon.code)
        return coupon

    def apply_coupon(self, code: str, org_id: str) -> Optional[Coupon]:
        self._telemetry["apply_coupon_calls"] += 1
        coupon = self._find_coupon_by_code(code)
        if not coupon:
            logger.warning("Coupon code not found: %s", code)
            return None

        now = datetime.now(timezone.utc)
        if now < datetime.fromisoformat(coupon.valid_from):
            logger.warning("Coupon %s is not yet valid", code)
            return None
        if now > datetime.fromisoformat(coupon.valid_until):
            logger.warning("Coupon %s has expired", code)
            return None
        if coupon.current_uses >= coupon.max_uses:
            logger.warning("Coupon %s has reached max uses", code)
            return None

        subs = [s for s in self._subscriptions.values() if s.org_id == org_id]
        for sub in subs:
            if coupon.applicable_plans and sub.plan_type not in coupon.applicable_plans:
                continue
            sub.coupon_code = code
            sub.discount_percent = max(sub.discount_percent, coupon.discount_percent)
            sub.updated_at = datetime.now(timezone.utc).isoformat()
            sub.current_bill = self.get_current_bill(sub.id)

        coupon.current_uses += 1
        self._save()
        logger.info("Applied coupon %s to org %s", code, org_id)
        return coupon

    def _find_coupon_by_code(self, code: str) -> Optional[Coupon]:
        for coupon in self._coupons.values():
            if coupon.code == code:
                return coupon
        return None

    def update_seats(self, sub_id: str, new_seats: int) -> Optional[Subscription]:
        self._telemetry["update_seats_calls"] += 1
        sub = self._subscriptions.get(sub_id)
        if not sub:
            logger.warning("Attempted to update seats for unknown subscription: %s", sub_id)
            return None

        # Check plan max_seats limit
        plan = self._plans.get(sub.plan_id)
        max_seats = plan.max_seats if plan else BASE_PLAN_PRICING.get(sub.plan_type, BASE_PLAN_PRICING[PlanType.FREE])["max_seats"]
        if new_seats > max_seats:
            logger.warning("Seat update for %s exceeds plan max of %d", sub_id, max_seats)
            return None

        sub.seats = new_seats
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        sub.current_bill = self.get_current_bill(sub.id)
        self._save()
        logger.info("Updated seats for subscription %s: %d", sub_id, new_seats)
        return sub

    def get_subscription_analytics(self, org_id: str) -> dict:
        self._telemetry["get_subscription_analytics_calls"] += 1
        org_subs = [s for s in self._subscriptions.values() if s.org_id == org_id]
        org_invoices = [inv for inv in self._invoices.values() if inv.org_id == org_id]
        org_usage = [u for u in self._usage_records.values() if u.org_id == org_id]
        org_credits = [c for c in self._credit_transactions.values() if c.org_id == org_id]

        total_billed = sum(s.total_billed for s in org_subs)
        total_invoiced = sum(inv.amount for inv in org_invoices)
        pending_invoices = sum(inv.amount for inv in org_invoices if inv.status == "pending")
        paid_invoices = sum(inv.amount for inv in org_invoices if inv.status == "paid")

        usage_by_metric: dict[str, float] = defaultdict(float)
        for u in org_usage:
            usage_by_metric[u.metric_name] += u.metric_value

        credit_balance = sum(c.amount for c in org_credits)

        active_subs = [s for s in org_subs if s.status == SubscriptionStatus.ACTIVE]
        trial_subs = [s for s in org_subs if s.status == SubscriptionStatus.TRIAL]

        return {
            "org_id": org_id,
            "total_subscriptions": len(org_subs),
            "active_subscriptions": len(active_subs),
            "trial_subscriptions": len(trial_subs),
            "total_billed": round(total_billed, 4),
            "total_invoiced": round(total_invoiced, 4),
            "pending_invoices": round(pending_invoices, 4),
            "paid_invoices": round(paid_invoices, 4),
            "credit_balance": round(credit_balance, 4),
            "usage_by_metric": {k: round(v, 4) for k, v in usage_by_metric.items()},
            "current_plan": org_subs[0].plan_type.value if org_subs else None,
            "current_seats": org_subs[0].seats if org_subs else 0,
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
