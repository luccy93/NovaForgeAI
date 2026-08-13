"""Data Retention Engine - configurable retention policies per dataset with enforcement."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional


@dataclass
class RetentionPolicy:
    dataset: str
    days: int  # 0 = keep forever
    action: str = "archive"  # archive | delete
    enabled: bool = True
    created_at: str = ""


class RetentionEngine:
    """Policy registry + compliance-aware enforcement planning."""

    DEFAULTS = {
        "raw_events": (90, "archive"),
        "aggregated_events": (730, "archive"),
        "ai_logs": (180, "archive"),
        "security_events": (365, "archive"),
        "audit_events": (730, "archive"),
        "analytics": (1825, "archive"),
        "repository_history": (0, "keep"),
        "billing_data": (730, "archive"),
        "user_activity": (365, "archive"),
    }

    def __init__(self, override: Optional[dict] = None):
        self.policies: dict[str, RetentionPolicy] = {}
        for name, cfg in {**self.DEFAULTS, **(override or {})}.items():
            if isinstance(cfg, tuple):
                self.policies[name] = RetentionPolicy(name, cfg[0], cfg[1])
            else:
                self.policies[name] = RetentionPolicy(name, cfg["days"], cfg.get("action", "archive"))
        self.enforcement_log: list[dict] = []

    def configure(self, dataset: str, days: int, action: str = "archive") -> RetentionPolicy:
        p = RetentionPolicy(dataset, days, action)
        self.policies[dataset] = p
        return p

    def keep(self, dataset: str, created_at: Optional[str] = None) -> bool:
        policy = self.policies.get(dataset)
        if not policy or not policy.enabled or policy.days == 0:
            return True
        if not created_at:
            return False
        try:
            created = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            return True
        return created > datetime.now(timezone.utc) - timedelta(days=policy.days)

    def expired_items(self, dataset: str, items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Returns (item_id, created_at) pairs beyond the retention window."""
        return [(item_id, ts) for item_id, ts in items if not self.keep(dataset, ts)]

    def run(self, dataset: str, items: list[tuple[str, str]],
            executor: Optional[Callable[[str, list[str]], int]] = None) -> dict:
        policy = self.policies.get(dataset)
        if not policy or not policy.enabled:
            return {"dataset": dataset, "action": "disabled", "items": 0}
        expired = self.expired_items(dataset, items)
        removed = 0
        if executor and expired:
            removed = executor(dataset, [item_id for item_id, _ in expired])
        self.enforcement_log.append({"dataset": dataset, "action": policy.action,
                                     "expired": len(expired), "removed": removed,
                                     "at": datetime.now(timezone.utc).isoformat()})
        return {"dataset": dataset, "action": policy.action,
                "expired": len(expired), "removed": removed}

    def status(self) -> list[dict]:
        return [{"dataset": name, "days": p.days, "action": p.action, "enabled": p.enabled}
                for name, p in sorted(self.policies.items())]