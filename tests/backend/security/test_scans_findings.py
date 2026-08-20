"""Scan and Findings lifecycle tests (Volume 47)."""

from fastapi.testclient import TestClient


def test_create_scan(client: TestClient):
    resp = client.post("/security/scans", json={
        "tenant": "test", "scan_type": "sast", "target_type": "repository",
        "target_id": "org/repo", "repository": "org/repo",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_type"] == "sast"
    assert data["status"] == "pending"


def test_list_scans(client: TestClient):
    client.post("/security/scans", json={
        "tenant": "test", "scan_type": "secrets", "target_type": "repository",
        "target_id": "org/repo",
    })
    resp = client.get("/security/scans", params={"tenant": "test"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_scan(client: TestClient):
    create_resp = client.post("/security/scans", json={
        "tenant": "test", "scan_type": "full", "target_type": "repository",
        "target_id": "org/repo",
    })
    scan_id = create_resp.json()["id"]
    resp = client.get(f"/security/scans/{scan_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == scan_id


def test_get_scan_not_found(client: TestClient):
    from uuid import uuid4
    resp = client.get(f"/security/scans/{uuid4()}")
    assert resp.status_code == 404


def test_findings_summary(client: TestClient):
    resp = client.get("/security/findings/summary", params={"tenant": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "by_severity" in data


def test_scan_secrets(client: TestClient):
    resp = client.post("/security/secrets/scan", json={
        "tenant": "test", "content": "AWS_ACCESS_KEY = AKIAIOSFODNN7EXAMPLE",
        "file_path": "config.py", "repository": "org/repo",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["findings_count"] >= 1
    assert data["findings"][0]["rule"] == "aws_access_key"


def test_scan_secrets_no_findings(client: TestClient):
    resp = client.post("/security/secrets/scan", json={
        "tenant": "test", "content": "x = 42\nprint('hello')",
    })
    assert resp.status_code == 200
    assert resp.json()["findings_count"] == 0


def test_scan_sast(client: TestClient):
    resp = client.post("/security/sast/scan", json={
        "tenant": "test", "content": "result = eval(user_input)",
        "file_path": "app.py", "repository": "org/repo",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["findings_count"] >= 1
    assert any(f["rule"] == "code_injection" for f in data["findings"])


def test_scan_sast_insecure_random(client: TestClient):
    resp = client.post("/security/sast/scan", json={
        "tenant": "test", "content": "import random\ntoken = random.randint(100000, 999999)",
        "file_path": "auth.py",
    })
    assert resp.status_code == 200
    assert resp.json()["findings_count"] >= 1


def test_scan_iac_dockerfile(client: TestClient):
    resp = client.post("/security/iac/scan", json={
        "tenant": "test", "files": {"Dockerfile": "FROM ubuntu:latest\nUSER root\nRUN apt-get install curl"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["findings_count"] >= 1
    rules = [f["rule"] for f in data["findings"]]
    assert "dockerfile_latest_tag" in rules


def test_scan_iac_kubernetes(client: TestClient):
    resp = client.post("/security/iac/scan", json={
        "tenant": "test", "files": {"pod.yaml": "apiVersion: v1\nkind: Pod\nspec:\n  containers:\n  - name: app\n    securityContext:\n      privileged: true"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["findings_count"] >= 1
    assert any(f["rule"] == "k8s_privileged_container" for f in data["findings"])


def test_scan_iac_terraform(client: TestClient):
    resp = client.post("/security/iac/scan", json={
        "tenant": "test", "files": {"main.tf": 'resource "aws_s3_bucket" "data" {\n  acl = "public-read"\n}'},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["findings_count"] >= 1


def test_risk_summary(client: TestClient):
    resp = client.get("/security/risk/summary", params={"tenant": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_score" in data
    assert "risk_level" in data


def test_risk_score(client: TestClient):
    resp = client.get("/security/risk/score", params={"tenant": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "level" in data


def test_security_search(client: TestClient):
    resp = client.get("/security/search", params={"tenant": "test", "q": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
