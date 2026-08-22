"""Dunning service — handle payment failures, retries, downgrades, suspensions."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.billing.constants import DunningAction, SubscriptionStatus
from app.billing.config import get_billing_config


class DunningService:
    def __init__(self):
        self._records: dict[str, dict] = {}
        self._sub_dunning: dict[str, list[str]] = {}
        self._org_dunning: dict[str, list[str]] = {}

    def create_dunning_record(
        self,
        subscription_id: str,
        organization_id: str,
        invoice_id: str,
        action: str = "email_retry",
        reason: str = "",
    ) -> dict:
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        config = get_billing_config()
        attempt = self._get_attempt_count(subscription_id) + 1
        retry_idx = min(attempt - 1, len(config.dunning_retry_hours) - 1)
        next_retry_hours = config.dunning_retry_hours[retry_idx] if retry_idx < len(config.dunning_retry_hours) else config.dunning_retry_hours[-1]
        next_retry_at = now + timedelta(hours=next_retry_hours) if attempt <= config.max_dunning_retries else None
        record = {
            "id": record_id,
            "subscription_id": subscription_id,
            "organization_id": organization_id,
            "invoice_id": invoice_id,
            "attempt_number": attempt,
            "action": action,
            "action_result": "pending",
            "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
            "completed_at": None,
            "failure_reason": reason,
            "metadata": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._records[record_id] = record
        self._sub_dunning.setdefault(subscription_id, []).append(record_id)
        self._org_dunning.setdefault(organization_id, []).append(record_id)
        return record

    def _get_attempt_count(self, subscription_id: str) -> int:
        ids = self._sub_dunning.get(subscription_id, [])
        return sum(1 for rid in ids if rid in self._records)

    def get_dunning_record(self, record_id: str) -> Optional[dict]:
        return self._records.get(record_id)

    def get_subscription_dunning(self, subscription_id: str) -> list[dict]:
        ids = self._sub_dunning.get(subscription_id, [])
        return [self._records[rid] for rid in ids if rid in self._records]

    def list_dunning_records(
        self,
        organization_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        if subscription_id:
            ids = self._sub_dunning.get(subscription_id, [])
            results = [self._records[rid] for rid in ids if rid in self._records]
        elif organization_id:
            ids = self._org_dunning.get(organization_id, [])
            results = [self._records[rid] for rid in ids if rid in self._records]
        else:
            results = list(self._records.values())
        if status:
            results = [r for r in results if r["action_result"] == status]
        return results[-limit:]

    def complete_dunning(self, record_id: str, result: str = "success") -> Optional[dict]:
        record = self._records.get(record_id)
        if not record:
            return None
        now = datetime.now(timezone.utc)
        record["action_result"] = result
        record["completed_at"] = now.isoformat()
        record["updated_at"] = now.isoformat()
        return record

    def should_suspend(self, subscription_id: str) -> bool:
        config = get_billing_config()
        if not config.enable_dunning:
            return False
        records = self.get_subscription_dunning(subscription_id)
        pending = [r for r in records if r["action_result"] == "pending"]
        return len(pending) >= config.max_dunning_retries

    def execute_dunning_action(self, subscription_id: str, action: str) -> dict:
        config = get_billing_config()
        now = datetime.now(timezone.utc)
        result = {"subscription_id": subscription_id, "action": action, "executed_at": now.isoformat()}
        if action == DunningAction.SUSPEND.value:
            result["action_taken"] = "suspended"
            result["subscription_status"] = SubscriptionStatus.SUSPENDED.value if hasattr(SubscriptionStatus, "SUSPENDED") else SubscriptionStatus.PAST_DUE.value
        elif action == DunningAction.DOWNGRADE.value:
            result["action_taken"] = "downgrade_queued"
        elif action == DunningAction.CANCEL.value:
            result["action_taken"] = "canceled"
            result["subscription_status"] = SubscriptionStatus.CANCELED.value
        elif action == DunningAction.EMAIL_RETRY.value:
            result["action_taken"] = "email_queued"
        elif action == DunningAction.RETRY_PAYMENT.value:
            result["action_taken"] = "retry_scheduled"
        return result

    def get_telemetry(self) -> dict:
        return {
            "total_records": len(self._records),
            "pending": sum(1 for r in self._records.values() if r["action_result"] == "pending"),
            "completed": sum(1 for r in self._records.values() if r["action_result"] in ("success", "failed")),
        }


dunning_service = DunningService()
