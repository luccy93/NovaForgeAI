"""SRE default catalog seeding (Volume 35).

Seeds *configuration* only - the service catalog, SLO definitions,
dependency edges, runbooks, regions and status components. No operational
measurements are ever fabricated here. Seeding is idempotent and only
runs when the catalog is empty.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    DEFAULT_RPO_MINUTES,
    DEFAULT_RTO_MINUTES,
    DEFAULT_SLO_TARGETS,
    REGION_ACTIVE_ACTIVE,
    REGION_WARM_STANDBY,
    SEV2,
    SEV3,
    STATUS_OPERATIONAL,
    TIER_0,
    TIER_1,
    TIER_2,
    TIER_3,
)
from app.sre.models import SRERegion, SRESLO, SREService, SREServiceDependency, SREStatusComponent
from app.sre.playbooks import create_runbook, default_runbooks, validate_default_scenarios
from app.sre.slo import compute_error_budget

logger = logging.getLogger(__name__)

# (service_id, name, description, tier, owner, team)
DEFAULT_SERVICES = [
    ("auth", "Authentication", "Login, registration, tokens, MFA", TIER_0, "platform-core", "Platform"),
    ("api-gateway", "API Gateway", "Routing, rate limiting, API surface", TIER_0, "platform-core", "Platform"),
    ("control-plane", "Control Plane", "Global control plane coordination", TIER_0, "platform-core", "Platform"),
    ("agent-runtime", "Agent Runtime", "Core multi-agent execution runtime", TIER_0, "agents", "Agents"),
    ("workflow-runtime", "Workflow Runtime", "Workflow execution engine", TIER_0, "automation", "Automation"),
    ("event-infra", "Event Infrastructure", "Event bus persistence and delivery", TIER_0, "platform-core", "Platform"),
    ("billing", "Billing", "Subscriptions and payments", TIER_0, "growth", "Growth"),
    ("model-gateway", "Model Gateway", "AI provider gateway with failover", TIER_1, "ai-platform", "AI"),
    ("ai-chat", "AI Chat", "Conversational AI over code/repos", TIER_1, "ai-platform", "AI"),
    ("rag", "RAG", "Retrieval augmented generation pipeline", TIER_1, "ai-platform", "AI"),
    ("repo-intelligence", "Repository Intelligence", "Repo analysis and indexing", TIER_1, "code", "Code"),
    ("agent-services", "Agent Services", "Agent tooling and execution services", TIER_1, "agents", "Agents"),
    ("search", "Search", "Global and repository search", TIER_1, "code", "Code"),
    ("deployment", "Deployment", "Deployment and CI/CD integration", TIER_1, "release", "Release"),
    ("security", "Security", "Scanning, governance, threat detection", TIER_1, "security", "Security"),
    ("notifications", "Notifications", "Email, Slack, Teams notifications", TIER_2, "growth", "Growth"),
    ("analytics", "Analytics", "Platform analytics", TIER_2, "data", "Data"),
    ("reports", "Reports", "Operational and business reports", TIER_2, "data", "Data"),
    ("marketplace", "Marketplace", "Plugin and model marketplace", TIER_2, "growth", "Growth"),
    ("documentation", "Documentation", "Public documentation", TIER_2, "growth", "Growth"),
    ("postgresql", "PostgreSQL", "Primary transactional database", TIER_0, "data", "Data"),
    ("redis", "Redis", "Cache, sessions, queues", TIER_0, "platform-core", "Platform"),
    ("qdrant", "Qdrant", "Vector store", TIER_1, "ai-platform", "AI"),
    ("neo4j", "Neo4j", "Graph database", TIER_2, "data", "Data"),
    ("object-storage", "Object Storage", "Blob storage for artifacts and media", TIER_1, "data", "Data"),
]

# service_id -> [(depends_on, kind, critical)]
DEFAULT_DEPENDENCIES = {
    "api-gateway": [("auth", "service", True), ("redis", "database", True), ("postgresql", "database", True)],
    "ai-chat": [("api-gateway", "service", True), ("auth", "service", True), ("rag", "service", True), ("model-gateway", "service", True), ("redis", "database", False), ("postgresql", "database", True)],
    "rag": [("qdrant", "service", True), ("model-gateway", "service", True), ("postgresql", "database", True)],
    "repo-intelligence": [("qdrant", "service", True), ("postgresql", "database", True), ("event-infra", "service", True)],
    "agent-runtime": [("model-gateway", "service", True), ("event-infra", "service", True), ("redis", "database", False), ("postgresql", "database", True)],
    "workflow-runtime": [("event-infra", "service", True), ("redis", "database", True), ("postgresql", "database", True)],
    "deployment": [("api-gateway", "service", True), ("postgresql", "database", True), ("object-storage", "service", True)],
    "auth": [("postgresql", "database", True), ("redis", "database", True)],
    "billing": [("postgresql", "database", True), ("event-infra", "service", True)],
    "security": [("postgresql", "database", True), ("object-storage", "service", True)],
    "search": [("qdrant", "service", True), ("postgresql", "database", True)],
    "analytics": [("postgresql", "database", True), ("object-storage", "service", True)],
    "notifications": [("event-infra", "service", True), ("redis", "database", False)],
    "model-gateway": [("redis", "database", False)],
}

# (service_id, sli_type, target, name, severity)
DEFAULT_SLOS = [
    ("api-gateway", "availability", None, "API Availability", SEV2),
    ("api-gateway", "latency", None, "API p95 Latency < 500ms", SEV3),
    ("auth", "availability", None, "Authentication Availability", SEV2),
    ("ai-chat", "availability", None, "AI Chat Availability", SEV2),
    ("rag", "availability", None, "RAG Availability", SEV3),
    ("repo-intelligence", "availability", None, "Repository Indexing Availability", SEV3),
    ("workflow-runtime", "availability", None, "Workflow Availability", SEV3),
    ("event-infra", "availability", None, "Event Processing Availability", SEV3),
    ("model-gateway", "availability", None, "AI Response Availability", SEV2),
    ("deployment", "availability", None, "Deployment Availability", SEV3),
]

DEFAULT_REGIONS = [
    ("us-east-1", REGION_ACTIVE_ACTIVE),
    ("eu-west-1", REGION_ACTIVE_ACTIVE),
    ("ap-southeast-1", REGION_WARM_STANDBY),
]


async def is_seeded(db: AsyncSession) -> bool:
    count = (await db.execute(select(func.count()).select_from(SREService))).scalar() or 0
    return int(count) > 0


async def seed_defaults(db: AsyncSession, *, force: bool = False) -> dict:
    """Seed default catalog configuration. Idempotent when catalog exists."""
    if await is_seeded(db) and not force:
        return {"seeded": False, "reason": "catalog already populated"}

    service_tiers = {service_id: tier for service_id, _, _, tier, _, _ in DEFAULT_SERVICES}
    services = {}
    for service_id, name, description, tier, owner, team in DEFAULT_SERVICES:
        service = SREService(
            service_id=service_id,
            name=name,
            description=description,
            owner=owner,
            team=team,
            tier=tier,
            criticality="critical" if tier == TIER_0 else "high",
            deployment_strategy="canary" if tier in (TIER_0, TIER_1) else "rolling",
            scaling_strategy="queue-based + reactive",
            backup_strategy=(
                "daily full + PITR, cross-region" if tier in (TIER_0, TIER_1) else "daily full"
            ),
            rto_minutes=DEFAULT_RTO_MINUTES.get(tier, 60),
            rpo_minutes=DEFAULT_RPO_MINUTES.get(tier, 60),
            status=STATUS_OPERATIONAL,
        )
        db.add(service)
        services[service_id] = service

    for service_id, deps in DEFAULT_DEPENDENCIES.items():
        for depends_on, kind, critical in deps:
            if service_id in services and depends_on in services:
                db.add(
                    SREServiceDependency(
                        service_id=service_id,
                        depends_on=depends_on,
                        kind=kind,
                        critical=critical,
                    )
                )

    slos = []
    for service_id, sli_type, target, name, severity in DEFAULT_SLOS:
        tier_target = DEFAULT_SLO_TARGETS.get(service_tiers.get(service_id, TIER_1), 0.999)
        slo = SRESLO(
            slo_id=f"{service_id}-{sli_type}",
            service_id=service_id,
            name=name,
            description=f"{name} SLO",
            sli_type=sli_type,
            target=target if target is not None else tier_target,
            window="monthly",
            measurement=f"measure {sli_type} over monthly window",
            query=f"sli:{service_id}:{sli_type}",
            owner=services[service_id].owner,
            severity=severity,
            status="active",
            version=1,
        )
        db.add(slo)
        slos.append(slo)

    for region, mode in DEFAULT_REGIONS:
        db.add(SRERegion(region=region, mode=mode, status=STATUS_OPERATIONAL))

    runbook_ids = []
    for runbook in default_runbooks():
        await create_runbook(db, **{k: v for k, v in runbook.items() if k != "scenario"})
        runbook_ids.append(runbook["runbook_id"])

    for service_id, name, _, _, _, _ in DEFAULT_SERVICES:
        db.add(
            SREStatusComponent(
                component_id=f"status-{service_id}",
                service_id=service_id,
                name=name,
                status=STATUS_OPERATIONAL,
                public=service_id in ("api-gateway", "ai-chat", "auth"),
            )
        )

    await db.flush()
    missing_scenarios = validate_default_scenarios()
    logger.info(
        "seeded SRE catalog: %d services, %d SLOs, %d runbooks, %d regions",
        len(services),
        len(slos),
        len(runbook_ids),
        len(DEFAULT_REGIONS),
    )
    return {
        "seeded": True,
        "services": len(services),
        "slos": len(slos),
        "runbooks": len(runbook_ids),
        "regions": len(DEFAULT_REGIONS),
        "missing_runbook_scenarios": missing_scenarios,
    }