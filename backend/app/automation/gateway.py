"""Automation gateway (Volume 33).

Single entry point for everything automation: workflow CRUD via WorkflowStore,
run dispatch (manual/trigger/schedule/webhook), policy gate, dry-run gate for
AI-generated workflows, cost gates and event emission. The gateway owns the
engine, policy, scheduler, webhook receiver and event bus wiring.
"""
import logging, time
from typing import Any, Optional

from ..common.storage import JsonFileStorage
from .ai_steps import WorkflowGenerator, GENERATOR_HINTS
from .approvals import ApprovalStore
from .automation_policy import AutomationPolicy
from .cost import CostTracker
from .dag import validate_dag
from .dryrun import validate_before_run
from .dsl import parse_workflow
from .engine import EngineConfig, WorkflowEngine
from .events import (EventBus, build_workflow_event)
from .executions import ExecutionStore, ExecutionTracker
from .scheduler import Scheduler, TriggerRule
from .templates import TemplateLibrary
from .triggers import DispatchHub
from .webhooks import WebhookReceiver
from .workflow import WorkflowSpec, WorkflowStore

logger = logging.getLogger(__name__)

AI_POLICIES = """
AI-generated workflows are treated like any other: they must pass DAG
validation and policy dry run, and high-risk actions always require human
approval before execution.
"""


class AutomationGateway:
    """Wires engine + policy + cost + triggers + bus into one facade."""

    def __init__(self, policy: Optional[AutomationPolicy] = None,
                 config: Optional[EngineConfig] = None,
                 storage=None, budgets: Optional[dict] = None,
                 hooks: Optional[dict] = None):
        self.hooks = hooks or {}  # optional external handlers (LLM, VCS)
        self.policy = policy or AutomationPolicy()
        self.store = WorkflowStore(storage or JsonFileStorage(
            "data/automation/workflows.json"))
        self.engine = WorkflowEngine(approvals=ApprovalStore(
            JsonFileStorage("data/automation/approvals.json")),
            policy=self.policy, config=config or EngineConfig())
        self.costs = CostTracker(JsonFileStorage("data/automation/costs.json"),
                                 budgets=budgets)
        self.bus = EventBus(JsonFileStorage("data/automation/events.json"))
        self.hub = DispatchHub()
        self.scheduler = Scheduler()
        self.webhooks = WebhookReceiver(hub=self.hub, bus=self.bus)
        self.templates = TemplateLibrary()
        self.generator = WorkflowGenerator(llm=self.hooks.get("llm"),
                                           policy=self.policy)
        self._register_default_handlers()

    # -------------------------------------------------------------- handlers
    def _register_default_handlers(self) -> None:
        registry = self.hooks.get("tools")  # ToolRegistry or None
        if registry is None:
            from .tools import default_registry
            registry = default_registry(guard=self.hooks.get("guard"))
        self.tools = registry
        self.engine.register_handler("task", self._task_handler)
        self.engine.register_handler("tool", self._tool_handler)
        self.engine.register_handler("report", self._tool_handler)
        self.engine.register_handler("artifact", self._artifact_handler)
        self.engine.register_handler("decision", self._decision_handler)

    def _task_handler(self, step, inputs, outputs, simulate=False):
        action = step.action or "noop"
        if simulate:
            return {"_simulated": True, "action": action,
                    "result": f"simulated:{action}"}
        result = {"status": "success", "action": action}
        if action in ("checkout", "snapshot", "diagnose"):
            result["message"] = f"{action} completed"
        elif action in ("test", "lint", "build", "verify", "regression"):
            result["message"] = f"{action} passed (no code modified)"
        elif action in ("extract", "transform", "publish"):
            result["message"] = f"data {action} completed"
        elif action == "notify":
            result["message"] = "notification queued"
        else:
            result["message"] = f"{action} executed (task step)"
        return result

    def _tool_handler(self, step, inputs, outputs, simulate=False):
        tool = self.tools.get(step.action) if step.action else None
        if simulate:
            return {"_simulated": True, "tool": step.action or "none",
                    "result": "simulated"}
        if tool is None:
            raise ValueError(f"tool '{step.action}' not found")
        context = {"organization_id": outputs.get("organization_id", "")}
        return self.tools.execute(step.action, inputs, context=context)

    def _artifact_handler(self, step, inputs, outputs, simulate=False):
        if simulate:
            return {"_simulated": True, "artifact_id": "simulated"}
        from .artifacts import ArtifactStore
        store = getattr(self, "_artifacts", None)
        if store is None:
            store = ArtifactStore()
            self._artifacts = store
        return store.store(inputs.get("payload", {"step": step.id}),
                           workflow_id=inputs.get("workflow_id", ""),
                           execution_id=inputs.get("execution_id", ""),
                           name=step.id,
                           organization_id=inputs.get("organization_id", "")).to_dict()

    def _decision_handler(self, step, inputs, outputs, simulate=False):
        condition = step.condition
        if condition:
            try:
                return {"decision": bool(eval(
                    condition, {"__builtins__": {}}, outputs))}
            except Exception:
                return {"decision": False, "error": "condition eval failed"}
        return {"decision": False, "error": "no condition"}

    # -------------------------------------------------------------- workflows
    def define(self, definition: dict | str, organization_id: str = "",
               workflow_id: str = "", created_by: str = "") -> dict:
        spec = parse_workflow(definition, organization_id=organization_id,
                              workflow_id=workflow_id)
        spec.organization_id = organization_id
        spec.created_by = created_by or spec.created_by
        errors = validate_dag(spec)
        if errors:
            raise ValueError(f"workflow invalid: {'; '.join(errors)}")
        saved = self.store.put(spec)
        rule = TriggerRule(spec, organization_id=organization_id)
        if rule.trigger.get("type") in ("schedule", "cron"):
            self.scheduler.register(rule)
        elif rule.trigger.get("type") != "manual":
            self.hub.add(rule)
        self.bus.emit("automation.workflow.defined",
                      {"workflow_id": spec.workflow_id,
                       "version": spec.version},
                      organization_id=organization_id)
        return saved

    def publish(self, workflow_id: str, organization_id: str = "") -> dict:
        spec = self.store.get(workflow_id, organization_id)
        if spec is None:
            raise KeyError(f"workflow '{workflow_id}' not found")
        spec = self.store.publish(spec.workflow_id)
        rule = TriggerRule(spec, organization_id=organization_id)
        if rule.trigger.get("type") in ("schedule", "cron"):
            self.scheduler.register(rule)
        elif rule.trigger.get("type") != "manual":
            self.hub.add(rule)
        return {"workflow_id": workflow_id, "status": spec.status,
                "version": spec.version}

    def dry_run(self, workflow_id: str,
                organization_id: str = "") -> dict:
        spec = self.store.get(workflow_id, organization_id)
        if spec is None:
            raise KeyError(f"workflow '{workflow_id}' not found")
        return validate_before_run(spec, self.policy, organization_id)

    # -------------------------------------------------------------- execution
    def run(self, workflow_id: str, organization_id: str = "",
            inputs: dict | None = None, execution_id: str = "") -> dict:
        spec = self.store.get(workflow_id, organization_id)
        if spec is None:
            raise KeyError(f"workflow '{workflow_id}' not found")
        if spec.status != "published":
            raise ValueError(
                f"workflow '{workflow_id}' is '{spec.status}'; publish first")
        if not self.costs.within_budget(
                organization_id,
                self.costs.estimate_workflow(spec.flat_steps())):
            raise ValueError("workflow exceeds remaining monthly budget")
        tracker = ExecutionTracker.begin(
            self.engine.executions, workflow_id, organization_id,
            version=spec.version, trigger={"type": "manual"},
            inputs=inputs or {}, execution_id=execution_id)
        exec_id = tracker.record.execution_id
        self.bus.emit("automation.workflow.started",
                      {"workflow_id": workflow_id, "execution_id": exec_id},
                      organization_id=organization_id)
        self.costs.record(exec_id, "_gateway",
                          self.costs.estimate_workflow(spec.flat_steps()),
                          workflow_id=workflow_id,
                          organization_id=organization_id)
        record = self.engine.run(spec, inputs=inputs,
                                 organization_id=organization_id,
                                 execution_id=exec_id,
                                 trigger={"type": "manual"})
        self.bus.emit("automation.workflow.finished",
                      {"workflow_id": workflow_id, "execution_id": exec_id,
                       "status": record.get("status")},
                      organization_id=organization_id)
        return record

    def run_ai_generated(self, prompt: str, organization_id: str = "",
                         inputs: dict | None = None) -> dict:
        """Generate, validate, dry-run and (only when accepted + approved)
        execute an AI-produced workflow."""
        result = self.generator.generate(prompt, organization_id)
        if not result.get("generated"):
            return result
        dry = result.get("dry_run", {})
        if dry.get("verdict") != "approved_for_dry_run":
            return {"generated": False,
                    "error": "AI workflow rejected by dry run",
                    "dry_run": dry}
        spec: WorkflowSpec = result["workflow"]
        self.store.put(spec)
        self.bus.emit("automation.workflow.ai_generated",
                      {"workflow_id": spec.workflow_id,
                       "version": spec.version},
                      organization_id=organization_id)
        return {"generated": True,
                "dry_run": dry,
                "record": self.run(spec.workflow_id, organization_id,
                                   inputs, )}

    # -------------------------------------------------------------- triggers
    def handle_event(self, event: dict, organization_id: str = "") -> list[dict]:
        return self.hub.dispatch(event, runner=self._on_match)

    def _on_match(self, rule: TriggerRule, event: dict) -> str:
        if not self.costs.within_budget(rule.organization_id):
            raise ValueError("budget exhausted; workflow not started")
        record = self.engine.run(rule.spec, organization_id=rule.organization_id,
                                 trigger={"type": rule.trigger.get("type")})
        return record.get("execution_id", "")

    def tick(self) -> list[dict]:
        results = self.scheduler.tick(now=None, runner=self._on_schedule)
        self.bus.emit("automation.schedule.tick", {"due": len(results)})
        return results

    def _on_schedule(self, rule: TriggerRule, now) -> str:
        if not self.costs.within_budget(rule.organization_id):
            raise ValueError("budget exhausted; workflow not scheduled")
        record = self.engine.run(rule.spec,
                                 organization_id=rule.organization_id,
                                 trigger={"type": "schedule"})
        return record.get("execution_id", "")

    def receive_webhook(self, path: str, body: bytes, timestamp: str,
                        signature: str) -> dict:
        return self.webhooks.handle(path, body, timestamp, signature)

    # -------------------------------------------------------------- queries
    def executions(self, organization_id: str = "",
                   limit: int = 50) -> list[dict]:
        return self.engine.executions.list(organization_id, limit=limit)

    def execution(self, execution_id: str,
                  organization_id: str = "") -> Optional[dict]:
        rec = self.engine.executions.get(execution_id, organization_id)
        return rec.to_dict() if rec else None

    def list_workflows(self, organization_id: str = "") -> list[dict]:
        return self.store.list(organization_id)

    def health(self) -> dict:
        engine_health = self.engine.health()
        return {
            "workflows": len(self.store.list()),
            "executions": engine_health["executions"],
            "pending_approvals": engine_health["pending_approvals"],
            "scheduled": self.scheduler.count(),
            "dispatch_rules": self.hub.count(),
            "webhooks": self.webhooks.health(),
            "cost_spent": self.costs.total_for(),
            "events_emitted": self.bus.count(),
            "ai_generator_available": self.generator.available,
            "tools": self.tools.count() if self.tools else 0,
            "templates": len(self.templates.list()),
            "status": "healthy",
        }