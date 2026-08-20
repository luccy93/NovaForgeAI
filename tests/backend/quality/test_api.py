"""Quality Engine API tests (Volume 48)."""

from fastapi.testclient import TestClient


def test_create_review(client: TestClient):
    resp = client.post("/quality/reviews", json={
        "tenant": "test", "repo_id": "org/repo", "review_type": "file",
        "target_ref": "app.py", "mode": "standard",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["mode"] == "standard"


def test_list_reviews(client: TestClient):
    client.post("/quality/reviews", json={"tenant": "test", "repo_id": "r1"})
    client.post("/quality/reviews", json={"tenant": "test", "repo_id": "r1"})
    resp = client.get("/quality/reviews", params={"tenant": "test", "repo_id": "r1"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_review(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


def test_get_review_not_found(client: TestClient):
    from uuid import uuid4
    resp = client.get(f"/quality/reviews/{uuid4()}")
    assert resp.status_code == 404


def test_review_status(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_cancel_review(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.post(f"/quality/reviews/{rid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_get_report(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "findings" in data


def test_get_inline_review(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}/inline")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_pr_summary(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_level" in data


def test_list_findings(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}/findings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_dedup(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}/findings/dedup")
    assert resp.status_code == 200


def test_evaluate_gates(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.post(f"/quality/reviews/{rid}/gates/evaluate")
    assert resp.status_code == 200
    data = resp.json()
    assert "verdict" in data


def test_get_gates(client: TestClient):
    create = client.post("/quality/reviews", json={"tenant": "test"})
    rid = create.json()["id"]
    resp = client.get(f"/quality/reviews/{rid}/gates")
    assert resp.status_code == 200


def test_create_baseline(client: TestClient):
    resp = client.post("/quality/baselines", json={
        "tenant": "test", "repo_id": "r1", "name": "v1",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "v1"


def test_list_baselines(client: TestClient):
    client.post("/quality/baselines", json={"tenant": "test", "repo_id": "r1", "name": "b1"})
    resp = client.get("/quality/baselines", params={"tenant": "test"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_baseline(client: TestClient):
    client.post("/quality/baselines", json={"tenant": "test", "repo_id": "r1", "name": "current"})
    resp = client.get("/quality/baselines/current", params={"tenant": "test", "repo_id": "r1"})
    assert resp.status_code == 200


def test_get_baseline_not_found(client: TestClient):
    resp = client.get("/quality/baselines/nonexistent", params={"tenant": "test"})
    assert resp.status_code == 404


def test_delete_baseline(client: TestClient):
    client.post("/quality/baselines", json={"tenant": "test", "repo_id": "r1", "name": "to_delete"})
    resp = client.delete("/quality/baselines/to_delete", params={"tenant": "test", "repo_id": "r1"})
    assert resp.status_code == 200


def test_analyze_file(client: TestClient):
    resp = client.post("/quality/analyze/file", json={
        "file_path": "app.py",
        "content": "def my_func():\n    pass",
        "tenant": "test",
        "mode": "quick",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "review_id" in data
    assert "quality_scores" in data


def test_analyze_commit(client: TestClient):
    resp = client.post("/quality/analyze/commit", json={
        "repo_id": "org/repo", "commit_sha": "abc123", "tenant": "test",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_analyze_pr(client: TestClient):
    resp = client.post("/quality/analyze/pr", json={
        "repo_id": "org/repo", "pr_number": 42, "tenant": "test",
    })
    assert resp.status_code == 200
    assert resp.json()["pr_number"] == 42
