"""Policy, remediation, reporting, dashboard tests (Volume 47)."""

from fastapi.testclient import TestClient


def test_create_policy(client: TestClient):
    resp = client.post("/security/policies", json={
        "tenant": "test", "name": "block_critical",
        "description": "Block critical findings",
        "conditions": {"severity": "critical"},
        "actions": {"decision": "block"},
        "priority": 100,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "block_critical"
    assert data["policy_type"] == "gate"


def test_list_policies(client: TestClient):
    client.post("/security/policies", json={
        "tenant": "test", "name": "policy1",
    })
    resp = client.get("/security/policies", params={"tenant": "test"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_evaluate_policies(client: TestClient):
    client.post("/security/policies", json={
        "tenant": "test", "name": "block_crit",
        "conditions": {"severity": "critical"},
        "actions": {"decision": "block"},
    })
    resp = client.post("/security/policies/evaluate", json={
        "tenant": "test", "target_type": "repository", "target_id": "org/repo",
        "findings": [{"severity": "critical", "rule": "aws_key", "finding_type": "secret"}],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_decision"] == "block"
    assert len(data["evaluations"]) >= 1


def test_evaluate_policies_allow(client: TestClient):
    client.post("/security/policies", json={
        "tenant": "test", "name": "block_crit2",
        "conditions": {"severity": "critical"},
        "actions": {"decision": "block"},
    })
    resp = client.post("/security/policies/evaluate", json={
        "tenant": "test", "target_type": "repository", "target_id": "org/repo",
        "findings": [{"severity": "low", "rule": "info", "finding_type": "sast"}],
    })
    assert resp.status_code == 200
    assert resp.json()["overall_decision"] == "allow"


def test_generate_report_executive(client: TestClient):
    resp = client.get("/security/reports/executive", params={"tenant": "test", "days": 30})
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "executive"
    assert "summary" in data


def test_generate_report_dependency(client: TestClient):
    resp = client.get("/security/reports/dependency", params={"tenant": "test"})
    assert resp.status_code == 200
    assert resp.json()["report_type"] == "dependency"


def test_generate_report_unknown(client: TestClient):
    resp = client.get("/security/reports/unknown_type", params={"tenant": "test"})
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_dashboard(client: TestClient):
    resp = client.get("/security/dashboard", params={"tenant": "test", "days": 30})
    assert resp.status_code == 200
    data = resp.json()
    assert "severity_breakdown" in data
    assert "status_breakdown" in data
    assert "gate_status" in data
    assert "compliance_score" in data


def test_remediation_lifecycle(client: TestClient):
    scan_resp = client.post("/security/scans", json={
        "tenant": "test", "scan_type": "sast", "target_type": "repository", "target_id": "org/repo",
    })
    scan_id = scan_resp.json()["id"]
    sast_resp = client.post("/security/sast/scan", json={
        "tenant": "test", "content": "eval(user_input)",
        "file_path": "app.py", "repository": "org/repo",
    })
    finding_id = sast_resp.json()["findings"][0]["id"]

    rem_resp = client.post("/security/remediate", json={
        "tenant": "test", "finding_id": finding_id, "approach": "Replace eval with ast.literal_eval",
    })
    assert rem_resp.status_code == 200
    rem_id = rem_resp.json()["id"]
    assert rem_resp.json()["status"] == "pending"

    get_resp = client.get(f"/security/remediation/{rem_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == rem_id

    list_resp = client.get("/security/remediation", params={"tenant": "test"})
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1


def test_provenance_record_and_get(client: TestClient):
    resp = client.post("/security/provenance/record", json={
        "tenant": "test", "chain_id": "chain-1",
        "source_type": "git", "source_id": "commit-abc",
        "target_type": "artifact", "target_id": "artifact-v1",
        "relationship": "produced_by", "signed": True, "signature_valid": True,
    })
    assert resp.status_code == 200
    chain_id = resp.json()["chain_id"]

    get_resp = client.get(f"/security/provenance/{chain_id}", params={"tenant": "test"})
    assert get_resp.status_code == 200
    assert len(get_resp.json()["records"]) >= 1


def test_verify_slsa(client: TestClient):
    for i in range(3):
        client.post("/security/provenance/record", json={
            "tenant": "test", "chain_id": "chain-slsa",
            "source_type": "git", "source_id": f"commit-{i}",
            "target_type": "artifact", "target_id": f"artifact-{i}",
            "relationship": "produced_by", "signed": True, "signature_valid": True,
            "builder": "github-actions",
        })
    resp = client.post("/security/provenance/verify-slsa", params={"chain_id": "chain-slsa", "tenant": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] >= 1
    assert data["has_signed_artifacts"] is True


def test_dependency_scan(client: TestClient):
    resp = client.post("/security/dependencies/scan", json={
        "tenant": "test", "files": {
            "requirements.txt": "requests==2.28.0\nflask==2.2.0\npillow==9.0.0",
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["findings_count"] >= 1


def test_search(client: TestClient):
    client.post("/security/sast/scan", json={
        "tenant": "test", "content": "eval(x)",
        "file_path": "test.py",
    })
    resp = client.get("/security/search", params={"tenant": "test", "q": "code_injection"})
    assert resp.status_code == 200
    assert len(resp.json()["results"]) >= 1
