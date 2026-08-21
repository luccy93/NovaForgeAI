"""Incident Response Platform -- CLI (Volume 49).

9 subcommands: create, list, get, acknowledge, alert, triage, timeline,
runbook, health.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

from app.incident.incident_service import IncidentService
from app.incident.alert_service import AlertIngestionService
from app.incident.triage_service import TriageService
from app.incident.timeline_service import TimelineService
from app.incident.runbook_engine import RunbookEngine
from app.incident.escalation_manager import EscalationManager
from app.incident.remediation_engine import RemediationEngine
from app.incident.reliability_metrics import ReliabilityMetricsService
from app.incident.health_service import HealthService


def _print(title: str, data: Any):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, default=str))


def handle_incident_command(args: list[str]):
    """Dispatch incident CLI subcommands."""
    if not args:
        print("Usage: nova incident <subcommand> [args...]")
        print("Subcommands: create, list, get, acknowledge, alert, triage,")
        print("             timeline, runbook, health")
        return

    sub = args[0]
    rest = args[1:]

    if sub == "create":
        if len(rest) < 2:
            print("Usage: incident create <title> <severity> [service] [tenant]")
            return
        incident_svc = IncidentService()
        incident = incident_svc.create(
            tenant=rest[3] if len(rest) > 3 else "default",
            title=rest[0], severity=rest[1],
            service=rest[2] if len(rest) > 2 else "")
        _print("Incident Created", incident)

    elif sub == "list":
        tenant = rest[0] if rest else "default"
        incident_svc = IncidentService()
        incidents = incident_svc.list_incidents(tenant=tenant)
        _print("Incidents", {"count": len(incidents), "incidents": incidents})

    elif sub == "get":
        if not rest:
            print("Usage: incident get <incident_id>")
            return
        incident_svc = IncidentService()
        incident = incident_svc.get(rest[0])
        if incident:
            _print("Incident", incident)
        else:
            print("Incident not found")

    elif sub == "acknowledge":
        if not rest:
            print("Usage: incident acknowledge <incident_id> [commander]")
            return
        incident_svc = IncidentService()
        result = incident_svc.acknowledge(rest[0], commander=rest[1] if len(rest) > 1 else "")
        _print("Acknowledged", result)

    elif sub == "alert":
        if len(rest) < 2:
            print("Usage: incident alert <alert_source> <alert_id> [service] [severity]")
            return
        alert_svc = AlertIngestionService()
        result = alert_svc.ingest(
            tenant="default", alert_source=rest[0], alert_id=rest[1],
            service=rest[2] if len(rest) > 2 else "",
            severity=rest[3] if len(rest) > 3 else "medium")
        _print("Alert Ingested", result)

    elif sub == "triage":
        if not rest:
            print("Usage: incident triage <incident_id>")
            return
        incident_svc = IncidentService()
        incident = incident_svc.get(rest[0])
        if not incident:
            print("Incident not found")
            return
        triage_svc = TriageService()
        result = triage_svc.triage(incident)
        _print("Triage Result", result)

    elif sub == "timeline":
        if not rest:
            print("Usage: incident timeline <incident_id>")
            return
        timeline_svc = TimelineService()
        timeline = timeline_svc.get_timeline(rest[0])
        summary = timeline_svc.generate_summary(rest[0])
        _print("Timeline", {"events": timeline, "summary": summary})

    elif sub == "runbook":
        if len(rest) < 2:
            print("Usage: incident runbook <action> <name> [incident_type]")
            print("Actions: create, list")
            return
        action = rest[0]
        runbook_engine = RunbookEngine()
        if action == "create":
            rb = runbook_engine.create(tenant="default", name=rest[1],
                                       incident_type=rest[2] if len(rest) > 2 else "",
                                       steps=[{"step": 1, "description": "Check service health"}])
            _print("Runbook Created", rb)
        elif action == "list":
            runbooks = runbook_engine.list_runbooks(tenant="default")
            _print("Runbooks", {"count": len(runbooks), "runbooks": runbooks})
        else:
            print(f"Unknown runbook action: {action}")

    elif sub == "health":
        health_svc = HealthService()
        result = health_svc.check_incident_system_health()
        _print("Incident System Health", result)

    else:
        print(f"Unknown incident sub-command: {sub}")
