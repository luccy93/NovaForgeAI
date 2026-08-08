"""Billing & subscription API endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.organization import Organization, Subscription
from app.models.support import UsageRecord
from app.schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    BillingPortalResponse,
    PlanOut,
    SubscriptionOut,
    UsageSummary,
    UsageSummaryResponse,
)
from app.api.auth import _get_current_user
from app.services.billing import billing_service, get_all_plans, get_plan, PLANS
from app.core.authorization import Permission

router = APIRouter()


@router.get("/plans", response_model=list[PlanOut])
async def list_plans():
    return [PlanOut(**p) for p in get_all_plans()]


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan_detail(plan_id: str):
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return PlanOut(**plan)


@router.get("/subscriptions/current", response_model=Optional[SubscriptionOut])
async def get_current_subscription(
    organization_id: str = Query(...),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[SubscriptionOut]:
    try:
        oid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    result = await db.execute(
        select(Subscription).where(
            Subscription.organization_id == oid,
            Subscription.status.in_(["active", "trialing", "past_due"]),
        ).order_by(Subscription.created_at.desc()).limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None
    return SubscriptionOut(
        id=str(sub.id),
        plan_id=sub.plan_id,
        status=sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        canceled_at=sub.canceled_at,
        trial_end=sub.trial_end,
    )


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = get_plan(request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Invalid plan")
    org_id = str(current_user.id)
    session = await billing_service.create_checkout_session(
        plan_id=request.plan_id,
        organization_id=org_id,
        success_url=request.success_url,
        cancel_url=request.cancel_url,
        customer_email=current_user.email,
    )
    if not session:
        raise HTTPException(status_code=502, detail="Billing service unavailable")
    return CheckoutSessionResponse(url=session["url"], session_id=session["id"])


@router.post("/portal", response_model=BillingPortalResponse)
async def create_portal_session(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_customer_id.isnot(None)
        ).limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
    url = await billing_service.create_portal_session(
        str(sub.stripe_customer_id), "http://localhost:3000/settings/billing"
    )
    if not url:
        raise HTTPException(status_code=502, detail="Billing portal unavailable")
    return BillingPortalResponse(url=url)


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = await billing_service.process_webhook(payload, sig)
    if not event:
        raise HTTPException(status_code=400, detail="Invalid webhook")
    return {"received": True, "type": event["type"]}


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    organization_id: str = Query(...),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryResponse:
    try:
        oid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")

    org_result = await db.execute(select(Organization).where(Organization.id == oid))
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    plan = get_plan(org.plan) or get_plan("free")
    limits = plan["limits"]
    thirty_days_ago = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=30)

    usage_data = {}
    for metric_key, metric_field in [("ai_tokens_monthly", "ai_tokens"), ("storage_gb", "storage")]:
        limit_val = limits.get(metric_key, 0)
        usage_sum = await db.execute(
            select(func.coalesce(func.sum(UsageRecord.value), 0)).where(
                UsageRecord.organization_id == oid,
                UsageRecord.metric == metric_field,
                UsageRecord.recorded_at >= thirty_days_ago,
            )
        )
        current_val = float(usage_sum.scalar() or 0)
        usage_data[metric_field] = {
            "current": current_val,
            "limit": float(limit_val) if limit_val else float("inf"),
        }

    repo_count_result = await db.execute(
        select(func.count()).select_from(text("repositories")).where(
            text(f"organization_id = '{oid}'")
        )
    )
    repo_count = repo_count_result.scalar() or 0

    repo_limit = float(limits.get("repositories", 0) or 0)
    ai_limit = float(limits.get("ai_tokens_monthly", 0) or 0) or float("inf")
    seat_limit = float(limits.get("seats", 0) or 0) or float("inf")
    repo_current = float(repo_count or 0)
    ai_current = float(usage_data.get("ai_tokens", {}).get("current", 0) or 0)

    usage = [
        UsageSummary(
            metric="repositories",
            current=repo_current,
            limit=repo_limit or float("inf"),
            percentage=min(100.0, (repo_current / repo_limit * 100)) if repo_limit > 0 else 0,
        ),
        UsageSummary(
            metric="ai_tokens",
            current=ai_current,
            limit=ai_limit,
            percentage=0,
        ),
        UsageSummary(
            metric="seats",
            current=0.0,
            limit=seat_limit or float("inf"),
            percentage=0,
        ),
    ]
    return UsageSummaryResponse(
        organization_id=organization_id,
        plan=org.plan,
        usage=usage,
    )
