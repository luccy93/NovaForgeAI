"""Support integration tests (Volume 54)."""
import pytest
import asyncio
from app.support.ticket_service import TicketService
from app.support.message_service import MessageService
from app.support.classification_service import ClassificationService
from app.support.routing_service import RoutingService
from app.support.knowledge_service import KnowledgeService
from app.support.sla_service import SLAService
from app.support.escalation_service import EscalationService
from app.support.automation_service import AutomationService
from app.support.incident_correlation import IncidentCorrelationService
from app.support.analytics_service import SupportAnalyticsService
from app.support.status_page_service import StatusPageService
from app.support.constants import TicketStatus

@pytest.fixture()
def ticket_svc(): return TicketService()
@pytest.fixture()
def msg_svc(): return MessageService()
@pytest.fixture()
def cls_svc(): return ClassificationService()
@pytest.fixture()
def routing_svc(): return RoutingService()
@pytest.fixture()
def knowledge_svc(): return KnowledgeService()
@pytest.fixture()
def sla_svc(): return SLAService()
@pytest.fixture()
def esc_svc(): return EscalationService()
@pytest.fixture()
def auto_svc(): return AutomationService()
@pytest.fixture()
def corr_svc(): return IncidentCorrelationService()
@pytest.fixture()
def analytics_svc(): return SupportAnalyticsService()
@pytest.fixture()
def status_svc(): return StatusPageService()


class TestEndToEndLifecycle:
    def test_full_lifecycle(self, ticket_svc, msg_svc, cls_svc, routing_svc, sla_svc):
        t = ticket_svc.create_ticket("org1", "cust-1", "API bug", description="500 error")
        cls_result = cls_svc.classify_ticket(t["subject"], t["description"])
        assert cls_result["category"]
        sla_svc.start_tracking(t["id"], priority=t["priority"])
        routing = routing_svc.route_ticket(t["id"], cls_result["category"], t["priority"])
        assert routing["team"]
        ticket_svc.transition_ticket(t["id"], "open")
        msg_svc.create_message(t["id"], "cust-1", "Please help", sender_type="customer")
        ticket_svc.mark_first_response(t["id"])
        msg_svc.create_message(t["id"], "agent-1", "We are looking into it", sender_type="agent")
        sla_svc.mark_first_response_met(t["id"])
        ticket_svc.transition_ticket(t["id"], "in_progress")
        ticket_svc.transition_ticket(t["id"], "resolved")
        sla_svc.mark_resolution_met(t["id"])
        ticket_svc.transition_ticket(t["id"], "closed")
        final = ticket_svc.get_ticket(t["id"])
        assert final["status"] == "closed"
        assert final["resolved_at"] is not None

    def test_classification_and_routing(self, ticket_svc, cls_svc, routing_svc):
        t = ticket_svc.create_ticket("org1", "cust-1", "Security vulnerability found")
        cls_result = cls_svc.classify_ticket(t["subject"], t["description"])
        routing = routing_svc.route_ticket(t["id"], cls_result["category"], t["priority"])
        assert routing["team"]

    def test_knowledge_and_ticket(self, knowledge_svc, ticket_svc):
        knowledge_svc.create_article("org1", title="How to deploy", content="Deploy steps", category="faq")
        t = ticket_svc.create_ticket("org1", "cust-1", "How to deploy")
        results = knowledge_svc.search_articles("deploy", tenant_id="org1", status=None)
        assert len(results) >= 1

    def test_escalation_flow(self, ticket_svc, sla_svc, esc_svc):
        t = ticket_svc.create_ticket("org1", "cust-1", "Critical issue", priority="critical")
        sla_svc.start_tracking(t["id"], priority="critical")
        ticket_svc.transition_ticket(t["id"], "open")
        ticket_svc.transition_ticket(t["id"], "escalated")
        esc = esc_svc.create_escalation(t["id"], "severity_based", "oncall", reason="Critical issue")
        assert esc["to_level"] == "oncall"

    def test_automation_flow(self, auto_svc):
        run = auto_svc.create_run("t1", "auto_classify")
        assert run["status"] == "completed" or run["status"] == "pending"
        auto_svc.execute_run(run["id"], output_data={"category": "bug"})
        assert auto_svc.get_run(run["id"])["status"] == "completed"

    def test_incident_correlation(self, corr_svc):
        active = [{"id": "inc-1", "service": "api", "environment": "prod", "title": "API outage", "severity": "s1"}]
        result = corr_svc.correlate_ticket("t1", "org1", service_affected="api",
                                           environment="prod", active_incidents=active)
        assert len(result["matches"]) >= 1

    def test_full_ticket_with_messages(self, ticket_svc, msg_svc):
        t = ticket_svc.create_ticket("org1", "cust-1", "Help needed")
        msg_svc.create_message(t["id"], "cust-1", "I need help with billing")
        msg_svc.create_message(t["id"], "agent-1", "Let me check", sender_type="agent")
        msgs = msg_svc.list_messages(t["id"])
        assert len(msgs) == 2
        assert msg_svc.count_messages(t["id"]) == 2

    def test_internal_notes_hidden(self, msg_svc, ticket_svc):
        t = ticket_svc.create_ticket("org1", "cust-1", "Question")
        msg_svc.create_message(t["id"], "agent-1", "Internal note", visibility="internal")
        msg_svc.create_message(t["id"], "agent-1", "Public reply", visibility="customer")
        customer_msgs = msg_svc.list_messages(t["id"], include_internal=False)
        assert len(customer_msgs) == 1
        internal_msgs = msg_svc.get_internal_messages(t["id"])
        assert len(internal_msgs) == 1

    def test_sla_with_ticket(self, ticket_svc, sla_svc):
        t = ticket_svc.create_ticket("org1", "cust-1", "Bug report", priority="high")
        sla_svc.start_tracking(t["id"], priority="high")
        sla = sla_svc.get_tracking(t["id"])
        assert sla["first_response_deadline"]
        sla_svc.mark_first_response_met(t["id"])
        sla_svc.mark_resolution_met(t["id"])
        updated = sla_svc.get_tracking(t["id"])
        assert updated["first_response_met"] is True

    def test_knowledge_gaps(self, knowledge_svc):
        gaps = knowledge_svc.detect_knowledge_gaps("org1")
        assert len(gaps) > 0

    def test_status_page(self, status_svc):
        public = status_svc.get_public_status()
        assert public["overall_status"] == "operational"
        assert len(public["services"]) > 0

    def test_analytics(self, ticket_svc, analytics_svc):
        ticket_svc.create_ticket("org1", "cust-1", "T1")
        ticket_svc.create_ticket("org1", "cust-1", "T2")
        result = analytics_svc.get_ticket_analytics(ticket_svc, "org1")
        assert result["total"] == 2

    def test_feedback_flow(self, analytics_svc):
        record = analytics_svc.record_feedback("t1", 5, "csat", comment="Great!")
        assert record["rating"] == 5
        csat = analytics_svc.get_csat_summary()
        assert csat["total_responses"] == 1
        assert csat["avg_rating"] == 5.0

    def test_routing_teams(self, routing_svc):
        routing_svc.route_ticket("t1", "billing")
        routing_svc.route_ticket("t2", "bug", severity="s1")
        queues = routing_svc.get_team_queues()
        assert len(queues) >= 2
