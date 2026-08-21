"""Incident Platform schema tests (Volume 49)."""

from app.incident.schemas import (
    IncidentCreate, IncidentUpdate, IncidentAcknowledge, IncidentTransition,
    AlertIngest, HypothesisCreate, HypothesisUpdate, ActionCreate,
    ActionApprove, ActionExecute, RunbookCreate, PostmortemCreate,
    EscalationPolicyCreate, AlertPolicyCreate, InvestigateRequest,
)


def test_incident_create_schema():
    schema = IncidentCreate(title="Test incident", severity="SEV1", service="api-gateway")
    assert schema.title == "Test incident"
    assert schema.severity == "SEV1"
    assert schema.service == "api-gateway"
    assert schema.tenant == "default"
    assert schema.incident_type == "availability"


def test_incident_create_defaults():
    schema = IncidentCreate(title="Minimal")
    assert schema.severity == "SEV2"
    assert schema.source == "alert"
    assert schema.environment == "production"
    assert schema.symptoms == []
    assert schema.impact == {}


def test_incident_update_schema():
    schema = IncidentUpdate(severity="SEV0", commander="alice")
    assert schema.severity == "SEV0"
    assert schema.commander == "alice"
    assert schema.status is None


def test_incident_acknowledge_schema():
    schema = IncidentAcknowledge()
    assert schema.commander == "on-call"


def test_incident_transition_schema():
    schema = IncidentTransition(status="investigating", message="Starting investigation", actor="alice")
    assert schema.status == "investigating"
    assert schema.actor == "alice"


def test_alert_ingest_schema():
    schema = AlertIngest(alert_source="datadog", alert_id="AL-1234", severity="SEV1",
                         service="api-gateway", message="High latency")
    assert schema.alert_source == "datadog"
    assert schema.alert_id == "AL-1234"
    assert schema.severity == "SEV1"
    assert schema.labels == {}


def test_hypothesis_create_schema():
    schema = HypothesisCreate(incident_id="inc-1", hypothesis="Database connection pool exhausted",
                               confidence=0.8)
    assert schema.incident_id == "inc-1"
    assert schema.confidence == 0.8
    assert schema.source == "ai"


def test_hypothesis_update_schema():
    schema = HypothesisUpdate(status="confirmed")
    assert schema.status == "confirmed"


def test_action_create_schema():
    schema = ActionCreate(incident_id="inc-1", action_type="restart_service",
                          risk_level="low", approval_required=False)
    assert schema.action_type == "restart_service"
    assert schema.approval_required is False


def test_action_approve_schema():
    schema = ActionApprove(approver="bob")
    assert schema.approver == "bob"


def test_action_execute_schema():
    schema = ActionExecute(dry_run=True)
    assert schema.dry_run is True


def test_runbook_create_schema():
    schema = RunbookCreate(name="Restart Service", incident_type="service_restart",
                           steps=[{"step": 1, "action": "check health"}])
    assert schema.name == "Restart Service"
    assert len(schema.steps) == 1
    assert schema.auto_executable is False


def test_postmortem_create_schema():
    schema = PostmortemCreate(incident_id="inc-1", summary="Database pool exhaustion",
                               root_cause="Max connections exceeded",
                               impact="Elevated error rates for 15 minutes")
    assert schema.incident_id == "inc-1"
    assert schema.contributing_factors == []


def test_escalation_policy_create_schema():
    schema = EscalationPolicyCreate(name="SEV0 Policy", description="Immediate escalation",
                                     rules=[{"after_minutes": 0, "targets": ["on-call"]}])
    assert schema.name == "SEV0 Policy"
    assert len(schema.rules) == 1


def test_alert_policy_create_schema():
    schema = AlertPolicyCreate(name="High Latency Policy",
                                conditions={"metric": "latency_p99", "operator": ">", "threshold": 1000})
    assert schema.name == "High Latency Policy"


def test_investigate_request_schema():
    schema = InvestigateRequest(incident_id="inc-1", focus_areas=["database", "network"])
    assert schema.incident_id == "inc-1"
    assert len(schema.focus_areas) == 2
    assert schema.max_tokens == 5000
