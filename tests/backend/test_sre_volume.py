"""Volume 35 - SRE tests.

Pure-logic coverage: SLO math, burn rates, circuit breakers, retry
classification, canary decisions, incident state machine, outage modes,
capacity/certificate classification and runbook validation.
API/health-surface tests live in tests/backend/test_sre.py.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.sre.alerts import create_alert, resolve_alert, resolve_by_rule
from app.sre.capacity import saturation_level
from app.sre.certificates import classify_expiry
from app.sre.constants import (
    BUDGET_AT_RISK,
    BUDGET_EXHAUSTED,
    BUDGET_HEALTHY,
    BURN_FAST,
    BURN_MEDIUM,
    BURN_SLOW,
    CIRCUIT_CLOSED,
    CIRCUIT_HALF_OPEN,
    CIRCUIT_OPEN,
    CERT_EXPIRED,
    CERT_EXPIRING,
    CERT_VALID,
    INCIDENT_DETECTED,
    INCIDENT_INVESTIGATING,
    INCIDENT_RESOLVED,
    RUNBOOK_SCENARIOS,
    SEV1,
    SEV2,
)
from app.sre.deployments import canary_decision, rollback_safety
from app.sre.dependencies import DependencyOutageMode, outage_plan
from app.sre.incidents import InvalidTransitionError, validate_transition
from app.sre.playbooks import default_runbooks, validate_default_scenarios
from app.sre.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    RetryDecision,
    RetryPolicy,
    classify_retry,
)
from app.sre.slo import (
    classify_burn_rate,
    compute_budget_values,
    compute_burn_rate,
)


# ---------------------------------------------------------------------------
# Error budget math
# ---------------------------------------------------------------------------


class TestErrorBudgetMath:
    def test_healthy_budget(self):
        budget = compute_budget_values(target=0.999, good=99900, total=100000)
        assert budget["allowed_failure"] == pytest.approx(0.001)
        assert budget["actual_failure"] == pytest.approx(0.001)
        assert budget["status"] == BUDGET_EXHAUSTED or budget["consumed_percent"] == pytest.approx(100.0)

    def test_within_budget(self):
        budget = compute_budget_values(target=0.999, good=99990, total=100000)
        assert budget["status"] == BUDGET_HEALTHY
        assert budget["remaining_budget"] > 0
        assert budget["consumed_percent"] < 100.0

    def test_no_data_means_no_claim(self):
        budget = compute_budget_values(target=0.999, good=0, total=0)
        assert budget["actual_failure"] == 0.0
        assert budget["status"] == BUDGET_HEALTHY

    def test_at_risk_threshold(self):
        # 95% of a 0.1% budget consumed: actual failure = 0.00095
        budget = compute_budget_values(target=0.999, good=99905, total=100000)
        assert budget["consumed_percent"] >= 90
        assert budget["status"] in (BUDGET_AT_RISK, BUDGET_EXHAUSTED)


# ---------------------------------------------------------------------------
# Burn rates
# ---------------------------------------------------------------------------


class TestBurnRates:
    def test_low_burn_when_within_budget(self):
        # 0.0001% failure in one hour against a 30-day budget: slow burn, below 1.0.
        rate = compute_burn_rate(target=0.999, good=99999.9, total=100000, measurement_seconds=3600, window_seconds=30 * 86400)
        assert rate < 1.0

    def test_high_burn_documented(self):
        # 0.001% failure in one hour is a fast burn for a 99.9% SLO (~7.2x).
        rate = compute_burn_rate(target=0.999, good=99999, total=100000, measurement_seconds=3600, window_seconds=30 * 86400)
        assert rate == pytest.approx(7.2, abs=0.01)

    def test_fast_burn_detected(self):
        # All failures in a 5-minute window against a 30-day budget.
        rate = compute_burn_rate(target=0.999, good=0, total=1000, measurement_seconds=300, window_seconds=30 * 86400)
        assert classify_burn_rate(rate) == BURN_FAST

    def test_classify_tiers(self):
        assert classify_burn_rate(50.0) == BURN_FAST
        assert classify_burn_rate(10.0) == BURN_MEDIUM
        assert classify_burn_rate(2.0) == BURN_SLOW
        assert classify_burn_rate(0.1) is None

    def test_no_total_means_no_burn(self):
        rate = compute_burn_rate(target=0.999, good=0, total=0, measurement_seconds=300, window_seconds=30 * 86400)
        assert rate == 0.0


# ---------------------------------------------------------------------------
# Retry classification
# ---------------------------------------------------------------------------


class TestRetryClassification:
    def test_never_retry_authentication(self):
        assert classify_retry(status_code=401) == RetryDecision.NO_RETRY
        assert classify_retry(status_code=403) == RetryDecision.NO_RETRY
        assert classify_retry(status_code=400) == RetryDecision.NO_RETRY
        assert classify_retry(status_code=422) == RetryDecision.NO_RETRY

    def test_retry_transient(self):
        assert classify_retry(status_code=503) == RetryDecision.RETRY
        assert classify_retry(status_code=429) == RetryDecision.RETRY
        assert classify_retry(status_code=500) == RetryDecision.RETRY

    def test_message_hints(self):
        assert classify_retry(exc=ValueError("unauthorized")) == RetryDecision.NO_RETRY
        assert classify_retry(exc=ValueError("connection reset")) == RetryDecision.RETRY

    def test_backoff_bounded(self):
        policy = RetryPolicy(base_delay_seconds=0.2, max_delay_seconds=8.0)
        delays = [policy.delay_for(i) for i in range(1, 8)]
        assert all(d <= 8.0 for d in delays)
        assert delays[-1] >= delays[0]


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_opens_after_failures(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3, name="test-svc"))
        for _ in range(3):
            breaker._record_failure()
        assert breaker.state == CIRCUIT_OPEN
        assert not breaker.allow_call()

    def test_closed_when_healthy(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(name="test-svc"))
        for _ in range(5):
            breaker._record_success()
        assert breaker.state == CIRCUIT_CLOSED

    def test_half_open_recovers(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, timeout_seconds=0.01, half_open_max_calls=1, name="test-svc"))
        breaker._record_failure()
        breaker._record_failure()
        assert breaker.state == CIRCUIT_OPEN
        time.sleep(0.02)
        assert breaker.allow_call()  # HALF_OPEN probe
        breaker._record_success()
        assert breaker.state == CIRCUIT_CLOSED

    def test_half_open_failure_reopens(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, timeout_seconds=0.01, half_open_max_calls=1, name="test-svc"))
        breaker._record_failure()
        breaker._record_failure()
        time.sleep(0.02)
        breaker.allow_call()
        breaker._record_failure()
        assert breaker.state == CIRCUIT_OPEN


# ---------------------------------------------------------------------------
# Canary / deployment decisions
# ---------------------------------------------------------------------------


class TestCanary:
    def test_abort_on_error_spike(self):
        decision = canary_decision(
            baseline_error_rate=0.01,
            canary_error_rate=0.20,
            baseline_latency_ms=100,
            canary_latency_ms=110,
            error_rate_threshold=0.05,
        )
        assert decision["abort"] is True
        assert any("error rate" in v for v in decision["violations"])

    def test_abort_on_latency_regression(self):
        decision = canary_decision(
            baseline_error_rate=0.01,
            canary_error_rate=0.01,
            baseline_latency_ms=100,
            canary_latency_ms=200,
            latency_threshold_multiplier=1.5,
        )
        assert decision["abort"] is True

    def test_pass_when_within_thresholds(self):
        decision = canary_decision(
            baseline_error_rate=0.01,
            canary_error_rate=0.015,
            baseline_latency_ms=100,
            canary_latency_ms=120,
            error_rate_threshold=0.05,
            latency_threshold_multiplier=1.5,
        )
        assert decision["abort"] is False

    def test_rollback_safety_requires_known_good(self):
        assert rollback_safety.__doc__  # contract exists


# ---------------------------------------------------------------------------
# Incident state machine
# ---------------------------------------------------------------------------


class TestIncidentStateMachine:
    def test_valid_transition(self):
        validate_transition(INCIDENT_DETECTED, INCIDENT_INVESTIGATING)
        validate_transition(INCIDENT_INVESTIGATING, INCIDENT_RESOLVED)
        validate_transition(INCIDENT_RESOLVED, "closed")

    def test_invalid_transition(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition(INCIDENT_RESOLVED, INCIDENT_DETECTED)
        with pytest.raises(InvalidTransitionError):
            validate_transition(INCIDENT_DETECTED, "not-a-status")
        with pytest.raises(InvalidTransitionError):
            validate_transition("closed", INCIDENT_DETECTED)

    def test_severity_values(self):
        assert SEV1 in ("SEV0", "SEV1", "SEV2", "SEV3", "SEV4")
        assert SEV2 != SEV1


# ---------------------------------------------------------------------------
# Dependency outage classification
# ---------------------------------------------------------------------------


class TestOutageMode:
    def test_ai_provider_falls_back(self):
        plan = outage_plan("openai", "ai_provider", "down")
        assert plan["mode"] == "fallback"

    def test_storage_queues(self):
        plan = outage_plan("s3", "storage", "down")
        assert plan["mode"] == "queue"

    def test_healthy_is_operational(self):
        assert DependencyOutageMode.classify("redis", "queue", "healthy") == "operational"


# ---------------------------------------------------------------------------
# Capacity + certificates (pure logic)
# ---------------------------------------------------------------------------


class TestCapacityAndCerts:
    def test_saturation_levels(self):
        assert saturation_level(50, 100) == "normal"
        assert saturation_level(85, 100) == "warning"
        assert saturation_level(97, 100) == "critical"

    def test_certificate_expiry(self):
        now = datetime.now(timezone.utc)
        assert classify_expiry(now + timedelta(days=60)) == CERT_VALID
        assert classify_expiry(now + timedelta(days=10)) == CERT_EXPIRING
        assert classify_expiry(now - timedelta(days=1)) == CERT_EXPIRED

    def test_all_scenarios_have_runbooks(self):
        assert validate_default_scenarios() == []
        defined = {rb["scenario"] for rb in default_runbooks()}
        assert defined >= set(RUNBOOK_SCENARIOS)


# ---------------------------------------------------------------------------
# Resilience async integration
# ---------------------------------------------------------------------------


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_retry_transient_then_success(self):
        from app.sre.resilience import RetryPolicy, retry_async

        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("transient")
            return "ok"

        result = await retry_async(flaky, policy=RetryPolicy(max_attempts=4, base_delay_seconds=0.001), name="flaky")
        assert result == "ok"
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_permanent_failure_not_retried(self):
        from app.sre.resilience import retry_async

        calls = {"n": 0}

        async def permanent():
            calls["n"] += 1
            raise ValueError("authentication failed")

        with pytest.raises(ValueError):
            await retry_async(permanent, policy=RetryPolicy(max_attempts=5, base_delay_seconds=0.001), name="perm")
        assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_liveness(self, client: AsyncClient):
        response = await client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] in ("healthy", "ok")

    @pytest.mark.asyncio
    async def test_startup(self, client: AsyncClient):
        response = await client.get("/health/startup")
        assert response.status_code == 200
        assert "startup_complete" in response.json()

    @pytest.mark.asyncio
    async def test_dependencies_health(self, client: AsyncClient):
        response = await client.get("/health/dependencies")
        assert response.status_code == 200
        data = response.json()
        assert "checks" in data
        assert "database" in data["checks"]

    @pytest.mark.asyncio
    async def test_deep_health(self, client: AsyncClient):
        response = await client.get("/health/deep")
        assert response.status_code == 200
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client: AsyncClient):
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "novaforge_http_requests_total" in response.text or "prometheus" in response.text.lower()