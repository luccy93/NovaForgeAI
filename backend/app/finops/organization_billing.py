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


class BillingEntity(Enum):
    ORGANIZATION = "organization"
    WORKSPACE = "workspace"
    REPOSITORY = "repository"
    USER = "user"
    TEAM = "team"
    AI_AGENT = "ai_agent"
    API = "api"
    MODEL = "model"
    PLUGIN = "plugin"
    EXTENSION = "extension"
    INTEGRATION = "integration"


class BillingStatus(Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    PENDING = "pending"
    TRIAL = "trial"


class InvoiceStatus(Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class AllocationType(Enum):
    DIRECT = "direct"
    PRORATED = "prorated"
    FIXED = "fixed"
    USAGE_BASED = "usage_based"
    MANUAL = "manual"


@dataclass
class OrganizationBillingProfile:
    id: str
    org_id: str
    name: str
    email: str
    address: str
    tax_id: str
    currency: str
    billing_cycle: str
    status: BillingStatus
    payment_terms_days: int = 30
    credit_limit: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OrganizationBillingProfile":
        data["status"] = BillingStatus(data.get("status", "pending"))
        return cls(**data)


@dataclass
class WorkspaceBillingAllocation:
    id: str
    org_id: str
    workspace_id: str
    name: str
    allocation: AllocationType
    percentage: float = 0.0
    fixed_amount: float = 0.0
    usage_factor: float = 1.0
    total_allocated: float = 0.0
    period_start: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    period_end: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["allocation"] = self.allocation.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceBillingAllocation":
        data["allocation"] = AllocationType(data.get("allocation", "direct"))
        return cls(**data)


@dataclass
class EntityCostAllocation:
    id: str
    org_id: str
    entity_type: BillingEntity
    entity_id: str
    entity_name: str
    period_start: str
    period_end: str
    total_cost: float = 0.0
    by_category: dict = field(default_factory=dict)
    by_service: dict = field(default_factory=dict)
    allocation_method: AllocationType = AllocationType.DIRECT
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        d["allocation_method"] = self.allocation_method.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EntityCostAllocation":
        data["entity_type"] = BillingEntity(data.get("entity_type", "organization"))
        data["allocation_method"] = AllocationType(data.get("allocation_method", "direct"))
        return cls(**data)


@dataclass
class TeamBillingSummary:
    id: str
    org_id: str
    team_id: str
    team_name: str
    period_start: str
    period_end: str
    total_cost: float = 0.0
    by_member: dict = field(default_factory=dict)
    by_service: dict = field(default_factory=dict)
    avg_cost_per_member: float = 0.0
    budget_comparison: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TeamBillingSummary":
        return cls(**data)


@dataclass
class BillingInvoice:
    id: str
    org_id: str
    invoice_number: str
    billing_profile_id: str
    period_start: str
    period_end: str
    items: list
    subtotal: float = 0.0
    tax: float = 0.0
    discount: float = 0.0
    total: float = 0.0
    currency: str = "USD"
    status: InvoiceStatus = InvoiceStatus.DRAFT
    due_date: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
    paid_at: str = ""
    payment_method: str = ""
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BillingInvoice":
        data["status"] = InvoiceStatus(data.get("status", "draft"))
        return cls(**data)


class OrganizationBilling:
    def __init__(self, storage_dir: str = "organization_billing_data"):
        self.storage_dir = storage_dir
        self._billing_profiles: dict[str, OrganizationBillingProfile] = {}
        self._workspace_allocations: dict[str, WorkspaceBillingAllocation] = {}
        self._entity_allocations: dict[str, EntityCostAllocation] = {}
        self._team_summaries: dict[str, TeamBillingSummary] = {}
        self._invoices: dict[str, BillingInvoice] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _billing_profiles_path(self) -> str:
        return os.path.join(self.storage_dir, "billing_profiles.json")

    def _workspace_allocations_path(self) -> str:
        return os.path.join(self.storage_dir, "workspace_allocations.json")

    def _entity_allocations_path(self) -> str:
        return os.path.join(self.storage_dir, "entity_allocations.json")

    def _team_summaries_path(self) -> str:
        return os.path.join(self.storage_dir, "team_summaries.json")

    def _invoices_path(self) -> str:
        return os.path.join(self.storage_dir, "invoices.json")

    def _save(self) -> None:
        try:
            profiles_data = {pid: p.to_dict() for pid, p in self._billing_profiles.items()}
            with open(self._billing_profiles_path(), "w", encoding="utf-8") as f:
                json.dump(profiles_data, f, indent=2, default=str)

            allocs_data = {aid: a.to_dict() for aid, a in self._workspace_allocations.items()}
            with open(self._workspace_allocations_path(), "w", encoding="utf-8") as f:
                json.dump(allocs_data, f, indent=2, default=str)

            entity_data = {eid: e.to_dict() for eid, e in self._entity_allocations.items()}
            with open(self._entity_allocations_path(), "w", encoding="utf-8") as f:
                json.dump(entity_data, f, indent=2, default=str)

            team_data = {tid: t.to_dict() for tid, t in self._team_summaries.items()}
            with open(self._team_summaries_path(), "w", encoding="utf-8") as f:
                json.dump(team_data, f, indent=2, default=str)

            invoices_data = {iid: i.to_dict() for iid, i in self._invoices.items()}
            with open(self._invoices_path(), "w", encoding="utf-8") as f:
                json.dump(invoices_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save organization billing data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._billing_profiles_path()):
                with open(self._billing_profiles_path(), "r", encoding="utf-8") as f:
                    profiles_data = json.load(f)
                for pid, data in profiles_data.items():
                    try:
                        self._billing_profiles[pid] = OrganizationBillingProfile.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed billing profile %s: %s", pid, e)

            if os.path.exists(self._workspace_allocations_path()):
                with open(self._workspace_allocations_path(), "r", encoding="utf-8") as f:
                    allocs_data = json.load(f)
                for aid, data in allocs_data.items():
                    try:
                        self._workspace_allocations[aid] = WorkspaceBillingAllocation.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed workspace allocation %s: %s", aid, e)

            if os.path.exists(self._entity_allocations_path()):
                with open(self._entity_allocations_path(), "r", encoding="utf-8") as f:
                    entity_data = json.load(f)
                for eid, data in entity_data.items():
                    try:
                        self._entity_allocations[eid] = EntityCostAllocation.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed entity allocation %s: %s", eid, e)

            if os.path.exists(self._team_summaries_path()):
                with open(self._team_summaries_path(), "r", encoding="utf-8") as f:
                    team_data = json.load(f)
                for tid, data in team_data.items():
                    try:
                        self._team_summaries[tid] = TeamBillingSummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed team summary %s: %s", tid, e)

            if os.path.exists(self._invoices_path()):
                with open(self._invoices_path(), "r", encoding="utf-8") as f:
                    invoices_data = json.load(f)
                for iid, data in invoices_data.items():
                    try:
                        self._invoices[iid] = BillingInvoice.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed invoice %s: %s", iid, e)
        except Exception as e:
            logger.error("Failed to load organization billing data: %s", e, exc_info=True)

    def create_billing_profile(self, profile: OrganizationBillingProfile) -> OrganizationBillingProfile:
        self._telemetry["create_billing_profile_calls"] += 1
        if not profile.id:
            profile.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        profile.created_at = now
        profile.updated_at = now
        self._billing_profiles[profile.id] = profile
        self._save()
        logger.info("Created billing profile %s for org %s", profile.id, profile.org_id)
        return profile

    def get_billing_profile(self, org_id: str) -> Optional[OrganizationBillingProfile]:
        self._telemetry["get_billing_profile_calls"] += 1
        for profile in self._billing_profiles.values():
            if profile.org_id == org_id:
                return profile
        return None

    def update_billing_profile(self, org_id: str, updates: dict) -> Optional[OrganizationBillingProfile]:
        self._telemetry["update_billing_profile_calls"] += 1
        profile = self.get_billing_profile(org_id)
        if not profile:
            logger.warning("Attempted to update unknown billing profile for org %s", org_id)
            return None
        for key, value in updates.items():
            if hasattr(profile, key) and key not in ("id", "org_id", "created_at"):
                if key == "status":
                    setattr(profile, key, BillingStatus(value) if isinstance(value, str) else value)
                else:
                    setattr(profile, key, value)
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated billing profile for org %s", org_id)
        return profile

    def set_workspace_allocation(self, allocation: WorkspaceBillingAllocation) -> WorkspaceBillingAllocation:
        self._telemetry["set_workspace_allocation_calls"] += 1
        if not allocation.id:
            allocation.id = str(uuid.uuid4())
        if not allocation.created_at:
            allocation.created_at = datetime.now(timezone.utc).isoformat()
        self._workspace_allocations[allocation.id] = allocation
        self._save()
        logger.info("Set workspace allocation %s for workspace %s", allocation.id, allocation.workspace_id)
        return allocation

    def get_workspace_allocations(self, org_id: str) -> list[WorkspaceBillingAllocation]:
        self._telemetry["get_workspace_allocations_calls"] += 1
        return [a for a in self._workspace_allocations.values() if a.org_id == org_id]

    def allocate_costs_to_entities(self, org_id: str, entity_type: BillingEntity, period_start: str, period_end: str) -> list[EntityCostAllocation]:
        self._telemetry["allocate_costs_to_entities_calls"] += 1
        allocations = [a for a in self._entity_allocations.values() if a.org_id == org_id and a.entity_type == entity_type and a.period_start >= period_start and a.period_end <= period_end]
        if allocations:
            return allocations

        workspace_allocs = [a for a in self._workspace_allocations.values() if a.org_id == org_id]
        if not workspace_allocs:
            return []

        total_base = sum(a.fixed_amount + a.total_allocated for a in workspace_allocs)
        if total_base == 0:
            total_base = len(workspace_allocs)

        results = []
        for wa in workspace_allocs:
            if wa.allocation == AllocationType.DIRECT:
                cost = wa.total_allocated
            elif wa.allocation == AllocationType.PRORATED:
                cost = total_base * (wa.percentage / 100.0) if total_base > 0 else 0.0
            elif wa.allocation == AllocationType.FIXED:
                cost = wa.fixed_amount
            elif wa.allocation == AllocationType.USAGE_BASED:
                cost = wa.total_allocated * wa.usage_factor
            else:
                cost = wa.total_allocated

            entity_alloc = EntityCostAllocation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                entity_type=entity_type,
                entity_id=wa.workspace_id,
                entity_name=wa.name,
                period_start=period_start,
                period_end=period_end,
                total_cost=round(cost, 4),
                by_category={},
                by_service={},
                allocation_method=wa.allocation,
            )
            self._entity_allocations[entity_alloc.id] = entity_alloc
            results.append(entity_alloc)

        self._save()
        return results

    def get_team_billing_summary(self, org_id: str, team_id: str, period_start: str, period_end: str) -> TeamBillingSummary:
        self._telemetry["get_team_billing_summary_calls"] += 1
        for summary in self._team_summaries.values():
            if summary.org_id == org_id and summary.team_id == team_id and summary.period_start == period_start and summary.period_end == period_end:
                return summary

        entity_allocs = [e for e in self._entity_allocations.values() if e.org_id == org_id and e.period_start >= period_start and e.period_end <= period_end]
        team_entities = [e for e in entity_allocs if e.entity_type == BillingEntity.TEAM and e.entity_id == team_id]
        total_cost = sum(e.total_cost for e in team_entities)

        by_member: dict[str, float] = defaultdict(float)
        by_service: dict[str, float] = defaultdict(float)
        for e in team_entities:
            for member, cost in e.by_category.items():
                by_member[member] += cost
            for svc, cost in e.by_service.items():
                by_service[svc] += cost

        member_count = max(len(by_member), 1)
        avg_cost_per_member = round(total_cost / member_count, 4) if member_count > 0 else 0.0

        summary = TeamBillingSummary(
            id=str(uuid.uuid4()),
            org_id=org_id,
            team_id=team_id,
            team_name=f"team_{team_id}",
            period_start=period_start,
            period_end=period_end,
            total_cost=round(total_cost, 4),
            by_member=dict(by_member),
            by_service=dict(by_service),
            avg_cost_per_member=avg_cost_per_member,
            budget_comparison={"budget": 0.0, "actual": round(total_cost, 4), "variance": round(-total_cost, 4)},
        )
        self._team_summaries[summary.id] = summary
        self._save()
        return summary

    def get_org_cost_summary(self, org_id: str, period_start: str, period_end: str) -> dict:
        self._telemetry["get_org_cost_summary_calls"] += 1
        entity_allocs = [e for e in self._entity_allocations.values() if e.org_id == org_id and e.period_start >= period_start and e.period_end <= period_end]
        total = sum(e.total_cost for e in entity_allocs)

        by_workspace: dict[str, float] = defaultdict(float)
        by_entity: dict[str, float] = defaultdict(float)
        for e in entity_allocs:
            by_workspace[e.entity_id] += e.total_cost
            by_entity[e.entity_type.value] += e.total_cost

        return {
            "org_id": org_id,
            "period_start": period_start,
            "period_end": period_end,
            "total": round(total, 4),
            "by_workspace": {k: round(v, 4) for k, v in by_workspace.items()},
            "by_entity": {k: round(v, 4) for k, v in by_entity.items()},
        }

    def get_user_billing(self, org_id: str, user_id: str, period_start: str, period_end: str) -> dict:
        self._telemetry["get_user_billing_calls"] += 1
        entity_allocs = [e for e in self._entity_allocations.values() if e.org_id == org_id and e.entity_type == BillingEntity.USER and e.entity_id == user_id and e.period_start >= period_start and e.period_end <= period_end]
        total_cost = sum(e.total_cost for e in entity_allocs)
        by_category: dict[str, float] = defaultdict(float)
        by_service: dict[str, float] = defaultdict(float)
        for e in entity_allocs:
            for cat, cost in e.by_category.items():
                by_category[cat] += cost
            for svc, cost in e.by_service.items():
                by_service[svc] += cost

        return {
            "org_id": org_id,
            "user_id": user_id,
            "period_start": period_start,
            "period_end": period_end,
            "total_cost": round(total_cost, 4),
            "by_category": dict(by_category),
            "by_service": dict(by_service),
            "allocation_count": len(entity_allocs),
        }

    def get_workspace_billing(self, org_id: str, workspace_id: str, period_start: str, period_end: str) -> dict:
        self._telemetry["get_workspace_billing_calls"] += 1
        entity_allocs = [e for e in self._entity_allocations.values() if e.org_id == org_id and e.entity_id == workspace_id and e.period_start >= period_start and e.period_end <= period_end]
        total_cost = sum(e.total_cost for e in entity_allocs)

        by_category: dict[str, float] = defaultdict(float)
        by_service: dict[str, float] = defaultdict(float)
        for e in entity_allocs:
            for cat, cost in e.by_category.items():
                by_category[cat] += cost
            for svc, cost in e.by_service.items():
                by_service[svc] += cost

        workspace_alloc = next((a for a in self._workspace_allocations.values() if a.org_id == org_id and a.workspace_id == workspace_id), None)

        return {
            "org_id": org_id,
            "workspace_id": workspace_id,
            "period_start": period_start,
            "period_end": period_end,
            "total_cost": round(total_cost, 4),
            "by_category": dict(by_category),
            "by_service": dict(by_service),
            "allocation": workspace_alloc.to_dict() if workspace_alloc else None,
        }

    def get_model_billing(self, org_id: str, model_id: str, period_start: str, period_end: str) -> dict:
        self._telemetry["get_model_billing_calls"] += 1
        entity_allocs = [e for e in self._entity_allocations.values() if e.org_id == org_id and e.entity_type == BillingEntity.MODEL and e.entity_id == model_id and e.period_start >= period_start and e.period_end <= period_end]
        total_cost = sum(e.total_cost for e in entity_allocs)

        by_category: dict[str, float] = defaultdict(float)
        by_service: dict[str, float] = defaultdict(float)
        for e in entity_allocs:
            for cat, cost in e.by_category.items():
                by_category[cat] += cost
            for svc, cost in e.by_service.items():
                by_service[svc] += cost

        return {
            "org_id": org_id,
            "model_id": model_id,
            "period_start": period_start,
            "period_end": period_end,
            "total_cost": round(total_cost, 4),
            "by_category": dict(by_category),
            "by_service": dict(by_service),
            "allocation_count": len(entity_allocs),
        }

    def generate_invoice(self, org_id: str, period_start: str, period_end: str) -> BillingInvoice:
        self._telemetry["generate_invoice_calls"] += 1
        profile = self.get_billing_profile(org_id)
        if not profile:
            profile = OrganizationBillingProfile(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name="Default",
                email="",
                address="",
                tax_id="",
                currency="USD",
                billing_cycle="monthly",
                status=BillingStatus.ACTIVE,
            )
            self._billing_profiles[profile.id] = profile

        entity_allocs = [e for e in self._entity_allocations.values() if e.org_id == org_id and e.period_start >= period_start and e.period_end <= period_end]
        total_cost = sum(e.total_cost for e in entity_allocs)

        items = []
        for e in entity_allocs:
            items.append({
                "entity_type": e.entity_type.value,
                "entity_id": e.entity_id,
                "entity_name": e.entity_name,
                "cost": round(e.total_cost, 4),
                "allocation_method": e.allocation_method.value,
            })

        subtotal = round(total_cost, 4)
        tax = round(subtotal * 0.0, 4)
        discount = 0.0
        total = round(subtotal + tax - discount, 4)

        invoice = BillingInvoice(
            id=str(uuid.uuid4()),
            org_id=org_id,
            invoice_number=f"INV-{int(time.time())}-{org_id[:8]}",
            billing_profile_id=profile.id if profile else "",
            period_start=period_start,
            period_end=period_end,
            items=items,
            subtotal=subtotal,
            tax=tax,
            discount=discount,
            total=total,
            currency=profile.currency if profile else "USD",
            status=InvoiceStatus.DRAFT,
            due_date=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        )
        self._invoices[invoice.id] = invoice
        self._save()
        logger.info("Generated invoice %s for org %s: %.2f", invoice.invoice_number, org_id, total)
        return invoice

    def list_invoices(self, org_id: str, status: Optional[InvoiceStatus] = None) -> list[BillingInvoice]:
        self._telemetry["list_invoices_calls"] += 1
        results = []
        for inv in self._invoices.values():
            if inv.org_id != org_id:
                continue
            if status is not None and inv.status != status:
                continue
            results.append(inv)
        results.sort(key=lambda i: i.created_at, reverse=True)
        return results

    def get_outstanding_balance(self, org_id: str) -> float:
        self._telemetry["get_outstanding_balance_calls"] += 1
        balance = 0.0
        for inv in self._invoices.values():
            if inv.org_id == org_id and inv.status in (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE):
                if inv.status == InvoiceStatus.PARTIALLY_PAID:
                    balance += inv.total * 0.5
                else:
                    balance += inv.total
        return round(balance, 4)

    def get_revenue_report(self, org_id: str, period_start: str, period_end: str) -> dict:
        self._telemetry["get_revenue_report_calls"] += 1
        org_invoices = [inv for inv in self._invoices.values() if inv.org_id == org_id and inv.period_start >= period_start and inv.period_end <= period_end]

        total_invoiced = sum(inv.total for inv in org_invoices)
        total_paid = sum(inv.total for inv in org_invoices if inv.status == InvoiceStatus.PAID)
        total_overdue = sum(inv.total for inv in org_invoices if inv.status == InvoiceStatus.OVERDUE)
        total_outstanding = sum(inv.total for inv in org_invoices if inv.status in (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE))

        by_status: dict[str, float] = defaultdict(float)
        for inv in org_invoices:
            by_status[inv.status.value] += inv.total

        return {
            "org_id": org_id,
            "period_start": period_start,
            "period_end": period_end,
            "total_invoiced": round(total_invoiced, 4),
            "total_paid": round(total_paid, 4),
            "total_overdue": round(total_overdue, 4),
            "total_outstanding": round(total_outstanding, 4),
            "by_status": {k: round(v, 4) for k, v in by_status.items()},
            "invoice_count": len(org_invoices),
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
