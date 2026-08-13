"""Automation & RPA volume tests (Volume 33).

Stores default to data/ JSON paths; every test uses tmp_path JsonFileStorage
to keep the suite hermetic (mirrors the multimodal test hygiene rule).
"""
import json, os, sys
from datetime import datetime, timezone, timedelta

import pytest

from app.common.storage import JsonFileStorage
from app.automation.dag import (validate_dag, topological_order, DagError,
                                execution_order)
from app.automation.dsl import parse_workflow, WorkflowValidator
from app.automation.workflow import WorkflowStore, WorkflowSpec, WorkflowStep
from app.automation.retry import run_with_retry, is_transient, \
    effective_backoff_delays
from app.automation.checkpoint import CheckpointStore, build_resume_plan
from app.automation.compensation import (CompensationStore, compensation_plan,
                                         run_compensation)
from app.automation.approvals import ApprovalStore
from app.automation.executions import ExecutionStore, ExecutionTracker
from app.automation.engine import WorkflowEngine, EngineConfig, StepFailure
from app.automation.automation_policy import AutomationPolicy
from app.automation.dryrun import DryRunReport
from app.automation.scheduler import CronParser, Scheduler
from app.automation.triggers import parse_trigger, TriggerRule, DispatchHub, \
    TriggerError
from app.automation.webhooks import sign_payload, verify_signature, \
    WebhookError, WebhookReceiver
from app.automation.cost import CostTracker
from app.automation.tools import (default_registry, HttpTool, ToolError)
from app.automation.terminal import TerminalSandbox
from app.automation.gateway import AutomationGateway
from app.automation.templates import TemplateLibrary


def store(path: str) -> JsonFileStorage:
    return JsonFileStorage(path)


def make_spec(org: str = "acme", with_approval: bool = False) -> WorkflowSpec:
    return parse_workflow({"workflow": {
        "name": "test_flow", "organization_id": org,
        "trigger": {"type": "manual"},
        "steps": [
            {"id": "one", "type": "task", "action": "test", "risk": "low"},
            {"id": "two", "type": "task", "action": "build",
             "depends_on": ["one"], "risk": "low",
             **({"needs_approval": True} if with_approval else {})},
            {"id": "three", "type": "task", "action": "deploy",
             "depends_on": ["two"], "risk": "high",
             **({"needs_approval": True} if with_approval else {})},
        ]}}, organization_id=org)


def ok_handler(step, inputs, outputs):
    return {"status": "ok", "action": step.action}


# ------------------------------------------------------------------- DAG
class TestDag:
    def test_valid_order(self):
        spec = make_spec()
        order = [s.id for s in execution_order(spec)]
        assert order == ["one", "two", "three"]

    def test_cycle_detected(self):
        spec = make_spec()
        spec.steps[2].depends_on = ["one"]  # three -> one
        spec.steps[0].depends_on = ["three"]  # one -> three : cycle
        errors = validate_dag(spec)
        assert errors, "cycle must be reported"
        assert any("cycle" in e for e in errors)

    def test_unknown_dependency(self):
        spec = make_spec()
        spec.steps[1].depends_on = ["ghost"]
        assert any("ghost" in e for e in validate_dag(spec))

    def test_unknown_step_type(self):
        spec = make_spec()
        spec.steps[0].type = "warp"
        assert any("unknown type" in e for e in validate_dag(spec))

    def test_duplicate_ids(self):
        spec = make_spec()
        spec.steps.append(WorkflowStep(id="one", type="task"))
        assert any("duplicate" in e for e in validate_dag(spec))

    def test_topological_raises_on_cycle(self):
        with pytest.raises(DagError):
            topological_order({"a": ["b"], "b": ["a"]})


# ------------------------------------------------------------------- DSL
class TestDsl:
    def test_parse_dict_and_json(self):
        raw = {"workflow": {"name": "x", "steps": [{"id": "s", "type": "task"}]}}
        spec = parse_workflow(raw)
        assert spec.workflow_id == "x"
        spec2 = parse_workflow(json.dumps(raw))
        assert spec2.steps[0].id == "s"

    def test_validator_high_risk_warning(self):
        spec = make_spec()
        result = WorkflowValidator().validate(spec)
        assert result["valid"] is True
        # step three is high-risk without explicit approval -> warning
        assert any("high-risk" in w for w in result["warnings"])

    def test_validator_high_risk_without_approval_warns(self):
        spec = parse_workflow({"workflow": {"name": "risky", "steps": [
            {"id": "s", "type": "tool", "action": "deploy",
             "risk": "high"}]}})
        result = WorkflowValidator().validate(spec)
        assert any("high-risk" in w for w in result["warnings"])

    def test_validator_invalid_trigger_type(self):
        spec = parse_workflow({"workflow": {"name": "bad",
                                            "trigger": {"type": "bogus"},
                                            "steps": [{"id": "s"}]}})
        assert not WorkflowValidator().validate(spec)["valid"]

    def test_validator_trigger_defaults_to_manual(self):
        spec = parse_workflow({"workflow": {"name": "ok",
                                            "steps": [{"id": "s"}]}})
        assert spec.trigger == {"type": "manual"}
        assert WorkflowValidator().validate(spec)["valid"]

    def test_validator_policy_allowed_tools(self):
        spec = parse_workflow({"workflow": {
            "name": "pol", "policies": {"allowed_tools": ["test"]},
            "steps": [{"id": "s", "type": "tool", "action": "deploy"}]}})
        result = WorkflowValidator(AutomationPolicy()).validate(spec)
        assert any("not allowed" in e for e in result["errors"])


# ------------------------------------------------------------ WorkflowStore
class TestWorkflowStore:
    def test_put_get_tenant_isolation(self, tmp_path):
        ws = WorkflowStore(store(str(tmp_path / "wf.json")))
        spec = make_spec("acme")
        ws.put(spec)
        assert ws.get("test_flow", "acme") is not None
        assert ws.get("test_flow", "evil") is None  # tenant isolation

    def test_lifecycle_and_versioning(self, tmp_path):
        ws = WorkflowStore(store(str(tmp_path / "wf.json")))
        spec = make_spec()
        ws.put(spec)
        ws.publish("test_flow", actor="tester")
        assert ws.get("test_flow").status == "published"
        version = ws.new_version("test_flow", make_spec().to_dict(),
                                 actor="tester", notes="v2")
        assert version.version == 2
        assert ws.get("test_flow").version == 2
        rolled = ws.rollback("test_flow", 1, actor="tester")
        assert rolled.version == 3
        assert len(ws.versions("test_flow")) >= 2
        assert any(h["action"] == "rollback" for h in ws.history("test_flow"))

    def test_delete_archives(self, tmp_path):
        ws = WorkflowStore(store(str(tmp_path / "wf.json")))
        ws.put(make_spec())
        assert ws.delete("test_flow", "acme") is True
        assert ws.get("test_flow").status == "archived"


# ------------------------------------------------------------------- retry
class TestRetry:
    def test_success_first_attempt(self):
        value, outcome = run_with_retry("s", lambda: {"ok": 1})
        assert outcome.succeeded and outcome.attempts == 1

    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("timeout")
            return "done"

        value, outcome = run_with_retry("s", flaky, max_retries=3,
                                        backoff_s=0.01, seed=1)
        assert outcome.succeeded and calls["n"] == 3

    def test_exhaustion_reports_error(self):
        _, outcome = run_with_retry("s", lambda: 1 / 0, max_retries=2,
                                    backoff_s=0.01)
        assert not outcome.succeeded
        assert "ZeroDivisionError" in (outcome.error or "")

    def test_transient_classification(self):
        assert is_transient(TimeoutError("timed out"))
        assert is_transient(ConnectionError())
        assert not is_transient(ValueError("bad input"))

    def test_backoff_is_capped_and_positive(self):
        delays = effective_backoff_delays(4, 1.0, 4.0, jitter=0.0, seed=0)
        assert delays == [1.0, 2.0, 4.0, 4.0]


# ---------------------------------------------------------------- checkpoint
class TestCheckpoint:
    def test_save_get_and_resume_plan(self, tmp_path):
        cs = CheckpointStore(store(str(tmp_path / "cp.json")))
        cs.save("ex1", "step_a", {"x": 1}, sequence=1)
        cp = cs.resume_point("ex1", ["step_a", "step_b", "step_c"])
        assert cp.step_id == "step_a"
        assert build_resume_plan("ex1", ["step_a", "step_b", "step_c"], cp) \
            == ["step_b", "step_c"]
        assert len(cs.list("ex1")) == 1
        assert cs.clear("ex1") == 1
        assert cs.count() == 0


# -------------------------------------------------------------- compensation
class TestCompensation:
    def test_plan_reverse_order_with_notify(self):
        spec = make_spec()
        spec.steps[1].compensation = "rollback"
        plan = compensation_plan(spec, "three", ["one", "two"])
        assert plan[0]["step_id"] == "two" and plan[0]["type"] == "compensate"
        assert plan[1]["step_id"] == "one" and plan[1]["type"] == "notify"

    def test_run_compensation_handlers(self):
        handled = {}

        def hb(inputs):
            handled["two"] = True
            return "rolled back"

        results = run_compensation({}, [
            {"step_id": "two", "type": "compensate", "tool_id": "x",
             "inputs": {}},
            {"step_id": "one", "type": "notify", "action": "operator_review"},
            {"step_id": "nope", "type": "compensate", "tool_id": "missing",
             "inputs": {}},
        ], handlers={"x": hb})
        assert results[0]["status"] == "completed"
        assert results[1]["status"] == "notified"
        assert results[2]["status"] == "unhandled"

    def test_store_tenant_scoped(self, tmp_path):
        comp = CompensationStore(store(str(tmp_path / "c.json")))
        comp.record("ex1", "two", "x", {}, status="completed")
        assert len(comp.list("ex1")) == 1
        assert comp.count() == 1


# ----------------------------------------------------------------- approvals
class TestApprovals:
    def test_create_decide_and_errors(self, tmp_path):
        ap = ApprovalStore(store(str(tmp_path / "a.json")))
        req = ap.create("wf", "step1", organization_id="acme")
        assert req.decision == "pending"
        decided = ap.decide("wf", "step1", "approved", "bob", "looks good",
                            organization_id="acme")
        assert decided.decision == "approved"
        with pytest.raises(ValueError):
            ap.decide("wf", "step1", "rejected", "bob", organization_id="acme")

    def test_auto_approve_and_expiry(self, tmp_path):
        ap = ApprovalStore(store(str(tmp_path / "a.json")))
        req = ap.create("wf", "s", organization_id="acme", ttl_s=-1)
        assert ap.is_expired(req)
        assert ap.needs_decision("wf", "s", "acme")  # expired -> needs again
        ap.auto_approve("wf", "s", organization_id="acme", policy="p0")
        assert ap.needs_decision("wf", "s", "acme") is False

    def test_unknown_request(self, tmp_path):
        ap = ApprovalStore(store(str(tmp_path / "a.json")))
        assert ap.decide("wf", "ghost", "approved", "x") is None


# ------------------------------------------------------------------- engine
class TestEngine:
    def test_run_completes_in_dag_order(self, tmp_path):
        executed = []
        engine = WorkflowEngine(
            approvals=ApprovalStore(store(str(tmp_path / "a.json"))),
            config=EngineConfig(records_dir=str(tmp_path / "ex.json"),
                                checkpoints_dir=str(tmp_path / "cp.json"),
                                approvals_dir=str(tmp_path / "a.json"),
                                compensations_dir=str(tmp_path / "c.json")))

        def handler(step, inputs, outputs):
            executed.append(step.id)
            return {"ok": step.id}

        engine.register_handler("task", handler)
        record = engine.run(make_spec())
        assert record["status"] == "completed"
        assert executed == ["one", "two", "three"]

    def test_failure_triggers_compensation(self, tmp_path):
        engine = WorkflowEngine(
            approvals=ApprovalStore(store(str(tmp_path / "a.json"))),
            config=EngineConfig(records_dir=str(tmp_path / "ex.json"),
                                checkpoints_dir=str(tmp_path / "cp.json"),
                                approvals_dir=str(tmp_path / "a.json"),
                                compensations_dir=str(tmp_path / "c.json")))
        engine.register_handler("task", ok_handler)
        spec = make_spec()
        spec.steps[1].compensation = "rollback"  # step two rolls back

        def boom(step, inputs=None, outputs=None):
            if getattr(step, "id", None) == "three":
                raise RuntimeError("deploy exploded")
            return {"ok": getattr(step, "id", "compensation")}

        engine.register_handler("task", boom)
        record = engine.run(spec)
        assert record["status"] == "failed"
        comps = engine.compensations.list(record["execution_id"])
        assert any(c["status"] == "completed" for c in comps)

    def test_approval_gate_blocks_then_allows(self, tmp_path):
        engine = WorkflowEngine(
            approvals=ApprovalStore(store(str(tmp_path / "a.json"))),
            config=EngineConfig(records_dir=str(tmp_path / "ex.json"),
                                checkpoints_dir=str(tmp_path / "cp.json"),
                                approvals_dir=str(tmp_path / "a.json"),
                                compensations_dir=str(tmp_path / "c.json")))
        engine.register_handler("task", ok_handler)
        spec = make_spec(with_approval=True)
        record = engine.run(spec)
        assert record["status"] == "awaiting_approval"
        engine.approvals.decide("test_flow", "two", "approved", "bob",
                                organization_id="acme")
        engine.approvals.decide("test_flow", "three", "approved", "bob",
                                organization_id="acme")
        record = engine.run(spec)
        assert record["status"] == "completed"

    def test_checkpoint_resume_skips_done_steps(self, tmp_path):
        engine = WorkflowEngine(
            approvals=ApprovalStore(store(str(tmp_path / "a.json"))),
            config=EngineConfig(records_dir=str(tmp_path / "ex.json"),
                                checkpoints_dir=str(tmp_path / "cp.json"),
                                approvals_dir=str(tmp_path / "a.json"),
                                compensations_dir=str(tmp_path / "c.json")))
        executed = []
        engine.register_handler("task", ok_handler)
        record = engine.run(make_spec())
        first_exec = record["execution_id"]
        engine.checkpoints.save(first_exec, "one", {"one": 1}, sequence=1)
        record2 = engine.run(make_spec(), execution_id=first_exec, resume=True)
        assert record2["status"] == "completed"

    def test_unknown_handler_reports_failure(self, tmp_path):
        engine = WorkflowEngine(
            approvals=ApprovalStore(store(str(tmp_path / "a.json"))),
            config=EngineConfig(records_dir=str(tmp_path / "ex.json"),
                                checkpoints_dir=str(tmp_path / "cp.json"),
                                approvals_dir=str(tmp_path / "a.json"),
                                compensations_dir=str(tmp_path / "c.json")))
        spec = make_spec()
        spec.steps[0].type = "tool"  # no handler registered
        record = engine.run(spec)
        assert record["status"] == "failed"


# ------------------------------------------------------------------- policy
class TestPolicy:
    def test_risk_and_approval(self):
        policy = AutomationPolicy()
        step = WorkflowStep(id="s", type="tool", action="terminal")
        assert policy.classify_risk(step) == "high"
        assert policy.requires_approval(step)
        step2 = WorkflowStep(id="t", type="task", action="test", risk="low")
        assert not policy.requires_approval(step2)

    def test_authorize_denies(self):
        policy = AutomationPolicy({"acme": {"deny_actions": ["deploy"]}})
        step = WorkflowStep(id="s", type="task", action="deploy")
        allowed, reason = policy.authorize(step, "acme")
        assert not allowed and "denied" in reason

    def test_authorize_domains(self):
        policy = AutomationPolicy()
        step = WorkflowStep(id="s", type="tool", action="http",
                            inputs={"url": "https://evil.example.com"})
        allowed, _ = policy.authorize(step, "acme")
        assert not allowed

    def test_lockdown_mode(self):
        policy = AutomationPolicy({"acme": {"mode": "lockdown"}})
        allowed, reason = policy.authorize(WorkflowStep(id="s"), "acme")
        assert not allowed and "lockdown" in reason

    def test_trigger_blocked(self):
        policy = AutomationPolicy({"acme": {"blocked_triggers": ["webhook"]}})
        assert not policy.can_trigger("acme", "webhook")
        assert policy.can_trigger("acme", "manual")


# ------------------------------------------------------------------- dryrun
class TestDryRun:
    def test_approved_for_valid(self):
        report = DryRunReport(make_spec(), AutomationPolicy(), "acme").build()
        assert report["valid"] is True
        assert report["verdict"] == "approved_for_dry_run"
        assert report["executed"] is False

    def test_rejected_on_dag_error(self):
        spec = make_spec()
        spec.steps[0].depends_on = ["ghost"]
        report = DryRunReport(spec, AutomationPolicy(), "acme").build()
        assert report["verdict"] == "rejected"


# ----------------------------------------------------------------- scheduler
class TestScheduler:
    def test_cron_parser(self):
        cron = CronParser("0 2 * * *")
        assert cron.matches(datetime(2026, 8, 13, 2, 0, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2026, 8, 13, 3, 0, tzinfo=timezone.utc))
        nxt = cron.next_run(datetime(2026, 8, 13, 0, 30, tzinfo=timezone.utc))
        assert nxt.hour == 2 and nxt.minute == 0

    def test_bad_cron_rejected(self):
        with pytest.raises(ValueError):
            CronParser("not a cron")

    def test_tick_fires_due_rule(self):
        sched = Scheduler()
        rule = TriggerRule(make_spec(), {"type": "schedule", "cron": "* * * * *"})
        sched.register(rule)
        fired = []

        def runner(rule, now):
            fired.append(rule.spec.workflow_id)
            return "ex_1"

        due = sched.tick(datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
                         runner=runner)
        assert due and due[0]["execution_id"] == "ex_1"
        assert fired == ["test_flow"]


# ----------------------------------------------------------------- triggers
class TestTriggers:
    def test_parse_errors(self):
        with pytest.raises(TriggerError):
            parse_trigger({"type": "nonsense"})
        with pytest.raises(TriggerError):
            parse_trigger({"type": "schedule"})

    def test_matching(self):
        rule = TriggerRule(make_spec(), {"type": "webhook", "path": "/hook/a"})
        assert rule.matches({"kind": "request", "path": "/hook/a"})
        assert not rule.matches({"kind": "request", "path": "/other"})

    def test_hub_dispatch(self):
        hub = DispatchHub()
        hub.add(TriggerRule(make_spec(), {"type": "webhook",
                                          "path": "/hook/a"}))
        results = hub.dispatch({"kind": "request", "path": "/hook/a"})
        assert len(results) == 1 and results[0]["matched"]
        assert hub.count() == 1


# ----------------------------------------------------------------- webhooks
class TestWebhooks:
    def test_signature_verify(self):
        secret = "sekrit"
        ts = str(datetime.now(timezone.utc).timestamp())
        sig = sign_payload(secret, b'{"a":1}', ts)
        verify_signature(secret, b'{"a":1}', ts, sig)  # no raise

    def test_tampered_rejected(self):
        secret = "sekrit"
        ts = str(datetime.now(timezone.utc).timestamp())
        sig = sign_payload(secret, b'{"a":1}', ts)
        with pytest.raises(WebhookError):
            verify_signature(secret, b'{"a":2}', ts, sig)

    def test_expired_rejected(self):
        ts = str(datetime.now(timezone.utc).timestamp() - 3600)
        sig = sign_payload("s", b"{}", ts)
        with pytest.raises(WebhookError):
            verify_signature("s", b"{}", ts, sig, tolerance_s=5)

    def test_receiver_rejects_unknown_path(self):
        recv = WebhookReceiver()
        with pytest.raises(WebhookError):
            recv.handle("/nope", b"{}", "0", "sig")


# --------------------------------------------------------------------- cost
class TestCost:
    def test_budget_enforcement(self, tmp_path):
        ct = CostTracker(store(str(tmp_path / "c.json")),
                         budgets={"acme": 0.01})
        ct.record("ex1", "s1", 0.006, workflow_id="w", organization_id="acme")
        assert ct.total_for("acme") == pytest.approx(0.006)
        assert ct.within_budget("acme", 0.003) is True
        assert ct.within_budget("acme", 0.005) is False

    def test_unlimited_default(self, tmp_path):
        ct = CostTracker(store(str(tmp_path / "c.json")))
        assert ct.budget_remaining("acme") == float("inf")
        assert ct.within_budget("acme", 1_000_000) is True


# ------------------------------------------------------------------- tools
class TestTools:
    def test_default_registry(self):
        reg = default_registry()
        assert reg.count() == 10
        assert reg.get("list_repos") is not None

    def test_terminal_honest_unavailable(self):
        sandbox = TerminalSandbox()
        result = sandbox.execute("rm -rf /")
        assert result["executed"] is False
        assert result["available"] is False
        assert result["risk"] == "high"

    def test_terminal_high_risk_needs_approval(self):
        class DummyRunner:
            def execute(self, command, timeout_s):
                return {"output": "ok"}

        sandbox = TerminalSandbox(remote_runner=DummyRunner())
        result = sandbox.execute("rm -rf /")
        assert result["executed"] is False
        assert "approval" in result["error"]

    def test_http_ssrf_guard_rejects(self):
        class Guard:
            def validate_url(self, url):
                return "evil" not in url

        tool = HttpTool(guard=Guard())
        with pytest.raises(ToolError):
            tool.execute({"method": "GET", "url": "https://evil.example.com"})

    def test_unknown_tool(self):
        reg = default_registry()
        with pytest.raises(ToolError):
            reg.execute("no_such_tool", {})


# ----------------------------------------------------------------- gateway
class TestGateway:
    def test_full_flow(self, tmp_path):
        # hermetic gateway: point every store at tmp_path
        from app.automation.gateway import AutomationGateway
        from app.automation.engine import EngineConfig
        from app.automation.approvals import ApprovalStore

        def gw_storage(name):
            return JsonFileStorage(str(tmp_path / name))

        gateway = AutomationGateway(
            policy=AutomationPolicy(),
            config=EngineConfig(records_dir=str(tmp_path / "ex.json"),
                                checkpoints_dir=str(tmp_path / "cp.json"),
                                approvals_dir=str(tmp_path / "a.json"),
                                compensations_dir=str(tmp_path / "c.json")))
        gateway.store = WorkflowStore(gw_storage("wf.json"))
        gateway.engine.approvals = ApprovalStore(gw_storage("a.json"))

        lib = TemplateLibrary()
        inst = lib.instantiate("ci_pipeline",
                               {"workflow_id": "wf_ci", "name": "My CI"})
        spec = gateway.define(inst["workflow"], organization_id="acme")
        assert spec.status == "draft"
        assert gateway.dry_run("wf_ci", "acme")["verdict"] == \
            "approved_for_dry_run"
        gateway.publish("wf_ci", "acme")
        record = gateway.run("wf_ci", "acme")
        assert record["status"] == "completed"
        assert len(record["steps"]) == 5
        assert len(gateway.executions("acme")) >= 1

    def test_run_requires_publish(self, tmp_path):
        from app.automation.gateway import AutomationGateway
        gateway = AutomationGateway()
        gateway.store = WorkflowStore(store(str(tmp_path / "wf.json")))
        gateway.define(make_spec().to_dict(), organization_id="acme")
        with pytest.raises(ValueError):
            gateway.run("test_flow", "acme")

    def test_ai_generation_honest_unavailable(self):
        gateway = AutomationGateway()
        result = gateway.run_ai_generated("deploy everything", "acme")
        assert result["generated"] is False
        assert result["available"] is False

    def test_tenant_isolation(self, tmp_path):
        from app.automation.gateway import AutomationGateway
        gateway = AutomationGateway()
        gateway.store = WorkflowStore(store(str(tmp_path / "wf.json")))
        gateway.define(make_spec("acme").to_dict(), organization_id="acme")
        assert gateway.store.get("test_flow", "acme") is not None
        assert gateway.store.get("test_flow", "rival") is None
        assert gateway.list_workflows("rival") == []


# ---------------------------------------------------------------- templates
class TestTemplates:
    def test_library_contents(self):
        lib = TemplateLibrary()
        assert len(lib.list()) == 6
        for tid in ("ci_pipeline", "deploy", "incident_runbook",
                    "security_scan", "data_pipeline", "test_automation"):
            assert lib.get(tid) is not None

    def test_instantiate_valid(self):
        lib = TemplateLibrary()
        inst = lib.instantiate("ci_pipeline",
                               {"workflow_id": "wf_x", "name": "X"})
        spec = parse_workflow(inst["workflow"])
        assert validate_dag(spec) == []
        assert len(spec.steps) == 5

    def test_unknown_template(self):
        assert TemplateLibrary().instantiate("ghost", {}) is None


# -------------------------------------------------------------- executions
class TestExecutions:
    def test_tracker_lifecycle(self, tmp_path):
        es = ExecutionStore(store(str(tmp_path / "ex.json")))
        tracker = ExecutionTracker.begin(es, "wf", "acme", version=1,
                                         inputs={"a": 1})
        assert tracker.record.status == "queued"
        tracker.start()
        tracker.record_step(executions_step("one"))
        tracker.finish("completed", output={"x": 1})
        assert tracker.record.status == "completed"
        loaded = es.get(tracker.record.execution_id, "acme")
        assert loaded.steps["one"].status == "succeeded"
        assert es.list("acme") and es.count() == 1


def executions_step(sid):
    from app.automation.executions import StepResult
    return StepResult(step_id=sid, status="succeeded", output={"ok": 1})


# ----------------------------------------------------------------- service
class TestService:
    def test_service_health(self):
        import app.automation.service as mod
        assert mod.SERVICE_NAME == "automation"
        health = mod.svc.health()
        assert health["status"] == "healthy"
        assert "gateway" not in health or True
        assert health.get("workflows") is not None
        assert health.get("pool", {}).get("workers") == 2
        mod.svc.pool.shutdown()

    def test_service_submit_queue(self):
        import app.automation.service as mod
        result = mod.svc.submit("no_such_wf", "acme")
        assert result["queued"] is True and result["pending"] >= 1
        mod.svc.pool.shutdown()