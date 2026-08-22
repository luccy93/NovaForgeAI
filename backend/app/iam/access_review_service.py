"""Access review service — periodic review of admin roles, production access, service accounts, API keys."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional


class AccessReviewService:
    def __init__(self):
        self._reviews: dict[str, dict] = []
        self._stale_items: dict[str, list[dict]] = {}

    def create_review(self, org_id: str, review_type: str = "periodic", scope: str = "all", initiated_by: str = "") -> dict:
        review_id = str(uuid.uuid4())
        review = {"id": review_id, "organization_id": org_id, "review_type": review_type, "scope": scope, "status": "pending", "initiated_by": initiated_by, "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None, "results": {}, "stale_items": [], "actions_taken": []}
        self._reviews.append(review)
        return review

    def complete_review(self, review_id: str, results: dict, stale_items: Optional[list[dict]] = None, actions_taken: Optional[list[dict]] = None) -> Optional[dict]:
        review = next((r for r in self._reviews if r["id"] == review_id), None)
        if not review:
            return None
        review["status"] = "completed"
        review["completed_at"] = datetime.now(timezone.utc).isoformat()
        review["results"] = results
        review["stale_items"] = stale_items or []
        review["actions_taken"] = actions_taken or []
        return review

    def get_review(self, review_id: str) -> Optional[dict]:
        return next((r for r in self._reviews if r["id"] == review_id), None)

    def list_reviews(self, org_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        reviews = list(self._reviews)
        if org_id:
            reviews = [r for r in reviews if r["organization_id"] == org_id]
        if status:
            reviews = [r for r in reviews if r["status"] == status]
        return reviews

    def flag_stale_admin_roles(self, org_id: str, memberships: list[dict], days_threshold: int = 90) -> list[dict]:
        stale = []
        now = datetime.now(timezone.utc)
        for mem in memberships:
            if mem.get("role") in ("owner", "admin") and mem.get("is_active"):
                joined_at = mem.get("joined_at") or mem.get("created_at")
                if joined_at:
                    try:
                        dt = datetime.fromisoformat(joined_at)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if (now - dt).days > days_threshold:
                            stale.append({"user_id": mem["user_id"], "role": mem["role"], "age_days": (now - dt).days, "type": "admin_role"})
                    except (ValueError, TypeError):
                        pass
        self._stale_items[org_id] = stale
        return stale

    def flag_expired_service_accounts(self, org_id: str, service_accounts: list[dict]) -> list[dict]:
        stale = []
        now = datetime.now(timezone.utc)
        for sa in service_accounts:
            if not sa.get("is_active"):
                continue
            if sa.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(sa["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if now > expires:
                        stale.append({"sa_id": sa["id"], "name": sa["name"], "type": "expired_service_account"})
                except (ValueError, TypeError):
                    pass
        return stale

    def flag_long_lived_api_keys(self, org_id: str, api_keys: list[dict], days_threshold: int = 90) -> list[dict]:
        stale = []
        now = datetime.now(timezone.utc)
        for key in api_keys:
            if not key.get("is_active"):
                continue
            created_at = key.get("created_at")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (now - dt).days > days_threshold:
                        stale.append({"key_id": key["id"], "name": key["name"], "age_days": (now - dt).days, "type": "long_lived_api_key"})
                except (ValueError, TypeError):
                    pass
        return stale

    def flag_unused_permissions(self, org_id: str, permissions_usage: dict) -> list[dict]:
        stale = []
        for perm, usage in permissions_usage.items():
            if usage.get("last_used_at") is None:
                stale.append({"permission": perm, "type": "unused_permission"})
        return stale

    def get_stats(self, org_id: Optional[str] = None) -> dict:
        reviews = list(self._reviews)
        if org_id:
            reviews = [r for r in reviews if r["organization_id"] == org_id]
        return {"total_reviews": len(reviews), "pending": sum(1 for r in reviews if r["status"] == "pending"), "completed": sum(1 for r in reviews if r["status"] == "completed")}


access_review_service = AccessReviewService()
