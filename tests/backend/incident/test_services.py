"""Incident Platform service tests (Volume 49)."""

import pytest

from app.incident.incident_service import IncidentService
from app.incident.alert_service import AlertIngestionService
from app.incident.correlation_service import CorrelationService
from app.incident.change_correlation import ChangeCorrelationService
from app.incident.investigation_agent import InvestigationAgent
from app.incident.root_cause_service import RootCauseService
from app.incident.triage_service import TriageService
from app.incident.timeline_service import TimelineService
from app.incident.remediation_engine import RemediationEngine
from app.incident.runbook_engine import RunbookEngine
from app.incident.escalation_manager import EscalationManager
from app.incident.anomaly_detector import AnomalyDetector
from app.incident.ai_incident_detector import AIIncidentDetector
from app.incident.recurrence_detector import RecurrenceDetector
from app.incident.incident_memory import IncidentMemory
from app.incident.reliability_metrics import ReliabilityMetricsService
from app.incident.health_service import HealthService


class TestIncidentService:
    def test_create_incident(self):
        svc = IncidentService()
        inc = svc.create(tenant="t1", title="Test incident", severity="SEV1", service="api")
        assert inc["tenant"] == "t1"
        assert inc["severity"] == "SEV1"
        assert inc["service"] == "api"
        assert inc["status"] == "detected"

    def test_get_incident(self):
        svc = IncidentService()
        inc = svc.create(tenant="t1", title="Test")
        result = svc.get(inc["id"])
        assert result is not None
        assert result["id"] == inc["id"]

    def test_get_nonexistent(self):
        svc = IncidentService()
        assert svc.get("nonexistent") is None

    def test_list_incidents(self):
        svc = IncidentService()
        svc.create(tenant="t1", title="A", severity="SEV1", service="s1")
        svc.create(tenant="t1", title="B", severity="SEV2", service="s1")
        svc.create(tenant="t2", title="C", severity="SEV1", service="s2")
        results = svc.list_incidents(tenant="t1")
        assert len(results) == 2
        results = svc.list_incidents(tenant="t1", service="s1", severity="SEV1")
        assert len(results) == 1

    def test_acknowledge_incident(self):
        svc = IncidentService()
        inc = svc.create(tenant="t1", title="Test")
        result = svc.acknowledge(inc["id"], commander="alice")
        assert result["status"] == "triaged"
        assert result["commander"] == "alice"

    def test_acknowledge_already_triaged(self):
        svc = IncidentService()
        inc = svc.create(tenant="t1", title="Test")
        svc.acknowledge(inc["id"], commander="alice")
        result = svc.acknowledge(inc["id"], commander="bob")
        assert result["status"] == "triaged"

    def test_transition_incident(self):
        svc = IncidentService()
        inc = svc.create(tenant="t1", title="Test")
        result = svc.transition(inc["id"], "investigating", actor="alice")
        assert result["status"] == "investigating"

    def test_transition_invalid(self):
        svc = IncidentService()
        inc = svc.create(tenant="t1", title="Test")
        with pytest.raises(ValueError, match="Invalid transition"):
            svc.transition(inc["id"], "bogus_status")

    def test_get_events(self):
        svc = IncidentService()
        inc = svc.create(tenant="t1", title="Test")
        events = svc.get_events(inc["id"])
        assert len(events) >= 1

    def test_get_active_count(self):
        svc = IncidentService()
        svc.create(tenant="t1", title="A")
        svc.create(tenant="t1", title="B")
        count = svc.get_active_count("t1")
        assert count == 2


class TestAlertService:
    def test_ingest_alert(self):
        svc = AlertIngestionService()
        result = svc.ingest(tenant="t1", alert_source="datadog", alert_id="A1",
                            rule_name="high_latency", severity="SEV1",
                            service="api", environment="production",
                            message="High latency detected")
        assert result["status"] == "ingested"

    def test_dedup_alert(self):
        svc = AlertIngestionService()
        svc.ingest(tenant="t1", alert_source="datadog", alert_id="A1",
                   rule_name="high_latency", severity="SEV1",
                   service="api", environment="production",
                   message="High latency detected")
        r2 = svc.ingest(tenant="t1", alert_source="datadog", alert_id="A1",
                        rule_name="high_latency", severity="SEV1",
                        service="api", environment="production",
                        message="High latency detected")
        assert r2["status"] == "deduplicated"

    def test_acknowledge_alert(self):
        svc = AlertIngestionService()
        result = svc.ingest(tenant="t1", alert_source="dd", alert_id="A1",
                            rule_name="test", severity="SEV2",
                            service="api", environment="production",
                            message="Test alert")
        alert_id = result["alert_id"]
        acked = svc.acknowledge(alert_id)
        assert acked["status"] == "acknowledged"

    def test_resolve_alert(self):
        svc = AlertIngestionService()
        result = svc.ingest(tenant="t1", alert_source="dd", alert_id="A1",
                            rule_name="test", severity="SEV2",
                            service="api", environment="production",
                            message="Test alert")
        alert_id = result["alert_id"]
        resolved = svc.resolve(alert_id)
        assert resolved["status"] == "resolved"

    def test_list_alerts(self):
        svc = AlertIngestionService()
        svc.ingest(tenant="t1", alert_source="dd", alert_id="A1", rule_name="r1",
                   severity="SEV2", service="s1", environment="prod", message="m")
        svc.ingest(tenant="t1", alert_source="dd", alert_id="A2", rule_name="r2",
                   severity="SEV1", service="s2", environment="prod", message="m")
        alerts = svc.list_alerts(tenant="t1")
        assert len(alerts) == 2
        filtered = svc.list_alerts(tenant="t1", service="s1")
        assert len(filtered) == 1

    def test_firing_count(self):
        svc = AlertIngestionService()
        svc.ingest(tenant="t1", alert_source="dd", alert_id="A1", rule_name="r1",
                   severity="SEV2", service="s1", environment="prod", message="m")
        assert svc.get_firing_count("t1") == 1


class TestCorrelationService:
    def test_record_deployment(self):
        svc = CorrelationService()
        result = svc.record_deployment("d1", "api", "production", "v1.0.0", "abc123")
        assert result["deploy_id"] == "d1"

    def test_record_commit(self):
        svc = CorrelationService()
        result = svc.record_commit("abc123", "api", "org/repo", "alice", "Fix bug")
        assert result["commit_sha"] == "abc123"

    def test_correlate_deployments(self):
        svc = CorrelationService()
        svc.record_deployment("d1", "api", "production", "v1.0.0", "abc123")
        incident = {"id": "i1", "service": "api", "environment": "production",
                    "detected_at": "2026-01-01T00:01:00Z"}
        result = svc.correlate_deployments(incident)
        assert isinstance(result, list)

    def test_blast_radius(self):
        svc = CorrelationService()
        incident = {"id": "i1", "service": "api", "environment": "production"}
        radius = svc.compute_blast_radius(incident)
        assert "affected_services" in radius

    def test_get_summary(self):
        svc = CorrelationService()
        incident = {"id": "i1", "service": "api"}
        summary = svc.get_summary(incident)
        assert "correlated_deployments" in summary


class TestChangeCorrelation:
    def test_record_change(self):
        svc = ChangeCorrelationService()
        result = svc.record_change("deployment", "api", "production", "d1",
                                    description="Deploy v1.0", author="alice")
        assert result["change_id"] == "d1"

    def test_classify_risk(self):
        svc = ChangeCorrelationService()
        change = {"change_type": "deployment", "files_changed": ["a.py", "b.py"]}
        result = svc.classify_change_risk(change)
        assert "risk_score" in result
        assert "risk_level" in result

    def test_find_related(self):
        svc = ChangeCorrelationService()
        svc.record_change("deployment", "api", "production", "d1",
                          changed_at="2026-01-01T00:00:00Z")
        incident = {"service": "api", "environment": "production",
                    "detected_at": "2026-01-01T00:01:00Z"}
        results = svc.find_related_changes(incident)
        assert len(results) == 1

    def test_get_summary(self):
        svc = ChangeCorrelationService()
        incident = {"service": "api", "environment": "production",
                    "detected_at": "2026-01-01T00:01:00Z"}
        summary = svc.get_change_summary(incident)
        assert "total_changes" in summary


class TestInvestigationAgent:
    def test_investigate(self):
        svc = InvestigationAgent()
        incident = {"id": "i1", "service": "api", "severity": "SEV1"}
        result = svc.investigate(incident, focus_areas=["logs"])
        assert "hypotheses" in result
        assert "logs_analyzed" in result

    def test_list_investigations(self):
        svc = InvestigationAgent()
        incident = {"id": "i1", "service": "api"}
        svc.investigate(incident)
        results = svc.list_investigations(incident_id="i1")
        assert len(results) == 1


class TestRootCauseService:
    def test_analyze(self):
        svc = RootCauseService()
        incident = {"id": "i1", "service": "api", "severity": "SEV1"}
        result = svc.analyze(incident, {})
        assert "hypotheses" in result

    def test_analyze_with_correlation(self):
        svc = RootCauseService()
        incident = {"id": "i1", "service": "api"}
        corr = {"correlated_deployments": 1, "correlated_commits": 0,
                "most_recent_deployment": {"deploy_id": "d1"}}
        result = svc.analyze(incident, corr)
        assert len(result["hypotheses"]) > 0


class TestTriageService:
    def test_triage(self):
        svc = TriageService()
        incident = {"id": "i1", "service": "api", "severity": "SEV2", "status": "detected"}
        result = svc.triage(incident, {})
        assert "facts" in result
        assert "severity_suggestion" in result


class TestTimelineService:
    def test_add_event(self):
        svc = TimelineService()
        event = svc.add_event("inc-1", "detected", "datadog", "High latency alert")
        assert event["event_type"] == "detected"

    def test_get_timeline(self):
        svc = TimelineService()
        svc.add_event("inc-1", "detected", "datadog", "Alert fired")
        svc.add_event("inc-1", "acknowledged", "alice", "Taken ownership")
        timeline = svc.get_timeline("inc-1")
        assert len(timeline) == 2

    def test_generate_summary(self):
        svc = TimelineService()
        svc.add_event("inc-1", "detected", "dd", "Alert")
        summary = svc.generate_summary("inc-1")
        assert len(summary) > 0


class TestRemediationEngine:
    def test_propose(self):
        engine = RemediationEngine()
        action = engine.propose("inc-1", "restart_service", "Restart the API server", "safe",
                                approval_required=False)
        assert action["status"] == "proposed"
        assert action["action_type"] == "restart_service"
        assert action["approval_required"] is False

    def test_approve(self):
        engine = RemediationEngine()
        action = engine.propose("inc-1", "restart", "Restart", "moderate", approval_required=True)
        approved = engine.approve(action["id"], approver="bob")
        assert approved["status"] == "approved"

    def test_approve_nonexistent(self):
        engine = RemediationEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.approve("bogus")

    def test_execute_dry_run(self):
        engine = RemediationEngine()
        action = engine.propose("inc-1", "restart", "Restart", "moderate", approval_required=True)
        engine.approve(action["id"], approver="bob")
        executed = engine.execute(action["id"], dry_run=True)
        assert executed["dry_run_result"]["dry_run"] is True

    def test_execute_without_approval(self):
        engine = RemediationEngine()
        action = engine.propose("inc-1", "restart", "Restart", "moderate", approval_required=True)
        with pytest.raises(ValueError, match="approval"):
            engine.execute(action["id"])

    def test_list_actions(self):
        engine = RemediationEngine()
        engine.propose("inc-1", "restart", "Restart", "low", approval_required=False)
        engine.propose("inc-2", "scale", "Scale up", "moderate", approval_required=False)
        actions = engine.list_actions(incident_id="inc-1")
        assert len(actions) == 1

    def test_pending_approvals(self):
        engine = RemediationEngine()
        engine.propose("inc-1", "restart", "Restart", "moderate", approval_required=True)
        pending = engine.get_pending_approvals()
        assert len(pending) == 1


class TestRunbookEngine:
    def test_create_runbook(self):
        engine = RunbookEngine()
        rb = engine.create("default", "Restart API", "service_restart",
                           steps=[{"step": 1, "description": "Check health"}])
        assert rb["name"] == "Restart API"

    def test_match_runbook(self):
        engine = RunbookEngine()
        engine.create("default", "Restart API", "service_restart")
        incident = {"id": "i1", "service": "api", "incident_type": "service_restart"}
        matched = engine.match_runbook(incident, "default")
        assert matched is not None

    def test_list_runbooks(self):
        engine = RunbookEngine()
        engine.create("default", "RB1", "service_restart")
        engine.create("default", "RB2", "database_issue")
        runbooks = engine.list_runbooks("default")
        assert len(runbooks) == 2

    def test_execute_runbook(self):
        engine = RunbookEngine()
        rb = engine.create("default", "RB1", "service_restart",
                           steps=[{"step": 1, "description": "Check health"}], auto_executable=True)
        result = engine.execute_runbook(rb["id"], "inc-1", dry_run=True)
        assert "steps_executed" in result


class TestEscalationManager:
    def test_create_policy(self):
        mgr = EscalationManager()
        policy = mgr.create_policy("t1", "SEV0 Policy")
        assert policy["name"] == "SEV0 Policy"

    def test_set_oncall(self):
        mgr = EscalationManager()
        result = mgr.set_oncall("api", [{"name": "alice", "email": "alice@test.com"}])
        assert result["oncall_count"] == 1
        oncall = mgr.get_oncall("api")
        assert oncall["name"] == "alice"

    def test_check_escalation(self):
        mgr = EscalationManager()
        incident = {"id": "i1", "severity": "SEV0", "status": "detected", "service": "api"}
        result = mgr.check_escalation(incident)
        assert result["should_escalate"] is True

    def test_get_stats(self):
        mgr = EscalationManager()
        mgr.create_policy("t1", "P1")
        stats = mgr.get_stats("t1")
        assert stats["policies_count"] == 1


class TestAnomalyDetector:
    def test_record_metric(self):
        detector = AnomalyDetector()
        result = detector.record_metric("api", "latency_ms", 250.0)
        assert result["value"] == 250.0

    def test_detect_anomalies_insufficient_data(self):
        detector = AnomalyDetector()
        detector.record_metric("api", "latency_ms", 250.0)
        anomalies = detector.detect_anomalies("api")
        assert anomalies == []

    def test_detect_latency_anomaly(self):
        detector = AnomalyDetector()
        for i in range(10):
            detector.record_metric("api", "latency_ms", 5000.0 + i * 100)
        anomalies = detector.detect_anomalies("api")
        latency = [a for a in anomalies if a["type"] == "latency_anomaly"]
        assert len(latency) > 0

    def test_get_metric_history(self):
        detector = AnomalyDetector()
        for i in range(5):
            detector.record_metric("api", "latency_ms", 100.0 + i)
        history = detector.get_metric_history("api", "latency_ms")
        assert len(history) == 5

    def test_compute_baseline(self):
        detector = AnomalyDetector()
        for i in range(10):
            detector.record_metric("api", "latency_ms", 100.0 + i)
        baseline = detector.compute_baseline("api", "latency_ms")
        assert baseline["count"] == 10
        assert baseline["mean"] > 0


class TestAIIncidentDetector:
    def test_record_event(self):
        detector = AIIncidentDetector()
        result = detector.record_event("llm_call", "api", provider="openai", success=True)
        assert result["provider"] == "openai"

    def test_detect_provider_outage(self):
        detector = AIIncidentDetector()
        for i in range(10):
            detector.record_event("llm_call", "api", provider="openai", success=False)
        incidents = detector.analyze("api")
        provider_outages = [i for i in incidents if i["type"] == "ai_provider_outage"]
        assert len(provider_outages) > 0

    def test_detect_token_exhaustion(self):
        detector = AIIncidentDetector()
        for i in range(5):
            detector.record_event("llm_call", "api", provider="openai", success=True, tokens_used=50000)
        incidents = detector.analyze("api")
        token = [i for i in incidents if i["type"] == "ai_token_exhaustion"]
        assert len(token) > 0

    def test_get_event_stats(self):
        detector = AIIncidentDetector()
        detector.record_event("llm_call", "api", success=True)
        detector.record_event("llm_call", "api", success=False)
        stats = detector.get_event_stats("api")
        assert stats["failure_rate"] == 0.5


class TestRecurrenceDetector:
    def test_record_incident(self):
        detector = RecurrenceDetector()
        detector.record_incident({"id": "i1", "service": "api", "fingerprint": "fp1"})
        stats = detector.get_recurrence_stats()
        assert stats["total"] == 1

    def test_detect_recurrences(self):
        detector = RecurrenceDetector()
        detector.record_incident({"id": "i1", "service": "api", "fingerprint": "fp1",
                                   "tenant": "t1", "root_cause": "connection_pool"})
        detector.record_incident({"id": "i2", "service": "api", "fingerprint": "fp1",
                                   "tenant": "t1", "root_cause": "connection_pool"})
        current = {"id": "i3", "service": "api", "fingerprint": "fp1", "tenant": "t1"}
        matches = detector.detect_recurrences(current)
        assert len(matches) >= 1

    def test_suggest_preventive_actions(self):
        detector = RecurrenceDetector()
        suggestions = detector.suggest_preventive_actions(
            {}, [{"score": 5, "reasons": ["same_fingerprint"]}])
        assert len(suggestions) > 0


class TestIncidentMemory:
    def test_store_verified(self):
        mem = IncidentMemory()
        result = mem.store_verified_incident(
            {"id": "i1", "title": "DB exhaustion", "service": "api",
             "fingerprint": "fp1", "root_cause": "pool_exhaustion"})
        assert result["verified"] is True

    def test_search(self):
        mem = IncidentMemory()
        mem.store_verified_incident({"id": "i1", "title": "DB exhaustion", "service": "api"})
        results = mem.search(query="exhaustion", service="api")
        assert len(results) == 1

    def test_get_similar(self):
        mem = IncidentMemory()
        mem.store_verified_incident({"id": "i1", "service": "api", "fingerprint": "fp1"})
        matches = mem.get_similar_incidents({"service": "api", "fingerprint": "fp1"})
        assert len(matches) == 1

    def test_stats(self):
        mem = IncidentMemory()
        mem.store_verified_incident({"id": "i1", "service": "api"})
        stats = mem.get_stats()
        assert stats["total_memories"] == 1


class TestReliabilityMetrics:
    def test_record_and_compute(self):
        svc = ReliabilityMetricsService()
        svc.record_incident({"id": "i1", "tenant": "t1", "service": "api",
                              "severity": "SEV1", "detected_at": "2026-01-01T00:00:00Z",
                              "acknowledged_at": "2026-01-01T00:05:00Z",
                              "resolved_at": "2026-01-01T00:30:00Z"})
        metrics = svc.compute_metrics("t1", "api")
        assert metrics["incident_count"] == 1
        assert metrics["mtta_seconds"] == 300
        assert metrics["mttr_seconds"] == 1800

    def test_slo_computation(self):
        svc = ReliabilityMetricsService()
        svc.record_incident({"id": "i1", "tenant": "t1", "service": "api",
                              "detected_at": "2026-01-01T00:00:00Z",
                              "resolved_at": "2026-01-01T00:00:30Z"})
        slo = svc.compute_service_slo("t1", "api", availability_target=0.999)
        assert slo["status"] == "healthy"
        assert slo["availability_actual"] > 0.99

    def test_empty_metrics(self):
        svc = ReliabilityMetricsService()
        metrics = svc.compute_metrics("nonexistent")
        assert metrics["incident_count"] == 0


class TestHealthService:
    def test_system_health(self):
        svc = HealthService()
        result = svc.check_incident_system_health()
        assert result["status"] == "healthy"
        assert "checks" in result

    def test_service_health(self):
        svc = HealthService()
        result = svc.check_service_health("api", {"db": {"status": "healthy"}})
        assert result["status"] == "healthy"

    def test_cached_health(self):
        svc = HealthService()
        svc.check_service_health("api")
        cached = svc.get_cached_health("api")
        assert cached is not None
