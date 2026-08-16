"""Runbook / playbook system (Volume 35).

Reusable runbooks for every critical failure scenario. Default runbooks
are configuration (not operational data) and are seeded through
sre/seed.py. The structure follows the mandated runbook template:
purpose, symptoms, impact, diagnosis, commands, checks, mitigation,
rollback, recovery, escalation, post-incident.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import RUNBOOK_SCENARIOS
from app.sre.models import SRERunbook
from app.sre.store import new_key

logger = logging.getLogger(__name__)


async def create_runbook(
    db: AsyncSession,
    *,
    runbook_id: str,
    service_id: str = "",
    title: str,
    purpose: str = "",
    symptoms: Optional[list] = None,
    impact: str = "",
    diagnosis: Optional[list] = None,
    commands: Optional[list] = None,
    checks: Optional[list] = None,
    mitigation: Optional[list] = None,
    rollback: Optional[list] = None,
    recovery: Optional[list] = None,
    escalation: Optional[list] = None,
    post_incident: Optional[list] = None,
    owner: str = "",
) -> SRERunbook:
    runbook = SRERunbook(
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


async def search_runbooks(
    db: AsyncSession,
    *,
    service_id: str = "",
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    stmt = select(SRERunbook)
    if service_id:
        stmt = stmt.where(SRERunbook.service_id == service_id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(SRERunbook.title).offset(offset).limit(limit)
    runbooks = list((await db.execute(stmt)).scalars().all())
    return [runbook.to_dict() for runbook in runbooks], total


async def get_runbook(db: AsyncSession, runbook_id: str) -> Optional[SRERunbook]:
    result = await db.execute(select(SRERunbook).where(SRERunbook.runbook_id == runbook_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Default runbooks (seeded once into an empty catalog)
# ---------------------------------------------------------------------------

def default_runbooks() -> list[dict]:
    return [
        {
            "runbook_id": "rb-api-outage",
            "service_id": "api-gateway",
            "title": "API Outage",
            "scenario": "api_outage",
            "purpose": "Restore API availability after total or partial API outage.",
            "symptoms": [
                "HTTP 5xx spike on /api/v1",
                "readiness probe failing",
                "customer report: everything is down",
                "error-budget burning fast",
            ],
            "impact": "All platform traffic affected; Tier 0 incident.",
            "diagnosis": ["Check /health/dependencies for infra failure", "Inspect error-rate golden signal per service", "Correlate with recent deployments and config changes"],
            "commands": ["curl /health/ready", "kubectl get pods -n novaforge | grep api", "kubectl logs deploy/novaforge-api --tail=200"],
            "checks": ["Database connectivity (SELECT 1)", "Redis ping", "Rate limiter state", "Recent rollouts"],
            "mitigation": ["Restart unhealthy API pods (safe automation)", "Scale API pool if saturation", "Fail over to second region if regional"],
            "rollback": ["Roll back the latest deployment to previous version", "Disable feature flags enabled in the last 24h"],
            "recovery": ["Confirm error rate back to baseline for 15 minutes", "Drain and restart canary", "Verify SLO budget status"],
            "escalation": ["SEV1 -> SEV0 when >5% of requests failing or all regions affected", "Page Tier 0 on-call"],
            "post_incident": ["Draft postmortem", "Track corrective actions", "Verify canary thresholds triggered"],
        },
        {
            "runbook_id": "rb-db-outage",
            "service_id": "postgresql",
            "title": "Database (PostgreSQL) Outage",
            "scenario": "database_outage",
            "purpose": "Recover from degraded or failed PostgreSQL primary.",
            "symptoms": ["/health/ready reports database down", "connection pool exhaustion", "query latency spikes", "write failures"],
            "impact": "Most services degraded; data writes blocked.",
            "diagnosis": ["Check database connectivity and replication lag", "Inspect connection pool and lock waits", "Check disk and storage"],
            "commands": ["pg_isready -h <primary>", "kubectl get pods -l app=postgres", "SHOW pg_stat_activity", "SELECT pg_wal_lsn_diff(...)"],
            "checks": ["Backup freshness (RPO compliance)", "Replica lag", "Storage utilization", "Disk exhaustion"],
            "mitigation": ["Promote replica (failover) when policy allows", "Freeze non-critical writes", "Fail over read traffic to replicas"],
            "rollback": ["Switch back to original primary after repairs (failback)", "Point-in-time recovery if data loss"],
            "recovery": ["Verify data integrity", "Confirm replication lag < 10s", "Restore backup job schedule"],
            "escalation": ["SEV0 when primary unavailability > RTO", "Database lead required"],
            "post_incident": ["Postmortem with PITR review", "Verify restore tests", "Track capacity growth"],
        },
        {
            "runbook_id": "rb-redis-outage",
            "service_id": "redis",
            "title": "Redis Outage",
            "scenario": "redis_outage",
            "purpose": "Recover cache, session and queue infrastructure after Redis failure.",
            "symptoms": ["redis ping fails", "rate limiting errors", "queue backlog growth", "cache miss storms"],
            "impact": "Caching and queueing degraded; sessions may reset.",
            "diagnosis": ["Check Redis process and memory", "Inspect eviction policy counters", "Check replication"],
            "commands": ["redis-cli ping", "redis-cli INFO memory", "redis-cli INFO replication", "redis-cli --latency"],
            "checks": ["Memory utilization", "Evicted keys rate", "Queue recovery", "Persistent AOF/RDB availability"],
            "mitigation": ["Restart Redis (data loss acceptable for cache-only roles)", "Fail over to replica where persistence required", "Scale memory or adjust eviction policy"],
            "rollback": ["Repoint clients back to original after recovery"],
            "recovery": ["Rebuild caches gradually", "Replay event bus queue", "Verify rate limiting restored"],
            "escalation": ["SEV2 for cache-only impact", "SEV1 when queues blocked"],
            "post_incident": ["Postmortem on eviction/memory policy", "Verify queue recovery"],
        },
        {
            "runbook_id": "rb-qdrant-outage",
            "service_id": "qdrant",
            "title": "Qdrant Vector Store Outage",
            "scenario": "qdrant_outage",
            "purpose": "Restore vector search after Qdrant failure.",
            "symptoms": ["vector search errors", "RAG degrading", "embedding pipeline backlog"],
            "impact": "RAG and repository intelligence degraded.",
            "diagnosis": ["Check Qdrant health endpoint", "Inspect collection status", "Check storage"],
            "commands": ["curl http://qdrant:6333/healthz", "curl http://qdrant:6333/collections"],
            "checks": ["Collection replica status", "Index health", "Storage", "Snapshots freshness"],
            "mitigation": ["Restart Qdrant", "Restore from latest snapshot", "Rebuild index from embeddings pipeline"],
            "rollback": ["Switch to read replica collection"],
            "recovery": ["Verify search latency back to baseline", "Re-run missed embedding jobs from queue"],
            "escalation": ["SEV1 when RAG unavailable", "Escalate to data platform team"],
            "post_incident": ["Postmortem on snapshot strategy", "Verify restore test"],
        },
        {
            "runbook_id": "rb-neo4j-outage",
            "service_id": "neo4j",
            "title": "Neo4j Graph Outage",
            "scenario": "neo4j_outage",
            "purpose": "Recover graph database after failure.",
            "symptoms": ["graph queries error", "dependency graph unavailable", "relationship checks failing"],
            "impact": "Dependency/relationship features degraded.",
            "diagnosis": ["Check Neo4j connectivity", "Inspect storage and backups"],
            "commands": ["cypher-shell 'RETURN 1'", "kubectl get pods -l app=neo4j"],
            "checks": ["Backup freshness", "Storage utilization", "Index consistency"],
            "mitigation": ["Restart Neo4j", "Restore from backup", "Run consistency check"],
            "rollback": ["Rebuild from export if schema change caused issue"],
            "recovery": ["Verify dependency graph queries", "Resume relationship indexer jobs"],
            "escalation": ["SEV2", "Graph team lead"],
            "post_incident": ["Verify restore procedure", "Track storage growth"],
        },
        {
            "runbook_id": "rb-ai-provider-outage",
            "service_id": "model-gateway",
            "title": "AI Provider Outage",
            "scenario": "ai_provider_outage",
            "purpose": "Degrade safely and fail over when a primary AI provider fails.",
            "symptoms": ["provider error rate spike", "401/429/5xx from provider", "model latency spike", "AI cost anomaly"],
            "impact": "AI features degraded; platform remains available with fallbacks.",
            "diagnosis": ["Check provider status page", "Inspect model gateway error classification", "Check circuit breaker state"],
            "commands": ["curl /health/dependencies (ai_provider)", "Check circuit_breaker_registry snapshot"],
            "checks": ["Provider quota", "Fallback provider availability", "Organization policy allows fallback?", "Rate limit state"],
            "mitigation": ["Enable fallback provider from approved list", "Queue embeddings/vision work when unavailable", "Return controlled degraded responses - never fabricate"],
            "rollback": ["Return traffic to primary when provider recovers"],
            "recovery": ["Verify tokens/cost within guardrails", "Replay queued jobs", "Confirm quality of fallback responses"],
            "escalation": ["SEV1 when all providers down", "AI platform manager"],
            "post_incident": ["Postmortem on provider dependency", "Adjust provider weights"],
        },
        {
            "runbook_id": "rb-deployment-failure",
            "service_id": "release",
            "title": "Deployment Failure / Rollback",
            "scenario": "deployment_failure",
            "purpose": "Contain failed deployments and roll back safely.",
            "symptoms": ["canary error rate spike", "post-deploy SLO violation", "health check failure after rollout", "alerts tied to a deployment"],
            "impact": "Service instability; automated rollback may trigger.",
            "diagnosis": ["Check canary run results", "Compare error rate before/after", "Inspect deployment record"],
            "commands": ["kubectl rollout status deploy/<svc>", "kubectl rollout undo deploy/<svc>", "flagger check deployment"],
            "checks": ["Triggering alert (sre_alerts)", "Error budget state", "Rollback safety: previous version healthy", "Feature flags involved"],
            "mitigation": ["Trigger automatic rollback when thresholds met", "Disable feature flag", "Tune canary thresholds for future runs"],
            "rollback": ["Rollback to last known-good version", "Verify post-rollback health 15 min"],
            "recovery": ["Record rollback in SREDeployment", "Verify deployment frequency metric"],
            "escalation": ["SEV2, deployment owner", "SEV1 if rollback fails"],
            "post_incident": ["Corrective actions on CI checks", "Extend canary duration"],
        },
        {
            "runbook_id": "rb-auth-outage",
            "service_id": "auth",
            "title": "Authentication Outage",
            "scenario": "authentication_outage",
            "purpose": "Restore authentication and authorization services.",
            "symptoms": ["login failures 5xx", "token validation errors", "auth latency spike", "401 bursts"],
            "impact": "All users locked out; Tier 0.",
            "diagnosis": ["Check auth service health", "Check DB and Redis (session store)", "Check JWT key state", "Check security incidents"],
            "commands": ["curl /health/ready", "kubectl logs deploy/novaforge-auth"],
            "checks": ["Database connectivity", "Redis sessions", "Rate limiter on /auth endpoints", "Recent security events"],
            "mitigation": ["Restart auth service", "Fail over session store", "Extend token verification caching if DB slow"],
            "rollback": ["Roll back auth deployment"],
            "recovery": ["Verify login rate restored", "Verify token refresh"],
            "escalation": ["SEV0 as auth is Tier 0", "Security lead if compromise suspected"],
            "post_incident": ["Postmortem", "Verify credential rotation policies"],
        },
        {
            "runbook_id": "rb-queue-failure",
            "service_id": "queue",
            "title": "Queue / Worker Failure",
            "scenario": "queue_failure",
            "purpose": "Recover asynchronous pipelines after queue or worker failure.",
            "symptoms": ["queue depth growing", "oldest message age high", "dead letters increasing", "worker heartbeats stale"],
            "impact": "Indexing, embeddings, notifications and workflows delayed.",
            "diagnosis": ["Check queue depth per pipeline", "Inspect worker health", "Inspect DLQ entries"],
            "commands": ["redis-cli LLEN novaforge:queue:*", "kubectl get pods -l role=worker"],
            "checks": ["Backlog growth classification", "Poison messages", "Worker concurrency", "Retry counts"],
            "mitigation": ["Restart unhealthy workers (safe)", "Scale worker pool", "Move poison messages to DLQ", "Replay DLQ entries"],
            "rollback": ["N/A - replay instead"],
            "recovery": ["Verify earliest message age drops", "Confirm DLQ drain"],
            "escalation": ["SEV2 when backlog critical", "SEV1 when SLO at risk"],
            "post_incident": ["Add poison-message handling", "Verify idempotent consumers"],
        },
        {
            "runbook_id": "rb-high-latency",
            "service_id": "api-gateway",
            "title": "High Latency",
            "scenario": "high_latency",
            "purpose": "Diagnose and reduce sustained high latency.",
            "symptoms": ["p95 latency above SLO", "timeout errors", "queue delay growing", "resource saturation"],
            "impact": "SLO violations; degraded UX; error budget burn.",
            "diagnosis": ["Compare latency by service/region", "Check saturation (CPU/memory/queue)", "Check slow queries", "Check provider latency"],
            "commands": ["/metrics scrape latency histograms", "EXPLAIN ANALYZE on slow queries"],
            "checks": ["Golden signals per service", "DB slow query log", "Provider latency", "Auto-scaling lag"],
            "mitigation": ["Scale saturated pools", "Throttle non-critical load", "Enable load shedding", "Reduce p95 via caching"],
            "rollback": ["Roll back recent perf-regressing change"],
            "recovery": ["Verify p95 back in budget", "Monitor for 1 hour"],
            "escalation": ["SEV2, performance owner"],
            "post_incident": ["Add latency regression checks", "Capacity plan update"],
        },
        {
            "runbook_id": "rb-memory-exhaustion",
            "service_id": "platform",
            "title": "Memory Exhaustion",
            "scenario": "memory_exhaustion",
            "purpose": "Recover pods/processes from memory exhaustion.",
            "symptoms": ["OOMKilled pods", "high memory saturation", "restart loops"],
            "impact": "Service restarts; possible brief unavailability.",
            "diagnosis": ["Check memory utilization", "Inspect recent deploys", "Check leak candidates"],
            "commands": ["kubectl top pods", "kubectl describe pod <p> | grep -i oom"],
            "checks": ["Memory limits", "Pod restart count", "Traffic correlates to memory?"],
            "mitigation": ["Restart affected pods", "Raise memory limits within capacity plan", "Reduce concurrency"],
            "rollback": ["Roll back suspect change"],
            "recovery": ["Verify memory returns to baseline"],
            "escalation": ["SEV2"],
            "post_incident": ["Add memory regression monitoring"],
        },
        {
            "runbook_id": "rb-disk-exhaustion",
            "service_id": "platform",
            "title": "Disk Exhaustion",
            "scenario": "disk_exhaustion",
            "purpose": "Prevent and recover from disk-full conditions.",
            "symptoms": ["disk saturation critical", "write failures", "backup failures"],
            "impact": "Database writes fail; backups fail; degradation.",
            "diagnosis": ["Check disk utilization", "Find large consumers (logs, temp, snapshots)"],
            "commands": ["df -h", "du -sh /var/log /data"],
            "checks": ["Capacity metric disk", "Backup job status", "Log rotation"],
            "mitigation": ["Purge rotated logs", "Move snapshots to object storage", "Expand volume per capacity plan"],
            "rollback": ["N/A"],
            "recovery": ["Verify disk under threshold", "Verify backups succeed"],
            "escalation": ["SEV2, storage owner"],
            "post_incident": ["Add disk growth forecast"],
        },
        {
            "runbook_id": "rb-security-incident",
            "service_id": "security",
            "title": "Security Incident",
            "scenario": "security_incident",
            "purpose": "Integrate security incidents with incident management.",
            "symptoms": ["credential compromise signal", "suspicious traffic / DDoS", "privilege escalation", "malicious upload"],
            "impact": "Depends on compromise extent; containment first.",
            "diagnosis": ["Confirm security alert source", "Correlate with auth and API logs", "Check abuse detection signals"],
            "commands": ["kubectl get events", "Inspect audit log for affected tenant"],
            "checks": ["Rate limits", "Token revocation state", "Security governance incidents"],
            "mitigation": ["Revoke affected credentials (with approval)", "Enable stricter rate limiting", "Block malicious actor (IP/API key)", "Isolate affected tenant"],
            "rollback": ["Restore from clean state if compromise"],
            "recovery": ["Verify abuse stopped", "Rotate credentials", "Notify per policy"],
            "escalation": ["Always with Security Lead", "External disclosure per policy"],
            "post_incident": ["Security postmortem", "Track hardenings as corrective actions"],
        },
        {
            "runbook_id": "rb-certificate-expiration",
            "service_id": "platform",
            "title": "Certificate Expiration",
            "scenario": "certificate_expiration",
            "purpose": "Renew TLS certificates before expiry breaks traffic.",
            "symptoms": ["certificate monitoring alert", "TLS handshake failures", "browser warnings"],
            "impact": "Traffic fails at TLS if expiry passes; alerting well ahead prevents this.",
            "diagnosis": ["Check certificate records for expiring status"],
            "commands": ["openssl s_client -connect <host>:443 -servername <host> 2>/dev/null | openssl x509 -noout -dates"],
            "checks": ["not_after dates", "auto_renew settings", "renewal job logs"],
            "mitigation": ["Trigger automated renewal (Let's Encrypt / managed CA)", "Manual replacement for exotic certs"],
            "rollback": ["Reinstall previous cert if renewal misconfigured"],
            "recovery": ["Verify handshake + expiry pushed out"],
            "escalation": ["SEV3 30 days out; SEV2 < 7 days; SEV1 < 24h"],
            "post_incident": ["Add expiry alerting to monitoring"],
        },
        {
            "runbook_id": "rb-dns-failure",
            "service_id": "platform",
            "title": "DNS Failure",
            "scenario": "dns_failure",
            "purpose": "Detect and recover from DNS resolution failures.",
            "symptoms": ["DNS resolution latency", "connection errors to services", "regional routing failure"],
            "impact": "Users cannot reach platform; services cannot reach dependencies.",
            "diagnosis": ["Check DNS resolver health", "Test resolution per region"],
            "commands": ["nslookup api.novaforge.ai", "kubectl exec -- nslookup <svc>"],
            "checks": ["DNS monitoring records", "Propagation state", "TTL status"],
            "mitigation": ["Fail over to secondary resolver", "Use IP-based routing temporarily", "Clear cache poisoning vectors"],
            "rollback": ["Restore primary resolver"],
            "recovery": ["Verify resolution latency", "Verify regional routing"],
            "escalation": ["SEV1 if global"],
            "post_incident": ["Add DNS checks to dependency monitoring"],
        },
    ]


def scenario_for_runbook(runbook: dict) -> str:
    return runbook.get("scenario", "")


def validate_default_scenarios() -> list[str]:
    """Self-check: every defined scenario has a default runbook."""
    defined = {scenario_for_runbook(rb) for rb in default_runbooks()}
    missing = [scenario for scenario in RUNBOOK_SCENARIOS if scenario not in defined]
    return missing