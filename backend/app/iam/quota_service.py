"""Quota service — enforce per-org quotas for users, repos, storage, AI tokens, etc."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.iam.config import get_iam_config
from app.iam.constants import (
    QUOTA_DEFAULT_USERS, QUOTA_DEFAULT_REPOSITORIES, QUOTA_DEFAULT_STORAGE_GB,
    QUOTA_DEFAULT_AI_TOKENS, QUOTA_DEFAULT_AGENTS, QUOTA_DEFAULT_WORKFLOWS,
    QUOTA_DEFAULT_API_CALLS, QUOTA_DEFAULT_CI_JOBS, QUOTA_DEFAULT_DEPLOYMENTS,
)


class QuotaService:
    def __init__(self):
        self._quotas: dict[str, dict] = {}
        self._config = get_iam_config()
        self._usage_log: list[dict] = []

    def initialize_org_quotas(self, org_id: str) -> list[dict]:
        defaults = {"users": QUOTA_DEFAULT_USERS, "repositories": QUOTA_DEFAULT_REPOSITORIES, "storage_gb": QUOTA_DEFAULT_STORAGE_GB, "ai_tokens": QUOTA_DEFAULT_AI_TOKENS, "agents": QUOTA_DEFAULT_AGENTS, "workflows": QUOTA_DEFAULT_WORKFLOWS, "api_calls": QUOTA_DEFAULT_API_CALLS, "ci_jobs": QUOTA_DEFAULT_CI_JOBS, "deployments": QUOTA_DEFAULT_DEPLOYMENTS}
        created = []
        for quota_type, limit in defaults.items():
            quota_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            quota = {"id": quota_id, "organization_id": org_id, "quota_type": quota_type, "limit": limit, "used": 0, "period": "monthly", "period_start": now.isoformat(), "period_end": (now + timedelta(days=30)).isoformat(), "is_active": True, "created_at": now.isoformat()}
            self._quotas[quota_id] = quota
            created.append(quota)
        return created

    def get_quota(self, org_id: str, quota_type: str) -> Optional[dict]:
        for q in self._quotas.values():
            if q["organization_id"] == org_id and q["quota_type"] == quota_type:
                return q
        return None

    def check_quota(self, org_id: str, quota_type: str, amount: int = 1) -> dict:
        quota = self.get_quota(org_id, quota_type)
        if not quota:
            return {"allowed": True, "reason": "No quota defined, allowing by default"}
        if not self._is_current_period(quota):
            self._reset_period(quota)
        remaining = quota["limit"] - quota["used"]
        allowed = remaining >= amount
        return {"allowed": allowed, "quota_type": quota_type, "limit": quota["limit"], "used": quota["used"], "remaining": remaining, "requested": amount, "exceeded": not allowed}

    def consume_quota(self, org_id: str, quota_type: str, amount: int = 1) -> dict:
        check = self.check_quota(org_id, quota_type, amount)
        if not check["allowed"]:
            return check
        quota = self.get_quota(org_id, quota_type)
        if quota:
            quota["used"] += amount
            self._usage_log.append({"org_id": org_id, "quota_type": quota_type, "amount": amount, "time": datetime.now(timezone.utc).isoformat()})
        return {"consumed": True, "quota_type": quota_type, "amount": amount, "new_usage": quota["used"] if quota else 0}

    def update_quota(self, org_id: str, quota_type: str, limit: int, period: str = "monthly") -> Optional[dict]:
        quota = self.get_quota(org_id, quota_type)
        if not quota:
            quota_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            quota = {"id": quota_id, "organization_id": org_id, "quota_type": quota_type, "limit": limit, "used": 0, "period": period, "period_start": now.isoformat(), "period_end": (now + timedelta(days=30)).isoformat(), "is_active": True, "created_at": now.isoformat()}
            self._quotas[quota_id] = quota
        else:
            quota["limit"] = limit
            quota["period"] = period
        return quota

    def get_all_quotas(self, org_id: str) -> list[dict]:
        return [q for q in self._quotas.values() if q["organization_id"] == org_id]

    def get_usage_summary(self, org_id: str) -> dict:
        quotas = self.get_all_quotas(org_id)
        return {q["quota_type"]: {"limit": q["limit"], "used": q["used"], "remaining": q["limit"] - q["used"], "utilization": round(q["used"] / q["limit"] * 100, 1) if q["limit"] > 0 else 0} for q in quotas}

    def _is_current_period(self, quota: dict) -> bool:
        now = datetime.now(timezone.utc)
        try:
            end = datetime.fromisoformat(quota["period_end"])
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            return now <= end
        except (ValueError, KeyError):
            return True

    def _reset_period(self, quota: dict) -> None:
        now = datetime.now(timezone.utc)
        quota["used"] = 0
        quota["period_start"] = now.isoformat()
        if quota["period"] == "monthly":
            quota["period_end"] = (now + timedelta(days=30)).isoformat()
        elif quota["period"] == "yearly":
            quota["period_end"] = (now + timedelta(days=365)).isoformat()
        else:
            quota["period_end"] = (now + timedelta(days=30)).isoformat()

    def get_stats(self, org_id: Optional[str] = None) -> dict:
        quotas = self.get_all_quotas(org_id) if org_id else list(self._quotas.values())
        exceeded = [q for q in quotas if q["used"] >= q["limit"]]
        return {"total_quotas": len(quotas), "exceeded": len(exceeded), "total_usage_log": len(self._usage_log)}


quota_service = QuotaService()
