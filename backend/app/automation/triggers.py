"""Trigger registry (Volume 33).

Workflows start on triggers (manual, schedule/cron, webhook, event, API,
CLI, GitHub/GitLab, metric). Each trigger type has a parser + matcher.
Triggers are declarative; the scheduler and webhook endpoint dispatch
through DispatchHub.
"""
import logging, re, time
from typing import Any, Optional

from .workflow import WorkflowSpec

logger = logging.getLogger(__name__)

TRIGGER_TYPES = ("manual", "schedule", "cron", "webhook", "event", "github",
                 "gitlab", "metric_threshold", "pull_request", "commit",
                 "issue", "deployment", "security_finding", "incident",
                 "ai_decision", "api", "cli", "plugin")


class TriggerError(Exception):
    pass


def parse_trigger(raw: Any) -> dict:
    """Validate + normalize a trigger definition."""
    if raw is None:
        return {"type": "manual"}
    if isinstance(raw, str):
        raw = {"type": raw}
    ttype = str(raw.get("type", "manual"))
    if ttype not in TRIGGER_TYPES:
        raise TriggerError(f"unknown trigger type '{ttype}'")
    trigger = dict(raw)
    if ttype in ("schedule", "cron"):
        cron = trigger.get("cron", "") or trigger.get("expression", "")
        if not cron:
            raise TriggerError(f"{ttype} trigger requires cron expression")
        trigger["cron"] = cron
    if ttype == "webhook" and not trigger.get("path"):
        trigger["path"] = f"/automation/webhook/{trigger.get('name', 'wf')}"
    if "name" not in trigger:
        trigger["name"] = f"{ttype}_trigger"
    return trigger


def matches(trigger: dict, event: dict,
            now: Optional[float] = None) -> bool:
    """Does this event fire the trigger? Raw matching; the scheduler
    handles cron timing separately."""
    ttype = trigger.get("type")
    if ttype in ("schedule", "cron"):
        return event.get("kind") == "schedule_tick"
    if ttype == "webhook" and event.get("kind") == "request":
        path = trigger.get("path", "")
        return path in (event.get("path") or "")
    if ttype == "event":
        return event.get("kind") == trigger.get(
            "event_name", trigger.get("name"))
    if ttype in ("github", "gitlab"):
        ev = (event or {}).get("payload", {})
        return (event.get("source") == ttype and
                (not trigger.get("event") or
                 ev.get("action") == trigger.get("event")))
    if ttype == "metric_threshold":
        metric = (event or {}).get("metric")
        threshold = trigger.get("threshold")
        if metric is None or threshold is None:
            return False
        op = trigger.get("op", ">")
        try:
            return {"<": metric < threshold, "<=": metric <= threshold,
                    ">": metric > threshold, ">=": metric >= threshold,
                    "==": metric == threshold}.get(op, False)
        except TypeError:
            return False
    return False


class TriggerRule:
    """Bind a workflow to a trigger; used by DispatchHub/scheduler."""

    def __init__(self, spec: WorkflowSpec,
                 trigger: Optional[dict] = None,
                 organization_id: str = "",
                 enabled: bool = True):
        self.spec = spec
        self.trigger = parse_trigger(trigger or spec.trigger or
                                     {"type": "manual"})
        self.organization_id = organization_id or spec.organization_id
        self.enabled = enabled

    def matches(self, event: dict) -> bool:
        return self.enabled and matches(self.trigger, event)

    def to_dict(self) -> dict:
        return {"workflow_id": self.spec.workflow_id,
                "name": self.spec.name,
                "trigger": self.trigger,
                "organization_id": self.organization_id,
                "enabled": self.enabled}


class DispatchHub:
    """Fan-out: event -> matching TriggerRule -> run callback."""

    def __init__(self):
        self.rules: list[TriggerRule] = []
        self.dispatch_count = 0

    def add(self, rule: TriggerRule) -> None:
        self.rules.append(rule)

    def remove(self, workflow_id: str) -> int:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.spec.workflow_id != workflow_id]
        return before - len(self.rules)

    def dispatch(self, event: dict, runner=None) -> list[dict]:
        """runner(rule, event) is invoked for each match (async callback).
        Returns match results without raising."""
        results = []
        for rule in self.rules:
            try:
                matched = rule.matches(event)
            except Exception as exc:
                matched = False
            if matched:
                self.dispatch_count += 1
                results.append({"workflow_id": rule.spec.workflow_id,
                                "matched": True})
                if runner is not None:
                    try:
                        runner(rule, event)
                    except Exception as exc:
                        results[-1]["error"] = str(exc)
        return results

    def count(self) -> int:
        return len(self.rules)