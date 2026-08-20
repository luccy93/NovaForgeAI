"""Runner lifecycle tests (Volume 46)."""

from fastapi.testclient import TestClient


def test_create_runner(client: TestClient):
    resp = client.post("/delivery/runners", json={
        "name": "runner-1", "region": "us-east-1", "runner_type": "ephemeral",
        "capabilities": ["docker", "k8s"], "tenant": "testtenant",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "runner-1"
    assert data["region"] == "us-east-1"
    assert data["status"] == "available"


def test_list_runners(client: TestClient):
    client.post("/delivery/runners", json={"name": "r1", "tenant": "t"})
    client.post("/delivery/runners", json={"name": "r2", "tenant": "t"})
    resp = client.get("/delivery/runners")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_runner_heartbeat(client: TestClient):
    create_resp = client.post("/delivery/runners", json={"name": "hb-runner", "tenant": "t"})
    rid = create_resp.json()["id"]
    resp = client.post(f"/delivery/runners/{rid}/heartbeat")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_quarantine_runner(client: TestClient):
    create_resp = client.post("/delivery/runners", json={"name": "q-runner", "tenant": "t"})
    rid = create_resp.json()["id"]
    resp = client.post(f"/delivery/runners/{rid}/quarantine", params={"reason": "security issue"})
    assert resp.status_code == 200
    assert resp.json()["quarantined"] is True
    assert resp.json()["status"] == "quarantined"


def test_quarantine_heartbeat_not_found(client: TestClient):
    from uuid import uuid4
    resp = client.post(f"/delivery/runners/{uuid4()}/heartbeat")
    assert resp.status_code == 404


def test_create_runner_minimal(client: TestClient):
    resp = client.post("/delivery/runners", json={"name": "minimal"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["cpu"] == 4
    assert data["capacity"] == 1
