"""SRE / production reliability volume tests (Volume 35).

Covers: resilience primitives (circuit breaker, retries, timeouts),
service catalog + dependency graph, SLO/error-budget/burn-rate math,
health checks, incident lifecycle, chaos experiments, deployment
reliability + canary analysis, readiness scorecards, and the public
SRE API surface. All DB-backed tests use the session-scoped SQLite
test database created by tests/conftest.py.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_db_context
from app.models.user import User
from app.sre import constants as C
from app.sre.alerts import create_alert
from app.sre.chaos import ChaosManager
from app.sre.deployments import (
    canary_decision,
    complete_deployment,
    evaluate_canary,
    record_deployment,
    rollback_safety,
    start_canary,
)
from app.sre.health import HealthChecker
from app.sre.incident import IncidentManager
from app.sre.models import (
    SREAlert,
    SRECanaryRun,
    SREChaosExperiment,
    SREDeployment,
    SREErrorBudget,
    SREIncident,
    SREIncidentEvent,
    SREIncidentResponder,
    SREService,
    SREServiceDependency,
    SRESLIMeasurement,
    SRESLO,
    SRERunbook,
)
from app.sre.reliability import reliability_engine
from app.sre.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    RetryDecision,
    RetryPolicy,
    classify_retry,
    retry_async,
    with_timeout,
)
from app.sre.scorecard import READINESS_CHECKS, MaturityClassifier, ProductionReadiness, ScorecardEngine
from app.sre.service_catalog import service_catalog
from app.sre.slo import (
    aggregate_window,
    classify_burn_rate,
    compute_budget_values,
    compute_burn_rate,
    compute_error_budget,
    record_sli,
    slo_compliance,
)
from app.sre.store import get_one, new_id, new_key

# ---------------------------------------------------------------------------
# Resilience primitives
# ---------------------------------------------------------------------------


class TestRetryClassification:
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
    def test_client_errors_never_retried(self, status: int):
        assert classify_retry(status_code=status) is RetryDecision.NO_RETRY

    @pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
    def test_transient_errors_retried(self, status: int):
        assert classify_retry(status_code=status) is RetryDecision.RETRY

    @pytest.mark.parametrize(
        "message",
        [
            "unauthorized",
            "invalid api key",
            "permission denied",
            "authentication_error",
            "Invalid request",
            "content_policy violation",
            "not found",
        ],
    )
    def test_exception_hints_never_retried(self, message: str):
        assert classify_retry(Exception(message)) is RetryDecision.NO_RETRY

    def test_unknown_exception_retried(self):
        assert classify_retry(Exception("connection reset")) is RetryDecision.RETRY


class TestCircuitBreaker:
    def test_closed_allows_calls(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(name="t", failure_threshold=3))
        assert breaker.state == C.CIRCUIT_CLOSED
        assert breaker.allow_call() is True

    def test_opens_after_failure_threshold(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(name="t", failure_threshold=3))
        breaker._record_failure()
        breaker._record_failure()
        assert breaker.state == C.CIRCUIT_CLOSED
        breaker._record_failure()
        assert breaker.state == C.CIRCUIT_OPEN

    def test_open_rejects_calls_and_recovers_to_half_open(self, monkeypatch):
        breaker = CircuitBreaker(CircuitBreakerConfig(name="t", failure_threshold=1, timeout_seconds=0.01))
        clock = {"now": 1000.0}
        monkeypatch.setattr("time.monotonic", lambda: clock["now"])
        for _ in range(2):
            breaker._record_failure()
        assert breaker.state == C.CIRCUIT_OPEN
        assert breaker.allow_call() is False
        with pytest.raises(CircuitOpenError):
            asyncio.run(breaker.call(lambda: asyncio.sleep(0)))
        clock["now"] = 1000.0 + 0.05
        assert breaker.allow_call() is True
        assert breaker.state in (C.CIRCUIT_HALF_OPEN, C.CIRCUIT_OPEN)

    def test_half_open_success_closes(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(name="t", failure_threshold=1, timeout_seconds=0.0, half_open_max_calls=1))
        breaker._record_failure()
        assert breaker.state == C.CIRCUIT_OPEN
        breaker._opened_at = 0.0
        assert breaker.allow_call() is True
        assert breaker.state == C.CIRCUIT_HALF_OPEN
        breaker._record_success()
        assert breaker.state == C.CIRCUIT_CLOSED

    def test_async_call_success_and_failure(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(name="t", failure_threshold=2))

        async def ok():
            return 42

        async def boom():
            raise RuntimeError("boom")

        assert asyncio.run(breaker.call(ok)) == 42
        with pytest.raises(RuntimeError):
            asyncio.run(breaker.call(boom))
        snapshot = breaker.snapshot()
        assert snapshot["calls_total"] == 2  # one per guarded call
        assert snapshot["calls_failed"] == 1


class TestRetryAsync:
    def test_permanent_failure_raises_immediately(self):
        attempts = []

        async def op():
            attempts.append(1)
            raise ValueError("unauthorized")

        with pytest.raises(ValueError):
            asyncio.run(retry_async(op, name="test"))
        assert len(attempts) == 1

    def test_bounded_attempts(self):
        attempts = []

        async def op():
            attempts.append(1)
            raise TimeoutError("transient")

        with pytest.raises(TimeoutError):
            asyncio.run(
                retry_async(
                    op,
                    policy=RetryPolicy(
                        max_attempts=3, base_delay_seconds=0.0, max_delay_seconds=0.0, jitter=0.0
                    ),
                    name="test",
                )
            )
        assert len(attempts) == 3

    def test_success_returns_value(self):

        async def op():
            return "ok"

        assert asyncio.run(retry_async(op, name="t")) == "ok"


class TestTimeouts:
    def test_with_timeout_fires(self):
        async def slow():
            await asyncio.sleep(2)

        with pytest.raises(TimeoutError):
            asyncio.run(with_timeout(slow(), 0.01, "slow-op"))

    def test_with_timeout_completes(self):
        async def fast():
            return 1

        assert asyncio.run(with_timeout(fast(), 1.0)) == 1


# ---------------------------------------------------------------------------
# Service catalog & dependency graph
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sre_db():
    async with get_db_context() as db:
        await db.rollback()
        yield db


@pytest_asyncio.fixture
async def seeded_catalog(sre_db):
    count = await service_catalog.seed(sre_db)
    await sre_db.commit()
    return sre_db, count


class TestServiceCatalog:
    async def test_seed_is_idempotent(self, sre_db):
        first = await service_catalog.seed(sre_db)
        await sre_db.commit()
        second = await service_catalog.seed(sre_db)
        await sre_db.commit()
        assert first > 0
        assert second == 0

    async def test_catalog_has_tier0_services(self, sre_db):
        await service_catalog.seed(sre_db)
        await sre_db.commit()
        service = await get_one(sre_db, SREService, service_id="auth")
        assert service is not None
        assert service.tier == C.TIER_0_CRITICAL
        assert service.rto_minutes > 0
        assert service.runbook_id  # seeded runbook link

    async def test_impact_graph(self, sre_db):
        await service_catalog.seed(sre_db)
        await sre_db.commit()
        impact = await service_catalog.impact(sre_db, "auth")
        assert impact["service_id"] == "auth"
        # api-gateway and ai-chat depend on auth, so they are impacted.
        assert "api-gateway" in impact["impacted_services"]

    async def test_dependencies_of(self, sre_db):
        await service_catalog.seed(sre_db)
        await sre_db.commit()
        deps = await service_catalog.dependencies_of(sre_db, "ai-chat")
        assert "auth" in deps["dependencies"]
        assert "rag" in deps["dependencies"]

    async def test_register_and_set_status(self, sre_db):
        service = await service_catalog.register(
            sre_db,
            service_id="feature-flags",
            name="Feature Flags",
            tier=C.TIER_2_IMPORTANT,
            owner="platform",
        )
        assert service is not None
        assert service.tier == C.TIER_2_IMPORTANT
        updated = await service_catalog.set_status(sre_db, "feature-flags", "degraded")
        assert updated.status == "degraded"


# ---------------------------------------------------------------------------
# SLO / error budget / burn rate
# ---------------------------------------------------------------------------


class TestBudgetMath:
    def test_healthy_budget(self):
        budget = compute_budget_values(0.999, 999_900, 1_000_000)
        assert budget["status"] == C.BUDGET_HEALTHY
        assert budget["allowed_failure"] == pytest.approx(0.001)
        assert budget["consumed_percent"] == pytest.approx(10.0)  # 0.01% of window used

    def test_exhausted_budget(self):
        budget = compute_budget_values(0.999, 99_500, 100_000)
        assert budget["status"] == C.BUDGET_EXHAUSTED
        assert budget["consumed_percent"] == 100.0

    def test_at_risk_budget(self):
        budget = compute_budget_values(0.999, 99_905, 100_000)
        assert budget["status"] == C.BUDGET_AT_RISK
        assert 80.0 <= budget["consumed_percent"] < 100.0

    def test_zero_total_leaves_clean_state(self):
        budget = compute_budget_values(0.999, 0, 0)
        assert budget["total_events"] == 0
        assert budget["actual_failure"] == 0.0

    def test_burn_rate_computation(self):
        # 1% failure against a 0.1% budget over the whole window = 10x burn.
        rate = compute_burn_rate(0.999, 990, 1000, measurement_seconds=2_592_000, window_seconds=2_592_000)
        assert rate == pytest.approx(10.0, rel=0.2)


class TestBurnRateClassification:
    def test_slow_burn(self):
        assert classify_burn_rate(C.BURN_RATE_CONFIG[C.BURN_SLOW]["threshold"]) == C.BURN_SLOW

    def test_medium_burn(self):
        assert classify_burn_rate(C.BURN_RATE_CONFIG[C.BURN_MEDIUM]["threshold"] + 0.1) == C.BURN_MEDIUM

    def test_fast_burn(self):
        assert classify_burn_rate(100.0) == C.BURN_FAST

    def test_healthy(self):
        assert classify_burn_rate(0.1) is None


class TestSliRecording:
    async def test_record_and_aggregate(self, sre_db):
        slo = SRESLO(
            slo_id=new_key("slo"),
            service_id="test-svc",
            name="Test SLO",
            sli_type="availability",
            target=0.999,
            window="daily",
        )
        sre_db.add(slo)
        await sre_db.flush()
        await record_sli(sre_db, slo=slo, good=99, total=100)
        await record_sli(sre_db, slo=slo, good=99, total=100)
        await sre_db.commit()
        agg = await aggregate_window(sre_db, slo)
        assert agg["good"] == pytest.approx(198.0)
        assert agg["total"] == pytest.approx(200.0)
        assert agg["value"] == pytest.approx(0.99)

    async def test_compute_error_budget_persists(self, sre_db):
        slo = SRESLO(
            slo_id=new_key("slo"),
            service_id="test-svc",
            name="Test SLO",
            sli_type="availability",
            target=0.99,
            window="daily",
        )
        sre_db.add(slo)
        await sre_db.flush()
        await record_sli(sre_db, slo=slo, good=98, total=100)
        budget = await compute_error_budget(sre_db, slo, persist=True)
        await sre_db.commit()
        assert budget["status"] == C.BUDGET_EXHAUSTED
        assert budget["slo_id"] == slo.slo_id
        snapshots = (await sre_db.execute(select(SREErrorBudget))).scalars().all()
        assert any(s.slo_id == slo.slo_id for s in snapshots)

    async def test_slo_compliance(self, sre_db):
        budget = compute_budget_values(0.999, 999_900, 1_000_000)
        compliance = slo_compliance(budget)
        assert compliance["compliant"] is True
        assert "consumed" in compliance["reason"]


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


class TestHealthChecker:
    @pytest_asyncio.fixture
    async def checker(self):
        async def healthy():
            return True, None, {}

        async def down(reason="db unreachable"):
            return False, reason, {}

        checker = HealthChecker()
        checker.register("healthy-dep", healthy)
        checker.register("down-dep", down)
        return checker

    async def test_liveness_never_touches_dependencies(self, checker):
        result = await checker.liveness()
        assert result["status"] == C.HEALTH_HEALTHY
        assert "uptime_seconds" in result

    async def test_readiness_healthy_when_core_ok(self, checker):
        checker.startup_complete = True
        result = await checker.startup()
        assert result["status"] == C.HEALTH_HEALTHY
        assert result["startup_complete"] is True

    async def test_dependencies_reports_down(self, checker):
        result = await checker.dependencies()
        assert result["checks"]["down-dep"]["status"] == C.DEPENDENCY_STATUS_DOWN
        assert result["checks"]["healthy-dep"]["status"] == C.DEPENDENCY_STATUS_HEALTHY

    async def test_overall_classification(self, checker):
        results = await checker.run(["healthy-dep", "down-dep"])
        assert checker.overall(results) == C.HEALTH_DEGRADED
        assert checker.overall(results, required=["down-dep"]) == C.HEALTH_UNHEALTHY

    async def test_check_timeout_marks_down(self):
        async def hanging():
            await asyncio.sleep(10)

        checker = HealthChecker()
        checker.timeout_policy.overall_seconds = 0.01
        checker.register("hanging", hanging)
        results = await checker.run(["hanging"])
        assert results[0].status == C.DEPENDENCY_STATUS_DOWN
        assert "timed out" in results[0].detail


# ---------------------------------------------------------------------------
# Incident management
# ---------------------------------------------------------------------------


class TestIncidents:
    async def test_full_lifecycle(self, sre_db):
        incident = await IncidentManager().create(
            sre_db,
            title="API latency spike",
            severity=C.SEV1,
            service_id="api-gateway",
            organization_id="org-test",
            commander="commander@novaforge.ai",
        )
        assert incident.status == C.INCIDENT_DETECTED
        assert incident.severity == C.SEV1
        assert incident.incident_id.startswith("inc-")
        await sre_db.commit()

        invited = await IncidentManager().transition(
            sre_db, incident.incident_id, C.INCIDENT_INVESTIGATING, actor="responder"
        )
        assert invited.status == C.INCIDENT_INVESTIGATING
        await sre_db.commit()

        resolved = await IncidentManager().transition(sre_db, incident.incident_id, C.INCIDENT_RESOLVED)
        assert resolved.resolved_at is not None

        timeline = await IncidentManager().timeline(sre_db, incident.incident_id)
        assert len(timeline) >= 3
        assert any(t["event_type"] == "status" for t in timeline)

    async def test_invalid_transition_rejected(self, sre_db):
        incident = await IncidentManager().create(sre_db, title="T", severity=C.SEV2)
        with pytest.raises(ValueError):
            await IncidentManager().transition(sre_db, incident.incident_id, C.INCIDENT_CLOSED)

    async def test_invalid_severity_rejected(self, sre_db):
        with pytest.raises(ValueError):
            await IncidentManager().create(sre_db, title="T", severity="SEV9")

    async def test_command_roles(self, sre_db):
        incident = await IncidentManager().create(sre_db, title="T", severity=C.SEV2, commander="lead@novaforge.ai")
        await sre_db.commit()
        responders = await IncidentManager().responders(sre_db, incident.incident_id)
        assert any(r["role"] == "incident_commander" for r in responders)
        assert "lead@novaforge.ai" in {r["user_id"] for r in responders}

    async def test_detect_from_alert_is_idempotent(self, sre_db):
        alert = await create_alert(
            sre_db,
            rule_name="availability.dip",
            severity="SEV1",
            message="availability below target",
            service_id="api-gateway",
        )
        await sre_db.commit()
        first = await IncidentManager().detect_from_alert(sre_db, alert, organization_id="org-test")
        await sre_db.commit()
        second = await IncidentManager().detect_from_alert(sre_db, alert, organization_id="org-test")
        assert first.incident_id == second.incident_id

    async def test_metrics(self, sre_db):
        manager = IncidentManager()
        incident = await manager.create(sre_db, title="T", severity=C.SEV1, service_id="api-gateway")
        incident.detected_at = incident.detected_at - timedelta(minutes=5)
        await sre_db.flush()
        await manager.acknowledge(sre_db, incident.incident_id)
        await manager.transition(sre_db, incident.incident_id, C.INCIDENT_INVESTIGATING)
        await manager.mitigate(sre_db, incident.incident_id)
        await manager.transition(sre_db, incident.incident_id, C.INCIDENT_MITIGATING)
        await manager.transition(sre_db, incident.incident_id, C.INCIDENT_RESOLVED)
        await sre_db.commit()
        metrics = await manager.metrics(sre_db, window_days=30)
        assert metrics["incidents"] >= 1
        assert metrics["by_severity"].get(C.SEV1, 0) >= 1
        assert metrics["mttr_minutes"] > 0

    async def test_correlate(self, sre_db):
        incident = await IncidentManager().create(sre_db, title="T", severity=C.SEV2)
        await sre_db.commit()
        updated = await IncidentManager().correlate(
            sre_db, incident.incident_id, deployment_ids=["deploy-1"], alert_ids=["alert-1"]
        )
        assert "deploy-1" in updated.related_deployments
        assert "alert-1" in updated.related_alerts


# ---------------------------------------------------------------------------
# Chaos engineering
# ---------------------------------------------------------------------------


class TestChaos:
    async def test_create_validates_type_and_blast_radius(self, sre_db):
        with pytest.raises(ValueError):
            await ChaosManager().create(sre_db, name="x", experiment_type="weird", blast_radius="test")
        with pytest.raises(ValueError):
            await ChaosManager().create(sre_db, name="x", experiment_type="kill_worker", blast_radius="global")

    async def test_prod_limited_requires_safe_type(self, sre_db):
        with pytest.raises(ValueError):
            await ChaosManager().create(
                sre_db, name="x", experiment_type="fill_disk", blast_radius="prod-limited"
            )
        experiment = await ChaosManager().create(
            sre_db, name="x", experiment_type="kill_worker", blast_radius="prod-limited"
        )
        assert experiment.blast_radius == "prod-limited"

    async def test_lifecycle_pass_and_fail(self, sre_db):
        manager = ChaosManager()
        experiment = await manager.create(sre_db, name="drop 5%", experiment_type="drop_requests", blast_radius="test")
        await sre_db.commit()
        started = await manager.start(sre_db, experiment.experiment_id)
        assert started.status == C.CHAOS_RUNNING
        completed = await manager.complete(sre_db, experiment.experiment_id, actual_result="ok", passed=True)
        assert completed.status == C.CHAOS_PASSED
        failed = await manager.create(sre_db, name="kill", experiment_type="kill_worker", blast_radius="test")
        await manager.complete(sre_db, failed.experiment_id, actual_result="bad", passed=False)
        await sre_db.commit()
        stats = await manager.pass_rate(sre_db)
        assert stats["total"] == 2
        assert stats["passed"] == 1
        assert stats["pass_rate"] == pytest.approx(0.5)

    async def test_abort_and_check_abort(self, sre_db):
        manager = ChaosManager()
        experiment = await manager.create(sre_db, name="x", experiment_type="kill_worker", blast_radius="test")
        await sre_db.commit()
        assert await manager.check_abort(sre_db, experiment.experiment_id, True, "latency > 5s") is True
        aborted = await get_one(sre_db, SREChaosExperiment, experiment_id=experiment.experiment_id)
        assert aborted.status == C.CHAOS_ABORTED
        assert "latency > 5s" in aborted.actual_result


# ---------------------------------------------------------------------------
# Deployment reliability & canary analysis
# ---------------------------------------------------------------------------


class TestDeployments:
    async def test_record_and_complete(self, sre_db):
        deployment = await record_deployment(sre_db, service_id="ai-chat", version="2.4.1", strategy="canary")
        assert deployment.status == "in_progress"
        await complete_deployment(sre_db, deployment, duration_seconds=42, error_rate_after=0.01)
        await sre_db.commit()
        assert deployment.status == "success"
        assert deployment.duration_seconds == 42

    async def test_canary_aborts_on_error_delta(self, sre_db):
        deployment = await record_deployment(sre_db, service_id="ai-chat", version="3.0.0", strategy="canary")
        canary = await start_canary(
            sre_db,
            deployment_id=deployment.deployment_id,
            service_id="ai-chat",
            baseline_error_rate=0.01,
            error_rate_threshold=0.5,
        )
        result = await evaluate_canary(
            sre_db, canary, canary_error_rate=0.55, canary_latency_ms=180
        )
        await sre_db.commit()
        assert result["abort"] is True
        assert result["status"] == "aborted"
        # Deployment is flagged rolled_back, never blind.
        after = await get_one(sre_db, SREDeployment, deployment_id=deployment.deployment_id)
        assert after.status == "rolled_back"

    async def test_canary_passes_within_thresholds(self, sre_db):
        deployment = await record_deployment(sre_db, service_id="ai-chat", version="3.0.1", strategy="canary")
        canary = await start_canary(
            sre_db,
            deployment_id=deployment.deployment_id,
            service_id="ai-chat",
            baseline_error_rate=0.01,
            baseline_latency_ms=150,
        )
        result = await evaluate_canary(
            sre_db, canary, canary_error_rate=0.02, canary_latency_ms=160
        )
        await sre_db.commit()
        assert result["abort"] is False
        after = await get_one(sre_db, SREDeployment, deployment_id=deployment.deployment_id)
        assert after.status == "success"

    def test_canary_decision_pure(self):
        decision = canary_decision(
            baseline_error_rate=0.01, canary_error_rate=0.9,
            baseline_latency_ms=100, canary_latency_ms=500,
        )
        assert decision["abort"] is True
        assert len(decision["violations"]) == 2

    async def test_rollback_safety_requires_known_good(self, sre_db):
        safe = await rollback_safety(sre_db, "service-without-history")
        assert safe["safe"] is False
        current = await record_deployment(sre_db, service_id="payments", version="9.0.0")
        await complete_deployment(sre_db, current, status="success")
        previous = await record_deployment(sre_db, service_id="payments", version="8.9.0")
        await complete_deployment(sre_db, previous, status="success")
        await sre_db.commit()
        safe = await rollback_safety(sre_db, "payments", current_version="9.0.0")
        assert safe["safe"] is True
        assert safe["target_version"] == "8.9.0"


# ---------------------------------------------------------------------------
# Scorecard / readiness / maturity
# ---------------------------------------------------------------------------


class TestReadiness:
    async def test_assess_unknown_service(self, sre_db):
        result = await ProductionReadiness().assess(sre_db, service_id="does-not-exist")
        assert "error" in result

    async def test_tier0_service_readiness(self, sre_db):
        await service_catalog.seed(sre_db)
        await sre_db.commit()
        result = await ProductionReadiness().assess(sre_db, service_id="auth")
        assert result["tier"] == C.TIER_0_CRITICAL
        assert result["required"] == len({c["key"] for c in READINESS_CHECKS})
        assert result["readiness_percent"] > 0

    async def test_scorecard_shape(self, sre_db):
        await service_catalog.seed(sre_db)
        await sre_db.commit()
        result = await ScorecardEngine().scorecard(sre_db, service_id="api-gateway")
        assert "overall" in result
        assert result["dimensions"]["reliability"] >= 0

    async def test_maturity_classification(self, sre_db):
        await service_catalog.seed(sre_db)
        await sre_db.commit()
        result = await MaturityClassifier().classify(sre_db, service_id="auth")
        assert result["level"] >= 1
        unknown = await MaturityClassifier().classify(sre_db, service_id="unknown")
        assert unknown["level"] == 0

    async def test_reliability_score(self, sre_db):
        await service_catalog.seed(sre_db)
        await sre_db.commit()
        result = await reliability_engine.score(sre_db, service_id="api-gateway", window_days=30)
        assert "score" in result


# ---------------------------------------------------------------------------
# Workers (start/stop lifecycle only - loops are schedule-driven)
# ---------------------------------------------------------------------------


class TestWorkers:
    async def test_start_stop(self):
        from app.sre.workers import SREWorkers

        workers = SREWorkers()
        workers.start()
        assert workers._running is True
        assert len(workers._tasks) == 6
        await workers.stop()
        assert workers._running is False
        assert workers._tasks == []


# ---------------------------------------------------------------------------
# Health endpoints (public surface)
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    async def test_liveness(self, client):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("healthy", "ok")

    async def test_deep_endpoint_structure(self, client):
        resp = await client.get("/health/deep")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "checks" in body
        assert "database" in body["checks"]


# ---------------------------------------------------------------------------
# SRE API surface
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _superuser_token(app) -> str:
    """Create a superuser directly in the DB and return a JWT."""
    from jose import jwt

    from app.core.config import settings

    async def _make() -> str:
        async with get_db_context() as db:
            user = User(
                email="sre-api-admin@novaforge.local",
                username="sre-api-admin",
                hashed_password="x",
                full_name="SRE API Admin",
                is_superuser=True,
            )
            db.add(user)
            await db.flush()
            uid = str(user.id)
        payload = {
            "sub": uid,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    return asyncio.run(_make())


@pytest.fixture
def _admin_client(client: AsyncClient, _superuser_token: str):
    class AdminClient:
        def __init__(self, ac: AsyncClient, token: str):
            self._ac = ac
            self._token = token

        async def get(self, url: str, **kwargs):
            return await self._ac.get(url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)

        async def post(self, url: str, **kwargs):
            return await self._ac.post(url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)

        async def put(self, url: str, **kwargs):
            return await self._ac.put(url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)

        async def delete(self, url: str, **kwargs):
            return await self._ac.delete(url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)

    yield AdminClient(client, _superuser_token)


class TestSreApi:
    async def test_seed_and_list_services(self, _admin_client):
        resp = await _admin_client.post("/api/v1/sre/seed")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        assert "catalog" in body and "playbooks" in body and "dependencies" in body
        lists = await _admin_client.get("/api/v1/sre/services")
        assert lists.status_code == 200
        data = lists.json()
        assert data["total"] > 0
        assert any(s["service_id"] == "auth" for s in data["items"])

    async def test_incident_flow_via_api(self, client):
        created = await client.post(
            "/api/v1/sre/incidents",
            json={"title": "API incident via test", "severity": "SEV2", "service_id": "api-gateway"},
        )
        assert created.status_code == 200
        incident = created.json()
        assert incident["incident_id"].startswith("inc-")
        assert incident["status"] == "detected"

        transitioned = await client.post(
            f"/api/v1/sre/incidents/{incident['incident_id']}/transition",
            params={"new_status": "investigating"},
        )
        assert transitioned.status_code == 200
        assert transitioned.json()["status"] == "investigating"

        active = await client.get("/api/v1/sre/incidents/active")
        assert active.status_code == 200
        active_ids = [i["incident_id"] for i in active.json()]
        assert incident["incident_id"] in active_ids

    async def test_slo_endpoint(self, _admin_client):
        await _admin_client.post("/api/v1/sre/seed")
        budgets = await _admin_client.get("/api/v1/sre/error-budgets")
        assert budgets.status_code == 200
        assert "items" in budgets.json()

    async def test_chaos_validation_via_api(self, _admin_client):
        resp = await _admin_client.post(
            "/api/v1/sre/chaos",
            json={"name": "bad", "experiment_type": "fill_disk", "blast_radius": "prod-limited"},
        )
        assert resp.status_code == 422

    async def test_admin_gate_enforced(self, client):
        resp = await client.post(
            "/api/v1/sre/chaos",
            json={"name": "nope", "experiment_type": "kill_worker", "blast_radius": "test"},
        )
        assert resp.status_code == 403

    async def test_runbook_available_for_tier0(self, _admin_client):
        await _admin_client.post("/api/v1/sre/seed")
        resp = await _admin_client.get("/api/v1/sre/runbooks/runbook-api-outage")
        assert resp.status_code == 200
        assert resp.json()["runbook_id"] == "runbook-api-outage"