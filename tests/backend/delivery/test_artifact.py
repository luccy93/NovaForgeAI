"""Artifact lifecycle tests (Volume 46)."""

from fastapi.testclient import TestClient


def test_create_artifact(client: TestClient):
    resp = client.post("/delivery/artifacts", json={
        "name": "app-v1.tar.gz", "artifact_type": "image",
        "hash": "sha256:abc123", "version": "1.0.0", "repository": "org/repo",
        "size_bytes": 1024000,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "app-v1.tar.gz"
    assert data["version"] == "1.0.0"


def test_list_artifacts(client: TestClient):
    client.post("/delivery/artifacts", json={"name": "a1", "artifact_type": "image", "hash": "h1"})
    client.post("/delivery/artifacts", json={"name": "a2", "artifact_type": "helm", "hash": "h2"})
    resp = client.get("/delivery/artifacts")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_list_artifacts_by_type(client: TestClient):
    client.post("/delivery/artifacts", json={"name": "img", "artifact_type": "image", "hash": "h1"})
    client.post("/delivery/artifacts", json={"name": "helm", "artifact_type": "helm", "hash": "h2"})
    resp = client.get("/delivery/artifacts", params={"artifact_type": "helm"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["artifact_type"] == "helm"


def test_verify_artifact_valid(client: TestClient):
    create_resp = client.post("/delivery/artifacts", json={
        "name": "verify-me", "artifact_type": "image", "hash": "sha256:valid",
    })
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]
    resp = client.get(f"/delivery/artifacts/{aid}/verify", params={"expected_hash": "sha256:valid"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    assert resp.json()["hash"] == "sha256:valid"


def test_verify_artifact_invalid(client: TestClient):
    create_resp = client.post("/delivery/artifacts", json={
        "name": "bad-hash", "artifact_type": "image", "hash": "sha256:actual",
    })
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]
    resp = client.get(f"/delivery/artifacts/{aid}/verify", params={"expected_hash": "sha256:wrong"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
    assert "hash mismatch" in resp.json()["error"]
