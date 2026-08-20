"""Preview environment and approval tests (Volume 46)."""

from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_preview(client: TestClient):
    resp = client.post("/delivery/previews", json={
        "tenant": "testtenant", "name": "pr-preview",
        "repository": "org/repo", "branch": "feat/x", "pr_number": 42,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["pr_number"] == 42
    assert data["branch"] == "feat/x"
    assert data["status"] == "creating"
    assert "preview.novaforge.dev" in data["url"]


def test_list_previews(client: TestClient):
    client.post("/delivery/previews", json={
        "tenant": "t", "name": "p1", "repository": "r", "branch": "main",
    })
    resp = client.get("/delivery/previews")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_list_previews_by_pr(client: TestClient):
    client.post("/delivery/previews", json={
        "tenant": "t", "name": "p1", "repository": "r1", "branch": "a", "pr_number": 1,
    })
    client.post("/delivery/previews", json={
        "tenant": "t", "name": "p2", "repository": "r1", "branch": "b", "pr_number": 2,
    })
    resp = client.get("/delivery/previews", params={"pr_number": 1})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["pr_number"] == 1


def test_destroy_preview(client: TestClient):
    create_resp = client.post("/delivery/previews", json={
        "tenant": "t", "name": "to-destroy", "repository": "r", "branch": "main",
    })
    pid = create_resp.json()["id"]
    resp = client.delete("/delivery/previews/" + pid)
    assert resp.status_code == 200
    assert resp.json()["status"] == "destroyed"


def test_destroy_preview_not_found(client: TestClient):
    resp = client.delete("/delivery/previews/" + str(uuid4()))
    assert resp.status_code == 404


def test_request_approval(client: TestClient):
    resp = client.post("/delivery/approvals", params={
        "requested_by": "dev", "gate_type": "manual",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "pending"
    assert data["requested_by"] == "dev"


def test_approve_decision(client: TestClient):
    create_resp = client.post("/delivery/approvals", params={
        "requested_by": "dev", "gate_type": "manual",
    })
    aid = create_resp.json()["id"]
    resp = client.post("/delivery/approvals/" + aid + "/approve",
                       json={"decided_by": "lead", "reason": "looks good"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "approved"
    assert data["decided_by"] == "lead"
    assert data["reason"] == "looks good"


def test_reject_decision(client: TestClient):
    create_resp = client.post("/delivery/approvals", params={
        "requested_by": "dev", "gate_type": "security",
    })
    aid = create_resp.json()["id"]
    resp = client.post("/delivery/approvals/" + aid + "/reject",
                       json={"decided_by": "sec-lead", "reason": "security concerns"})
    assert resp.status_code == 200
    assert resp.json()["decision"] == "rejected"
    assert resp.json()["reason"] == "security concerns"


def test_list_approvals(client: TestClient):
    client.post("/delivery/approvals", params={"requested_by": "dev", "gate_type": "manual"})
    client.post("/delivery/approvals", params={"requested_by": "ci", "gate_type": "auto"})
    resp = client.get("/delivery/approvals")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_approve_not_found(client: TestClient):
    resp = client.post("/delivery/approvals/" + str(uuid4()) + "/approve",
                       json={"decided_by": "x", "reason": "x"})
    assert resp.status_code == 404
