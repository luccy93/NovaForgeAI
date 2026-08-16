"""Service catalog and dependency graph (Volume 35).

Registers NovaForge services with tier classification, SLO defaults,
recovery objectives, and a directed dependency graph that answers
"If service X fails, what breaks?".
"""

import logging
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    DEPLOYMENT_ROLLING,
    TIER_0_CRITICAL,
    TIER_1_HIGH,
    TIER_2_IMPORTANT,
    TIER_3_NON_CRITICAL,
    TIER_DEFAULTS,
)
from app.sre.models import (
    SREDependencyHealth,
    SRERegion,
    SRERunbook,
    SREService,
    SREServiceDependency,
    SREServiceVersion,
    SRESLO,
    SREStatusComponent,
)
from app.sre.store import get_one, new_id, new_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default service catalog (tier classification per Volume 35)
# ---------------------------------------------------------------------------

DEFAULT_SERVICES: list[dict] = [
    # Tier 0 - critical
    {"service_id": "auth", "name": "Authentication", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "platform-security", "team": "Security", "deployment_strategy": "blue-green",
     "scaling_strategy": "reactive", "backup_strategy": "daily PITR + 15min WAL"},
    {"service_id": "api-gateway", "name": "API Gateway", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "platform-core", "team": "Platform", "deployment_strategy": DEPLOYMENT_ROLLING,
     "scaling_strategy": "predictive + reactive", "backup_strategy": "stateless"},
    {"service_id": "control-plane", "name": "Control Plane", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "platform-core", "team": "Platform", "deployment_strategy": "blue-green",
     "scaling_strategy": "reactive", "backup_strategy": "continuous PITR"},
    {"service_id": "agent-runtime", "name": "Core Agent Runtime", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "ai-agents", "team": "AI Platform", "deployment_strategy": "canary",
     "scaling_strategy": "queue-based", "backup_strategy": "task state snapshots"},
    {"service_id": "workflow-runtime", "name": "Workflow Runtime", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "ai-agents", "team": "Automation", "deployment_strategy": "canary",
     "scaling_strategy": "queue-based", "backup_strategy": "execution checkpoints"},
    {"service_id": "event-bus", "name": "Event Infrastructure", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "platform-core", "team": "Infrastructure", "deployment_strategy": "rolling",
     "scaling_strategy": "reactive", "backup_strategy": "redis persistence + DLQ"},
    {"service_id": "billing", "name": "Billing", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "business-systems", "team": "Billing", "deployment_strategy": "blue-green",
     "scaling_strategy": "reactive", "backup_strategy": "continuous PITR"},
    {"service_id": "authorization", "name": "Authorization", "tier": TIER_0_CRITICAL, "criticality": "critical",
     "owner": "platform-security", "team": "Security", "deployment_strategy": "blue-green",
     "scaling_strategy": "reactive", "backup_strategy": "daily PITR"},
    # Tier 1 - high
    {"service_id": "repository-intelligence", "name": "Repository Intelligence", "tier": TIER_1_HIGH, "criticality": "high",
     "owner": "code-analysis", "team": "Code Intelligence", "deployment_strategy": "rolling",
     "scaling_strategy": "queue-based", "backup_strategy": "index metadata backups"},
    {"service_id": "rag", "name": "RAG Pipeline", "tier": TIER_1_HIGH, "criticality": "high",
     "owner": "ai-agents", "team": "AI Platform", "deployment_strategy": "canary",
     "scaling_strategy": "queue-based", "backup_strategy": "qdrant snapshots"},
    {"service_id": "ai-chat", "name": "AI Chat", "tier": TIER_1_HIGH, "criticality": "high",
     "owner": "ai-agents", "team": "AI Platform", "deployment_strategy": "canary",
     "scaling_strategy": "latency-based", "backup_strategy": "conversation persistence"},
    {"service_id": "agent-services", "name": "Agent Services", "tier": TIER_1_HIGH, "criticality": "high",
     "owner": "ai-agents", "team": "AI Platform", "deployment_strategy": "canary",
     "scaling_strategy": "queue-based", "backup_strategy": "run snapshots"},
    {"service_id": "search", "name": "Search", "tier": TIER_1_HIGH, "criticality": "high",
     "owner": "code-analysis", "team": "Code Intelligence", "deployment_strategy": "rolling",
     "scaling_strategy": "reactive", "backup_strategy": "qdrant snapshots"},
    {"service_id": "deployment", "name": "Deployment Platform", "tier": TIER_1_HIGH, "criticality": "high",
     "owner": "release", "team": "Release Engineering", "deployment_strategy": "canary",
     "scaling_strategy": "reactive", "backup_strategy": "stateless"},
    {"service_id": "security", "name": "Security Scanning", "tier": TIER_1_HIGH, "criticality": "high",
     "owner": "platform-security", "team": "Security", "deployment_strategy": "rolling",
     "scaling_strategy": "queue-based", "backup_strategy": "scan result persistence"},
    # Tier 2 - important
    {"service_id": "analytics", "name": "Analytics", "tier": TIER_2_IMPORTANT, "criticality": "medium",
     "owner": "data", "team": "Data Platform", "deployment_strategy": "rolling",
     "scaling_strategy": "scheduled", "backup_strategy": "daily backups"},
    {"service_id": "reports", "name": "Reports", "tier": TIER_2_IMPORTANT, "criticality": "medium",
     "owner": "data", "team": "Data Platform", "deployment_strategy": "rolling",
     "scaling_strategy": "scheduled", "backup_strategy": "daily backups"},
    {"service_id": "marketplace", "name": "Marketplace", "tier": TIER_2_IMPORTANT, "criticality": "medium",
     "owner": "ecosystem", "team": "Ecosystem", "deployment_strategy": "rolling",
     "scaling_strategy": "reactive", "backup_strategy": "daily backups"},
    {"service_id": "documentation", "name": "Documentation", "tier": TIER_2_IMPORTANT, "criticality": "medium",
     "owner": "ecosystem", "team": "Ecosystem", "deployment_strategy": "rolling",
     "scaling_strategy": "reactive", "backup_strategy": "static content"},
    {"service_id": "notifications", "name": "Notifications", "tier": TIER_2_IMPORTANT, "criticality": "medium",
     "owner": "platform-core", "team": "Platform", "deployment_strategy": "rolling",
     "scaling_strategy": "queue-based", "backup_strategy": "delivery state persistence"},
    # Tier 3 - non-critical
    {"service_id": "experimental", "name": "Experimental Features", "tier": TIER_3_NON_CRITICAL, "criticality": "low",
     "owner": "innovation", "team": "Research", "deployment_strategy": "rolling",
     "scaling_strategy": "reactive", "backup_strategy": "none required"},
    {"service_id": "long-running-reports", "name": "Long-Running Reports", "tier": TIER_3_NON_CRITICAL, "criticality": "low",
     "owner": "data", "team": "Data Platform", "deployment_strategy": "rolling",
     "scaling_strategy": "scheduled", "backup_strategy": "none required"},
    {"service_id": "historical-analytics", "name": "Historical Analytics", "tier": TIER_3_NON_CRITICAL, "criticality": "low",
     "owner": "data", "team": "Data Platform", "deployment_strategy": "rolling",
     "scaling_strategy": "scheduled", "backup_strategy": "none required"},
]

# Service -> dependency edges (service | external).
DEFAULT_DEPENDENCIES: list[tuple[str, str, str]] = [
    ("ai-chat", "api-gateway", "service"),
    ("ai-chat", "auth", "service"),
    ("ai-chat", "rag", "service"),
    ("ai-chat", "qdrant", "external"),
    ("ai-chat", "model-gateway", "external"),
    ("ai-chat", "redis", "external"),
    ("ai-chat", "postgresql", "external"),
    ("rag", "qdrant", "external"),
    ("rag", "redis", "external"),
    ("rag", "ai_provider_openai", "external"),
    ("agent-runtime", "event-bus", "external"),
    ("agent-runtime", "postgresql", "external"),
    ("agent-runtime", "redis", "external"),
    ("agent-services", "agent-runtime", "service"),
    ("agent-services", "ai_provider_openai", "external"),
    ("agent-services", "ai_provider_anthropic", "external"),
    ("workflow-runtime", "event-bus", "external"),
    ("workflow-runtime", "postgresql", "external"),
    ("workflow-runtime", "redis", "external"),
    ("repository-intelligence", "postgresql", "external"),
    ("repository-intelligence", "neo4j", "external"),
    ("repository-intelligence", "qdrant", "external"),
    ("repository-intelligence", "github", "external"),
    ("search", "qdrant", "external"),
    ("search", "redis", "external"),
    ("deployment", "github", "external"),
    ("deployment", "object_storage", "external"),
    ("billing", "stripe", "external"),
    ("billing", "postgresql", "external"),
    ("api-gateway", "auth", "service"),
    ("api-gateway", "authorization", "service"),
    ("notifications", "event-bus", "external"),
    ("analytics", "postgresql", "external"),
    ("reports", "analytics", "service"),
    ("marketplace", "postgresql", "external"),
    ("documentation", "object_storage", "external"),
    ("control-plane", "postgresql", "external"),
    ("control-plane", "event-bus", "external"),
]

# Default SLOs seeded with the catalog (availability + latency per tier).
DEFAULT_SLOS: list[dict] = [
    {"slo_id": "slo-api-availability", "service_id": "api-gateway", "name": "API Availability",
     "sli_type": "availability", "target": 0.9995, "window": "monthly", "severity": "SEV1",
     "measurement": "successful_requests / total_requests", "owner": "platform-core"},
    {"slo_id": "slo-api-latency", "service_id": "api-gateway", "name": "API Latency p95",
     "sli_type": "latency", "target": 0.95, "window": "weekly", "severity": "SEV2",
     "measurement": "p95 latency < 300ms", "owner": "platform-core"},
    {"slo_id": "slo-auth-availability", "service_id": "auth", "name": "Authentication Availability",
     "sli_type": "availability", "target": 0.9999, "window": "monthly", "severity": "SEV0",
     "measurement": "successful_requests / total_requests", "owner": "platform-security"},
    {"slo_id": "slo-ai-chat-availability", "service_id": "ai-chat", "name": "AI Chat Availability",
     "sli_type": "availability", "target": 0.999, "window": "monthly", "severity": "SEV1",
     "measurement": "successful_requests / total_requests", "owner": "ai-agents"},
    {"slo_id": "slo-rag-availability", "service_id": "rag", "name": "RAG Availability",
     "sli_type": "availability", "target": 0.999, "window": "monthly", "severity": "SEV1",
     "measurement": "successful_requests / total_requests", "owner": "ai-agents"},
    {"slo_id": "slo-indexing-freshness", "service_id": "repository-intelligence", "name": "Indexing Freshness",
     "sli_type": "freshness", "target": 0.95, "window": "weekly", "severity": "SEV2",
     "measurement": "indexes fresh within 5 minutes", "owner": "code-analysis"},
    {"slo_id": "slo-workflow-success", "service_id": "workflow-runtime", "name": "Workflow Success Rate",
     "sli_type": "success_rate", "target": 0.99, "window": "monthly", "severity": "SEV1",
     "measurement": "successful_executions / total_executions", "owner": "ai-agents"},
    {"slo_id": "slo-event-processing", "service_id": "event-bus", "name": "Event Processing Availability",
     "sli_type": "availability", "target": 0.9999, "window": "monthly", "severity": "SEV1",
     "measurement": "delivered_events / published_events", "owner": "platform-core"},
    {"slo_id": "slo-deployment-success", "service_id": "deployment", "name": "Deployment Success Rate",
     "sli_type": "success_rate", "target": 0.995, "window": "monthly", "severity": "SEV1",
     "measurement": "successful_deployments / total_deployments", "owner": "release"},
]

DEFAULT_RUNBOOK_IDS: dict[str, str] = {
    "api-gateway": "runbook-api-outage",
    "auth": "runbook-auth-outage",
    "agent-runtime": "runbook-agent-outage",
}


class ServiceCatalog:
    """Service registry with tiered SLO defaults and dependency graph."""

    def __init__(self) -> None:
        self._seeded = False

    # ------------------------------------------------------------- seeding
    async def seed(self, db: AsyncSession) -> int:
        """Insert default catalog, dependencies and SLOs if absent (idempotent)."""
        if self._seeded:
            return 0
        count = 0
        for spec in DEFAULT_SERVICES:
            existing = await get_one(db, SREService, service_id=spec["service_id"])
            if existing:
                continue
            tier_defaults = TIER_DEFAULTS.get(spec["tier"], {})
            spec = {**spec, "runbook_id": DEFAULT_RUNBOOK_IDS.get(spec["service_id"], "")}
            db.add(SREService(**self._hydrate(spec, tier_defaults)))
            count += 1
        for slo in DEFAULT_SLOS:
            existing = await get_one(db, SRESLO, slo_id=slo["slo_id"])
            if existing:
                continue
            db.add(SRESLO(**slo))
            count += 1
        for service_id, depends_on, kind in DEFAULT_DEPENDENCIES:
            existing = await get_one(
                db, SREServiceDependency, service_id=service_id, depends_on=depends_on
            )
            if existing:
                continue
            db.add(
                SREServiceDependency(
                    id=new_id(),
                    service_id=service_id,
                    depends_on=depends_on,
                    kind=kind,
                    critical=kind == "external",
                )
            )
            count += 1
        for region in ("us-east", "eu-west", "ap-south"):
            existing = await get_one(db, SRERegion, region=region)
            if existing:
                continue
            db.add(SRERegion(region=region, mode="active-active", status="operational", capacity_percent=50.0))
            count += 1
        await db.flush()
        self._seeded = True
        logger.info("SRE catalog seeded (%d records)", count)
        return count

    @staticmethod
    def _hydrate(spec: dict, tier_defaults: dict) -> dict:
        return {
            "id": new_id(),
            "service_id": spec["service_id"],
            "name": spec["name"],
            "tier": spec.get("tier", TIER_1_HIGH),
            "criticality": spec.get("criticality", "high"),
            "owner": spec.get("owner", ""),
            "team": spec.get("team", ""),
            "deployment_strategy": spec.get("deployment_strategy", DEPLOYMENT_ROLLING),
            "scaling_strategy": spec.get("scaling_strategy", ""),
            "backup_strategy": spec.get("backup_strategy", ""),
            "rto_minutes": tier_defaults.get("rto_minutes", 60),
            "rpo_minutes": tier_defaults.get("rpo_minutes", 60),
            "runbook_id": spec.get("runbook_id", ""),
            "status": "operational",
            "metadata_json": {"availability_target": tier_defaults.get("availability_target", 0.999)},
        }

    # -------------------------------------------------------------- catalog
    async def register(
        self,
        db: AsyncSession,
        *,
        service_id: str,
        name: str,
        tier: str,
        criticality: str = "high",
        owner: str = "",
        team: str = "",
        deployment_strategy: str = DEPLOYMENT_ROLLING,
        scaling_strategy: str = "",
        backup_strategy: str = "",
        rto_minutes: Optional[int] = None,
        rpo_minutes: Optional[int] = None,
        runbook_id: str = "",
        on_call: str = "",
    ) -> SREService:
        """Register or update a service in the catalog."""
        service = await get_one(db, SREService, service_id=service_id)
        tier_defaults = TIER_DEFAULTS.get(tier, {})
        if service is None:
            service = SREService(
                id=new_id(),
                service_id=service_id,
                name=name,
                tier=tier,
                criticality=criticality,
                owner=owner,
                team=team,
                deployment_strategy=deployment_strategy,
                scaling_strategy=scaling_strategy,
                backup_strategy=backup_strategy,
                rto_minutes=rto_minutes if rto_minutes is not None else tier_defaults.get("rto_minutes", 60),
                rpo_minutes=rpo_minutes if rpo_minutes is not None else tier_defaults.get("rpo_minutes", 60),
                runbook_id=runbook_id,
                on_call=on_call,
                status="operational",
            )
            db.add(service)
            await db.flush()
            db.add(
                SREServiceVersion(
                    id=new_id(),
                    service_id=service_id,
                    version=1,
                    spec=service.to_dict(),
                    created_by="system",
                )
            )
        else:
            for key, value in {
                "name": name,
                "tier": tier,
                "criticality": criticality,
                "owner": owner,
                "team": team,
                "deployment_strategy": deployment_strategy,
                "scaling_strategy": scaling_strategy,
                "backup_strategy": backup_strategy,
                "on_call": on_call,
            }.items():
                setattr(service, key, value)
            if rto_minutes is not None:
                service.rto_minutes = rto_minutes
            if rpo_minutes is not None:
                service.rpo_minutes = rpo_minutes
            if runbook_id:
                service.runbook_id = runbook_id
            await db.flush()
        return service

    async def add_dependency(self, db: AsyncSession, service_id: str, depends_on: str, kind: str = "service") -> SREServiceDependency:
        existing = await get_one(db, SREServiceDependency, service_id=service_id, depends_on=depends_on)
        if existing:
            return existing
        dep = SREServiceDependency(id=new_id(), service_id=service_id, depends_on=depends_on, kind=kind)
        db.add(dep)
        await db.flush()
        return dep

    async def remove_dependency(self, db: AsyncSession, service_id: str, depends_on: str) -> bool:
        existing = await get_one(db, SREServiceDependency, service_id=service_id, depends_on=depends_on)
        if existing is None:
            return False
        await db.delete(existing)
        await db.flush()
        return True

    async def set_status(self, db: AsyncSession, service_id: str, status: str) -> Optional[SREService]:
        service = await get_one(db, SREService, service_id=service_id)
        if service is None:
            return None
        service.status = status
        await db.flush()
        return service

    # ------------------------------------------------------- dependency graph
    async def graph(self, db: AsyncSession) -> dict:
        """Return the full dependency graph with edges."""
        services = (await db.execute(select(SREService))).scalars().all()
        edges = (await db.execute(select(SREServiceDependency))).scalars().all()
        nodes = [s.to_dict() for s in services]
        return {
            "nodes": nodes,
            "edges": [{"service_id": e.service_id, "depends_on": e.depends_on, "kind": e.kind, "critical": e.critical} for e in edges],
        }

    async def impact(self, db: AsyncSession, service_id: str) -> dict:
        """If `service_id` fails, what breaks? (transitive consumers)"""
        edges = (await db.execute(select(SREServiceDependency))).scalars().all()
        reverse: dict[str, list[SREServiceDependency]] = {}
        for edge in edges:
            reverse.setdefault(edge.depends_on, []).append(edge)
        affected: list[str] = []
        queue = [service_id]
        seen: set[str] = set()
        while queue:
            current = queue.pop()
            for edge in reverse.get(current, []):
                if edge.service_id not in seen:
                    seen.add(edge.service_id)
                    affected.append(edge.service_id)
                    queue.append(edge.service_id)
        return {"service_id": service_id, "impacted_services": sorted(affected), "impacted_count": len(affected)}

    async def dependencies_of(self, db: AsyncSession, service_id: str) -> dict:
        """What does `service_id` depend on? (transitive)"""
        edges = (await db.execute(select(SREServiceDependency))).scalars().all()
        forward: dict[str, list[SREServiceDependency]] = {}
        for edge in edges:
            forward.setdefault(edge.service_id, []).append(edge)
        dependencies: list[str] = []
        queue = [service_id]
        seen: set[str] = set()
        while queue:
            current = queue.pop()
            for edge in forward.get(current, []):
                if edge.depends_on not in seen:
                    seen.add(edge.depends_on)
                    dependencies.append(edge.depends_on)
                    queue.append(edge.depends_on)
        return {"service_id": service_id, "dependencies": sorted(dependencies), "dependency_count": len(dependencies)}

    async def upsert_runbook_link(self, db: AsyncSession, service_id: str, runbook_id: str) -> None:
        service = await get_one(db, SREService, service_id=service_id)
        if service:
            service.runbook_id = runbook_id
            await db.flush()


service_catalog = ServiceCatalog()
