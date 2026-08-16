"""Automated operations and self-healing guardrails (Volume 35).

Every automated remediation is audited with reason, evidence, policy,
authorization, result and rollback. Guardrails prevent uncontrolled
self-healing loops: max attempts, cooldown, circuit breaker and
escalation to humans.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import SRERemediationAction
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

# Operations that may run automatically under policy.
SAFE_ACTIONS: set[str] = {
    "restart_worker",
    "scale_pool",
    "retry_job",
    "failover_approved_dependency",
    "drain_unhealthy_instance",
    "queue_non_critical_work",
    "rotate_short_lived_credential",
}

# Operations that always require explicit human approval.
UNSAFE_ACTIONS: set[str] = {
    "destructive_database_change",
    "production_data_delete",
    "credential_rotation_production_wide",
    "region_switch",
}


class RemediationAuditor:
    """Audit trail + policy gate for automated remediation."""

    def __init__(self) -> None:
        self._cooldown: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._lock = threading.Lock()

    async def execute(
        self,
        db: AsyncSession,
        *,
        action: str,
        target: str,
        reason: str,
        evidence: Optional[list] = None,
        policy: str = "sre-default",
        approved_by: str = "",
        max_attempts: int = 1,
        cooldown_seconds: float = 300.0,
        worker: Optional[callable] = None,
    ) -> SRERemediationAction:
        """Execute a remediation action under policy; audit everything."""
        record = SRERemediationAction(
            id=new_id(),
            action_id=new_key("action"),
            action=action,
            target=target,
            reason=reason,
            evidence=evidence or [],
            policy=policy,
            authorized=action in SAFE_ACTIONS,
            requires_approval=action in UNSAFE_ACTIONS,
            approved_by=approved_by,
            result="pending",
            max_attempts=max_attempts,
        )
        db.add(record)
        await db.flush()

        # Approval gate: unsafe actions require explicit approval.
        if record.requires_approval and not approved_by:
            record.result = "skipped"
            record.rollback = "unsafe action requires approval"
            await db.flush()
            return record

        # Self-healing guardrail: circuit breaker + cooldown per action.
        gate_key = f"{action}:{target}"
        with self._lock:
            last_run = self._cooldown.get(gate_key, 0.0)
            now = time.monotonic()
            if now - last_run < cooldown_seconds and last_run > 0:
                record.result = "skipped"
                record.rollback = f"cooldown active ({cooldown_seconds:.0f}s)"
                await db.flush()
                return record
            if self._failures.get(gate_key, 0) >= max_attempts:
                record.result = "skipped"
                record.rollback = f"max attempts ({max_attempts}) reached; escalation to human required"
                await db.flush()
                return record

        record.attempt = min(self._failures.get(gate_key, 0) + 1, max_attempts)
        try:
            if worker is not None:
                result = worker()
                if callable(result):
                    result = await result  # type: ignore[assignment]
            record.result = "success"
            record.executed_at = datetime.now(timezone.utc)
            with self._lock:
                self._cooldown[gate_key] = time.monotonic()
                self._failures[gate_key] = 0
            logger.info("Remediation executed: %s on %s (%s)", action, target, record.action_id)
        except Exception as exc:
            record.result = "failed"
            record.rollback = f"failed: {exc}"
            with self._lock:
                self._failures[gate_key] = self._failures.get(gate_key, 0) + 1
            logger.warning("Remediation failed: %s on %s: %s", action, target, exc)
        await db.flush()
        return record

    async def list(
        self,
        db: AsyncSession,
        *,
        action: str = "",
        result: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SRERemediationAction, limit=limit, offset=offset, order_by="created_at", action=action, result=result
        )
        return [r.to_dict() for r in items], total

    async def get(self, db: AsyncSession, action_id: str) -> Optional[dict]:
        record = await get_one(db, SRERemediationAction, action_id=action_id)
        return record.to_dict() if record else None


remediation_auditor = RemediationAuditor()