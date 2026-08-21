"""Incident Platform API tests (Volume 49)."""

from fastapi.testclient import TestClient


def _create_incident(client, **kwargs):
    defaults = {"tenant": "test", "title": "Test incident"}
    defaults.update(kwargs)
    resp = client.post("/incident/incidents", json=defaults)
    return resp.json()


def _ingest_alert(client, **kwargs):
    defaults = {"tenant": "test", "alert_source": "dd", "alert_id": "A1",
                "rule_name": "test_rule", "severity": "SEV2",
                "service": "api", "environment": "production", "message": "test"}
    defaults.update(kwargs)
    resp = client.post("/incident/alerts/ingest", json=defaults)
    return resp.json()


def _create_action(client, incident_id, **kwargs):
    defaults = {"incident_id": incident_id, "action_type": "restart",
                "description": "Restart", "risk_level": "moderate"}
    defaults.update(kwargs)
    resp = client.post("/incident/actions", json=defaults)
    return resp.json()


# ── Incidents ──────────────────────────────────────────────────────────

def test_create_incident(client: TestClient):
    resp = client.post("/incident/incidents", json={
        "tenant": "test", "title": "DB Connection Pool Exhausted",
        "severity": "SEV1", "service": "api-gateway"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "DB Connection Pool Exhausted"
    assert data["severity"] == "SEV1"


def test_list_incidents(client: TestClient):
    client.post("/incident/incidents", json={"tenant": "test", "title": "A", "service": "api"})
    client.post("/incident/incidents", json={"tenant": "test", "title": "B", "service": "api"})
    resp = client.get("/incident/incidents", params={"tenant": "test"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_incident(client: TestClient):
    inc = _create_incident(client)
    resp = client.get(f"/incident/incidents/{inc['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == inc["id"]


def test_get_incident_not_found(client: TestClient):
    resp = client.get("/incident/incidents/nonexistent")
    assert resp.status_code == 404


def test_acknowledge_incident(client: TestClient):
    inc = _create_incident(client)
    resp = client.post(f"/incident/incidents/{inc['id']}/acknowledge",
                       json={"commander": "alice"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "triaged"
    assert resp.json()["commander"] == "alice"


def test_transition_incident(client: TestClient):
    inc = _create_incident(client)
    resp = client.post(f"/incident/incidents/{inc['id']}/transition",
                       json={"status": "investigating", "message": "Looking into it"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "investigating"


def test_transition_invalid(client: TestClient):
    inc = _create_incident(client)
    resp = client.post(f"/incident/incidents/{inc['id']}/transition",
                       json={"status": "bogus"})
    assert resp.status_code == 400


def test_update_incident(client: TestClient):
    inc = _create_incident(client)
    resp = client.put(f"/incident/incidents/{inc['id']}",
                      json={"severity": "SEV0", "commander": "bob"})
    assert resp.status_code == 200
    assert resp.json()["severity"] == "SEV0"


def test_get_status(client: TestClient):
    inc = _create_incident(client)
    resp = client.get(f"/incident/incidents/{inc['id']}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "detected"


def test_active_count(client: TestClient):
    client.post("/incident/incidents", json={"tenant": "t1", "title": "A"})
    client.post("/incident/incidents", json={"tenant": "t1", "title": "B"})
    resp = client.get("/incident/incidents/active/count", params={"tenant": "t1"})
    assert resp.status_code == 200
    assert resp.json()["active_count"] >= 2


# ── Alerts ─────────────────────────────────────────────────────────────

def test_ingest_alert(client: TestClient):
    resp = client.post("/incident/alerts/ingest", json={
        "tenant": "test", "alert_source": "datadog", "alert_id": "AL-1",
        "rule_name": "high_latency", "severity": "SEV1",
        "service": "api", "environment": "production", "message": "High latency"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ingested"


def test_list_alerts(client: TestClient):
    _ingest_alert(client, alert_id="A1", service="s1")
    _ingest_alert(client, alert_id="A2", service="s2")
    resp = client.get("/incident/alerts", params={"tenant": "test"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_acknowledge_alert(client: TestClient):
    alert = _ingest_alert(client)
    alert_id = alert["alert_id"]
    resp = client.post(f"/incident/alerts/{alert_id}/acknowledge")
    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"


def test_resolve_alert(client: TestClient):
    alert = _ingest_alert(client)
    alert_id = alert["alert_id"]
    resp = client.post(f"/incident/alerts/{alert_id}/resolve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


def test_firing_count(client: TestClient):
    _ingest_alert(client, alert_id="A1")
    resp = client.get("/incident/alerts/firing/count", params={"tenant": "test"})
    assert resp.status_code == 200
    assert resp.json()["firing_count"] >= 1


# ── Timeline ───────────────────────────────────────────────────────────

def test_timeline(client: TestClient):
    inc = _create_incident(client)
    resp = client.get(f"/incident/incidents/{inc['id']}/timeline")
    assert resp.status_code == 200
    assert "events" in resp.json()


# ── Investigation ──────────────────────────────────────────────────────

def test_investigate(client: TestClient):
    inc = _create_incident(client)
    resp = client.post("/incident/investigate", json={"incident_id": inc["id"]})
    assert resp.status_code == 200
    assert "hypotheses" in resp.json()


# ── Root Cause ─────────────────────────────────────────────────────────

def test_analyze_root_cause(client: TestClient):
    inc = _create_incident(client)
    resp = client.post(f"/incident/incidents/{inc['id']}/analyze")
    assert resp.status_code == 200
    assert "hypotheses" in resp.json()


# ── Triage ─────────────────────────────────────────────────────────────

def test_triage(client: TestClient):
    inc = _create_incident(client)
    resp = client.post(f"/incident/incidents/{inc['id']}/triage")
    assert resp.status_code == 200
    assert "facts" in resp.json()
    assert "severity_suggestion" in resp.json()


# ── Actions ────────────────────────────────────────────────────────────

def test_create_action(client: TestClient):
    inc = _create_incident(client)
    resp = client.post("/incident/actions", json={
        "incident_id": inc["id"], "action_type": "restart_service",
        "description": "Restart API server", "risk_level": "safe"})
    assert resp.status_code == 200
    assert resp.json()["action_type"] == "restart_service"


def test_approve_action(client: TestClient):
    inc = _create_incident(client)
    act = _create_action(client, inc["id"])
    resp = client.post(f"/incident/actions/{act['id']}/approve",
                       json={"approver": "bob"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_execute_action(client: TestClient):
    inc = _create_incident(client)
    act = _create_action(client, inc["id"])
    client.post(f"/incident/actions/{act['id']}/approve", json={"approver": "bob"})
    resp = client.post(f"/incident/actions/{act['id']}/execute", json={"dry_run": True})
    assert resp.status_code == 200
    assert resp.json()["dry_run_result"]["dry_run"] is True


# ── Runbooks ───────────────────────────────────────────────────────────

def test_create_runbook(client: TestClient):
    resp = client.post("/incident/runbooks", json={
        "tenant": "test", "name": "Restart API", "incident_type": "service_restart",
        "steps": [{"step": 1, "description": "Check health"}]})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Restart API"


def test_list_runbooks(client: TestClient):
    client.post("/incident/runbooks", json={"tenant": "test", "name": "RB1"})
    client.post("/incident/runbooks", json={"tenant": "test", "name": "RB2"})
    resp = client.get("/incident/runbooks", params={"tenant": "test"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


# ── Escalation ─────────────────────────────────────────────────────────

def test_create_escalation_policy(client: TestClient):
    resp = client.post("/incident/escalation-policies", json={
        "tenant": "test", "name": "SEV0 Policy", "description": "Immediate"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "SEV0 Policy"


def test_list_escalation_policies(client: TestClient):
    client.post("/incident/escalation-policies", json={"tenant": "test", "name": "P1"})
    resp = client.get("/incident/escalation-policies", params={"tenant": "test"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_check_escalation(client: TestClient):
    inc = _create_incident(client, severity="SEV0")
    resp = client.post(f"/incident/incidents/{inc['id']}/escalation/check")
    assert resp.status_code == 200
    assert "should_escalate" in resp.json()


# ── Health & Metrics ───────────────────────────────────────────────────

def test_health(client: TestClient):
    resp = client.get("/incident/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_get_anomalies(client: TestClient):
    resp = client.get("/incident/anomalies")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_slo(client: TestClient):
    resp = client.get("/incident/slo/api-gateway", params={"tenant": "test"})
    assert resp.status_code == 200
    assert "availability_target" in resp.json()


def test_get_metrics(client: TestClient):
    resp = client.get("/incident/metrics/api-gateway", params={"tenant": "test"})
    assert resp.status_code == 200
    assert "incident_count" in resp.json()


# ── Postmortem ─────────────────────────────────────────────────────────

def test_create_postmortem(client: TestClient):
    inc = _create_incident(client)
    resp = client.post("/incident/postmortems", json={
        "incident_id": inc["id"], "summary": "DB pool exhaustion",
        "root_cause": "Max connections exceeded"})
    assert resp.status_code == 200


# ── Recurrence ─────────────────────────────────────────────────────────

def test_check_recurrence(client: TestClient):
    inc = _create_incident(client)
    resp = client.get(f"/incident/recurrence/{inc['id']}")
    assert resp.status_code == 200
    assert "recurrences" in resp.json()
