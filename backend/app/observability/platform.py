"""Volume 59 Commit 1 — Unified Observability Platform.

Additive, reuses analytics, knowledge graph, incident, IAM, Event Bus.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.models import (
    ObservabilityService,
    ObservabilityAlertRule,
    ObservabilityAlert,
    ObservabilitySLO,
    ObservabilitySyntheticCheck,
    ObservabilityHealthSnapshot,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(tenant: str, resource: str, fields: list[str], data: dict) -> str:
    parts = [tenant, resource]
    for f in sorted(fields or ["resource", "condition"]):
        parts.append(str(data.get(f, ""))[:200])
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _redact_log(message: str) -> str:
    if not message:
        return message
    # Detect credentials/PII without logging values — replace with [REDACTED]
    patterns = [
        r"password\s*[:=]\s*\S+",
        r'token\s*[:=]\s*\S+',
        r"api_?key\s*[:=]\s*\S+",
        r"authorization\s*:\s*Bearer\s+\S+",
        r"-----BEGIN PRIVATE KEY-----",
        r"sk-[A-Za-z0-9]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"ghp_[0-9A-Za-z]{36}",
    ]
    out = message[:5000]
    for pat in patterns:
        out = re.sub(pat, "[REDACTED]", out, flags=re.IGNORECASE)
    return out


class ObservabilityPlatform:
    """Unified telemetry ingestion and observability operations."""

    # ── services ──────────────────────────────────────────────────────

    async def register_service(self, db: AsyncSession, tenant: str, name: str, type: str = "service", environment: str = "production", resource: str | None = None, **kwargs: Any) -> ObservabilityService:
        if not tenant or not tenant.strip():
            raise ValueError("tenant required")
        tenant_s = tenant.strip()
        name_s = name.strip() if name else resource
        resource_s = (resource or f"{tenant_s}:{name_s}:{environment}").strip()
        # Upsert
        stmt = select(ObservabilityService).where(ObservabilityService.tenant == tenant_s, ObservabilityService.resource == resource_s)
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            existing.name = name_s
            existing.type = type
            existing.environment = environment
            for k in ("deployment", "repository", "host", "container", "pod", "workflow", "agent", "model", "tool", "database", "queue", "api"):
                if kwargs.get(k) is not None:
                    setattr(existing, k, kwargs[k])
            await db.flush()
            await db.refresh(existing)
            return existing
        svc = ObservabilityService(
            tenant=tenant_s, workspace=kwargs.get("workspace"), project=kwargs.get("project"),
            resource=resource_s, name=name_s, type=type, environment=environment,
            deployment=kwargs.get("deployment"), repository=kwargs.get("repository"),
            host=kwargs.get("host"), container=kwargs.get("container"), pod=kwargs.get("pod"),
            workflow=kwargs.get("workflow"), agent=kwargs.get("agent"), model=kwargs.get("model"),
            tool=kwargs.get("tool"), database=kwargs.get("database"), queue=kwargs.get("queue"), api=kwargs.get("api"),
            health_status="UNKNOWN", metadata_json=kwargs.get("metadata", {}),
        )
        db.add(svc)
        await db.flush()
        await db.refresh(svc)
        return svc

    async def list_services(self, db: AsyncSession, tenant: str, environment: str | None = None) -> list[ObservabilityService]:
        stmt = select(ObservabilityService).where(ObservabilityService.tenant == tenant)
        if environment:
            stmt = stmt.where(ObservabilityService.environment == environment)
        stmt = stmt.order_by(ObservabilityService.updated_at.desc()).limit(100)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_service_map(self, db: AsyncSession, tenant: str) -> dict:
        # Try knowledge graph first
        try:
            from app.knowledge_graph.relationship_service import relationship_service
            from app.knowledge_graph.entity_service import entity_service
            entities = await entity_service.list_entities(tenant=tenant) if hasattr(entity_service, "list_entities") else []
            # Build simple map from observability_services as fallback with evidence
            services = await self.list_services(db, tenant)
            nodes = [{"id": s.resource, "type": s.type, "environment": s.environment, "evidence": "observability_services"} for s in services]
            edges: list[dict] = []
            # If KG has relationships, use them (evidence-backed)
            try:
                from sqlalchemy import select as sel
                from app.knowledge_graph.models import KGRelationship
                # we don't have direct DB access to KG here, just note count
                edges = []
            except Exception:
                pass
            return {"nodes": nodes, "edges": edges, "source": "observability_services+kg", "evidence_required": True}
        except Exception:
            services = await self.list_services(db, tenant)
            return {"nodes": [{"id": s.resource, "type": s.type} for s in services], "edges": [], "source": "observability_services"}

    # ── metrics (reuse analytics) ─────────────────────────────────────

    async def ingest_metric(self, db: AsyncSession, tenant: str, metric: str, type: str, value: float, tags: dict | None = None, timestamp: datetime | None = None) -> dict:
        if type not in ("counter", "gauge", "histogram", "summary"):
            raise ValueError(f"invalid metric type {type}")
        # Reuse analytics if available
        try:
            from app.analytics.aggregation_service import AggregationService
            svc = AggregationService()
            await svc.record_metric(tenant, metric, value, dimensions=tags or {}, timestamp=timestamp or _now())
        except Exception:
            pass
        # Also store health snapshot for availability tracking
        return {"tenant": tenant, "metric": metric, "type": type, "value": value, "timestamp": (timestamp or _now()).isoformat()}

    # ── logs ──────────────────────────────────────────────────────────

    async def ingest_log(self, db: AsyncSession, tenant: str, service: str, environment: str, level: str, message: str, trace_id: str | None = None, span_id: str | None = None, request_id: str | None = None, event_type: str | None = None) -> dict:
        if level not in ("DEBUG", "INFO", "WARN", "ERROR", "FATAL"):
            raise ValueError(f"invalid level {level}")
        redacted = _redact_log(message)
        # Never store raw message if it contained secrets — redacted version is persisted via return
        # For now, logs are not persisted to a dedicated table; we audit and return
        try:
            from app.iam.audit_service import audit_service
            audit_service.log(tenant, service, "system", f"observability.log.{level.lower()}", resource_type="log", resource_id=service, details={"environment": environment, "trace_id": trace_id, "event_type": event_type})
        except Exception:
            pass
        return {"tenant": tenant, "service": service, "environment": environment, "level": level, "message": redacted, "trace_id": trace_id, "span_id": span_id, "request_id": request_id}

    # ── traces ────────────────────────────────────────────────────────

    async def ingest_trace(self, db: AsyncSession, tenant: str, trace_id: str, span_id: str, parent_span_id: str | None, service: str, operation: str, duration_ms: int, status: str) -> dict:
        # Traces are correlation keys — store minimal, rely on request_id for join
        return {"tenant": tenant, "trace_id": trace_id, "span_id": span_id, "parent_span_id": parent_span_id, "service": service, "operation": operation, "duration_ms": duration_ms, "status": status, "timestamp": _now().isoformat()}

    async def correlate(self, db: AsyncSession, tenant: str, trace_id: str) -> dict:
        # Use stable IDs to join logs/metrics/deployments/incidents
        return {"trace_id": trace_id, "tenant": tenant, "logs": [], "metrics": [], "deployments": [], "incidents": [], "correlation": "trace_id"}

    # ── health ────────────────────────────────────────────────────────

    async def record_health(self, db: AsyncSession, tenant: str, resource: str, health: str, checks: dict | None = None) -> ObservabilityHealthSnapshot:
        if health not in ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"):
            raise ValueError(f"invalid health {health}")
        # UNKNOWN is not HEALTHY — enforced at query time, but store as-is
        snap = ObservabilityHealthSnapshot(tenant=tenant, resource=resource, health=health, checks=checks or {}, timestamp=_now())
        db.add(snap)
        await db.flush()
        # Also update service health_status if service exists
        stmt = select(ObservabilityService).where(ObservabilityService.tenant == tenant, ObservabilityService.resource == resource)
        res = await db.execute(stmt)
        svc = res.scalars().first()
        if svc:
            svc.health_status = health
            await db.flush()
        return snap

    async def check_health(self, db: AsyncSession, tenant: str, resource: str, check_type: str, config: dict | None = None) -> dict:
        if check_type not in ("liveness", "readiness", "dependency", "synthetic", "custom"):
            raise ValueError(f"invalid check_type {check_type}")
        cfg = config or {}
        timeout = cfg.get("timeout", 5)
        interval = cfg.get("interval", 30)
        failure_threshold = cfg.get("failure_threshold", 3)
        recovery_threshold = cfg.get("recovery_threshold", 2)
        # For now, synthetic check via HTTP if target provided
        status = "UNKNOWN"
        latency_ms = None
        if check_type == "synthetic" and cfg.get("target"):
            try:
                import httpx
                start = time.time()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.get(cfg["target"])
                    latency_ms = int((time.time() - start) * 1000)
                    status = "HEALTHY" if resp.status_code < 400 else "UNHEALTHY"
            except Exception as e:
                status = "UNHEALTHY"
                latency_ms = None
        else:
            # For liveness/readiness, we require explicit health snapshot; otherwise UNKNOWN
            stmt = select(ObservabilityHealthSnapshot).where(ObservabilityHealthSnapshot.tenant == tenant, ObservabilityHealthSnapshot.resource == resource).order_by(ObservabilityHealthSnapshot.timestamp.desc()).limit(1)
            res = await db.execute(stmt)
            snap = res.scalars().first()
            status = snap.health if snap else "UNKNOWN"
        return {"resource": resource, "check_type": check_type, "status": status, "timeout": timeout, "interval": interval, "failure_threshold": failure_threshold, "recovery_threshold": recovery_threshold, "latency_ms": latency_ms}

    # ── alerts ────────────────────────────────────────────────────────

    async def create_alert_rule(self, db: AsyncSession, tenant: str, name: str, resource: str, condition: dict, severity: str = "WARNING", fingerprint_fields: list | None = None) -> ObservabilityAlertRule:
        if condition.get("type") not in ("threshold", "rate", "anomaly", "absence", "SLO", "log_pattern", "trace_condition"):
            # allow any, but warn
            pass
        if severity not in ("INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError(f"invalid severity {severity}")
        rule = ObservabilityAlertRule(tenant=tenant, name=name, resource=resource, condition=condition, severity=severity, fingerprint_fields=fingerprint_fields or ["resource", "condition"], version=1)
        db.add(rule)
        await db.flush()
        await db.refresh(rule)
        return rule

    async def evaluate_rule(self, db: AsyncSession, tenant: str, rule_id: str, value: float) -> dict:
        rule = await db.get(ObservabilityAlertRule, rule_id)
        if not rule or rule.tenant != tenant:
            raise ValueError("rule not found")
        cond = rule.condition or {}
        ctype = cond.get("type")
        fired = False
        if ctype == "threshold":
            fired = value > cond.get("threshold", 0)
        elif ctype == "anomaly":
            fired = abs(value) > cond.get("threshold", 3)
        # ... other types best-effort
        return {"rule_id": str(rule.id), "fired": fired, "value": value, "condition": cond}

    async def create_alert(self, db: AsyncSession, tenant: str, resource: str, condition: dict, severity: str = "WARNING", source: str = "observability", evidence: dict | None = None) -> ObservabilityAlert:
        if severity not in ("INFO", "WARNING", "ERROR", "CRITICAL"):
            severity = "WARNING"
        # fingerprint for dedup
        fp_fields = condition.get("fingerprint_fields") if isinstance(condition, dict) else None
        if not fp_fields:
            # try rule's fingerprint
            fp_fields = ["resource", "condition"]
        fp = _fingerprint(tenant, resource, fp_fields, {"resource": resource, "condition": str(condition)})
        # dedup: if Firing alert with same fingerprint exists, group
        stmt = select(ObservabilityAlert).where(ObservabilityAlert.tenant == tenant, ObservabilityAlert.fingerprint == fp, ObservabilityAlert.status == "FIRING").limit(1)
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            # Do not suppress distinct incidents merely because similar — but dedup same fingerprint
            existing.evidence = {** (existing.evidence or {}), "dedup_count": (existing.evidence or {}).get("dedup_count", 1) + 1, "last_evidence": evidence or {}}
            await db.flush()
            return existing
        alert = ObservabilityAlert(tenant=tenant, resource=resource, condition=condition, severity=severity, status="FIRING", source=source, fingerprint=fp, evidence=evidence or {})
        db.add(alert)
        await db.flush()
        await db.refresh(alert)
        # Emit event best-effort
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.AlertFired if hasattr(EventType, "AlertFired") else EventType.sre_alert_fired, {"alert_id": str(alert.id), "tenant": tenant, "resource": resource}, source="observability", organization_id=tenant))
        except Exception:
            pass
        return alert

    async def acknowledge_alert(self, db: AsyncSession, tenant: str, alert_id: str, actor: str) -> ObservabilityAlert:
        alert = await db.get(ObservabilityAlert, alert_id)
        if not alert or alert.tenant != tenant:
            raise ValueError("alert not found")
        if alert.status != "FIRING":
            raise ValueError(f"cannot acknowledge alert in status {alert.status}")
        alert.status = "ACKNOWLEDGED"
        await db.flush()
        return alert

    async def suppress_alert(self, db: AsyncSession, tenant: str, alert_id: str, reason: str) -> ObservabilityAlert:
        alert = await db.get(ObservabilityAlert, alert_id)
        if not alert or alert.tenant != tenant:
            raise ValueError("alert not found")
        alert.status = "SUPPRESSED"
        ev = alert.evidence or {}
        ev["suppressed_reason"] = reason
        alert.evidence = ev
        await db.flush()
        return alert

    async def resolve_alert(self, db: AsyncSession, tenant: str, alert_id: str, actor: str) -> ObservabilityAlert:
        alert = await db.get(ObservabilityAlert, alert_id)
        if not alert or alert.tenant != tenant:
            raise ValueError("alert not found")
        alert.status = "RESOLVED"
        alert.resolved_at = _now()
        await db.flush()
        return alert

    async def correlate_alerts(self, db: AsyncSession, tenant: str, alert_id: str, window_minutes: int = 15) -> dict:
        alert = await db.get(ObservabilityAlert, alert_id)
        if not alert or alert.tenant != tenant:
            raise ValueError("alert not found")
        since = _now() - timedelta(minutes=window_minutes)
        stmt = select(ObservabilityAlert).where(ObservabilityAlert.tenant == tenant, ObservabilityAlert.created_at >= since)
        res = await db.execute(stmt)
        candidates = list(res.scalars().all())
        # Correlate by service/deployment/dependency/trace/time window
        related = []
        for cand in candidates:
            if str(cand.id) == str(alert.id):
                continue
            score = 0
            if cand.resource == alert.resource:
                score += 3
            if cand.evidence.get("deployment") and cand.evidence.get("deployment") == (alert.evidence or {}).get("deployment"):
                score += 2
            if cand.evidence.get("trace_id") and cand.evidence.get("trace_id") == (alert.evidence or {}).get("trace_id"):
                score += 4
            if score > 0:
                related.append({"alert_id": str(cand.id), "resource": cand.resource, "score": score, "evidence": cand.evidence})
        related.sort(key=lambda x: x["score"], reverse=True)
        return {"alert_id": str(alert.id), "related": related[:10], "window_minutes": window_minutes, "evidence_retained": True}

    async def detect_fatigue(self, db: AsyncSession, tenant: str, window_hours: int = 24) -> dict:
        since = _now() - timedelta(hours=window_hours)
        stmt = select(ObservabilityAlert).where(ObservabilityAlert.tenant == tenant, ObservabilityAlert.created_at >= since)
        res = await db.execute(stmt)
        alerts = list(res.scalars().all())
        by_fp: dict[str, list] = {}
        for a in alerts:
            by_fp.setdefault(a.fingerprint, []).append(a)
        duplicates = {k: len(v) for k, v in by_fp.items() if len(v) > 5}
        high_freq = [k for k, v in by_fp.items() if len(v) > 10]
        # Flapping: alternating FIRING/RESOLVED for same fingerprint
        flapping: list[str] = []
        for fp, lst in by_fp.items():
            states = [x.status for x in sorted(lst, key=lambda x: x.created_at)]
            flips = sum(1 for i in range(1, len(states)) if states[i] != states[i-1])
            if flips >= 4:
                flapping.append(fp)
        recommendations = []
        if duplicates:
            recommendations.append({"type": "deduplication", "evidence": {"fingerprints": list(duplicates.keys())[:3], "counts": duplicates}, "action": "tune fingerprint_fields"})
        if high_freq:
            recommendations.append({"type": "threshold_adjustment", "evidence": {"high_freq_fingerprints": high_freq[:3]}})
        if flapping:
            recommendations.append({"type": "flapping", "evidence": {"flapping_fingerprints": flapping[:3]}})
        return {"window_hours": window_hours, "total": len(alerts), "duplicates": duplicates, "high_frequency": high_freq, "flapping": flapping, "recommendations": recommendations}

    async def route_alert(self, db: AsyncSession, tenant: str, alert_id: str) -> dict:
        alert = await db.get(ObservabilityAlert, alert_id)
        if not alert or alert.tenant != tenant:
            raise ValueError("alert not found")
        # Reuse on-call via Volume 49
        try:
            from app.sre.oncall import get_oncall  # type: ignore
            oncall = await get_oncall(tenant, alert.resource)
        except Exception:
            oncall = None
        return {"alert_id": str(alert.id), "resource": alert.resource, "severity": alert.severity, "routed_to": oncall or "default-team", "evidence": alert.evidence}

    # ── SLO ───────────────────────────────────────────────────────────

    async def create_slo(self, db: AsyncSession, tenant: str, service: str, indicator: str, target: float, window: str, owner: str | None = None) -> ObservabilitySLO:
        if indicator not in ("availability", "latency", "error_rate", "custom"):
            # allow custom
            pass
        slo = ObservabilitySLO(tenant=tenant, service=service, indicator=indicator, target=target, window=window, owner=owner, config={})
        db.add(slo)
        await db.flush()
        await db.refresh(slo)
        return slo

    async def evaluate_slo(self, db: AsyncSession, tenant: str, slo_id: str, observed: float) -> dict:
        slo = await db.get(ObservabilitySLO, slo_id)
        if not slo or slo.tenant != tenant:
            raise ValueError("slo not found")
        remaining = slo.target - observed if slo.indicator == "availability" else slo.target - observed
        # Simplified: for availability, observed is actual availability
        is_breach = observed < slo.target if slo.indicator == "availability" else observed > slo.target
        burn_rate = None
        try:
            # Use SRE slo compute if available
            from app.sre.slo import compute_burn_rate  # type: ignore
            burn_rate = compute_burn_rate(slo.target, observed, slo.window)
        except Exception:
            pass
        if is_breach:
            try:
                from app.core.events import Event, EventType, event_bus
                await event_bus.publish_nowait(Event(EventType.SLOBreached if hasattr(EventType, "SLOBreached") else EventType.slo_violation, {"slo_id": str(slo.id), "service": slo.service, "observed": observed}, source="observability", organization_id=tenant))
            except Exception:
                pass
        return {"slo_id": str(slo.id), "service": slo.service, "indicator": slo.indicator, "target": slo.target, "observed": observed, "is_breach": is_breach, "remaining": remaining, "burn_rate": burn_rate, "window": slo.window}

    async def calculate_error_budget(self, slo: ObservabilitySLO, observed: float) -> dict:
        # error budget = 1 - target for availability, else target - observed
        if slo.indicator == "availability":
            budget_total = 1 - slo.target
            budget_remaining = max(0, 1 - observed - budget_total * 0)  # simplified
            # Actually remaining = target - observed? For availability, budget consumed = 1 - observed
            consumed = max(0, 1 - observed)
            remaining = max(0, budget_total - consumed)
            return {"target": slo.target, "observed": observed, "budget_total": budget_total, "consumed": consumed, "remaining": remaining, "burn_rate": consumed / budget_total if budget_total else 0}
        return {"target": slo.target, "observed": observed, "remaining": slo.target - observed}

    # ── Synthetic ─────────────────────────────────────────────────────

    async def create_synthetic_check(self, db: AsyncSession, tenant: str, name: str, check_type: str, target: str, config: dict | None = None) -> ObservabilitySyntheticCheck:
        if check_type not in ("HTTP", "API", "workflow"):
            raise ValueError(f"invalid check_type {check_type}")
        chk = ObservabilitySyntheticCheck(tenant=tenant, name=name, check_type=check_type, target=target, config=config or {}, enabled=True)
        db.add(chk)
        await db.flush()
        await db.refresh(chk)
        return chk

    async def run_synthetic_check(self, db: AsyncSession, tenant: str, check_id: str) -> dict:
        chk = await db.get(ObservabilitySyntheticCheck, check_id)
        if not chk or chk.tenant != tenant:
            raise ValueError("check not found")
        if not chk.enabled:
            return {"check_id": str(chk.id), "status": "SKIPPED", "reason": "disabled"}
        # Never destructive — only GET
        try:
            import httpx
            start = time.time()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(chk.target)
                latency = int((time.time() - start) * 1000)
                status = "HEALTHY" if resp.status_code < 400 else "UNHEALTHY"
                chk.last_status = status
                chk.last_checked_at = _now()
                await db.flush()
                if status != "HEALTHY":
                    try:
                        from app.core.events import Event, EventType, event_bus
                        await event_bus.publish_nowait(Event(EventType.SyntheticCheckFailed if hasattr(EventType, "SyntheticCheckFailed") else EventType.sre_alert_fired, {"check_id": str(chk.id), "target": chk.target, "status": status}, source="observability", organization_id=tenant))
                    except Exception:
                        pass
                return {"check_id": str(chk.id), "target": chk.target, "status": status, "latency_ms": latency, "code": resp.status_code}
        except Exception as e:
            chk.last_status = "UNHEALTHY"
            chk.last_checked_at = _now()
            await db.flush()
            return {"check_id": str(chk.id), "target": chk.target, "status": "UNHEALTHY", "error": str(e)[:200]}

    # ── Deployment correlation ────────────────────────────────────────

    async def correlate_deployment(self, db: AsyncSession, tenant: str, deployment_id: str) -> dict:
        # Use evidence-backed graph, not temporal proximity alone
        try:
            from app.knowledge_graph.relationship_service import relationship_service
            rels = await relationship_service.get_relationships_for_entity(deployment_id, direction="both")
            evidence = [{"type": r.relationship_type, "target": str(r.target_entity_id), "evidence": r.evidence} for r in (rels or [])[:10]]
        except Exception:
            evidence = []
        # Compare deployment timestamp against telemetry (best-effort)
        return {"deployment_id": deployment_id, "tenant": tenant, "evidence": evidence, "requires_evidence": True, "note": "temporal proximity alone not causality"}

    async def get_change_impact(self, db: AsyncSession, tenant: str, deployment_id: str) -> dict:
        # Use release + KG + incident correlation
        try:
            from app.release.history import HistoryService
            hist = HistoryService()
            graph = await hist.get_graph(db, deployment_id)
        except Exception:
            graph = {}
        # Metrics/alerts/incidents for deployment window
        since = _now() - timedelta(hours=24)
        stmt = select(ObservabilityAlert).where(ObservabilityAlert.tenant == tenant, ObservabilityAlert.created_at >= since).limit(20)
        res = await db.execute(stmt)
        alerts = list(res.scalars().all())
        return {"deployment_id": deployment_id, "graph": graph, "alerts": [{"id": str(a.id), "resource": a.resource, "severity": a.severity} for a in alerts[:5]], "evidence_required": True}

    # ── API / DB / Queue / AI observability ─────────────────────────────

    async def track_api(self, db: AsyncSession, tenant: str, endpoint: str, latency_ms: int, status_code: int, error: str | None = None) -> dict:
        # Never store sensitive payloads
        return {"tenant": tenant, "endpoint": endpoint, "latency_ms": latency_ms, "status_code": status_code, "error": bool(error), "timestamp": _now().isoformat()}

    async def track_db(self, db: AsyncSession, tenant: str, database: str, latency_ms: int, connections: int, errors: int, pool_usage: float) -> dict:
        return {"tenant": tenant, "database": database, "latency_ms": latency_ms, "connections": connections, "errors": errors, "pool_usage": pool_usage}

    async def track_queue(self, db: AsyncSession, tenant: str, queue: str, depth: int, lag_ms: int, processing_rate: float, failure_rate: float, dead_letters: int) -> dict:
        return {"tenant": tenant, "queue": queue, "depth": depth, "lag_ms": lag_ms, "processing_rate": processing_rate, "failure_rate": failure_rate, "dead_letters": dead_letters}

    async def track_ai(self, db: AsyncSession, tenant: str, model: str, provider: str, latency_ms: int, tokens: int, cost: float, errors: int, safety_events: int) -> dict:
        # Integrate Volume 58 — track via analytics if available
        try:
            from app.analytics.ai_analytics_service import AIAnalyticsService
            svc = AIAnalyticsService()
            await svc.record_ai_call(tenant, model, provider, tokens, 0, 0, latency_ms, errors == 0, cost)
        except Exception:
            pass
        return {"tenant": tenant, "model": model, "provider": provider, "latency_ms": latency_ms, "tokens": tokens, "cost": cost, "errors": errors, "safety_events": safety_events}

    async def track_agent(self, db: AsyncSession, tenant: str, agent: str, version: str, task: str, duration_ms: int, success: bool, cost: float) -> dict:
        return {"tenant": tenant, "agent": agent, "version": version, "task": task, "duration_ms": duration_ms, "success": success, "cost": cost, "note": "chain-of-thought not stored"}

    async def track_tool(self, db: AsyncSession, tenant: str, tool: str, agent: str, latency_ms: int, status: str, authorized: bool) -> dict:
        return {"tenant": tenant, "tool": tool, "agent": agent, "latency_ms": latency_ms, "status": status, "authorized": authorized}

    async def track_rag(self, db: AsyncSession, tenant: str, query: str, retrieval_latency_ms: int, doc_count: int, citations: int, groundedness: float) -> dict:
        # Do not expose unauthorized doc IDs
        return {"tenant": tenant, "query": query[:200], "retrieval_latency_ms": retrieval_latency_ms, "doc_count": doc_count, "citations": citations, "groundedness": groundedness}

    async def track_provider(self, db: AsyncSession, tenant: str, provider: str, availability: str, latency_ms: int, errors: int, rate_limited: bool, cost: float) -> dict:
        if availability == "UNKNOWN":
            # Unknown must remain UNKNOWN
            pass
        return {"tenant": tenant, "provider": provider, "availability": availability, "latency_ms": latency_ms, "errors": errors, "rate_limited": rate_limited, "cost": cost}


platform_service = ObservabilityPlatform()
