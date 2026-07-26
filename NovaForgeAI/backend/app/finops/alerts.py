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


class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertCategory(Enum):
    BUDGET_EXCEEDED = "budget_exceeded"
    HIGH_AI_COST = "high_ai_cost"
    INFRASTRUCTURE_SPIKE = "infrastructure_spike"
    ABNORMAL_USAGE = "abnormal_usage"
    QUOTA_EXCEEDED = "quota_exceeded"
    REVENUE_DROP = "revenue_drop"
    STORAGE_GROWTH = "storage_growth"
    GPU_EXHAUSTION = "gpu_exhaustion"
    COST_ANOMALY = "cost_anomaly"
    FORECAST_WARNING = "forecast_warning"
    SUBSCRIPTION_EXPIRY = "subscription_expiry"
    RATE_LIMIT = "rate_limit"
    ERROR_SPIKE = "error_spike"


class AlertStatus(Enum):
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    ESCALATED = "escalated"


class NotificationChannel(Enum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    SMS = "sms"
    IN_APP = "in_app"
    TEAMS = "teams"
    DISCORD = "discord"


@dataclass
class AlertRule:
    id: str
    org_id: str
    name: str
    category: AlertCategory
    severity: AlertSeverity
    metric_name: str
    condition: str
    threshold: float
    duration_minutes: int
    cooldown_minutes: int
    channels: list[NotificationChannel]
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["channels"] = [c.value for c in self.channels]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AlertRule":
        data = data.copy()
        data["category"] = AlertCategory(data.get("category", "budget_exceeded"))
        data["severity"] = AlertSeverity(data.get("severity", "medium"))
        channels_raw = data.get("channels", [])
        data["channels"] = [NotificationChannel(c) if isinstance(c, str) else c for c in channels_raw]
        return cls(**data)


@dataclass
class AlertEvent:
    id: str
    rule_id: str
    org_id: str
    category: AlertCategory
    severity: AlertSeverity
    status: AlertStatus
    title: str
    message: str
    metric_name: str
    current_value: float
    threshold: float
    triggered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: str = ""
    resolved_at: str = ""
    acknowledged_by: str = ""
    resolved_by: str = ""
    escalation_level: int = 0
    notifications_sent: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AlertEvent":
        data = data.copy()
        data["category"] = AlertCategory(data.get("category", "budget_exceeded"))
        data["severity"] = AlertSeverity(data.get("severity", "medium"))
        data["status"] = AlertStatus(data.get("status", "triggered"))
        return cls(**data)


@dataclass
class AlertEscalationPolicy:
    id: str
    org_id: str
    name: str
    category: AlertCategory
    levels: list
    wait_minutes: list
    notify: list
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AlertEscalationPolicy":
        data = data.copy()
        data["category"] = AlertCategory(data.get("category", "budget_exceeded"))
        return cls(**data)


class AlertManager:
    def __init__(self, storage_dir: str = "alert_data"):
        self.storage_dir = storage_dir
        self._rules: dict[str, AlertRule] = {}
        self._events: dict[str, AlertEvent] = {}
        self._escalation_policies: dict[str, AlertEscalationPolicy] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _rules_path(self) -> str:
        return os.path.join(self.storage_dir, "rules.json")

    def _events_path(self) -> str:
        return os.path.join(self.storage_dir, "events.json")

    def _escalation_path(self) -> str:
        return os.path.join(self.storage_dir, "escalation_policies.json")

    def _save(self) -> None:
        try:
            rules_data = {rid: r.to_dict() for rid, r in self._rules.items()}
            with open(self._rules_path(), "w", encoding="utf-8") as f:
                json.dump(rules_data, f, indent=2, default=str)

            events_data = {eid: e.to_dict() for eid, e in self._events.items()}
            with open(self._events_path(), "w", encoding="utf-8") as f:
                json.dump(events_data, f, indent=2, default=str)

            esc_data = {pid: p.to_dict() for pid, p in self._escalation_policies.items()}
            with open(self._escalation_path(), "w", encoding="utf-8") as f:
                json.dump(esc_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save alert data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._rules_path()):
                with open(self._rules_path(), "r", encoding="utf-8") as f:
                    rules_data = json.load(f)
                for rid, data in rules_data.items():
                    try:
                        self._rules[rid] = AlertRule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed rule %s: %s", rid, e)

            if os.path.exists(self._events_path()):
                with open(self._events_path(), "r", encoding="utf-8") as f:
                    events_data = json.load(f)
                for eid, data in events_data.items():
                    try:
                        self._events[eid] = AlertEvent.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed event %s: %s", eid, e)

            if os.path.exists(self._escalation_path()):
                with open(self._escalation_path(), "r", encoding="utf-8") as f:
                    esc_data = json.load(f)
                for pid, data in esc_data.items():
                    try:
                        self._escalation_policies[pid] = AlertEscalationPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed escalation policy %s: %s", pid, e)
        except Exception as e:
            logger.error("Failed to load alert data: %s", e, exc_info=True)

    def create_rule(self, rule: AlertRule) -> AlertRule:
        self._telemetry["create_rule_calls"] += 1
        if not rule.id:
            rule.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        rule.created_at = now
        rule.updated_at = now
        self._rules[rule.id] = rule
        self._save()
        logger.info("Created alert rule %s: %s (category=%s, severity=%s)", rule.id, rule.name, rule.category.value, rule.severity.value)
        return rule

    def update_rule(self, rule_id: str, updates: dict) -> Optional[AlertRule]:
        self._telemetry["update_rule_calls"] += 1
        rule = self._rules.get(rule_id)
        if not rule:
            logger.warning("Attempted to update unknown alert rule: %s", rule_id)
            return None
        for key, value in updates.items():
            if hasattr(rule, key) and key not in ("id", "org_id", "created_at"):
                if key == "category":
                    setattr(rule, key, AlertCategory(value) if isinstance(value, str) else value)
                elif key == "severity":
                    setattr(rule, key, AlertSeverity(value) if isinstance(value, str) else value)
                elif key == "channels":
                    setattr(rule, key, [NotificationChannel(c) if isinstance(c, str) else c for c in value])
                else:
                    setattr(rule, key, value)
        rule.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated alert rule: %s", rule_id)
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        self._telemetry["delete_rule_calls"] += 1
        if rule_id not in self._rules:
            logger.warning("Attempted to delete unknown alert rule: %s", rule_id)
            return False
        del self._rules[rule_id]
        self._save()
        logger.info("Deleted alert rule: %s", rule_id)
        return True

    def list_rules(self, org_id: str, category: Optional[AlertCategory] = None, enabled: Optional[bool] = None) -> list[AlertRule]:
        self._telemetry["list_rules_calls"] += 1
        results = []
        for rule in self._rules.values():
            if rule.org_id != org_id:
                continue
            if category is not None and rule.category != category:
                continue
            if enabled is not None and rule.enabled != enabled:
                continue
            results.append(rule)
        results.sort(key=lambda r: r.updated_at, reverse=True)
        return results

    def evaluate_rules(self, org_id: str, metrics: dict) -> list[AlertEvent]:
        self._telemetry["evaluate_rules_calls"] += 1
        triggered = []
        now = datetime.now(timezone.utc)

        for rule in self._rules.values():
            if rule.org_id != org_id or not rule.enabled:
                continue

            current_value = metrics.get(rule.metric_name)
            if current_value is None:
                continue

            threshold = rule.threshold
            condition = rule.condition
            triggered_flag = False

            if condition == "gt" or condition == ">":
                triggered_flag = current_value > threshold
            elif condition == "gte" or condition == ">=":
                triggered_flag = current_value >= threshold
            elif condition == "lt" or condition == "<":
                triggered_flag = current_value < threshold
            elif condition == "lte" or condition == "<=":
                triggered_flag = current_value <= threshold
            elif condition == "eq" or condition == "==":
                triggered_flag = current_value == threshold
            elif condition == "neq" or condition == "!=":
                triggered_flag = current_value != threshold
            elif condition == "pct_change_gt":
                triggered_flag = current_value > threshold
            elif condition == "pct_change_lt":
                triggered_flag = current_value < threshold

            if not triggered_flag:
                continue

            # Check cooldown - don't re-trigger within cooldown period
            recent_alerts = [e for e in self._events.values() if e.rule_id == rule.id and e.status in (AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED, AlertStatus.ESCALATED)]
            skip = False
            for recent in recent_alerts:
                recent_time = datetime.fromisoformat(recent.triggered_at)
                if (now - recent_time).total_seconds() < rule.cooldown_minutes * 60:
                    skip = True
                    break
            if skip:
                continue

            event = self.trigger_alert(rule, current_value, rule.metric_name)
            triggered.append(event)

        return triggered

    def trigger_alert(self, rule: AlertRule, current_value: float, metric_name: str) -> AlertEvent:
        self._telemetry["trigger_alert_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()

        title = f"{rule.severity.value.upper()}: {rule.name}"
        message = f"Alert rule '{rule.name}' triggered: {metric_name} is at {current_value} (threshold: {rule.threshold}, condition: {rule.condition})"

        event = AlertEvent(
            id=str(uuid.uuid4()),
            rule_id=rule.id,
            org_id=rule.org_id,
            category=rule.category,
            severity=rule.severity,
            status=AlertStatus.TRIGGERED,
            title=title,
            message=message,
            metric_name=metric_name,
            current_value=current_value,
            threshold=rule.threshold,
            triggered_at=now,
            notifications_sent=[c.value for c in rule.channels],
        )

        # Check escalation policies
        for policy in self._escalation_policies.values():
            if policy.org_id == rule.org_id and policy.category == rule.category:
                event.escalation_level = 0
                event.metadata["escalation_policy_id"] = policy.id
                break

        self._events[event.id] = event
        self._save()
        logger.info("Triggered alert %s: %s (rule=%s, value=%.2f, threshold=%.2f)", event.id, title, rule.id, current_value, rule.threshold)
        return event

    def acknowledge_alert(self, alert_id: str, user: str) -> Optional[AlertEvent]:
        self._telemetry["acknowledge_alert_calls"] += 1
        event = self._events.get(alert_id)
        if not event:
            logger.warning("Attempted to acknowledge unknown alert: %s", alert_id)
            return None
        if event.status not in (AlertStatus.TRIGGERED, AlertStatus.ESCALATED):
            logger.warning("Alert %s cannot be acknowledged (status: %s)", alert_id, event.status.value)
            return None
        event.status = AlertStatus.ACKNOWLEDGED
        event.acknowledged_at = datetime.now(timezone.utc).isoformat()
        event.acknowledged_by = user
        self._save()
        logger.info("Acknowledged alert %s by %s", alert_id, user)
        return event

    def resolve_alert(self, alert_id: str, user: str) -> Optional[AlertEvent]:
        self._telemetry["resolve_alert_calls"] += 1
        event = self._events.get(alert_id)
        if not event:
            logger.warning("Attempted to resolve unknown alert: %s", alert_id)
            return None
        if event.status in (AlertStatus.RESOLVED, AlertStatus.DISMISSED):
            logger.warning("Alert %s already %s", alert_id, event.status.value)
            return None
        event.status = AlertStatus.RESOLVED
        event.resolved_at = datetime.now(timezone.utc).isoformat()
        event.resolved_by = user
        self._save()
        logger.info("Resolved alert %s by %s", alert_id, user)
        return event

    def get_active_alerts(self, org_id: str, severity: Optional[AlertSeverity] = None) -> list[AlertEvent]:
        self._telemetry["get_active_alerts_calls"] += 1
        results = []
        for event in self._events.values():
            if event.org_id != org_id:
                continue
            if event.status not in (AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED, AlertStatus.ESCALATED):
                continue
            if severity is not None and event.severity != severity:
                continue
            results.append(event)
        results.sort(key=lambda e: e.triggered_at, reverse=True)
        return results

    def get_alert_history(self, org_id: str, days: int = 30) -> list[AlertEvent]:
        self._telemetry["get_alert_history_calls"] += 1
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        results = []
        for event in self._events.values():
            if event.org_id != org_id:
                continue
            if event.triggered_at < cutoff:
                continue
            results.append(event)
        results.sort(key=lambda e: e.triggered_at, reverse=True)
        return results

    def get_alert_stats(self, org_id: str) -> dict:
        self._telemetry["get_alert_stats_calls"] += 1
        org_events = [e for e in self._events.values() if e.org_id == org_id]

        severity_counts: dict[str, int] = defaultdict(int)
        category_counts: dict[str, int] = defaultdict(int)
        status_counts: dict[str, int] = defaultdict(int)

        total_resolution_time = 0.0
        resolved_count = 0

        for event in org_events:
            severity_counts[event.severity.value] += 1
            category_counts[event.category.value] += 1
            status_counts[event.status.value] += 1

            if event.status == AlertStatus.RESOLVED and event.resolved_at:
                triggered = datetime.fromisoformat(event.triggered_at)
                resolved = datetime.fromisoformat(event.resolved_at)
                total_resolution_time += (resolved - triggered).total_seconds()
                resolved_count += 1

        avg_resolution_seconds = round(total_resolution_time / max(resolved_count, 1), 2)
        avg_resolution_minutes = round(avg_resolution_seconds / 60, 2)

        return {
            "org_id": org_id,
            "total_alerts": len(org_events),
            "by_severity": dict(severity_counts),
            "by_category": dict(category_counts),
            "by_status": dict(status_counts),
            "avg_resolution_time_seconds": avg_resolution_seconds,
            "avg_resolution_time_minutes": avg_resolution_minutes,
            "resolved_count": resolved_count,
            "active_count": sum(1 for e in org_events if e.status in (AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED, AlertStatus.ESCALATED)),
        }

    def create_escalation_policy(self, policy: AlertEscalationPolicy) -> AlertEscalationPolicy:
        self._telemetry["create_escalation_policy_calls"] += 1
        if not policy.id:
            policy.id = str(uuid.uuid4())
        if not policy.created_at:
            policy.created_at = datetime.now(timezone.utc).isoformat()
        self._escalation_policies[policy.id] = policy
        self._save()
        logger.info("Created escalation policy %s: %s (%d levels)", policy.id, policy.name, len(policy.levels))
        return policy

    def simulate_alert(self, rule_id: str, current_value: float) -> dict:
        self._telemetry["simulate_alert_calls"] += 1
        rule = self._rules.get(rule_id)
        if not rule:
            return {"error": "Rule not found", "rule_id": rule_id}

        threshold = rule.threshold
        condition = rule.condition
        triggered = False

        if condition == "gt" or condition == ">":
            triggered = current_value > threshold
        elif condition == "gte" or condition == ">=":
            triggered = current_value >= threshold
        elif condition == "lt" or condition == "<":
            triggered = current_value < threshold
        elif condition == "lte" or condition == "<=":
            triggered = current_value <= threshold
        elif condition == "eq" or condition == "==":
            triggered = current_value == threshold
        elif condition == "neq" or condition == "!=":
            triggered = current_value != threshold
        elif condition == "pct_change_gt":
            triggered = current_value > threshold
        elif condition == "pct_change_lt":
            triggered = current_value < threshold

        # Check cooldown status
        cooldown_active = False
        now = datetime.now(timezone.utc)
        recent_alerts = [e for e in self._events.values() if e.rule_id == rule.id and e.status in (AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED, AlertStatus.ESCALATED)]
        for recent in recent_alerts:
            recent_time = datetime.fromisoformat(recent.triggered_at)
            if (now - recent_time).total_seconds() < rule.cooldown_minutes * 60:
                cooldown_active = True
                break

        return {
            "rule_id": rule_id,
            "rule_name": rule.name,
            "org_id": rule.org_id,
            "category": rule.category.value,
            "severity": rule.severity.value,
            "metric_name": rule.metric_name,
            "condition": rule.condition,
            "threshold": threshold,
            "current_value": current_value,
            "triggered": triggered,
            "cooldown_active": cooldown_active,
            "cooldown_remaining_minutes": max(0, rule.cooldown_minutes - int((now - datetime.fromisoformat(recent.triggered_at)).total_seconds() / 60)) if cooldown_active and recent_alerts else 0,
            "channels": [c.value for c in rule.channels],
            "would_notify": triggered and not cooldown_active,
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
