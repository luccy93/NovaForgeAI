import json
import uuid
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ApprovalType(Enum):
    SINGLE = "single"
    MULTI_LEVEL = "multi_level"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    DEPLOYMENT = "deployment"
    COMPLIANCE = "compliance"
    FINANCE = "finance"
    EXECUTIVE = "executive"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    CONDITIONALLY_APPROVED = "conditionally_approved"


class ApprovalRole(Enum):
    REVIEWER = "reviewer"
    APPROVER = "approver"
    SECURITY_OFFICER = "security_officer"
    COMPLIANCE_OFFICER = "compliance_officer"
    ARCHITECT = "architect"
    ENGINEERING_MANAGER = "engineering_manager"
    FINANCE_DIRECTOR = "finance_director"
    EXECUTIVE = "executive"
    ADMIN = "admin"


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ApprovalStep:
    id: str
    name: str
    role: ApprovalRole
    required_approvers: int = 1
    order: int = 0
    wait_for_previous: bool = True
    timeout_hours: int = 48
    escalation_after_hours: int = 24
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: list[str] = field(default_factory=list)
    approved_at: Optional[str] = None
    comments: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role"] = self.role.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalStep":
        data["role"] = ApprovalRole(data["role"])
        data["status"] = ApprovalStatus(data["status"])
        return cls(**data)


@dataclass
class ApprovalWorkflow:
    id: str
    org_id: str
    name: str
    description: str = ""
    type: ApprovalType = ApprovalType.SINGLE
    target_type: str = ""
    target_id: str = ""
    steps: list[ApprovalStep] = field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.PENDING
    current_step: int = 0
    initiated_by: str = ""
    initiated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        d["steps"] = [s.to_dict() for s in self.steps]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalWorkflow":
        data["type"] = ApprovalType(data["type"])
        data["status"] = ApprovalStatus(data["status"])
        data["steps"] = [ApprovalStep.from_dict(s) for s in data["steps"]]
        return cls(**data)


@dataclass
class ApprovalRequest:
    id: str
    workflow_id: str
    org_id: str
    requester: str
    target_type: str = ""
    target_id: str = ""
    reason: str = ""
    priority: NotificationPriority = NotificationPriority.MEDIUM
    status: ApprovalStatus = ApprovalStatus.PENDING
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    decision_notes: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRequest":
        data["priority"] = NotificationPriority(data["priority"])
        data["status"] = ApprovalStatus(data["status"])
        return cls(**data)


@dataclass
class ApprovalNotification:
    id: str
    request_id: str
    recipient: str
    role: ApprovalRole
    message: str = ""
    priority: NotificationPriority = NotificationPriority.MEDIUM
    sent_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    read_at: Optional[str] = None
    action_taken: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role"] = self.role.value
        d["priority"] = self.priority.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalNotification":
        data["role"] = ApprovalRole(data["role"])
        data["priority"] = NotificationPriority(data["priority"])
        return cls(**data)


@dataclass
class EscalationRule:
    id: str
    org_id: str
    name: str
    type: ApprovalType
    after_hours: int = 24
    escalate_to_role: ApprovalRole = ApprovalRole.APPROVER
    max_escalation_levels: int = 3
    notify_roles: list[ApprovalRole] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["escalate_to_role"] = self.escalate_to_role.value
        d["notify_roles"] = [r.value for r in self.notify_roles]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EscalationRule":
        data["type"] = ApprovalType(data["type"])
        data["escalate_to_role"] = ApprovalRole(data["escalate_to_role"])
        data["notify_roles"] = [ApprovalRole(r) for r in data["notify_roles"]]
        return cls(**data)


class ApprovalWorkflowEngine:
    def __init__(self, storage_dir: str = "approval_engine_data"):
        self.storage_dir = storage_dir
        self._workflows: dict[str, ApprovalWorkflow] = {}
        self._requests: dict[str, ApprovalRequest] = {}
        self._notifications: list[ApprovalNotification] = []
        self._escalation_rules: dict[str, EscalationRule] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _workflows_path(self) -> str:
        return os.path.join(self.storage_dir, "workflows.json")

    def _requests_path(self) -> str:
        return os.path.join(self.storage_dir, "requests.json")

    def _notifications_path(self) -> str:
        return os.path.join(self.storage_dir, "notifications.json")

    def _escalation_rules_path(self) -> str:
        return os.path.join(self.storage_dir, "escalation_rules.json")

    def _save(self) -> None:
        try:
            workflows_data = {wid: w.to_dict() for wid, w in self._workflows.items()}
            with open(self._workflows_path(), "w", encoding="utf-8") as f:
                json.dump(workflows_data, f, indent=2, default=str)

            requests_data = {rid: r.to_dict() for rid, r in self._requests.items()}
            with open(self._requests_path(), "w", encoding="utf-8") as f:
                json.dump(requests_data, f, indent=2, default=str)

            notifications_data = [n.to_dict() for n in self._notifications]
            with open(self._notifications_path(), "w", encoding="utf-8") as f:
                json.dump(notifications_data, f, indent=2, default=str)

            rules_data = {rid: r.to_dict() for rid, r in self._escalation_rules.items()}
            with open(self._escalation_rules_path(), "w", encoding="utf-8") as f:
                json.dump(rules_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save approval workflow engine data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._workflows_path()):
                with open(self._workflows_path(), "r", encoding="utf-8") as f:
                    workflows_data = json.load(f)
                for wid, data in workflows_data.items():
                    try:
                        self._workflows[wid] = ApprovalWorkflow.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed workflow %s: %s", wid, e)

            if os.path.exists(self._requests_path()):
                with open(self._requests_path(), "r", encoding="utf-8") as f:
                    requests_data = json.load(f)
                for rid, data in requests_data.items():
                    try:
                        self._requests[rid] = ApprovalRequest.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed request %s: %s", rid, e)

            if os.path.exists(self._notifications_path()):
                with open(self._notifications_path(), "r", encoding="utf-8") as f:
                    notifications_data = json.load(f)
                for ndata in notifications_data:
                    try:
                        self._notifications.append(ApprovalNotification.from_dict(ndata))
                    except Exception as e:
                        logger.warning("Skipping malformed notification: %s", e)

            if os.path.exists(self._escalation_rules_path()):
                with open(self._escalation_rules_path(), "r", encoding="utf-8") as f:
                    rules_data = json.load(f)
                for rid, data in rules_data.items():
                    try:
                        self._escalation_rules[rid] = EscalationRule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed escalation rule %s: %s", rid, e)
        except Exception as e:
            logger.error("Failed to load approval workflow engine data: %s", e, exc_info=True)

    def create_workflow(self, workflow: ApprovalWorkflow) -> ApprovalWorkflow:
        self._telemetry["create_workflow_calls"] += 1
        if workflow.id in self._workflows:
            raise ValueError(f"Workflow with id '{workflow.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        workflow.created_at = now
        workflow.initiated_at = now
        self._workflows[workflow.id] = workflow
        self._save()
        logger.info("Created approval workflow: %s (%s)", workflow.name, workflow.id)
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[ApprovalWorkflow]:
        self._telemetry["get_workflow_calls"] += 1
        return self._workflows.get(workflow_id)

    def list_workflows(self, org_id: Optional[str] = None, status: Optional[ApprovalStatus] = None, type: Optional[ApprovalType] = None) -> list[ApprovalWorkflow]:
        self._telemetry["list_workflows_calls"] += 1
        results = list(self._workflows.values())
        if org_id:
            results = [w for w in results if w.org_id == org_id]
        if status:
            results = [w for w in results if w.status == status]
        if type:
            results = [w for w in results if w.type == type]
        return results

    def submit_request(self, request: ApprovalRequest) -> ApprovalRequest:
        self._telemetry["submit_request_calls"] += 1
        if request.id in self._requests:
            raise ValueError(f"Request with id '{request.id}' already exists.")

        workflow = self._workflows.get(request.workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{request.workflow_id}' not found.")

        request.submitted_at = datetime.now(timezone.utc).isoformat()
        request.status = ApprovalStatus.PENDING
        self._requests[request.id] = request

        workflow.status = ApprovalStatus.PENDING
        workflow.current_step = 0
        if workflow.steps:
            workflow.steps[0].status = ApprovalStatus.PENDING

        notification = ApprovalNotification(
            id=str(uuid.uuid4()),
            request_id=request.id,
            recipient=request.requester,
            role=ApprovalRole.ADMIN,
            message=f"Request submitted for workflow '{workflow.name}'",
            priority=request.priority,
        )
        self._notifications.append(notification)

        self._save()
        logger.info("Submitted approval request %s for workflow %s", request.id, workflow.id)
        return request

    def approve_step(self, workflow_id: str, step_id: str, user: str, comments: str = "") -> Optional[ApprovalWorkflow]:
        self._telemetry["approve_step_calls"] += 1
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            logger.warning("Workflow not found: %s", workflow_id)
            return None

        current_step = None
        for step in workflow.steps:
            if step.id == step_id:
                current_step = step
                break

        if not current_step:
            logger.warning("Step %s not found in workflow %s", step_id, workflow_id)
            return None

        expected_step = workflow.steps[workflow.current_step] if workflow.current_step < len(workflow.steps) else None
        if expected_step and expected_step.id != step_id:
            logger.warning("Step %s is not the current active step (expected %s)", step_id, expected_step.id if expected_step else None)
            return None

        if user not in current_step.approved_by:
            current_step.approved_by.append(user)

        current_step.comments.append({
            "user": user,
            "comments": comments,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "approved",
        })

        if len(current_step.approved_by) >= current_step.required_approvers:
            current_step.status = ApprovalStatus.APPROVED
            current_step.approved_at = datetime.now(timezone.utc).isoformat()
            self._advance_workflow(workflow)

        notification = ApprovalNotification(
            id=str(uuid.uuid4()),
            request_id=workflow_id,
            recipient=user,
            role=current_step.role,
            message=f"Step '{current_step.name}' approved by {user}",
            priority=NotificationPriority.MEDIUM,
        )
        self._notifications.append(notification)

        self._save()
        logger.info("Step %s approved by %s in workflow %s", step_id, user, workflow_id)
        return workflow

    def reject_step(self, workflow_id: str, step_id: str, user: str, comments: str = "") -> Optional[ApprovalWorkflow]:
        self._telemetry["reject_step_calls"] += 1
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            logger.warning("Workflow not found: %s", workflow_id)
            return None

        current_step = None
        for step in workflow.steps:
            if step.id == step_id:
                current_step = step
                break

        if not current_step:
            logger.warning("Step %s not found in workflow %s", step_id, workflow_id)
            return None

        current_step.status = ApprovalStatus.REJECTED
        current_step.comments.append({
            "user": user,
            "comments": comments,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "rejected",
        })
        workflow.status = ApprovalStatus.REJECTED
        workflow.completed_at = datetime.now(timezone.utc).isoformat()

        notification = ApprovalNotification(
            id=str(uuid.uuid4()),
            request_id=workflow_id,
            recipient=user,
            role=current_step.role,
            message=f"Step '{current_step.name}' rejected by {user}",
            priority=NotificationPriority.HIGH,
        )
        self._notifications.append(notification)

        self._save()
        logger.info("Step %s rejected by %s in workflow %s", step_id, user, workflow_id)
        return workflow

    def _advance_workflow(self, workflow: ApprovalWorkflow) -> None:
        if workflow.current_step + 1 >= len(workflow.steps):
            workflow.status = ApprovalStatus.APPROVED
            workflow.completed_at = datetime.now(timezone.utc).isoformat()
            return

        next_idx = workflow.current_step + 1
        next_step = workflow.steps[next_idx]

        if next_step.wait_for_previous and workflow.steps[workflow.current_step].status != ApprovalStatus.APPROVED:
            return

        if workflow.type == ApprovalType.PARALLEL:
            for step in workflow.steps:
                if step.status == ApprovalStatus.PENDING:
                    step.status = ApprovalStatus.PENDING
            workflow.current_step = next_idx
        else:
            workflow.current_step = next_idx
            next_step.status = ApprovalStatus.PENDING

    def get_pending_requests(self, user_id: str, role: ApprovalRole) -> list[ApprovalRequest]:
        self._telemetry["get_pending_requests_calls"] += 1
        pending = []
        for request in self._requests.values():
            if request.status != ApprovalStatus.PENDING:
                continue
            workflow = self._workflows.get(request.workflow_id)
            if not workflow:
                continue
            if workflow.current_step < len(workflow.steps):
                step = workflow.steps[workflow.current_step]
                if step.role == role:
                    pending.append(request)
            elif workflow.status == ApprovalStatus.PENDING:
                pending.append(request)
        return pending

    def get_approval_history(self, org_id: str, days: int = 90) -> list[ApprovalWorkflow]:
        self._telemetry["get_approval_history_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = []
        for workflow in self._workflows.values():
            if workflow.org_id != org_id:
                continue
            try:
                initiated = datetime.fromisoformat(workflow.initiated_at)
                if initiated >= cutoff:
                    results.append(workflow)
            except (ValueError, TypeError):
                results.append(workflow)
        return results

    def check_escalation(self) -> list[ApprovalWorkflow]:
        self._telemetry["check_escalation_calls"] += 1
        escalated = []
        now = datetime.now(timezone.utc)

        for workflow in self._workflows.values():
            if workflow.status not in (ApprovalStatus.PENDING, ApprovalStatus.CONDITIONALLY_APPROVED):
                continue
            if workflow.current_step >= len(workflow.steps):
                continue

            step = workflow.steps[workflow.current_step]
            if step.status != ApprovalStatus.PENDING:
                continue

            try:
                step_created = datetime.fromisoformat(workflow.initiated_at)
            except (ValueError, TypeError):
                continue

            elapsed_hours = (now - step_created).total_seconds() / 3600

            if elapsed_hours >= step.timeout_hours:
                step.status = ApprovalStatus.EXPIRED
                workflow.status = ApprovalStatus.EXPIRED
                workflow.completed_at = now.isoformat()
                self._save()
                logger.info("Workflow %s step %s expired after %s hours", workflow.id, step.id, elapsed_hours)
                continue

            if elapsed_hours >= step.escalation_after_hours and step.status == ApprovalStatus.PENDING:
                for rule in self._escalation_rules.values():
                    if rule.org_id == workflow.org_id and rule.type == workflow.type and rule.enabled:
                        step.status = ApprovalStatus.ESCALATED
                        step.role = rule.escalate_to_role
                        workflow.status = ApprovalStatus.ESCALATED
                        escalated.append(workflow)

                        notification = ApprovalNotification(
                            id=str(uuid.uuid4()),
                            request_id=workflow.id,
                            recipient="",
                            role=rule.escalate_to_role,
                            message=f"Workflow '{workflow.name}' escalated after {elapsed_hours:.1f}h without approval",
                            priority=NotificationPriority.URGENT,
                        )
                        self._notifications.append(notification)
                        self._save()
                        logger.info("Workflow %s escalated to %s", workflow.id, rule.escalate_to_role.value)
                        break

        return escalated

    def calculate_approval_metrics(self, org_id: str) -> dict:
        self._telemetry["calculate_approval_metrics_calls"] += 1
        workflows = [w for w in self._workflows.values() if w.org_id == org_id]
        total = len(workflows)
        approved = sum(1 for w in workflows if w.status == ApprovalStatus.APPROVED)
        rejected = sum(1 for w in workflows if w.status == ApprovalStatus.REJECTED)
        expired = sum(1 for w in workflows if w.status == ApprovalStatus.EXPIRED)
        escalated = sum(1 for w in workflows if w.status == ApprovalStatus.ESCALATED)
        pending = sum(1 for w in workflows if w.status == ApprovalStatus.PENDING)

        approval_times = []
        for w in workflows:
            if w.status == ApprovalStatus.APPROVED and w.completed_at:
                try:
                    start = datetime.fromisoformat(w.initiated_at)
                    end = datetime.fromisoformat(w.completed_at)
                    approval_times.append((end - start).total_seconds() / 3600)
                except (ValueError, TypeError):
                    pass

        avg_approval_time_hours = sum(approval_times) / len(approval_times) if approval_times else 0.0
        approval_rate = (approved / total * 100) if total > 0 else 0.0
        rejection_rate = (rejected / total * 100) if total > 0 else 0.0
        escalation_rate = (escalated / total * 100) if total > 0 else 0.0

        type_breakdown = defaultdict(int)
        for w in workflows:
            type_breakdown[w.type.value] += 1

        return {
            "org_id": org_id,
            "total_workflows": total,
            "approved": approved,
            "rejected": rejected,
            "expired": expired,
            "escalated": escalated,
            "pending": pending,
            "approval_rate": round(approval_rate, 2),
            "rejection_rate": round(rejection_rate, 2),
            "escalation_rate": round(escalation_rate, 2),
            "avg_approval_time_hours": round(avg_approval_time_hours, 2),
            "type_breakdown": dict(type_breakdown),
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
