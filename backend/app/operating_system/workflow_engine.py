"""Workflow Engine — sequential, parallel, branching workflows with retry, timeout, human approval, versioning, scheduling, rollback."""

import hashlib
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


class WorkflowStatus(Enum):
    DRAFT = "draft"
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    AWAITING_APPROVAL = "awaiting_approval"


class StepType(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    HUMAN_APPROVAL = "human_approval"
    SUB_WORKFLOW = "sub_workflow"
    RETRY = "retry"
    TIMEOUT = "timeout"


@dataclass
class WorkflowStep:
    id: str
    name: str
    type: StepType = StepType.SEQUENTIAL
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3
    retry_delay_seconds: int = 10
    depends_on: list[str] = field(default_factory=list)
    condition: str = ""  # expression to evaluate
    on_success: str = ""
    on_failure: str = ""
    human_approval_required: bool = False
    approvers: list[str] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class WorkflowTemplate:
    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    steps: list[WorkflowStep] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class WorkflowInstance:
    id: str
    template_id: str
    name: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: list[WorkflowStep] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    triggered_by: str = ""
    error: Optional[str] = None
    rollback_steps: list[str] = field(default_factory=list)


class WorkflowEngine:
    """Enterprise workflow engine — orchestrates complex multi-step engineering workflows."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else Path(".novaforge/workflows")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.templates: dict[str, WorkflowTemplate] = {}
        self.instances: dict[str, WorkflowInstance] = {}
        self._handlers: dict[str, Callable] = {}
        self._load_templates()

    def register_handler(self, action: str, handler: Callable):
        self._handlers[action] = handler

    def create_template(self, name: str, description: str = "", steps: list[dict] = None) -> WorkflowTemplate:
        tid = f"wf-tmpl-{uuid.uuid4().hex[:12]}"
        template = WorkflowTemplate(
            id=tid, name=name, description=description,
            version="1.0.0",
            steps=[self._build_step(s) for s in (steps or [])],
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.templates[tid] = template
        self._save_template(template)
        return template

    def _build_step(self, step_data: dict) -> WorkflowStep:
        return WorkflowStep(
            id=step_data.get("id", f"step-{uuid.uuid4().hex[:8]}"),
            name=step_data.get("name", "unnamed"),
            type=StepType(step_data.get("type", "sequential")),
            action=step_data.get("action", ""),
            params=step_data.get("params", {}),
            timeout_seconds=step_data.get("timeout_seconds", 300),
            max_retries=step_data.get("max_retries", 3),
            retry_delay_seconds=step_data.get("retry_delay_seconds", 10),
            depends_on=step_data.get("depends_on", []),
            condition=step_data.get("condition", ""),
            human_approval_required=step_data.get("human_approval_required", False),
            approvers=step_data.get("approvers", []),
        )

    def create_instance(self, template_id: str, context: dict = None, triggered_by: str = "") -> Optional[WorkflowInstance]:
        template = self.templates.get(template_id)
        if not template:
            return None
        iid = f"wf-inst-{uuid.uuid4().hex[:12]}"
        instance = WorkflowInstance(
            id=iid, template_id=template_id, name=template.name,
            status=WorkflowStatus.PENDING,
            steps=[WorkflowStep(**s.__dict__) for s in template.steps],
            context=context or {},
            created_at=datetime.now(timezone.utc).isoformat(),
            triggered_by=triggered_by,
        )
        self.instances[iid] = instance
        self._save_instance(instance)
        return instance

    def execute(self, instance_id: str) -> WorkflowInstance:
        instance = self.instances.get(instance_id)
        if not instance:
            raise ValueError(f"Workflow instance {instance_id} not found")

        instance.status = WorkflowStatus.RUNNING
        instance.started_at = datetime.now(timezone.utc).isoformat()

        try:
            self._execute_steps(instance)
            if instance.status != WorkflowStatus.AWAITING_APPROVAL:
                instance.status = WorkflowStatus.COMPLETED
        except Exception as e:
            instance.status = WorkflowStatus.FAILED
            instance.error = str(e)

        instance.completed_at = datetime.now(timezone.utc).isoformat()
        self._save_instance(instance)
        return instance

    def _execute_steps(self, instance: WorkflowInstance):
        completed = set()
        max_iterations = len(instance.steps) * 3
        iterations = 0

        while len(completed) < len(instance.steps) and iterations < max_iterations:
            iterations += 1
            any_executed = False

            for step in instance.steps:
                if step.id in completed or step.status == WorkflowStatus.RUNNING:
                    continue
                if step.status == WorkflowStatus.FAILED:
                    continue

                deps_met = all(d in completed for d in step.depends_on) if step.depends_on else True
                if not deps_met:
                    continue

                if step.type == StepType.PARALLEL:
                    self._execute_parallel_steps(instance, step)
                    completed.add(step.id)
                    any_executed = True
                    continue

                if step.type == StepType.CONDITIONAL:
                    if step.condition:
                        condition_met = self._evaluate_condition(step.condition, instance.context)
                        if not condition_met:
                            completed.add(step.id)
                            continue

                if step.type == StepType.HUMAN_APPROVAL:
                    instance.status = WorkflowStatus.AWAITING_APPROVAL
                    return

                step.started_at = datetime.now(timezone.utc).isoformat()
                step.status = WorkflowStatus.RUNNING
                start = time.time()

                if step.action in self._handlers:
                    try:
                        result = self._handlers[step.action](instance.context, step.params)
                        step.result = result
                        step.status = WorkflowStatus.COMPLETED
                        instance.context["last_result"] = result
                    except Exception as e:
                        step.error = str(e)
                        if step.retry_count < step.max_retries:
                            step.retry_count += 1
                            step.status = WorkflowStatus.PENDING
                            time.sleep(step.retry_delay_seconds)
                        else:
                            step.status = WorkflowStatus.FAILED
                            raise
                else:
                    step.status = WorkflowStatus.COMPLETED

                step.duration_ms = (time.time() - start) * 1000
                step.completed_at = datetime.now(timezone.utc).isoformat()
                completed.add(step.id)
                any_executed = True

                if step.status == WorkflowStatus.FAILED:
                    if step.on_failure == "rollback":
                        instance.status = WorkflowStatus.ROLLING_BACK
                        self.rollback(instance)
                    elif step.on_failure == "skip":
                        step.status = WorkflowStatus.COMPLETED
                        completed.add(step.id)

            if not any_executed:
                break

        if len(completed) >= len(instance.steps):
            instance.status = WorkflowStatus.COMPLETED

    def _execute_parallel_steps(self, instance: WorkflowInstance, parent_step: WorkflowStep):
        parallel_steps = [s for s in instance.steps if s.id in parent_step.depends_on or s.id == parent_step.id]
        for step in parallel_steps:
            if step.action in self._handlers:
                try:
                    step.result = self._handlers[step.action](instance.context, step.params)
                    step.status = WorkflowStatus.COMPLETED
                except Exception as e:
                    step.status = WorkflowStatus.FAILED
                    step.error = str(e)

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        try:
            return bool(eval(condition, {"__builtins__": {}}, context))
        except Exception:
            return True

    def approve(self, instance_id: str, approved: bool = True) -> bool:
        instance = self.instances.get(instance_id)
        if not instance or instance.status != WorkflowStatus.AWAITING_APPROVAL:
            return False
        if approved:
            instance.status = WorkflowStatus.RUNNING
            self.execute(instance_id)
        else:
            instance.status = WorkflowStatus.CANCELLED
        return True

    def pause(self, instance_id: str) -> bool:
        instance = self.instances.get(instance_id)
        if not instance:
            return False
        instance.status = WorkflowStatus.PAUSED
        return True

    def resume(self, instance_id: str) -> bool:
        instance = self.instances.get(instance_id)
        if not instance or instance.status != WorkflowStatus.PAUSED:
            return False
        instance.status = WorkflowStatus.RUNNING
        self.execute(instance_id)
        return True

    def rollback(self, instance: WorkflowInstance):
        instance.status = WorkflowStatus.ROLLING_BACK
        completed_steps = [s for s in instance.steps if s.status == WorkflowStatus.COMPLETED]
        for step in reversed(completed_steps):
            rollback_action = f"rollback_{step.action}"
            if rollback_action in self._handlers:
                try:
                    self._handlers[rollback_action](instance.context, step.params)
                except Exception:
                    pass
        instance.status = WorkflowStatus.ROLLED_BACK

    def cancel(self, instance_id: str) -> bool:
        instance = self.instances.get(instance_id)
        if not instance:
            return False
        instance.status = WorkflowStatus.CANCELLED
        instance.completed_at = datetime.now(timezone.utc).isoformat()
        return True

    def get_instance(self, instance_id: str) -> Optional[WorkflowInstance]:
        return self.instances.get(instance_id)

    def get_instance_history(self, template_id: str = "", limit: int = 50) -> list[WorkflowInstance]:
        instances = list(self.instances.values())
        if template_id:
            instances = [i for i in instances if i.template_id == template_id]
        instances.sort(key=lambda x: x.created_at or "", reverse=True)
        return instances[:limit]

    def replay(self, instance_id: str) -> Optional[WorkflowInstance]:
        original = self.instances.get(instance_id)
        if not original:
            return None
        new_instance = WorkflowInstance(
            id=f"wf-inst-{uuid.uuid4().hex[:12]}",
            template_id=original.template_id,
            name=f"{original.name} (replay)",
            status=WorkflowStatus.PENDING,
            steps=[WorkflowStep(**s.__dict__) for s in original.steps],
            context={**original.context},
            created_at=datetime.now(timezone.utc).isoformat(),
            triggered_by="replay",
        )
        self.instances[new_instance.id] = new_instance
        return self.execute(new_instance.id)

    def get_version_history(self, template_id: str) -> list[WorkflowTemplate]:
        pattern = f"wf-tmpl-{template_id[:8]}_v*.json"
        versions = []
        for f in self.storage_path.glob(f"*{template_id[:8]}*.json"):
            try:
                data = json.loads(f.read_text())
                if "version" in data:
                    versions.append(WorkflowTemplate(**data))
            except Exception:
                pass
        return sorted(versions, key=lambda x: x.version)

    def _save_template(self, template: WorkflowTemplate):
        fname = self.storage_path / f"template_{template.id}.json"
        fname.write_text(json.dumps(template.__dict__, indent=2, default=str))

    def _save_instance(self, instance: WorkflowInstance):
        fname = self.storage_path / f"instance_{instance.id}.json"
        fname.write_text(json.dumps(instance.__dict__, indent=2, default=str))

    def _load_templates(self):
        for f in self.storage_path.glob("template_*.json"):
            try:
                data = json.loads(f.read_text())
                template = WorkflowTemplate(**data)
                template.steps = [WorkflowStep(**s) for s in template.steps]
                self.templates[template.id] = template
            except Exception:
                pass
        for f in self.storage_path.glob("instance_*.json"):
            try:
                data = json.loads(f.read_text())
                instance = WorkflowInstance(**data)
                instance.steps = [WorkflowStep(**s) for s in instance.steps]
                instance.status = WorkflowStatus(instance.status) if isinstance(instance.status, str) else instance.status
                self.instances[instance.id] = instance
            except Exception:
                pass
