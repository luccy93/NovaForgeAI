"""Release lifecycle tests (Volume 46)."""

from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_release(client: TestClient):
    resp = client.post("/delivery/releases", json={
        "tenant": "testtenant", "project": "proj1", "repository": "org/repo",
        "version": "1.0.0", "release_channel": "stable", "created_by": "ci",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == "1.0.0"
    assert data["status"] == "draft"
    assert data["release_channel"] == "stable"


def test_list_releases(client: TestClient):
    client.post("/delivery/releases", json={
        "tenant": "t", "project": "p", "repository": "r", "version": "1.0.0",
    })
    client.post("/delivery/releases", json={
        "tenant": "t", "project": "p", "repository": "r", "version": "1.1.0",
    })
    resp = client.get("/delivery/releases")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_promote_release(client: TestClient):
    create_resp = client.post("/delivery/releases", json={
        "tenant": "t", "project": "p", "repository": "r", "version": "2.0.0",
    })
    rid = create_resp.json()["id"]
    resp = client.post("/delivery/releases/" + rid + "/promote", params={"environment": "staging"})
    assert resp.status_code == 200
    data = resp.json()
    assert "staging" in data["deployed_environments"]
    assert data["status"] == "promoted"


def test_promote_release_not_found(client: TestClient):
    resp = client.post("/delivery/releases/" + str(uuid4()) + "/promote",
                       params={"environment": "prod"})
    assert resp.status_code == 404


def test_list_releases_by_channel(client: TestClient):
    client.post("/delivery/releases", json={
        "tenant": "t", "project": "p", "repository": "r",
        "version": "1.0.0", "release_channel": "stable",
    })
    client.post("/delivery/releases", json={
        "tenant": "t", "project": "p", "repository": "r",
        "version": "1.1.0-rc1", "release_channel": "beta",
    })
    resp = client.get("/delivery/releases", params={"release_channel": "beta"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["release_channel"] == "beta"
