"""Runbook system (Volume 35).

Every critical service has runbooks; standard incident-response
playbooks are provided out of the box for the common failure modes:
API outage, database outage, Redis/Qdrant/Neo4j outages, AI provider
outage, deployment failure, authentication outage, queue failure, high
latency, memory/disk exhaustion, security incidents, certificate
expiration, and DNS failure.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import SRERunbook
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

PLAYBOOKS: dict[str, dict] = {
    "runbook-api-outage": {
        "service_id": "api-gateway",
        "title": "API Outage",
        "purpose": "Restore API availability when the gateway is failing or slow.",
        "symptoms": ["5xx responses increase", "latency p95 exceeds SLO", "client timeouts", "gateway instances unhealthy"],
        "impact": "All API traffic is affected; dependent services degrade.",
        "diagnosis": [
            "Check /health/ready on gateway instances",
            "Review error rate and latency dashboards",
            "Check recent deployments (last 24h)",
            "Verify upstream dependencies (auth, database, redis)",
        ],
        "commands": ["curl /health/ready", "kubectl get pods -l app=api-gateway", "kubectl logs -l app=api-gateway --tail=200"],
        "checks": ["DNS resolution", "load balancer health", "TLS certificate", "rate limiter state"],
        "mitigation": ["Scale out gateway pool", "Enable load shedding for non-critical work", "Fail over to standby region if regional"],
        "rollback": ["Roll back last deployment if regression", "Revert config changes made in the last hour"],
        "recovery": ["Verify error rate returns to baseline", "Verify p95 latency within SLO", "Monitor for 15 minutes before declaring resolution"],
        "escalation": ["SEV1: page on-call; SEV0: incident commander + communications"],
        "post_incident": ["Postmortem required", "Corrective action: regression guard on deployment"],
    },
    "runbook-db-outage": {
        "service_id": "control-plane",
        "title": "Database Outage (PostgreSQL)",
        "purpose": "Restore database service and prevent data loss.",
        "symptoms": ["Connection refused", "SQLAlchemy OperationalError", "replication lag spikes", "read replicas stale"],
        "impact": "All persisted state unavailable; most services degrade.",
        "diagnosis": [
            "Check primary/replica status",
            "Check connection pool saturation",
            "Check disk and WAL volume",
            "Check recent schema migrations",
        ],
        "commands": ["pg_isready", "SELECT * FROM pg_stat_replication;", "SHOW max_connections;"],
        "checks": ["Backup age", "PITR window", "Replica lag", "Lock waits (pg_locks)"],
        "mitigation": [
            "Fail over to healthy replica",
            "Reduce connection pool pressure",
            "Terminate long-running queries if runaway",
            "Do NOT run DDL during outage",
        ],
        "rollback": ["Roll back risky migration if applied", "Switch back only after health verified"],
        "recovery": ["Verify PITR RPO met", "Run restore test if data was lost", "Verify application connectivity"],
        "escalation": ["Database lead", "SEV0/SEV1 on-call"],
        "post_incident": ["Postmortem", "Corrective action: connection pool hardening"],
    },
    "runbook-redis-outage": {
        "service_id": "event-bus",
        "title": "Redis Outage",
        "purpose": "Restore cache/queue infrastructure.",
        "symptoms": ["Cache misses spike", "Queue depth grows", "Event bus delivery stalls", "Rate limiter errors"],
        "impact": "Cache, queues and event bus degraded; system slower but durable data intact.",
        "diagnosis": ["Check Redis memory", "Check eviction policy", "Check replication", "Check network"],
        "commands": ["redis-cli INFO memory", "redis-cli INFO replication", "redis-cli SLOWLOG GET 10"],
        "checks": ["Memory usage", "Eviction count", "Replica sync state", "Keyspace misses"],
        "mitigation": ["Fail over to replica", "Raise maxmemory if misconfigured", "Drain and replay queues from DLQ"],
        "rollback": ["Restore from snapshot if data corruption"],
        "recovery": ["Verify cache warmup", "Verify queue drain", "Verify event bus delivery"],
        "escalation": ["Infrastructure on-call"],
        "post_incident": ["Corrective action: memory monitoring + alerting"],
    },
    "runbook-qdrant-outage": {
        "service_id": "rag",
        "title": "Qdrant Outage",
        "purpose": "Restore vector search availability.",
        "symptoms": ["Retrieval errors", "Search latency spikes", "Collection status unhealthy", "Embedding writes fail"],
        "impact": "RAG, search and repository intelligence degraded.",
        "diagnosis": ["Check collection health", "Check storage usage", "Check snapshot state", "Check replica state"],
        "commands": ["GET /collections", "GET /collections/{name}", "GET /collections/{name}/points?limit=1"],
        "checks": ["Storage free space", "Snapshot age", "Replica sync", "Indexing backlog"],
        "mitigation": ["Restore from latest verified snapshot", "Degrade RAG to controlled responses (no fabricated retrieval)"],
        "rollback": ["Fail back after snapshot verification"],
        "recovery": ["Verify search latency", "Re-run indexing jobs", "Verify retrieval quality"],
        "escalation": ["AI platform lead"],
        "post_incident": ["Corrective action: snapshot restore test scheduled"],
    },
    "runbook-neo4j-outage": {
        "service_id": "repository-intelligence",
        "title": "Neo4j Outage",
        "purpose": "Restore graph database connectivity.",
        "symptoms": ["Graph queries fail", "Repository intelligence incomplete", "Connection pool errors"],
        "impact": "Repository intelligence degraded; code graph features unavailable.",
        "diagnosis": ["Check database status", "Check store size", "Check transaction log"],
        "commands": ["CALL dbms.components()", "CALL dbms.checkConsistency()"],
        "checks": ["Backup age", "Store filesystem space", "Connection count"],
        "mitigation": ["Fail over to replica", "Restore from backup if corruption"],
        "rollback": ["Fail back after consistency check"],
        "recovery": ["Run relationship consistency checks", "Verify intelligence queries"],
        "escalation": ["Code intelligence lead"],
        "post_incident": ["Corrective action: consistency check automation"],
    },
    "runbook-ai-provider-outage": {
        "service_id": "ai-chat",
        "title": "AI Provider Outage",
        "purpose": "Keep AI features available across provider failures.",
        "symptoms": ["Provider errors", "Model latency spikes", "Rate limit errors", "Circuit breakers open"],
        "impact": "AI chat, agents and RAG generation affected.",
        "diagnosis": ["Check provider status page", "Check error patterns", "Check circuit breaker states"],
        "commands": ["GET /sre/ai/providers/health", "GET /sre/resilience/circuit-breakers"],
        "checks": ["Provider quotas", "Fallback chain policy", "Cost impact"],
        "mitigation": ["Enable provider failover", "Fall back to approved alternate models", "Degrade advanced features (vision, long-context)"],
        "rollback": ["Re-enable primary provider after recovery window"],
        "recovery": ["Verify provider health", "Verify model quality on fallback", "Restore primary routing"],
        "escalation": ["AI platform lead", "Model gateway owner"],
        "post_incident": ["Corrective action: expand provider coverage"],
    },
    "runbook-deployment-failure": {
        "service_id": "deployment",
        "title": "Deployment Failure",
        "purpose": "Detect, contain and roll back failed deployments.",
        "symptoms": ["Canary error rate above threshold", "Health checks failing after deploy", "SLO violation after change"],
        "impact": "Service quality degrades for affected users; dependent features affected.",
        "diagnosis": ["Check canary analysis", "Check deployment logs", "Compare baseline vs canary metrics"],
        "commands": ["GET /sre/deployments", "GET /sre/deployments/canary/{id}"],
        "checks": ["Error rate", "Latency", "CPU/memory", "Business metrics"],
        "mitigation": ["Abort canary", "Roll back to last known-good version"],
        "rollback": ["Rollback must validate target version and rollback safety first"],
        "recovery": ["Verify health after rollback", "Verify error budget recovers"],
        "escalation": ["Release engineering lead"],
        "post_incident": ["Corrective action: strengthen canary thresholds"],
    },
    "runbook-auth-outage": {
        "service_id": "auth",
        "title": "Authentication Outage",
        "purpose": "Restore authentication availability; never bypass auth controls.",
        "symptoms": ["Login failures", "Token issuance errors", "MFA failures", "401 storms"],
        "impact": "All users cannot authenticate; platform effectively down.",
        "diagnosis": ["Check auth service health", "Check JWT service", "Check database connectivity", "Check MFA provider"],
        "commands": ["GET /health/ready", "GET /api/v1/sre/services/auth"],
        "checks": ["Token signing keys", "Session store", "Rate limiter state", "Recent config changes"],
        "mitigation": ["Fail over auth instances", "Scale out if overload", "NEVER disable auth as a workaround"],
        "rollback": ["Roll back auth config changes"],
        "recovery": ["Verify login flow end-to-end", "Verify token validation"],
        "escalation": ["SEV0 page; security lead"],
        "post_incident": ["Postmortem required", "Corrective action: auth failover test"],
    },
    "runbook-queue-failure": {
        "service_id": "event-bus",
        "title": "Queue Failure",
        "purpose": "Restore message processing and protect against backlog.",
        "symptoms": ["Queue depth grows", "Worker failures", "DLQ entries increase", "Processing latency spikes"],
        "impact": "Background work stalls; user-visible features degrade gradually.",
        "diagnosis": ["Check queue depth by queue", "Check worker heartbeats", "Check DLQ", "Check poison messages"],
        "commands": ["GET /sre/queues/status", "GET /sre/dead-letters"],
        "checks": ["Age of oldest message", "Retry counts", "Backlog growth rate"],
        "mitigation": ["Restart unhealthy workers", "Scale worker pool", "Replay DLQ after root cause fix"],
        "rollback": ["Revert consumer code if regression"],
        "recovery": ["Verify queue drains to zero", "Verify DLQ empty or justified"],
        "escalation": ["Infrastructure on-call"],
        "post_incident": ["Corrective action: poison message handling"],
    },
    "runbook-high-latency": {
        "service_id": "api-gateway",
        "title": "High Latency",
        "purpose": "Identify and remove latency bottlenecks.",
        "symptoms": ["p95/p99 latency above SLO", "Timeouts", "Queue delays", "Saturation signals"],
        "impact": "Poor user experience; SLO breach risk.",
        "diagnosis": ["Review latency percentile charts", "Check dependency latency", "Check saturation (CPU, memory, connections)", "Review slow queries"],
        "commands": ["GET /sre/capacity/saturation", "EXPLAIN ANALYZE on slow queries"],
        "checks": ["Database slow query log", "Redis latency", "Provider latency", "GC / event loop stalls"],
        "mitigation": ["Scale out", "Enable load shedding", "Throttle non-critical work", "Add caching"],
        "rollback": ["Roll back recent perf-affecting changes"],
        "recovery": ["Verify latency back within SLO", "Monitor for 30 minutes"],
        "escalation": ["SRE on-call"],
        "post_incident": ["Corrective action: latency SLO guardrails"],
    },
    "runbook-memory-exhaustion": {
        "service_id": "agent-runtime",
        "title": "Memory Exhaustion",
        "purpose": "Recover workers from OOM conditions safely.",
        "symptoms": ["OOMKilled events", "Memory pressure alerts", "Pod restarts", "Garbage collection stalls"],
        "impact": "Workers crash; in-flight jobs must be recoverable from checkpoints.",
        "diagnosis": ["Check memory usage per instance", "Check heap dumps", "Check for leaks in recent changes"],
        "commands": ["kubectl top pods", "kubectl describe pod -l app=worker"],
        "checks": ["Memory limits vs requests", "Queue depth impact", "Checkpoint age"],
        "mitigation": ["Restart unhealthy worker (checkpointed jobs resume)", "Scale out to reduce per-instance load", "Set stricter concurrency limits"],
        "rollback": ["Roll back leak-introducing change if identified"],
        "recovery": ["Verify workers steady-state memory", "Verify job checkpoint recovery"],
        "escalation": ["SRE on-call"],
        "post_incident": ["Corrective action: leak test in CI"],
    },
    "runbook-disk-exhaustion": {
        "service_id": "control-plane",
        "title": "Disk Exhaustion",
        "purpose": "Free disk before databases become read-only.",
        "symptoms": ["Disk usage alerts", "WAL growth", "Write failures", "Database read-only mode"],
        "impact": "Writes fail; backups may fail; PITR at risk.",
        "diagnosis": ["Check disk usage per volume", "Check WAL generation", "Check log sizes", "Check backup storage"],
        "commands": ["df -h", "du -sh /var/lib/postgresql/*", "kubectl get pvc"],
        "checks": ["Retention policies", "Backup frequency", "Log rotation"],
        "mitigation": ["Purge old backups per retention policy", "Archive WAL", "Scale PVC", "Trim logs"],
        "rollback": ["N/A (non-destructive actions only; never delete current data)"],
        "recovery": ["Verify write path", "Verify backup jobs succeed"],
        "escalation": ["Infrastructure on-call"],
        "post_incident": ["Corrective action: disk growth alerting + capacity forecast"],
    },
    "runbook-security-incident": {
        "service_id": "security",
        "title": "Security Incident",
        "purpose": "Contain and investigate security incidents; coordinate with SRE.",
        "symptoms": ["Credential compromise", "DDoS / abuse", "Suspicious traffic", "Privilege escalation", "Malicious uploads", "Vulnerability exploit"],
        "impact": "Depends on scope; potential data exposure and availability impact.",
        "diagnosis": ["Review threat detection signals", "Review audit logs", "Check for credential misuse", "Check abuse detection"],
        "commands": ["GET /api/v1/admin/audit", "GET /sre/incidents"],
        "checks": ["Recent security events", "Unusual traffic patterns", "Privilege changes", "Secrets exposure"],
        "mitigation": [
            "Rotate affected credentials",
            "Revoke sessions",
            "Enable rate limiting / filtering",
            "Isolate affected tenants",
            "Engage security lead; do not destroy evidence",
        ],
        "rollback": ["Revert unauthorized changes"],
        "recovery": ["Verify no residual access", "Verify monitoring coverage"],
        "escalation": ["Security lead", "Incident commander", "Legal/Comms if disclosure required"],
        "post_incident": ["Postmortem required", "Corrective actions tracked with verification"],
    },
    "runbook-certificate-expiration": {
        "service_id": "api-gateway",
        "title": "Certificate Expiration",
        "purpose": "Renew TLS certificates before clients fail.",
        "symptoms": ["TLS handshake failures", "Expiry alert", "Browser warnings"],
        "impact": "All HTTPS traffic fails; platform unreachable.",
        "diagnosis": ["Check certificate not_after", "Check renewal job status", "Check DNS propagation"],
        "commands": ["GET /sre/certificates", "openssl s_client -connect host:443"],
        "checks": ["Auto-renewal enabled", "CA reachable", "DNS records"],
        "mitigation": ["Trigger renewal", "Install renewed certificate", "Verify chain"],
        "rollback": ["Reinstall previous valid certificate if renewal failed"],
        "recovery": ["Verify TLS handshake", "Verify expiry > 30 days"],
        "escalation": ["Platform lead"],
        "post_incident": ["Corrective action: alerting 30 days before expiry"],
    },
    "runbook-dns-failure": {
        "service_id": "api-gateway",
        "title": "DNS Failure",
        "purpose": "Restore name resolution and routing.",
        "symptoms": ["Resolution failures", "Global outage", "TTL propagation issues", "Health-based routing stale"],
        "impact": "Users cannot reach the platform; regions unreachable.",
        "diagnosis": ["Check DNS provider status", "Check records", "Check propagation", "Check load balancer health"],
        "commands": ["nslookup app.novaforge.ai", "dig +trace", "GET /sre/regions"],
        "checks": ["TTL values", "Failover records", "Health checks on routing"],
        "mitigation": ["Update records to healthy regions", "Reduce TTLs", "Enable health-based routing fallback"],
        "rollback": ["Restore previous records once provider recovers"],
        "recovery": ["Verify resolution globally", "Verify traffic routing"],
        "escalation": ["Platform lead"],
        "post_incident": ["Corrective action: multi-provider DNS"],
    },
}


class RunbookManager:
    """Runbook CRUD + built-in playbook seeding."""

    async def seed_playbooks(self, db: AsyncSession) -> int:
        """Insert the standard playbooks if absent (idempotent)."""
        count = 0
        for runbook_id, spec in PLAYBOOKS.items():
            existing = await get_one(db, SRERunbook, runbook_id=runbook_id)
            if existing:
                continue
            db.add(
                SRERunbook(
                    id=new_id(),
                    runbook_id=runbook_id,
                    service_id=spec.get("service_id", ""),
                    title=spec["title"],
                    purpose=spec.get("purpose", ""),
                    symptoms=spec.get("symptoms", []),
                    impact=spec.get("impact", ""),
                    diagnosis=spec.get("diagnosis", []),
                    commands=spec.get("commands", []),
                    checks=spec.get("checks", []),
                    mitigation=spec.get("mitigation", []),
                    rollback=spec.get("rollback", []),
                    recovery=spec.get("recovery", []),
                    escalation=spec.get("escalation", []),
                    post_incident=spec.get("post_incident", []),
                    owner="platform-sre",
                )
            )
            count += 1
        await db.flush()
        return count

    async def create(
        self,
        db: AsyncSession,
        *,
        title: str,
        service_id: str = "",
        purpose: str = "",
        symptoms: Optional[list[str]] = None,
        impact: str = "",
        diagnosis: Optional[list[str]] = None,
        commands: Optional[list[str]] = None,
        checks: Optional[list[str]] = None,
        mitigation: Optional[list[str]] = None,
        rollback: Optional[list[str]] = None,
        recovery: Optional[list[str]] = None,
        escalation: Optional[list[str]] = None,
        post_incident: Optional[list[str]] = None,
        owner: str = "",
        runbook_id: Optional[str] = None,
    ) -> SRERunbook:
        runbook_id = runbook_id or new_key("runbook")
        runbook = SRERunbook(
            id=new_id(),
            runbook_id=runbook_id,
            service_id=service_id,
            title=title,
            purpose=purpose,
            symptoms=symptoms or [],
            impact=impact,
            diagnosis=diagnosis or [],
            commands=commands or [],
            checks=checks or [],
            mitigation=mitigation or [],
            rollback=rollback or [],
            recovery=recovery or [],
            escalation=escalation or [],
            post_incident=post_incident or [],
            owner=owner,
        )
        db.add(runbook)
        await db.flush()
        return runbook

    async def update(self, db: AsyncSession, runbook_id: str, **values: dict) -> Optional[SRERunbook]:
        runbook = await get_one(db, SRERunbook, runbook_id=runbook_id)
        if runbook is None:
            return None
        for key, value in values.items():
            if hasattr(runbook, key):
                setattr(runbook, key, value)
        await db.flush()
        return runbook

    async def list(self, db: AsyncSession, *, service_id: str = "", limit: int = 100, offset: int = 0) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SRERunbook, limit=limit, offset=offset, order_by="title", descending=False, service_id=service_id
        )
        return [r.to_dict() for r in items], total

    async def get(self, db: AsyncSession, runbook_id: str) -> Optional[dict]:
        runbook = await get_one(db, SRERunbook, runbook_id=runbook_id)
        return runbook.to_dict() if runbook else None

    async def for_service(self, db: AsyncSession, service_id: str) -> Optional[dict]:
        result = await db.execute(
            select(SRERunbook).where(SRERunbook.service_id == service_id).limit(1)
        )
        runbook = result.scalar_one_or_none()
        return runbook.to_dict() if runbook else None


runbook_manager = RunbookManager()
