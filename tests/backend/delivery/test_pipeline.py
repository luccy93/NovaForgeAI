"""Pipeline lifecycle tests (Volume 46)."""

from fastapi.testclient import TestClient


def test_create_pipeline(client: TestClient):
    resp = client.post("/delivery/pipelines", json={
        "tenant": "testtenant", "project": "proj1", "repository": "org/repo",
        "branch": "main", "name": "CI Pipeline", "trigger": "push",
        "environment": "development", "deployment_strategy": "rolling",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "CI Pipeline"
    assert data["project"] == "proj1"
    assert data["repository"] == "org/repo"


def test_list_pipelines(client: TestClient):
    client.post("/delivery/pipelines", json={
        "tenant": "testtenant", "project": "proj1", "repository": "org/repo",
        "branch": "main", "name": "Pipeline A",
    })
    resp = client.get("/delivery/pipelines")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


def test_list_pipelines_by_tenant(client: TestClient):
    client.post("/delivery/pipelines", json={
        "tenant": "tenantA", "project": "p1", "repository": "org/repo",
        "branch": "main", "name": "T1 Pipeline",
    })
    client.post("/delivery/pipelines", json={
        "tenant": "tenantB", "project": "p2", "repository": "org/repo2",
        "branch": "main", "name": "T2 Pipeline",
    })
    resp = client.get("/delivery/pipelines", params={"tenant": "tenantA"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["project"] == "p1" for p in data)


def test_get_pipeline(client: TestClient):
    create_resp = client.post("/delivery/pipelines", json={
        "tenant": "testtenant", "project": "proj1", "repository": "org/repo",
        "branch": "main", "name": "Get Test",
    })
    pid = create_resp.json()["id"]
    resp = client.get(f"/delivery/pipelines/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


def test_get_pipeline_not_found(client: TestClient):
    from uuid import uuid4
    resp = client.get(f"/delivery/pipelines/{uuid4()}")
    assert resp.status_code == 404


def test_trigger_pipeline_run(client: TestClient):
    create_resp = client.post("/delivery/pipelines", json={
        "tenant": "testtenant", "project": "proj1", "repository": "org/repo",
        "branch": "main", "name": "Run Test",
    })
    pid = create_resp.json()["id"]
    resp = client.post(f"/delivery/pipelines/{pid}/run", json={
        "commit_sha": "abc123", "trigger": "push", "actor": "dev",
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "queued"


def test_trigger_run_not_found(client: TestClient):
    from uuid import uuid4
    resp = client.post(f"/delivery/pipelines/{uuid4()}/run", json={"commit_sha": "x"})
    assert resp.status_code == 404


def test_list_pipeline_runs(client: TestClient):
    create_resp = client.post("/delivery/pipelines", json={
        "tenant": "t", "project": "p", "repository": "r", "branch": "main", "name": "Runs Test",
    })
    pid = create_resp.json()["id"]
    client.post(f"/delivery/pipelines/{pid}/run", json={"commit_sha": "a"})
    client.post(f"/delivery/pipelines/{pid}/run", json={"commit_sha": "b"})
    resp = client.get(f"/delivery/pipelines/{pid}/runs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
