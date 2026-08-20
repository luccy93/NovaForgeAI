"""Deployment lifecycle tests (Volume 46)."""

from fastapi.testclient import TestClient


def _create_env(client, name="deploy-env"):
    resp = client.post("/delivery/environments", json={
        "tenant": "testtenant", "name": name, "env_type": "staging",
    })
    return resp.json()["id"]


def test_create_deployment(client: TestClient):
    eid = _create_env(client, "dep-create")
    resp = client.post("/delivery/deployments", json={
        "environment_id": eid, "strategy": "rolling", "version": "1.0.0",
        "deployed_by": "ci-bot",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["strategy"] == "rolling"
    assert data["version"] == "1.0.0"
    assert data["status"] == "pending"


def test_create_deployment_frozen_env(client: TestClient):
    eid = _create_env(client, "frozen-dep")
    client.post("/delivery/environments/" + eid + "/freeze", params={"reason": "frozen"})
    resp = client.post("/delivery/deployments", json={
        "environment_id": eid, "strategy": "rolling", "version": "1.0.0",
    })
    assert resp.status_code == 400
    assert "frozen" in resp.json()["detail"]


def test_create_deployment_locked_env(client: TestClient):
    eid = _create_env(client, "locked-dep")
    client.post("/delivery/environments/" + eid + "/lock")
    resp = client.post("/delivery/deployments", json={
        "environment_id": eid, "strategy": "rolling", "version": "1.0.0",
    })
    assert resp.status_code == 400
    assert "locked" in resp.json()["detail"]


def test_start_and_complete_deployment(client: TestClient):
    eid = _create_env(client, "dep-lifecycle")
    create_resp = client.post("/delivery/deployments", json={
        "environment_id": eid, "strategy": "canary", "version": "2.0.0",
    })
    did = create_resp.json()["id"]
    start_resp = client.post("/delivery/deployments/" + did + "/start")
    assert start_resp.json()["status"] == "in_progress"
    complete_resp = client.post("/delivery/deployments/" + did + "/complete")
    assert complete_resp.json()["status"] == "completed"
    assert complete_resp.json()["health_status"] == "healthy"


def test_approve_deployment(client: TestClient):
    eid = _create_env(client, "dep-approve")
    create_resp = client.post("/delivery/deployments", json={
        "environment_id": eid, "strategy": "rolling", "version": "1.0.0",
    })
    did = create_resp.json()["id"]
    resp = client.post("/delivery/deployments/" + did + "/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["approved_by"] == "operator"


def test_rollback_deployment(client: TestClient):
    eid = _create_env(client, "dep-rollback")
    create_resp = client.post("/delivery/deployments", json={
        "environment_id": eid, "strategy": "rolling", "version": "3.0.0",
    })
    did = create_resp.json()["id"]
    resp = client.post("/delivery/deployments/" + did + "/rollback",
                       json={"reason": "error spike"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reason"] == "error spike"
    assert data["initiated_by"] == ""


def test_list_deployments(client: TestClient):
    eid = _create_env(client, "dep-list")
    client.post("/delivery/deployments", json={"environment_id": eid, "version": "1.0.0"})
    client.post("/delivery/deployments", json={"environment_id": eid, "version": "1.1.0"})
    resp = client.get("/delivery/deployments")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_create_rollout(client: TestClient):
    eid = _create_env(client, "dep-rollout")
    create_resp = client.post("/delivery/deployments", json={
        "environment_id": eid, "version": "1.0.0",
    })
    did = create_resp.json()["id"]
    resp = client.post("/delivery/deployments/" + did + "/rollout", params={"strategy": "canary"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy"] == "canary"
    assert data["current_weight"] == 0
    assert data["target_weight"] == 100
