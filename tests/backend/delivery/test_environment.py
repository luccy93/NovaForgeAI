"""Environment lifecycle tests (Volume 46)."""

from fastapi.testclient import TestClient


def test_create_environment(client: TestClient):
    resp = client.post("/delivery/environments", json={
        "tenant": "testtenant", "name": "staging", "env_type": "staging",
        "region": "us-east-1", "cluster": "eks-prod",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "staging"
    assert data["env_type"] == "staging"
    assert data["locked"] is False
    assert data["frozen"] is False


def test_list_environments(client: TestClient):
    client.post("/delivery/environments", json={"tenant": "t", "name": "dev", "env_type": "development"})
    client.post("/delivery/environments", json={"tenant": "t", "name": "prod", "env_type": "production"})
    resp = client.get("/delivery/environments")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_list_environments_by_type(client: TestClient):
    client.post("/delivery/environments", json={"tenant": "t", "name": "d1", "env_type": "development"})
    client.post("/delivery/environments", json={"tenant": "t", "name": "p1", "env_type": "production"})
    resp = client.get("/delivery/environments", params={"env_type": "production"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["env_type"] == "production"


def test_lock_environment(client: TestClient):
    create_resp = client.post("/delivery/environments", json={
        "tenant": "t", "name": "lock-test", "env_type": "staging",
    })
    eid = create_resp.json()["id"]
    resp = client.post("/delivery/environments/" + eid + "/lock")
    assert resp.status_code == 200
    assert resp.json()["locked"] is True


def test_freeze_environment(client: TestClient):
    create_resp = client.post("/delivery/environments", json={
        "tenant": "t", "name": "freeze-test", "env_type": "staging",
    })
    eid = create_resp.json()["id"]
    resp = client.post("/delivery/environments/" + eid + "/freeze", params={"reason": "incident"})
    assert resp.status_code == 200
    assert resp.json()["frozen"] is True
    assert resp.json()["freeze_reason"] == "incident"


def test_can_deploy(client: TestClient):
    create_resp = client.post("/delivery/environments", json={
        "tenant": "t", "name": "deploy-ok", "env_type": "dev",
    })
    eid = create_resp.json()["id"]
    resp = client.get("/delivery/environments/" + eid + "/can-deploy")
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


def test_can_deploy_frozen(client: TestClient):
    create_resp = client.post("/delivery/environments", json={
        "tenant": "t", "name": "frozen-deploy", "env_type": "staging",
    })
    eid = create_resp.json()["id"]
    client.post("/delivery/environments/" + eid + "/freeze", params={"reason": "frozen"})
    resp = client.get("/delivery/environments/" + eid + "/can-deploy")
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
    assert "frozen" in resp.json()["reason"]


def test_list_environments_by_tenant(client: TestClient):
    client.post("/delivery/environments", json={"tenant": "ta", "name": "a1", "env_type": "dev"})
    client.post("/delivery/environments", json={"tenant": "tb", "name": "b1", "env_type": "dev"})
    resp = client.get("/delivery/environments", params={"tenant": "ta"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
