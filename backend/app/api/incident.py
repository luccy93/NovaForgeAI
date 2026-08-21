"""Incident Response Platform -- API (Volume 49).

~35 FastAPI endpoints for incident lifecycle, alerts, timeline,
investigation, hypotheses, runbooks, actions, postmortems, SLOs,
escalation, health, and metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query

from app.incident.schemas import (
    IncidentCreate, IncidentUpdate, IncidentAcknowledge, IncidentTransition,
    AlertIngest, HypothesisCreate, HypothesisUpdate, ActionCreate,
    ActionApprove, ActionExecute, RunbookCreate, PostmortemCreate,
    EscalationPolicyCreate, AlertPolicyCreate, InvestigateRequest,
)
from app.incident.incident_service import IncidentService
from app.incident.alert_service import AlertIngestionService
from app.incident.correlation_service import CorrelationService
from app.incident.change_correlation import ChangeCorrelationService
from app.incident.investigation_agent import InvestigationAgent
from app.incident.root_cause_service import RootCauseService
from app.incident.triage_service import TriageService
from app.incident.timeline_service import TimelineService
from app.incident.remediation_engine import RemediationEngine
from app.incident.runbook_engine import RunbookEngine
from app.incident.escalation_manager import EscalationManager
from app.incident.anomaly_detector import AnomalyDetector
from app.incident.ai_incident_detector import AIIncidentDetector
from app.incident.recurrence_detector import RecurrenceDetector
from app.incident.incident_memory import IncidentMemory
from app.incident.reliability_metrics import ReliabilityMetricsService
from app.incident.health_service import HealthService

router = APIRouter()

_incident_svc = IncidentService()
_alert_svc = AlertIngestionService()
_correlation_svc = CorrelationService()
_change_corr_svc = ChangeCorrelationService()
_investigation_agent = InvestigationAgent()
_root_cause_svc = RootCauseService()
_triage_svc = TriageService()
_timeline_svc = TimelineService()
_remediation_engine = RemediationEngine()
_runbook_engine = RunbookEngine()
_escalation_mgr = EscalationManager()
_anomaly_detector = AnomalyDetector()
_ai_detector = AIIncidentDetector()
_recurrence_detector = RecurrenceDetector()
_incident_memory = IncidentMemory()
_reliability_svc = ReliabilityMetricsService()
_health_svc = HealthService()

# ── Incidents ──────────────────────────────────────────────────────────

@router.post("/incidents")
async def create_incident(req: IncidentCreate):
    incident = _incident_svc.create(
        tenant=req.tenant, title=req.title, description=req.description,
        severity=req.severity, source=req.source, incident_type=req.incident_type,
        service=req.service, environment=req.environment,
        symptoms=req.symptoms, impact=req.impact,
    )
    _timeline_svc.add_event(incident["id"], "incident_detected", req.source,
                            f"Incident created: {req.title}")
    return incident


@router.get("/incidents")
async def list_incidents(
    tenant: str = Query("default"), service: str = Query(""),
    status: str = Query(""), severity: str = Query(""),
    environment: str = Query(""), limit: int = Query(50), offset: int = Query(0),
):
    return _incident_svc.list_incidents(
        tenant=tenant, service=service, status=status,
        severity=severity, environment=environment, limit=limit, offset=offset)


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return incident


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, req: IncidentAcknowledge):
    try:
        return _incident_svc.acknowledge(incident_id, commander=req.commander)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/incidents/{incident_id}/transition")
async def transition_incident(incident_id: str, req: IncidentTransition):
    try:
        return _incident_svc.transition(incident_id, req.status, req.message, req.actor)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/incidents/{incident_id}")
async def update_incident(incident_id: str, req: IncidentUpdate):
    result = _incident_svc.update(
        incident_id,
        severity=req.severity, commander=req.commander, description=req.description)
    if not result:
        raise HTTPException(404, "Incident not found")
    return result


@router.get("/incidents/{incident_id}/status")
async def get_incident_status(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return {"id": incident["id"], "status": incident["status"],
            "severity": incident["severity"], "service": incident["service"]}


@router.get("/incidents/active/count")
async def get_active_count(tenant: str = Query("default")):
    return {"active_count": _incident_svc.get_active_count(tenant)}


# ── Alerts ─────────────────────────────────────────────────────────────

@router.post("/alerts/ingest")
async def ingest_alert(req: AlertIngest):
    result = _alert_svc.ingest(
        tenant=req.tenant, alert_source=req.alert_source, alert_id=req.alert_id,
        rule_name=req.rule_name, severity=req.severity, service=req.service,
        environment=req.environment, message=req.message,
        raw_payload=req.raw_payload, labels=req.labels, timestamp=req.timestamp)
    return result


@router.get("/alerts")
async def list_alerts(
    tenant: str = Query("default"), service: str = Query(""),
    status: str = Query(""), environment: str = Query(""),
    limit: int = Query(50),
):
    return _alert_svc.list_alerts(tenant=tenant, service=service,
                                  status=status, environment=environment, limit=limit)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    result = _alert_svc.acknowledge(alert_id)
    if not result:
        raise HTTPException(404, "Alert not found")
    return result


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    result = _alert_svc.resolve(alert_id)
    if not result:
        raise HTTPException(404, "Alert not found")
    return result


@router.get("/alerts/firing/count")
async def get_firing_count(tenant: str = Query("default")):
    return {"firing_count": _alert_svc.get_firing_count(tenant)}


# ── Timeline ───────────────────────────────────────────────────────────

@router.get("/incidents/{incident_id}/timeline")
async def get_timeline(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    events = _incident_svc.get_events(incident_id)
    timeline_events = _timeline_svc.get_timeline(incident_id)
    return {"incident_id": incident_id, "events": events, "timeline": timeline_events,
            "summary": _timeline_svc.generate_summary(incident_id)}


# ── Investigation ──────────────────────────────────────────────────────

@router.post("/investigate")
async def investigate(req: InvestigateRequest):
    incident = _incident_svc.get(req.incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return _investigation_agent.investigate(incident, req.focus_areas, req.max_tokens)


@router.get("/investigations")
async def list_investigations(incident_id: str = Query("")):
    return _investigation_agent.list_investigations(incident_id=incident_id)


# ── Root Cause & Hypotheses ────────────────────────────────────────────

@router.post("/incidents/{incident_id}/analyze")
async def analyze_root_cause(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    corr_summary = _correlation_svc.get_summary(incident)
    investigation = _investigation_agent.list_investigations(incident_id=incident_id)
    inv = investigation[0] if investigation else None
    return _root_cause_svc.analyze(incident, corr_summary, inv)


@router.post("/hypotheses")
async def create_hypothesis(req: HypothesisCreate):
    incident = _incident_svc.get(req.incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    hypothesis = {"id": str(__import__("uuid").uuid4()),
                  "incident_id": req.incident_id, "hypothesis": req.hypothesis,
                  "confidence": req.confidence, "evidence": req.evidence,
                  "supporting_signals": req.supporting_signals,
                  "status": "proposed", "source": req.source}
    incident.setdefault("ai_hypotheses", []).append(hypothesis)
    return hypothesis


@router.get("/incidents/{incident_id}/hypotheses")
async def get_hypotheses(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return incident.get("ai_hypotheses", [])


# ── Triage ─────────────────────────────────────────────────────────────

@router.post("/incidents/{incident_id}/triage")
async def triage_incident(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    corr_summary = _correlation_svc.get_summary(incident)
    investigations = _investigation_agent.list_investigations(incident_id=incident_id)
    inv = investigations[0] if investigations else None
    return _triage_svc.triage(incident, corr_summary, inv)


# ── Correlation ────────────────────────────────────────────────────────

@router.get("/incidents/{incident_id}/correlation")
async def get_correlation(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return _correlation_svc.get_summary(incident)


@router.post("/deployments")
async def record_deployment(deploy_id: str = Query(""), service: str = Query(""),
                            environment: str = Query(""), version: str = Query(""),
                            commit_sha: str = Query(""), deployed_at: str = Query("")):
    return _correlation_svc.record_deployment(deploy_id, service, environment,
                                              version, commit_sha, deployed_at)


@router.post("/commits")
async def record_commit(commit_sha: str = Query(""), service: str = Query(""),
                        repository: str = Query(""), author: str = Query(""),
                        message: str = Query(""), committed_at: str = Query("")):
    return _correlation_svc.record_commit(commit_sha, service, repository,
                                          author, message, committed_at)


@router.get("/incidents/{incident_id}/blast-radius")
async def get_blast_radius(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return _correlation_svc.compute_blast_radius(incident)


# ── Actions / Remediation ──────────────────────────────────────────────

@router.post("/actions")
async def create_action(req: ActionCreate):
    return _remediation_engine.propose(
        incident_id=req.incident_id, action_type=req.action_type,
        description=req.description, risk_level=req.risk_level,
        approval_required=req.approval_required, runbook_id=req.runbook_id)


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, req: ActionApprove):
    try:
        return _remediation_engine.approve(action_id, req.approver)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/actions/{action_id}/execute")
async def execute_action(action_id: str, req: ActionExecute):
    try:
        return _remediation_engine.execute(action_id, dry_run=req.dry_run)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/actions/{action_id}/rollback")
async def rollback_action(action_id: str):
    try:
        return _remediation_engine.rollback(action_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/actions")
async def list_actions(incident_id: str = Query(""), status: str = Query(""),
                       limit: int = Query(50)):
    return _remediation_engine.list_actions(incident_id=incident_id, status=status,
                                            limit=limit)


@router.get("/actions/pending-approvals")
async def get_pending_approvals():
    return _remediation_engine.get_pending_approvals()


# ── Runbooks ───────────────────────────────────────────────────────────

@router.post("/runbooks")
async def create_runbook(req: RunbookCreate):
    return _runbook_engine.create(
        tenant=req.tenant, name=req.name, incident_type=req.incident_type,
        description=req.description, steps=req.steps, permissions=req.permissions,
        risk_level=req.risk_level, auto_executable=req.auto_executable)


@router.get("/runbooks")
async def list_runbooks(tenant: str = Query("default"), incident_type: str = Query("")):
    return _runbook_engine.list_runbooks(tenant=tenant, incident_type=incident_type)


@router.get("/runbooks/{runbook_id}")
async def get_runbook(runbook_id: str):
    rb = _runbook_engine.get(runbook_id)
    if not rb:
        raise HTTPException(404, "Runbook not found")
    return rb


@router.post("/runbooks/{runbook_id}/execute")
async def execute_runbook(runbook_id: str, incident_id: str = Query(""),
                          dry_run: bool = Query(True)):
    try:
        return _runbook_engine.execute_runbook(runbook_id, incident_id, dry_run)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/runbooks/match/{incident_id}")
async def match_runbook(incident_id: str, tenant: str = Query("default")):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    matched = _runbook_engine.match_runbook(incident, tenant)
    return {"matched_runbook": matched}


# ── Postmortem ─────────────────────────────────────────────────────────

@router.post("/postmortems")
async def create_postmortem(req: PostmortemCreate):
    incident = _incident_svc.get(req.incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    from uuid import uuid4
    pm_id = str(uuid4())
    postmortem = {
        "id": pm_id, "incident_id": req.incident_id, "summary": req.summary,
        "impact": req.impact, "root_cause": req.root_cause,
        "contributing_factors": req.contributing_factors,
        "what_went_well": req.what_went_well, "what_went_wrong": req.what_went_wrong,
        "timeline": _timeline_svc.get_timeline(req.incident_id),
        "status": "draft",
    }
    _incident_memory.store_verified_incident(incident, postmortem)
    return postmortem


@router.get("/incidents/{incident_id}/postmortem")
async def get_postmortem(incident_id: str):
    memory = _incident_memory.search(service="", limit=100)
    pm = [m for m in memory if m.get("incident_id") == incident_id]
    return pm[0] if pm else {"status": "not_found"}


# ── Escalation ─────────────────────────────────────────────────────────

@router.post("/escalation-policies")
async def create_escalation_policy(req: EscalationPolicyCreate):
    return _escalation_mgr.create_policy(req.tenant, req.name, req.description, req.rules)


@router.get("/escalation-policies")
async def list_escalation_policies(tenant: str = Query("default")):
    return _escalation_mgr.list_policies(tenant)


@router.post("/incidents/{incident_id}/escalation/check")
async def check_escalation(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    return _escalation_mgr.check_escalation(incident)


# ── Anomaly Detection ─────────────────────────────────────────────────

@router.get("/anomalies")
async def get_anomalies(service: str = Query(""), limit: int = Query(50)):
    return _anomaly_detector.get_anomalies(service=service, limit=limit)


@router.post("/anomalies/detect/{service}")
async def detect_anomalies(service: str):
    return _anomaly_detector.detect_anomalies(service)


# ── SLO ────────────────────────────────────────────────────────────────

@router.get("/slo/{service}")
async def get_slo_status(service: str, tenant: str = Query("default")):
    return _reliability_svc.compute_service_slo(tenant, service)


# ── Metrics ────────────────────────────────────────────────────────────

@router.get("/metrics/{service}")
async def get_reliability_metrics(service: str, tenant: str = Query("default")):
    return _reliability_svc.compute_metrics(tenant, service)


# ── Health ─────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    return _health_svc.check_incident_system_health()


@router.get("/recurrence/{incident_id}")
async def check_recurrence(incident_id: str):
    incident = _incident_svc.get(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    recurrences = _recurrence_detector.detect_recurrences(incident)
    suggestions = _recurrence_detector.suggest_preventive_actions(incident, recurrences)
    return {"recurrences": recurrences, "suggestions": suggestions}
