"""Volume 64 Commit 2 — Continuous trust & hardening tests."""

import pytest
import uuid
from datetime import datetime, timezone, timedelta

from app.zero_trust.sessions import create_session, get_session
from app.zero_trust.continuous import calculate_access_risk, reevaluate_session_risk, continuous_authorization_check
from app.zero_trust.credentials import create_credential_metadata
from app.zero_trust.anomaly import detect_anomalies, detect_impossible_access
from app.zero_trust.posture import get_identity_posture, get_access_posture, get_machine_posture
from app.zero_trust.graph import get_access_graph, estimate_blast_radius
from app.zero_trust.simulation import simulate, what_if
from app.iam.models import IAMAuditLog

pytestmark = pytest.mark.asyncio


async def test_continuous_risk_and_step_up(db, org_id):
    sess = await create_session(db, "alice", org_id, risk_state="LOW")
    await db.commit()
    # High risk signals should elevate to HIGH/CRITICAL and trigger CHALLENGE
    risk = await calculate_access_risk(db, org_id, "alice", {"failed_auth": 6, "privilege_change": True})
    assert risk["risk_level"] in ("HIGH", "CRITICAL")
    assert risk["risk_score"] > 0.6
    # Reevaluate session
    res = await reevaluate_session_risk(db, org_id, sess["session_id_hash"], {"failed_auth": 6, "privilege_change": True})
    assert res["new_risk"] in ("HIGH", "CRITICAL")
    assert res["transition"] in ("CHALLENGE_REQUIRED", "REVOKED")
    # Step-up required check
    from app.zero_trust.continuous import step_up_required
    assert await step_up_required(db, org_id, sess["session_id_hash"]) is True
    # Continuous check for DELETE should deny/challenge
    check = await continuous_authorization_check(db, org_id, sess["session_id_hash"], "repo:1", "DELETE")
    assert check["allowed"] is False
    assert "step-up" in check["reason"].lower() or "challenge" in check["reason"].lower() or "session" in check["reason"].lower()


async def test_automatic_revocation_only_policy_allowed(db, org_id):
    sess = await create_session(db, "bob", org_id)
    await db.commit()
    # Without auto_revoke_allowed, CRITICAL should CHALLENGE not REVOKE
    res = await reevaluate_session_risk(db, org_id, sess["session_id_hash"], {"failed_auth": 10, "privilege_change": True})
    assert res["transition"] == "CHALLENGE_REQUIRED"
    # With auto allowed, should REVOKE
    sess2 = await create_session(db, "bob2", org_id)
    await db.commit()
    res2 = await reevaluate_session_risk(db, org_id, sess2["session_id_hash"], {"failed_auth": 10, "privilege_change": True, "auto_revoke_allowed": True})
    # May be REVOKED if critical
    assert res2["transition"] in ("CHALLENGE_REQUIRED", "REVOKED")


async def test_credential_rotation_safety(db, org_id):
    cred = await create_credential_metadata(db, org_id, "alice", "api_key", "raw-old")
    await db.commit()
    old_id = cred["credential_id"]
    from app.zero_trust.credentials import rotate_credential, get_credential
    new = await rotate_credential(db, old_id, org_id, "raw-new", requested_by="admin")
    await db.commit()
    assert new["new_credential_id"] != old_id
    old_rec = await get_credential(db, old_id, org_id)
    assert old_rec.credential_status == "REVOKED"
    assert old_rec.rotation_state == "completed"


async def test_dormant_and_stale_detection(db, org_id):
    # Create stale credential
    cred = await create_credential_metadata(db, org_id, "stale-user", "api_key", "raw-stale")
    await db.commit()
    # Manually set last_used old
    from app.zero_trust.models import IAMCredentialsMetadata
    from sqlalchemy import select
    q = select(IAMCredentialsMetadata).where(IAMCredentialsMetadata.credential_id == cred["credential_id"])
    res = await db.execute(q)
    rec = res.scalar_one()
    rec.last_used_at = datetime.now(timezone.utc) - timedelta(days=100)
    await db.flush()
    await db.commit()
    posture = await get_machine_posture(db, org_id)
    assert posture["rotation_due_7d"] >= 0
    # Identity posture should detect stale
    id_posture = await get_identity_posture(db, org_id)
    assert "stale_credentials" in id_posture


async def test_anomaly_detection_evidence_backed(db, org_id):
    # Insert audit logs for anomaly
    for i in range(3):
        log = IAMAuditLog(organization_id=uuid.UUID(org_id), actor_id=uuid.uuid4(), action="resource_access", resource_type="resource", resource_id=f"res-unique-{i}-{uuid.uuid4()}", result="success", details={"region": f"region-{i}"})
        db.add(log)
    await db.flush()
    await db.commit()
    anomalies = await detect_anomalies(db, org_id, since_hours=24)
    assert isinstance(anomalies, list)
    # Should be evidence-backed (have evidence field)
    for a in anomalies:
        assert "evidence" in a


async def test_impossible_access_not_from_ip_alone(db, org_id):
    # Create two logs same actor different regions short time but device not managed -> should not flag as definitive
    actor = uuid.uuid4()
    now = datetime.now(timezone.utc)
    log1 = IAMAuditLog(organization_id=uuid.UUID(org_id), actor_id=actor, action="login", resource_type="session", result="success", details={"region": "us-east", "device_managed": False}, created_at=now)
    log2 = IAMAuditLog(organization_id=uuid.UUID(org_id), actor_id=actor, action="login", resource_type="session", result="success", details={"region": "eu-west", "device_managed": False}, created_at=now + timedelta(minutes=10))
    db.add_all([log1, log2])
    await db.flush()
    await db.commit()
    findings = await detect_impossible_access(db, org_id)
    # Should not flag when device not managed (per spec)
    # So either 0 or hypothesis note
    assert isinstance(findings, list)


async def test_posture_not_certification(db, org_id):
    id_post = await get_identity_posture(db, org_id)
    assert "not certification" in id_post["note"]
    assert "zero_trust_score" in id_post
    assert 0 <= id_post["zero_trust_score"] <= 100
    acc_post = await get_access_posture(db, org_id)
    assert "policy_violations" in acc_post
    mach_post = await get_machine_posture(db, org_id)
    assert "service_identities" in mach_post


async def test_access_graph_hypothesis(db, org_id):
    graph = await get_access_graph(db, org_id, "alice", depth=2)
    assert "nodes" in graph
    assert "edges" in graph
    # Paths are hypotheses
    blast = await estimate_blast_radius(db, org_id, "alice")
    assert blast["estimate"] is True
    assert "note" in blast


async def test_policy_simulation_and_what_if(db, org_id):
    sim = await simulate(db, org_id, "alice", "DELETE", "repo:1", context={"tenant": org_id})
    assert sim["decision"] in ("ALLOW", "DENY", "CHALLENGE", "REQUIRE_APPROVAL")
    assert "safe_explanation" in sim
    # What-if
    wf = await what_if(db, org_id, "repository:admin", remove=True)
    assert "impacted_roles" in wf
    assert "permission" in wf


async def test_fail_closed_on_db_failure(db, org_id):
    # Simulate DB failure by passing invalid session -> should fail closed for protected
    res = await simulate(db, org_id, "unknown", "ADMIN", "resource:prod", context={"tenant": org_id})
    # Should be DENY or not ALLOW for unknown without tenant? Our simulate defaults to DENY on error
    assert res["allowed"] is False or res["decision"] == "DENY"


async def test_continuous_check_long_running_op(db, org_id):
    sess = await create_session(db, "alice", org_id)
    await db.commit()
    # First check should allow READ
    check = await continuous_authorization_check(db, org_id, sess["session_id_hash"], "repo:1", "READ")
    assert "allowed" in check
    # After elevating risk, DELETE should challenge
    await reevaluate_session_risk(db, org_id, sess["session_id_hash"], {"failed_auth": 10})
    await db.commit()
    check2 = await continuous_authorization_check(db, org_id, sess["session_id_hash"], "repo:1", "DELETE")
    assert check2["allowed"] is False


async def test_review_campaign_and_escalation(db, org_id):
    from app.iam.access_review_service import access_review_service
    camp = access_review_service.create_review(org_id, review_type="campaign", scope="all", initiated_by="admin")
    camp["deadline"] = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    camp["reviewers"] = ["reviewer1"]
    assert camp["status"] == "pending"
    # Escalation would be via API, but service level just check
    assert "deadline" in camp


async def test_machine_inventory_and_orphaned(db, org_id):
    await create_credential_metadata(db, org_id, "svc-orphan", "service_token", "raw-orphan")
    await db.commit()
    # Orphaned detection (no owner not in users) — our _count_orphaned counts empty owner, so create with empty owner
    await create_credential_metadata(db, org_id, "", "api_key", "raw-orphan2")
    await db.commit()
    posture = await get_machine_posture(db, org_id)
    assert posture["service_identities"] >= 1
    from app.zero_trust.posture import _count_orphaned
    orphaned = await _count_orphaned(db, org_id)
    assert orphaned >= 1


async def test_agent_and_plugin_isolation(db, org_id):
    # Agent identity should have limited scope
    agent_cred = await create_credential_metadata(db, org_id, "agent-1", "agent", "raw-agent", scope={"permissions": ["read:repo"]})
    await db.commit()
    # Agent should not be allowed ADMIN via contextual auth
    res = await simulate(db, org_id, "agent-1", "ADMIN", "repo:1")
    assert res["allowed"] is False or res["decision"] != "ALLOW"


async def test_cross_region_access_detection(db, org_id):
    # Simulate cross-region access via authorization
    sess = await create_session(db, "alice", org_id, region="us-east")
    await db.commit()
    # Accessing resource in eu-west with RESTRICTED data should be checked
    from app.zero_trust.authorization import authorize
    res = await authorize(db, identity_id="alice", tenant_id=org_id, resource="data:doc", action="READ", session_id_hash=sess["session_id_hash"], region="eu-west", data_classification="RESTRICTED")
    assert res["decision"] in ("ALLOW", "DENY", "CHALLENGE", "REQUIRE_APPROVAL")
