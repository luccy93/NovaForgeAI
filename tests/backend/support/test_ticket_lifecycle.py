"""Ticket lifecycle tests (Volume 54)."""

import pytest
from app.support.ticket_service import TicketService
from app.support.constants import TicketStatus, TicketPriority


@pytest.fixture()
def svc():
    return TicketService()


@pytest.fixture()
def org_id():
    return "org-test-001"


class TestTicketCreation:
    def test_create_ticket(self, svc, org_id):
        ticket = svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                                   subject="Test issue", description="Details here")
        assert ticket["id"]
        assert ticket["subject"] == "Test issue"
        assert ticket["status"] == TicketStatus.NEW.value
        assert ticket["priority"] == TicketPriority.NORMAL.value
        assert ticket["tenant_id"] == org_id

    def test_create_ticket_with_priority(self, svc, org_id):
        ticket = svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                                   subject="Urgent", priority="urgent")
        assert ticket["priority"] == "urgent"
        assert ticket["sla_deadline_at"] is not None

    def test_create_ticket_with_category(self, svc, org_id):
        ticket = svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                                   subject="Bug report", category="bug")
        assert ticket["category"] == "bug"

    def test_create_ticket_with_severity(self, svc, org_id):
        ticket = svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                                   subject="SEV1", severity="s1")
        assert ticket["severity"] == "s1"

    def test_create_ticket_with_source(self, svc, org_id):
        ticket = svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                                   subject="From email", source="email")
        assert ticket["source"] == "email"

    def test_create_ticket_with_service(self, svc, org_id):
        ticket = svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                                   subject="API issue", service_affected="api")
        assert ticket["service_affected"] == "api"

    def test_create_ticket_with_plan_tier(self, svc, org_id):
        ticket = svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                                   subject="Enterprise", plan_tier="enterprise")
        assert ticket["id"]
        assert ticket["sla_deadline_at"] is not None


class TestTicketRetrieval:
    def test_get_ticket(self, svc, org_id):
        created = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="Test")
        fetched = svc.get_ticket(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_ticket_not_found(self, svc):
        assert svc.get_ticket("nonexistent") is None

    def test_list_tickets(self, svc, org_id):
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T1")
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T2")
        tickets = svc.list_tickets(tenant_id=org_id)
        assert len(tickets) == 2

    def test_list_tickets_by_status(self, svc, org_id):
        t1 = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T1")
        svc.transition_ticket(t1["id"], "open")
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T2")
        open_tickets = svc.list_tickets(tenant_id=org_id, status="open")
        assert len(open_tickets) == 1

    def test_list_tickets_by_customer(self, svc, org_id):
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T1")
        svc.create_ticket(tenant_id=org_id, customer_id="cust-2", subject="T2")
        results = svc.list_tickets(tenant_id=org_id, customer_id="cust-1")
        assert len(results) == 1

    def test_list_tickets_active_only(self, svc, org_id):
        t1 = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T1")
        svc.transition_ticket(t1["id"], "open")
        t2 = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T2")
        active = svc.list_tickets(tenant_id=org_id, active_only=True)
        assert len(active) == 2

    def test_list_tickets_pagination(self, svc, org_id):
        for i in range(5):
            svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject=f"T{i}")
        page = svc.list_tickets(tenant_id=org_id, limit=2, offset=0)
        assert len(page) == 2
        page2 = svc.list_tickets(tenant_id=org_id, limit=2, offset=2)
        assert len(page2) == 2

    def test_list_tickets_service_filter(self, svc, org_id):
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="API", service_affected="api")
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="DB", service_affected="database")
        results = svc.list_tickets(tenant_id=org_id, service_affected="api")
        assert len(results) == 1


class TestTicketTransitions:
    def test_new_to_open(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        result = svc.transition_ticket(t["id"], "open")
        assert result["status"] == "open"

    def test_open_to_in_progress(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        result = svc.transition_ticket(t["id"], "in_progress")
        assert result["status"] == "in_progress"

    def test_to_resolved(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        result = svc.transition_ticket(t["id"], "resolved")
        assert result["status"] == "resolved"
        assert result["resolved_at"] is not None

    def test_to_closed(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        svc.transition_ticket(t["id"], "resolved")
        result = svc.transition_ticket(t["id"], "closed")
        assert result["status"] == "closed"
        assert result["closed_at"] is not None

    def test_reopen(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        svc.transition_ticket(t["id"], "resolved")
        svc.transition_ticket(t["id"], "closed")
        result = svc.transition_ticket(t["id"], "reopened")
        assert result["status"] == "reopened"

    def test_invalid_transition(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        with pytest.raises(ValueError):
            svc.transition_ticket(t["id"], "resolved")

    def test_to_waiting_customer(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        result = svc.transition_ticket(t["id"], "waiting_customer")
        assert result["status"] == "waiting_customer"

    def test_to_escalated(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        result = svc.transition_ticket(t["id"], "escalated")
        assert result["status"] == "escalated"


class TestTicketAssignment:
    def test_assign_ticket(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        result = svc.assign_ticket(t["id"], "agent-1", assigned_by="system")
        assert result["assigned_agent"] == "agent-1"

    def test_assign_with_team(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        result = svc.assign_ticket(t["id"], "agent-1", assigned_by="system", team="tier2")
        assert result["assigned_team"] == "tier2"

    def test_assign_opens_new_ticket(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        assert t["status"] == "new"
        svc.assign_ticket(t["id"], "agent-1", assigned_by="system")
        updated = svc.get_ticket(t["id"])
        assert updated["status"] == "open"

    def test_assign_not_found(self, svc):
        result = svc.assign_ticket("nonexistent", "agent-1", assigned_by="system")
        assert result is None


class TestTicketSearch:
    def test_search_by_subject(self, svc, org_id):
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="API timeout error")
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="Billing question")
        results = svc.search_tickets("API timeout", tenant_id=org_id)
        assert len(results) >= 1
        assert any("API" in r["subject"] for r in results)

    def test_search_no_results(self, svc, org_id):
        results = svc.search_tickets("nonexistent", tenant_id=org_id)
        assert len(results) == 0


class TestTicketLinking:
    def test_link_to_incident(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        link = svc.link_ticket(t["id"], "incident", "inc-123")
        assert link["link_type"] == "incident"
        assert link["target_id"] == "inc-123"
        updated = svc.get_ticket(t["id"])
        assert updated["linked_incident_id"] == "inc-123"

    def test_link_to_issue(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.link_ticket(t["id"], "issue", "issue-456")
        updated = svc.get_ticket(t["id"])
        assert updated["linked_issue_id"] == "issue-456"

    def test_get_links(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.link_ticket(t["id"], "incident", "inc-1")
        svc.link_ticket(t["id"], "issue", "iss-1")
        links = svc.get_ticket_links(t["id"])
        assert len(links) == 2


class TestTicketAudit:
    def test_audit_log(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        svc.assign_ticket(t["id"], "agent-1", assigned_by="sys")
        log = svc.get_audit_log(t["id"])
        assert len(log) >= 3


class TestDuplicateDetection:
    def test_detect_duplicates(self, svc, org_id):
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                          subject="API timeout error", description="The API is timing out")
        dupes = svc.detect_duplicates(org_id, "API timeout error", "The API is timing out")
        assert len(dupes) >= 1

    def test_no_duplicates(self, svc, org_id):
        svc.create_ticket(tenant_id=org_id, customer_id="cust-1",
                          subject="Billing question", description="About my bill")
        dupes = svc.detect_duplicates(org_id, "API timeout error", "Completely different")
        assert len(dupes) == 0


class TestTicketTelemetry:
    def test_telemetry(self, svc, org_id):
        t = svc.create_ticket(tenant_id=org_id, customer_id="cust-1", subject="T")
        svc.transition_ticket(t["id"], "open")
        svc.transition_ticket(t["id"], "resolved")
        telemetry = svc.get_telemetry()
        assert telemetry["created"] >= 1
        assert telemetry["resolved"] >= 1
