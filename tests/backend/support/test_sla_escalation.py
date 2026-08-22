"""SLA and escalation tests (Volume 54)."""
import pytest
from datetime import datetime, timezone, timedelta
from app.support.sla_service import SLAService
from app.support.escalation_service import EscalationService
from app.support.constants import SLAState

@pytest.fixture()
def sla_svc(): return SLAService()

@pytest.fixture()
def esc_svc(): return EscalationService()

class TestSLAPolicies:
    def test_create_policy(self, sla_svc):
        p = sla_svc.create_policy("org1", "High SLA", "high", 60, 480)
        assert p["id"] and p["name"] == "High SLA" and p["is_active"] is True
    def test_get_policy(self, sla_svc):
        p = sla_svc.create_policy("org1", "Test", "normal", 120, 1440)
        assert sla_svc.get_policy(p["id"]) is not None
    def test_list_policies(self, sla_svc):
        sla_svc.create_policy("org1", "P1", "high", 60, 480)
        sla_svc.create_policy("org1", "P2", "low", 2880, 10080)
        assert len(sla_svc.list_policies("org1")) == 2
    def test_find_policy(self, sla_svc):
        sla_svc.create_policy("org1", "High", "high", 60, 480)
        assert sla_svc.find_policy("org1", "high") is not None
    def test_find_policy_not_found(self, sla_svc):
        assert sla_svc.find_policy("org1", "nonexistent") is None

class TestSLATracking:
    def test_start_tracking(self, sla_svc):
        t = sla_svc.start_tracking("t1", priority="normal")
        assert t["ticket_id"] == "t1" and t["sla_state"] == SLAState.ON_TRACK.value
    def test_get_tracking(self, sla_svc):
        sla_svc.start_tracking("t2", priority="high")
        assert sla_svc.get_tracking("t2") is not None
    def test_check_sla_on_track(self, sla_svc):
        sla_svc.start_tracking("t3", priority="low")
        assert sla_svc.check_sla_status("t3")["sla_state"] == SLAState.ON_TRACK.value
    def test_mark_first_response_met(self, sla_svc):
        sla_svc.start_tracking("t4", priority="normal")
        sla_svc.mark_first_response_met("t4")
        assert sla_svc.get_tracking("t4")["first_response_met"] is True
    def test_mark_resolution_met(self, sla_svc):
        sla_svc.start_tracking("t5", priority="normal")
        sla_svc.mark_resolution_met("t5")
        assert sla_svc.get_tracking("t5")["resolution_met"] is True
    def test_pause_resume(self, sla_svc):
        sla_svc.start_tracking("t6", priority="normal")
        sla_svc.pause_tracking("t6", reason="waiting_customer")
        assert sla_svc.get_tracking("t6")["sla_state"] == SLAState.PAUSED.value
        sla_svc.resume_tracking("t6")
        assert sla_svc.get_tracking("t6")["sla_state"] == SLAState.ON_TRACK.value
    def test_start_with_plan_tier(self, sla_svc):
        t = sla_svc.start_tracking("t7", priority="normal", plan_tier="enterprise")
        assert t["resolution_deadline"]
    def test_check_all_active(self, sla_svc):
        sla_svc.start_tracking("ta", priority="normal")
        result = sla_svc.check_all_active()
        assert "breached" in result and "at_risk" in result

class TestSLASummary:
    def test_summary(self, sla_svc):
        sla_svc.start_tracking("ts1", priority="normal")
        sla_svc.start_tracking("ts2", priority="high")
        s = sla_svc.get_sla_summary()
        assert s["total"] == 2 and s["compliance_rate"] >= 0

class TestSLATelemetry:
    def test_telemetry(self, sla_svc):
        sla_svc.create_policy("o", "T", "normal", 60, 480)
        sla_svc.start_tracking("tx", priority="normal")
        t = sla_svc.get_telemetry()
        assert t["policies_created"] >= 1 and t["tracking_started"] >= 1

class TestEscalationService:
    def test_create_escalation(self, esc_svc):
        e = esc_svc.create_escalation("t1", "time_based", "tier2", reason="SLA breach")
        assert e["id"] and e["to_level"] == "tier2"
    def test_get_escalation(self, esc_svc):
        e = esc_svc.create_escalation("t2", "severity_based", "oncall")
        assert esc_svc.get_escalation(e["id"]) is not None
    def test_list_escalations(self, esc_svc):
        esc_svc.create_escalation("t3", "time_based", "tier2")
        assert len(esc_svc.list_escalations(ticket_id="t3")) == 1
    def test_resolve_escalation(self, esc_svc):
        e = esc_svc.create_escalation("t4", "customer_requested", "tier3")
        esc_svc.resolve_escalation(e["id"], resolved_by="agent-1")
        assert esc_svc.get_escalation(e["id"])["is_resolved"] is True
    def test_should_escalate_time(self, esc_svc):
        assert esc_svc.should_escalate_time("breached", "normal", 0) is True
    def test_should_escalate_urgent(self, esc_svc):
        assert esc_svc.should_escalate_time("on_track", "critical", 0) is True
    def test_should_not_escalate(self, esc_svc):
        assert esc_svc.should_escalate_time("on_track", "low", 0) is False
    def test_on_call(self, esc_svc):
        now = datetime.now(timezone.utc)
        esc_svc.set_on_call("team1", "agent1", now.isoformat(), (now + timedelta(hours=8)).isoformat())
        assert esc_svc.get_on_call("team1") is not None
    def test_escalation_policies(self, esc_svc):
        p = esc_svc.create_escalation_policy("org1", "SLA breach escalation", "time_based",
                                              {"sla_state": "breached"}, "tier2")
        assert p["id"]
    def test_telemetry(self, esc_svc):
        esc_svc.create_escalation("t", "time_based", "tier2")
        assert esc_svc.get_telemetry()["escalations"] >= 1
