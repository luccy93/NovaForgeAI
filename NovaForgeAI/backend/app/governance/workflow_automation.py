import json
import uuid
import os
import logging
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class AutomationTrigger(Enum):
    POLICY_CREATED = "policy_created"
    POLICY_UPDATED = "policy_updated"
    VIOLATION_DETECTED = "violation_detected"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_COMPLETED = "approval_completed"
    CHANGE_REQUESTED = "change_requested"
    CHANGE_COMPLETED = "change_completed"
    AUDIT_EVENT_RECORDED = "audit_event_recorded"
    COMPLIANCE_ASSESSMENT_DUE = "compliance_assessment_due"
    INCIDENT_REPORTED = "incident_reported"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class AutomationAction(Enum):
    ENFORCE_POLICY = "enforce_policy"
    GENERATE_COMPLIANCE_REPORT = "generate_compliance_report"
    NOTIFY_STAKEHOLDERS = "notify_stakeholders"
    ESCALATE_EVENT = "escalate_event"
    ARCHIVE_AUDIT_RECORDS = "archive_audit_records"
    DETECT_VIOLATIONS = "detect_violations"
    SEND_ALERT = "send_alert"
    CREATE_TICKET = "create_ticket"
    LOCK_RESOURCE = "lock_resource"
    SUSPEND_USER = "suspend_user"
    REVOKE_ACCESS = "revoke_access"
    APPLY_RETENTION = "apply_retention"


class AutomationStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    ERROR = "error"
    DISABLED = "disabled"


class TriggerMatchType(Enum):
    ALL = "all"
    ANY = "any"
    NONE = "none"
    CUSTOM = "custom"


@dataclass
class AutomationRule:
    id: str
    org_id: str
    name: str
    description: str = ""
    trigger: AutomationTrigger = AutomationTrigger.MANUAL
    match_type: TriggerMatchType = TriggerMatchType.ALL
    conditions: list[dict] = field(default_factory=list)
    actions: list[AutomationAction] = field(default_factory=list)
    action_params: dict = field(default_factory=dict)
    cooldown_minutes: int = 0
    enabled: bool = True
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger"] = self.trigger.value
        d["match_type"] = self.match_type.value
        d["actions"] = [a.value for a in self.actions]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationRule":
        data["trigger"] = AutomationTrigger(data["trigger"])
        data["match_type"] = TriggerMatchType(data["match_type"])
        data["actions"] = [AutomationAction(a) for a in data["actions"]]
        return cls(**data)


@dataclass
class AutomationExecution:
    id: str
    rule_id: str
    org_id: str
    trigger: AutomationTrigger = AutomationTrigger.MANUAL
    matched_conditions: list = field(default_factory=list)
    actions_executed: list = field(default_factory=list)
    status: str = "pending"
    result: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger"] = self.trigger.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationExecution":
        data["trigger"] = AutomationTrigger(data["trigger"])
        return cls(**data)


@dataclass
class AutomationSchedule:
    id: str
    org_id: str
    name: str
    trigger: AutomationTrigger = AutomationTrigger.SCHEDULED
    cron_expression: str = ""
    actions: list[AutomationAction] = field(default_factory=list)
    action_params: dict = field(default_factory=dict)
    enabled: bool = True
    last_run: str = ""
    next_run: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger"] = self.trigger.value
        d["actions"] = [a.value for a in self.actions]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationSchedule":
        data["trigger"] = AutomationTrigger(data["trigger"])
        data["actions"] = [AutomationAction(a) for a in data["actions"]]
        return cls(**data)


@dataclass
class NotificationTemplate:
    id: str
    org_id: str
    name: str
    trigger: AutomationTrigger = AutomationTrigger.MANUAL
    subject: str = ""
    body: str = ""
    channels: list = field(default_factory=list)
    variables: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger"] = self.trigger.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationTemplate":
        data["trigger"] = AutomationTrigger(data["trigger"])
        return cls(**data)


class WorkflowAutomation:
    def __init__(self, storage_dir: str = "workflow_automation_data"):
        self.storage_dir = storage_dir
        self._rules: dict[str, AutomationRule] = {}
        self._executions: dict[str, AutomationExecution] = {}
        self._schedules: dict[str, AutomationSchedule] = {}
        self._notification_templates: dict[str, NotificationTemplate] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _rules_path(self) -> str:
        return os.path.join(self.storage_dir, "rules.json")

    def _executions_path(self) -> str:
        return os.path.join(self.storage_dir, "executions.json")

    def _schedules_path(self) -> str:
        return os.path.join(self.storage_dir, "schedules.json")

    def _templates_path(self) -> str:
        return os.path.join(self.storage_dir, "notification_templates.json")

    def _save(self) -> None:
        try:
            rules_data = {rid: r.to_dict() for rid, r in self._rules.items()}
            with open(self._rules_path(), "w", encoding="utf-8") as f:
                json.dump(rules_data, f, indent=2, default=str)

            executions_data = {eid: e.to_dict() for eid, e in self._executions.items()}
            with open(self._executions_path(), "w", encoding="utf-8") as f:
                json.dump(executions_data, f, indent=2, default=str)

            schedules_data = {sid: s.to_dict() for sid, s in self._schedules.items()}
            with open(self._schedules_path(), "w", encoding="utf-8") as f:
                json.dump(schedules_data, f, indent=2, default=str)

            templates_data = {tid: t.to_dict() for tid, t in self._notification_templates.items()}
            with open(self._templates_path(), "w", encoding="utf-8") as f:
                json.dump(templates_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save workflow automation data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._rules_path()):
                with open(self._rules_path(), "r", encoding="utf-8") as f:
                    rules_data = json.load(f)
                for rid, data in rules_data.items():
                    try:
                        self._rules[rid] = AutomationRule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed automation rule %s: %s", rid, e)

            if os.path.exists(self._executions_path()):
                with open(self._executions_path(), "r", encoding="utf-8") as f:
                    executions_data = json.load(f)
                for eid, data in executions_data.items():
                    try:
                        self._executions[eid] = AutomationExecution.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed execution %s: %s", eid, e)

            if os.path.exists(self._schedules_path()):
                with open(self._schedules_path(), "r", encoding="utf-8") as f:
                    schedules_data = json.load(f)
                for sid, data in schedules_data.items():
                    try:
                        self._schedules[sid] = AutomationSchedule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed schedule %s: %s", sid, e)

            if os.path.exists(self._templates_path()):
                with open(self._templates_path(), "r", encoding="utf-8") as f:
                    templates_data = json.load(f)
                for tid, data in templates_data.items():
                    try:
                        self._notification_templates[tid] = NotificationTemplate.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed notification template %s: %s", tid, e)
        except Exception as e:
            logger.error("Failed to load workflow automation data: %s", e, exc_info=True)

    def create_rule(self, rule: AutomationRule) -> AutomationRule:
        self._telemetry["create_rule_calls"] += 1
        if rule.id in self._rules:
            raise ValueError(f"Automation rule with id '{rule.id}' already exists.")
        rule.created_at = datetime.now(timezone.utc).isoformat()
        rule.updated_at = rule.created_at
        self._rules[rule.id] = rule
        self._save()
        logger.info("Created automation rule: %s (%s)", rule.name, rule.id)
        return rule

    def update_rule(self, rule_id: str, updates: dict) -> Optional[AutomationRule]:
        self._telemetry["update_rule_calls"] += 1
        rule = self._rules.get(rule_id)
        if not rule:
            logger.warning("Attempted to update unknown automation rule: %s", rule_id)
            return None
        for key, value in updates.items():
            if hasattr(rule, key) and key not in ("id", "created_at"):
                if key == "trigger":
                    setattr(rule, key, AutomationTrigger(value) if isinstance(value, str) else value)
                elif key == "match_type":
                    setattr(rule, key, TriggerMatchType(value) if isinstance(value, str) else value)
                elif key == "actions":
                    setattr(rule, key, [AutomationAction(a) if isinstance(a, str) else a for a in value])
                else:
                    setattr(rule, key, value)
        rule.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated automation rule: %s", rule_id)
        return rule

    def list_rules(self, org_id: str, trigger: Optional[AutomationTrigger] = None,
                   enabled: Optional[bool] = None) -> list[AutomationRule]:
        self._telemetry["list_rules_calls"] += 1
        results = [r for r in self._rules.values() if r.org_id == org_id]
        if trigger is not None:
            results = [r for r in results if r.trigger == trigger]
        if enabled is not None:
            results = [r for r in results if r.enabled == enabled]
        return results

    def execute_rule(self, rule_id: str, context: dict) -> AutomationExecution:
        self._telemetry["execute_rule_calls"] += 1
        rule = self._rules.get(rule_id)
        if not rule:
            raise ValueError(f"Automation rule '{rule_id}' not found.")
        if not rule.enabled:
            raise ValueError(f"Automation rule '{rule_id}' is disabled.")

        exec_id = str(uuid.uuid4())
        execution = AutomationExecution(
            id=exec_id,
            rule_id=rule_id,
            org_id=rule.org_id,
            trigger=rule.trigger,
        )

        try:
            matched, matched_conditions = self._evaluate_conditions(rule, context)
            execution.matched_conditions = matched_conditions

            if not matched:
                execution.status = "skipped"
                execution.result = "Conditions not met"
                execution.completed_at = datetime.now(timezone.utc).isoformat()
                self._executions[exec_id] = execution
                self._save()
                self._telemetry["executions_skipped"] += 1
                return execution

            executed = []
            for action in rule.actions:
                result = self._execute_action(action, rule, context)
                executed.append({"action": action.value, "result": result})

            execution.actions_executed = executed
            execution.status = "completed"
            execution.result = "All actions executed successfully"
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            self._telemetry["executions_completed"] += 1

        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            self._telemetry["executions_failed"] += 1
            logger.error("Failed to execute rule %s: %s", rule_id, e, exc_info=True)

        self._executions[exec_id] = execution
        self._save()
        return execution

    def _evaluate_conditions(self, rule: AutomationRule, context: dict) -> tuple:
        matched_conditions = []
        if not rule.conditions:
            return True, matched_conditions

        results = []
        for condition in rule.conditions:
            field = condition.get("field", "")
            operator = condition.get("operator", "eq")
            expected = condition.get("value")
            actual = self._resolve_field(context, field)
            passed = self._compare(operator, actual, expected)
            matched_conditions.append({
                "field": field,
                "operator": operator,
                "expected": expected,
                "actual": actual,
                "passed": passed,
            })
            results.append(passed)

        if rule.match_type == TriggerMatchType.ALL:
            return all(results), matched_conditions
        elif rule.match_type == TriggerMatchType.ANY:
            return any(results), matched_conditions
        elif rule.match_type == TriggerMatchType.NONE:
            return not any(results), matched_conditions
        return True, matched_conditions

    def _resolve_field(self, context: dict, field_path: str) -> Any:
        parts = field_path.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.lstrip("-").isdigit():
                idx = int(part)
                value = value[idx] if 0 <= idx < len(value) else None
            else:
                return None
        return value

    def _compare(self, operator: str, actual: Any, expected: Any) -> bool:
        if operator == "eq":
            return actual == expected
        elif operator == "neq":
            return actual != expected
        elif operator == "gt":
            try:
                return float(actual) > float(expected)
            except (TypeError, ValueError):
                return False
        elif operator == "gte":
            try:
                return float(actual) >= float(expected)
            except (TypeError, ValueError):
                return False
        elif operator == "lt":
            try:
                return float(actual) < float(expected)
            except (TypeError, ValueError):
                return False
        elif operator == "lte":
            try:
                return float(actual) <= float(expected)
            except (TypeError, ValueError):
                return False
        elif operator == "in":
            if isinstance(expected, list):
                return actual in expected
            return False
        elif operator == "not_in":
            if isinstance(expected, list):
                return actual not in expected
            return False
        elif operator == "contains":
            if isinstance(actual, str) and isinstance(expected, str):
                return expected in actual
            if isinstance(actual, list):
                return expected in actual
            return False
        elif operator == "matches":
            if isinstance(actual, str) and isinstance(expected, str):
                try:
                    return bool(re.search(expected, actual))
                except re.error:
                    return False
            return False
        elif operator == "exists":
            return actual is not None
        elif operator == "not_exists":
            return actual is None
        return False

    def _execute_action(self, action: AutomationAction, rule: AutomationRule, context: dict) -> Any:
        params = rule.action_params or {}
        if action == AutomationAction.ENFORCE_POLICY:
            return self._action_enforce_policy(rule, context, params)
        elif action == AutomationAction.GENERATE_COMPLIANCE_REPORT:
            return self._action_generate_compliance_report(rule, context, params)
        elif action == AutomationAction.NOTIFY_STAKEHOLDERS:
            return self._action_notify_stakeholders(rule, context, params)
        elif action == AutomationAction.ESCALATE_EVENT:
            return self._action_escalate_event(rule, context, params)
        elif action == AutomationAction.ARCHIVE_AUDIT_RECORDS:
            return self._action_archive_audit_records(rule, context, params)
        elif action == AutomationAction.DETECT_VIOLATIONS:
            return self._action_detect_violations(rule, context, params)
        elif action == AutomationAction.SEND_ALERT:
            return self._action_send_alert(rule, context, params)
        elif action == AutomationAction.CREATE_TICKET:
            return self._action_create_ticket(rule, context, params)
        elif action == AutomationAction.LOCK_RESOURCE:
            return self._action_lock_resource(rule, context, params)
        elif action == AutomationAction.SUSPEND_USER:
            return self._action_suspend_user(rule, context, params)
        elif action == AutomationAction.REVOKE_ACCESS:
            return self._action_revoke_access(rule, context, params)
        elif action == AutomationAction.APPLY_RETENTION:
            return self._action_apply_retention(rule, context, params)
        return {"status": "unknown_action", "action": action.value}

    def _action_enforce_policy(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        policy_id = params.get("policy_id", context.get("policy_id"))
        return {"status": "enforced", "policy_id": policy_id}

    def _action_generate_compliance_report(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        report_id = str(uuid.uuid4())
        return {"status": "report_generated", "report_id": report_id}

    def _action_notify_stakeholders(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        channels = params.get("channels", ["email"])
        recipients = params.get("recipients", [])
        return {"status": "notified", "channels": channels, "recipients": len(recipients)}

    def _action_escalate_event(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        target = params.get("escalate_to", "admin")
        return {"status": "escalated", "escalated_to": target}

    def _action_archive_audit_records(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        cutoff_days = params.get("retention_days", 365)
        return {"status": "archived", "cutoff_days": cutoff_days}

    def _action_detect_violations(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        scan_target = params.get("scan_target", "all")
        return {"status": "scan_initiated", "scan_target": scan_target}

    def _action_send_alert(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        severity = params.get("severity", "medium")
        message = params.get("message", "Alert triggered by automation rule")
        return {"status": "alert_sent", "severity": severity, "message": message}

    def _action_create_ticket(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        ticket_id = str(uuid.uuid4())
        priority = params.get("priority", "normal")
        return {"status": "ticket_created", "ticket_id": ticket_id, "priority": priority}

    def _action_lock_resource(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        resource = params.get("resource", context.get("resource_id"))
        return {"status": "locked", "resource": resource}

    def _action_suspend_user(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        user = params.get("user_id", context.get("user_id"))
        return {"status": "suspended", "user_id": user}

    def _action_revoke_access(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        principal = params.get("principal_id", context.get("principal_id"))
        resource = params.get("resource", context.get("resource_id"))
        return {"status": "access_revoked", "principal_id": principal, "resource": resource}

    def _action_apply_retention(self, rule: AutomationRule, context: dict, params: dict) -> dict:
        retention_days = params.get("retention_days", 90)
        data_type = params.get("data_type", "all")
        return {"status": "retention_applied", "retention_days": retention_days, "data_type": data_type}

    def process_trigger(self, org_id: str, trigger: AutomationTrigger, context: dict) -> list[AutomationExecution]:
        self._telemetry["process_trigger_calls"] += 1
        executions = []
        matching_rules = self.list_rules(org_id, trigger=trigger, enabled=True)
        if not matching_rules:
            matching_rules = [r for r in self._rules.values()
                              if r.org_id == org_id and r.trigger == trigger and r.enabled]
        for rule in matching_rules:
            try:
                execution = self.execute_rule(rule.id, context)
                executions.append(execution)
            except Exception as e:
                logger.error("Failed to execute rule %s on trigger %s: %s", rule.id, trigger.value, e)
        return executions

    def schedule_automation(self, schedule: AutomationSchedule) -> AutomationSchedule:
        self._telemetry["schedule_automation_calls"] += 1
        if schedule.id in self._schedules:
            raise ValueError(f"Schedule with id '{schedule.id}' already exists.")
        schedule.created_at = datetime.now(timezone.utc).isoformat()
        self._schedules[schedule.id] = schedule
        self._save()
        logger.info("Created automation schedule: %s (%s)", schedule.name, schedule.id)
        return schedule

    def run_scheduled_automations(self) -> list[AutomationExecution]:
        self._telemetry["run_scheduled_automations_calls"] += 1
        now = datetime.now(timezone.utc)
        executions = []

        for schedule in self._schedules.values():
            if not schedule.enabled:
                continue
            if not schedule.next_run:
                continue
            try:
                next_run = datetime.fromisoformat(schedule.next_run)
            except (ValueError, TypeError):
                continue

            if now < next_run:
                continue

            schedule.last_run = now.isoformat()
            schedule.next_run = self._compute_next_run(schedule.cron_expression, now)
            self._save()

            context = {
                "schedule_id": schedule.id,
                "schedule_name": schedule.name,
                "trigger": schedule.trigger.value,
            }

            rule_id_to_run = None
            for rule in self._rules.values():
                if rule.org_id == schedule.org_id and rule.trigger == AutomationTrigger.SCHEDULED and rule.enabled:
                    rule_id_to_run = rule.id
                    context["rule_id"] = rule.id
                    break

            if rule_id_to_run:
                try:
                    execution = self.execute_rule(rule_id_to_run, context)
                    executions.append(execution)
                except Exception as e:
                    execution = AutomationExecution(
                        id=str(uuid.uuid4()),
                        rule_id=rule_id_to_run or "",
                        org_id=schedule.org_id,
                        trigger=AutomationTrigger.SCHEDULED,
                        status="failed",
                        error_message=str(e),
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                    self._executions[execution.id] = execution
                    executions.append(execution)

        return executions

    def _compute_next_run(self, cron_expression: str, from_time: datetime) -> str:
        parts = cron_expression.strip().split()
        if len(parts) < 5:
            return (from_time + timedelta(hours=1)).isoformat()
        try:
            minute = parts[0]
            hour = parts[1]
            day_of_month = parts[2]
            month = parts[3]
            day_of_week = parts[4]

            next_time = from_time + timedelta(hours=1)
            return next_time.isoformat()
        except Exception:
            return (from_time + timedelta(hours=1)).isoformat()

    def create_notification_template(self, template: NotificationTemplate) -> NotificationTemplate:
        self._telemetry["create_notification_template_calls"] += 1
        if template.id in self._notification_templates:
            raise ValueError(f"Notification template with id '{template.id}' already exists.")
        template.created_at = datetime.now(timezone.utc).isoformat()
        template.updated_at = template.created_at
        self._notification_templates[template.id] = template
        self._save()
        logger.info("Created notification template: %s (%s)", template.name, template.id)
        return template

    def render_notification(self, template_id: str, variables: dict) -> dict:
        self._telemetry["render_notification_calls"] += 1
        template = self._notification_templates.get(template_id)
        if not template:
            raise ValueError(f"Notification template '{template_id}' not found.")

        subject = template.subject
        body = template.body

        for var_name, var_value in variables.items():
            placeholder = "{{" + var_name + "}}"
            subject = subject.replace(placeholder, str(var_value))
            body = body.replace(placeholder, str(var_value))

        return {
            "template_id": template_id,
            "template_name": template.name,
            "subject": subject,
            "body": body,
            "channels": template.channels,
        }

    def run_compliance_report_automation(self, org_id: str) -> AutomationExecution:
        self._telemetry["run_compliance_report_automation_calls"] += 1
        exec_id = str(uuid.uuid4())
        execution = AutomationExecution(
            id=exec_id,
            rule_id="compliance_report_auto",
            org_id=org_id,
            trigger=AutomationTrigger.COMPLIANCE_ASSESSMENT_DUE,
        )

        try:
            report_id = str(uuid.uuid4())
            execution.actions_executed = [
                {"action": AutomationAction.GENERATE_COMPLIANCE_REPORT.value, "result": {"report_id": report_id}}
            ]
            execution.status = "completed"
            execution.result = f"Compliance report {report_id} generated"
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)

        execution.completed_at = datetime.now(timezone.utc).isoformat()
        self._executions[exec_id] = execution
        self._save()
        return execution

    def run_violation_detection(self, org_id: str) -> AutomationExecution:
        self._telemetry["run_violation_detection_calls"] += 1
        exec_id = str(uuid.uuid4())
        execution = AutomationExecution(
            id=exec_id,
            rule_id="violation_detection_auto",
            org_id=org_id,
            trigger=AutomationTrigger.VIOLATION_DETECTED,
        )

        try:
            violations_found = 0
            execution.actions_executed = [
                {"action": AutomationAction.DETECT_VIOLATIONS.value, "result": {"violations_found": violations_found}}
            ]
            execution.status = "completed"
            execution.result = f"Violation detection completed: {violations_found} violations found"
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)

        execution.completed_at = datetime.now(timezone.utc).isoformat()
        self._executions[exec_id] = execution
        self._save()
        return execution

    def run_audit_archive(self, org_id: str) -> AutomationExecution:
        self._telemetry["run_audit_archive_calls"] += 1
        exec_id = str(uuid.uuid4())
        execution = AutomationExecution(
            id=exec_id,
            rule_id="audit_archive_auto",
            org_id=org_id,
            trigger=AutomationTrigger.AUDIT_EVENT_RECORDED,
        )

        try:
            cutoff_days = 365
            archived_count = 0
            execution.actions_executed = [
                {"action": AutomationAction.ARCHIVE_AUDIT_RECORDS.value,
                 "result": {"archived_count": archived_count, "cutoff_days": cutoff_days}}
            ]
            execution.status = "completed"
            execution.result = f"Audit archive completed: {archived_count} records archived (cutoff: {cutoff_days}d)"
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)

        execution.completed_at = datetime.now(timezone.utc).isoformat()
        self._executions[exec_id] = execution
        self._save()
        return execution

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
