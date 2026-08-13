"""Scheduler (Volume 33).

Cron-style scheduling for workflows via TriggerRule entries. The scheduler
is a pure matcher: `tick()` returns due rules; persistence + worker loop
live in the gateway. Cron parsing supports standard 5-field expressions.
"""
import logging, re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .triggers import TriggerRule

logger = logging.getLogger(__name__)


class CronParser:
    """Minimal 5-field cron parser (min hour dom mon dow), * and lists."""

    def __init__(self, expression: str):
        self.expression = expression
        self.fields = self._parse(expression)

    def _parse(self, expr: str) -> list[list[int]]:
        parts = [p.strip() for p in expr.split()]
        if len(parts) != 5:
            raise ValueError(f"cron must have 5 fields: '{expr}'")
        specs = [("minute", 0, 59), ("hour", 0, 23), ("day_of_month", 1, 31),
                 ("month", 1, 12), ("day_of_week", 0, 6)]
        parsed = []
        for i, part in enumerate(parts):
            name, lo, hi = specs[i]
            if part == "*":
                parsed.append(list(range(lo, hi + 1)))
                continue
            values = set()
            for token in part.split(","):
                if "/" in token:
                    base, step = token.split("/")
                    if base == "*":
                        values.update(range(lo, hi + 1, int(step)))
                    else:
                        values.update(self._range(base, lo, hi)[::int(step)])
                else:
                    values.update(self._range(token, lo, hi))
            parsed.append(sorted(values))
        return parsed

    def _range(self, token: str, lo: int, hi: int) -> list[int]:
        if "-" in token:
            a, b = token.split("-")
            return list(range(int(a), int(b) + 1))
        value = int(token)
        if not (lo <= value <= hi):
            raise ValueError(f"{token} out of range {lo}-{hi}")
        return [value]

    def next_run(self, after: Optional[datetime] = None) -> datetime:
        after = after or datetime.now(timezone.utc)
        probe = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(60 * 24 * 366):
            if self.matches(probe):
                return probe
            probe += timedelta(minutes=1)
        raise ValueError("no match within a year")

    def matches(self, moment: Optional[datetime] = None) -> bool:
        moment = moment or datetime.now(timezone.utc)
        minutes, hours, dom, months, dow = self.fields
        if moment.minute not in minutes or moment.hour not in hours:
            return False
        if moment.month not in months:
            return False
        if moment.weekday() not in dow:
            return False
        return True


class Scheduler:
    """Holds cron rules and reports due workflows on each tick."""

    def __init__(self):
        self.rules: list[TriggerRule] = []
        self.last_tick: Optional[datetime] = None
        self.ticks = 0

    def register(self, rule: TriggerRule) -> None:
        if rule.trigger.get("type") not in ("schedule", "cron"):
            raise ValueError(
                f"workflow '{rule.spec.workflow_id}' trigger is not cron")
        CronParser(rule.trigger["cron"])  # validate now
        self.rules.append(rule)

    def unregister(self, workflow_id: str) -> int:
        before = len(self.rules)
        self.rules = [r for r in self.rules
                      if r.spec.workflow_id != workflow_id]
        return before - len(self.rules)

    def tick(self, now: Optional[datetime] = None,
             runner=None) -> list[dict]:
        """Due rules at this minute. `runner(rule, now)` executes the run;
        runner failures are reported per rule without breaking the tick."""
        now = now or datetime.now(timezone.utc)
        self.last_tick = now
        self.ticks += 1
        due = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            try:
                if CronParser(rule.trigger["cron"]).matches(now):
                    due.append(rule)
            except ValueError as exc:
                logger.warning("bad cron for %s: %s",
                               rule.spec.workflow_id, exc)
        results = []
        for rule in due:
            entry = {"workflow_id": rule.spec.workflow_id,
                     "organization_id": rule.organization_id,
                     "cron": rule.trigger.get("cron"), "due": True}
            if runner is not None:
                try:
                    entry["execution_id"] = runner(rule, now)
                except Exception as exc:
                    entry["error"] = str(exc)
            results.append(entry)
        return results

    def count(self) -> int:
        return len(self.rules)