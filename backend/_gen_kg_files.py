"""Generate KG API, SDK, CLI files."""
import os

BASE = r"C:\Users\Devendraprasad\Downloads\GraphRAG-main\backend"

# ── API ────────────────────────────────────────────────────────────────
api_code = r'''"""NovaForge Knowledge Graph Platform -- API (Volume 51)."""
from __future__ import annotations
import asyncio
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/knowledge-graph", tags=["Knowledge Graph"])


class EntityCreateReq(BaseModel):
    tenant: str = "default"
    entity_type: str
    name: str
    external_id: str = ""
    provider: str = ""
    display_name: str = ""
    description: str = ""
    metadata_extra: dict = Field(default_factory=dict)
    aliases: list[dict] = Field(default_factory=list)


class EntityUpdateReq(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    metadata_extra: Optional[dict] = None
    aliases: Optional[list[dict]] = None


class BulkEntityReq(BaseModel):
    tenant: str = "default"
    entities: list[dict] = Field(default_factory=list)


class MergeReq(BaseModel):
    entity_ids: list[str]
    merge_into: str = ""


class AliasReq(BaseModel):
    alias_type: str
    alias_value: str
    source: str = ""


class AliasRemoveReq(BaseModel):
    alias_type: str
    alias_value: str


class RelCreateReq(BaseModel):
    tenant: str = "default"
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    confidence: str = "confirmed"
    evidence: list[dict] = Field(default_factory=list)
    metadata_extra: dict = Field(default_factory=dict)
    valid_from: str = ""
    observed_at: str = ""


class RelUpdateReq(BaseModel):
    confidence: Optional[str] = None
    metadata_extra: Optional[dict] = None
    is_active: Optional[bool] = None
    valid_to: Optional[str] = None
    observed_at: Optional[str] = None


class BulkRelReq(BaseModel):
    tenant: str = "default"
    relationships: list[dict] = Field(default_factory=list)


class EvidenceAddReq(BaseModel):
    evidence_source: str
    evidence_data: dict = Field(default_factory=dict)
    actor: str = ""


class EntitySearchReq(BaseModel):
    tenant: str = "default"
    query: str
    entity_type: str = ""
    provider: str = ""
    limit: int = 50


class PathReq(BaseModel):
    source_id: str
    target_id: str
    max_depth: int = 5


class NLQueryReq(BaseModel):
    tenant: str = "default"
    question: str


class TraverseReq(BaseModel):
    start_id: str
    direction: str = "outgoing"
    max_depth: int = 3
    relationship_types: Optional[list[str]] = None
    limit: int = 100


class ShortestPathReq(BaseModel):
    source_id: str
    target_id: str
    max_depth: int = 10
    relationship_types: Optional[list[str]] = None


class AllPathsReq(BaseModel):
    source_id: str
    target_id: str
    max_depth: int = 5
    relationship_types: Optional[list[str]] = None


class BlastRadiusReq(BaseModel):
    entity_id: str
    change_type: str = "modification"
    max_depth: int = 5
    entity_types: Optional[list[str]] = None


class ResolveReq(BaseModel):
    tenant: str = "default"
    entity_ids: list[str]
    merge_into: str = ""


class AutoResolveReq(BaseModel):
    tenant: str = "default"
    entity_type: str = ""
    threshold: float = 0.9


class DupDetectReq(BaseModel):
    tenant: str = "default"
    entity_type: str = ""
    threshold: float = 0.85


class SnapshotReq(BaseModel):
    tenant: str = "default"
    name: str
    description: str = ""
    snapshot_type: str = "manual"
    reference_id: str = ""
    reference_type: str = ""


class IngestReq(BaseModel):
    tenant: str = "default"
    source: str = "manual_assignment"
    data: dict = Field(default_factory=dict)


class PathStepReq(BaseModel):
    entity_id: str
    direction: str = "upstream"
    max_depth: int = 5


class CyclesReq(BaseModel):
    tenant: str = ""
    relationship_types: Optional[list[str]] = None


# ── Entity Endpoints ───────────────────────────────────────────────
@router.post("/entities")
async def create_entity(body: EntityCreateReq):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(
        entity_service.create_entity, body.tenant, body.entity_type, body.name,
        body.external_id, body.provider, body.display_name, body.description,
        body.metadata_extra or None, body.aliases or None)


@router.get("/entities")
async def list_entities(tenant: str = "default", entity_type: str = "", provider: str = "",
                        status: str = "", name_contains: str = "", external_id: str = "",
                        limit: int = 100, offset: int = 0):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(
        entity_service.list_entities, tenant, entity_type, provider, status,
        name_contains, external_id, limit, offset)


@router.get("/entities/stats")
async def entity_stats(tenant: str = "default"):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.get_entity_stats, tenant)


@router.get("/entities/search")
async def search_entities(tenant: str = "default", q: str = "", entity_type: str = "",
                          provider: str = "", limit: int = 50):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.search_entities, tenant, q, entity_type, provider, limit)


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str):
    from app.knowledge_graph.entity_service import entity_service
    result = await asyncio.to_thread(entity_service.get_entity, entity_id)
    return result or {"error": "entity not found"}


@router.put("/entities/{entity_id}")
async def update_entity(entity_id: str, body: EntityUpdateReq):
    from app.knowledge_graph.entity_service import entity_service
    kwargs = {k: v for k, v in body.dict().items() if v is not None}
    result = await asyncio.to_thread(entity_service.update_entity, entity_id, **kwargs)
    return result or {"error": "entity not found"}


@router.delete("/entities/{entity_id}")
async def delete_entity(entity_id: str):
    from app.knowledge_graph.entity_service import entity_service
    ok = await asyncio.to_thread(entity_service.delete_entity, entity_id)
    return {"deleted": ok}


@router.post("/entities/bulk")
async def bulk_create_entities(body: BulkEntityReq):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.bulk_create_entities, body.tenant, body.entities)


@router.post("/entities/merge")
async def merge_entities(body: MergeReq):
    from app.knowledge_graph.entity_service import entity_service
    if len(body.entity_ids) < 2:
        return {"error": "need at least 2 entity IDs"}
    return await asyncio.to_thread(
        entity_service.merge_entities, body.entity_ids[0], body.entity_ids[1], False)


@router.get("/entities/{entity_id}/aliases")
async def list_aliases(entity_id: str):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.list_aliases, entity_id)


@router.post("/entities/{entity_id}/aliases")
async def add_alias(entity_id: str, body: AliasReq):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.add_alias, entity_id, body.alias_type, body.alias_value, body.source)


@router.delete("/entities/{entity_id}/aliases")
async def remove_alias(entity_id: str, body: AliasRemoveReq):
    from app.knowledge_graph.entity_service import entity_service
    ok = await asyncio.to_thread(entity_service.remove_alias, entity_id, body.alias_type, body.alias_value)
    return {"removed": ok}


@router.get("/entities/{entity_id}/history")
async def entity_history(entity_id: str):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(temporal_service.get_entity_history, entity_id)


@router.get("/entities/{entity_id}/context")
async def entity_context(entity_id: str, depth: int = 2):
    from app.knowledge_graph.search_service import search_service
    return await asyncio.to_thread(search_service.get_entity_context, entity_id, depth)


@router.get("/entities/{entity_id}/dependencies")
async def dependency_tree(entity_id: str, depth: int = 3):
    from app.knowledge_graph.search_service import search_service
    return await asyncio.to_thread(search_service.get_dependency_tree, entity_id, depth)


@router.get("/entities/{entity_id}/impact")
async def impact_graph(entity_id: str, change_type: str = "modification", max_depth: int = 3):
    from app.knowledge_graph.search_service import search_service
    return await asyncio.to_thread(search_service.get_impact_graph, entity_id, change_type, max_depth)


# ── Relationship Endpoints ──────────────────────────────────────────
@router.post("/relationships")
async def create_relationship(body: RelCreateReq):
    from app.knowledge_graph.relationship_service import relationship_service
    return await asyncio.to_thread(
        relationship_service.create_relationship, body.tenant, body.source_entity_id,
        body.target_entity_id, body.relationship_type, body.confidence,
        body.evidence or None, body.metadata_extra or None, body.valid_from, body.observed_at)


@router.get("/relationships")
async def list_relationships(tenant: str = "default", source_entity_id: str = "",
                             target_entity_id: str = "", relationship_type: str = "",
                             confidence: str = "", is_active: bool = True,
                             limit: int = 100, offset: int = 0):
    from app.knowledge_graph.relationship_service import relationship_service
    return await asyncio.to_thread(
        relationship_service.list_relationships, tenant, source_entity_id,
        target_entity_id, relationship_type, confidence, is_active, limit, offset)


@router.get("/relationships/stats")
async def relationship_stats(tenant: str = "default"):
    from app.knowledge_graph.relationship_service import relationship_service
    return await asyncio.to_thread(relationship_service.get_relationship_stats, tenant)


@router.get("/relationships/{rel_id}")
async def get_relationship(rel_id: str):
    from app.knowledge_graph.relationship_service import relationship_service
    result = await asyncio.to_thread(relationship_service.get_relationship, rel_id)
    return result or {"error": "relationship not found"}


@router.put("/relationships/{rel_id}")
async def update_relationship(rel_id: str, body: RelUpdateReq):
    from app.knowledge_graph.relationship_service import relationship_service
    kwargs = {k: v for k, v in body.dict().items() if v is not None}
    result = await asyncio.to_thread(relationship_service.update_relationship, rel_id, **kwargs)
    return result or {"error": "relationship not found"}


@router.delete("/relationships/{rel_id}")
async def delete_relationship(rel_id: str):
    from app.knowledge_graph.relationship_service import relationship_service
    ok = await asyncio.to_thread(relationship_service.delete_relationship, rel_id)
    return {"deleted": ok}


@router.post("/relationships/bulk")
async def bulk_create_relationships(body: BulkRelReq):
    from app.knowledge_graph.relationship_service import relationship_service
    return await asyncio.to_thread(relationship_service.bulk_create_relationships, body.tenant, body.relationships)


@router.get("/relationships/{rel_id}/evidence")
async def get_evidence(rel_id: str):
    from app.knowledge_graph.evidence_service import evidence_service
    return await asyncio.to_thread(evidence_service.get_evidence, rel_id)


@router.post("/relationships/{rel_id}/evidence")
async def add_evidence(rel_id: str, body: EvidenceAddReq):
    from app.knowledge_graph.evidence_service import evidence_service
    return await asyncio.to_thread(evidence_service.add_evidence, rel_id, body.evidence_source, body.evidence_data, body.actor)


# ── Search Endpoints ───────────────────────────────────────────────
@router.post("/search/entities")
async def search_entities_post(body: EntitySearchReq):
    from app.knowledge_graph.search_service import search_service
    return await asyncio.to_thread(search_service.search_entities, body.tenant, body.query, body.entity_type, body.provider, body.limit)


@router.post("/search/paths")
async def search_paths(body: PathReq):
    from app.knowledge_graph.search_service import search_service
    return await asyncio.to_thread(search_service.search_paths, "", body.source_id, body.target_id, body.max_depth)


@router.post("/search/natural-language")
async def nl_query(body: NLQueryReq):
    from app.knowledge_graph.search_service import search_service
    return await asyncio.to_thread(search_service.natural_language_query, body.tenant, body.question)


# ── Traversal Endpoints ────────────────────────────────────────────
@router.post("/traverse/bfs")
async def bfs(body: TraverseReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.bfs, body.start_id, body.direction, body.max_depth, body.relationship_types, body.limit)


@router.post("/traverse/dfs")
async def dfs(body: TraverseReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.dfs, body.start_id, body.direction, body.max_depth, body.relationship_types, body.limit)


@router.post("/traverse/shortest-path")
async def shortest_path(body: ShortestPathReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.shortest_path, body.source_id, body.target_id, body.relationship_types, body.max_depth)


@router.post("/traverse/all-paths")
async def all_paths(body: AllPathsReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.all_paths, body.source_id, body.target_id, body.max_depth, body.relationship_types)


@router.post("/traverse/blast-radius")
async def blast_radius(body: BlastRadiusReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.blast_radius, body.entity_id, body.change_type, body.max_depth, body.entity_types)


@router.post("/traverse/dependency-path")
async def dependency_path(body: PathStepReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.dependency_path, body.entity_id, body.direction, body.max_depth)


@router.post("/traverse/ownership-path")
async def ownership_path(body: PathStepReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.ownership_path, body.entity_id, body.max_depth)


@router.post("/traverse/deployment-path")
async def deployment_path(body: PathStepReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.deployment_path, body.entity_id, body.max_depth)


@router.post("/traverse/incident-path")
async def incident_path(body: PathStepReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.incident_path, body.entity_id, body.max_depth)


@router.get("/traverse/connected-components")
async def connected_components():
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.get_connected_components)


@router.post("/traverse/cycles")
async def detect_cycles(body: CyclesReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.detect_cycles, body.tenant, body.relationship_types)


@router.get("/traverse/communities")
async def communities():
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.community_detection)


@router.get("/traverse/centrality")
async def centrality(tenant: str = "", entity_type: str = ""):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.get_degree_centrality, tenant, entity_type)


# ── Resolution Endpoints ───────────────────────────────────────────
@router.post("/resolution/detect")
async def detect_duplicates(body: DupDetectReq):
    from app.knowledge_graph.entity_resolution_service import entity_resolution_service
    return await asyncio.to_thread(entity_resolution_service.find_duplicates, body.tenant, body.entity_type, body.threshold)


@router.post("/resolution/resolve")
async def resolve_entities(body: ResolveReq):
    from app.knowledge_graph.entity_resolution_service import entity_resolution_service
    return await asyncio.to_thread(entity_resolution_service.resolve_entities, body.tenant, body.entity_ids, body.merge_into)


@router.post("/resolution/auto-resolve")
async def auto_resolve(body: AutoResolveReq):
    from app.knowledge_graph.entity_resolution_service import entity_resolution_service
    return await asyncio.to_thread(entity_resolution_service.auto_resolve, body.tenant, body.entity_type, body.threshold)


@router.get("/resolution/stats")
async def resolution_stats(tenant: str = "default"):
    from app.knowledge_graph.entity_resolution_service import entity_resolution_service
    return await asyncio.to_thread(entity_resolution_service.get_resolution_stats, tenant)


# ── Temporal Endpoints ─────────────────────────────────────────────
@router.get("/temporal/{entity_id}/ownership")
async def ownership_at_time(entity_id: str, timestamp: str = "", tenant: str = "default"):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(temporal_service.get_ownership_at_time, tenant, entity_id, timestamp)


@router.get("/temporal/{entity_id}/deployments")
async def deployments_at_time(entity_id: str, timestamp: str = "", tenant: str = "default"):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(temporal_service.get_deployments_at_time, tenant, entity_id, timestamp)


@router.post("/temporal/snapshots")
async def create_snapshot(body: SnapshotReq):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(
        temporal_service.create_snapshot, body.tenant, body.name, body.description,
        body.snapshot_type, body.reference_id, body.reference_type)


@router.get("/temporal/snapshots")
async def get_snapshot(tenant: str = "default", name: str = ""):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(temporal_service.get_snapshot_data, tenant, name)


@router.get("/temporal/consistency")
async def validate_consistency(tenant: str = ""):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(temporal_service.validate_temporal_consistency, tenant)


# ── Quality Endpoints ──────────────────────────────────────────────
@router.get("/quality/metrics")
async def quality_metrics(tenant: str = "default"):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.compute_quality_metrics, tenant)


@router.get("/quality/orphans")
async def orphans(tenant: str = "default"):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.detect_orphan_nodes, tenant)


@router.get("/quality/duplicates")
async def quality_duplicates(tenant: str = "default", threshold: float = 0.85):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.detect_duplicate_entities, tenant, "", threshold)


@router.get("/quality/stale")
async def stale(tenant: str = "default", stale_days: int = 90):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.detect_stale_relationships, tenant, stale_days)


@router.get("/quality/missing-evidence")
async def missing_evidence(tenant: str = "default"):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.detect_missing_evidence, tenant)


@router.get("/quality/invalid-edges")
async def invalid_edges(tenant: str = "default"):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.detect_invalid_edges, tenant)


@router.get("/quality/health-score")
async def health_score(tenant: str = "default"):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.get_health_score, tenant)


@router.get("/quality/report")
async def quality_report(tenant: str = "default"):
    from app.knowledge_graph.quality_service import quality_service
    return await asyncio.to_thread(quality_service.get_quality_report, tenant)


# ── Health Endpoints ───────────────────────────────────────────────
@router.get("/health")
async def graph_health(tenant: str = "default"):
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.get_health, tenant)


@router.get("/health/stats")
async def graph_stats(tenant: str = "default"):
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.get_stats, tenant)


@router.get("/health/performance")
async def query_performance():
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.get_query_performance)


@router.get("/health/consistency")
async def consistency_check(tenant: str = ""):
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.check_consistency, tenant)


@router.get("/health/summary")
async def graph_summary(tenant: str = "default"):
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.get_graph_summary, tenant)


@router.get("/health/neo4j")
async def neo4j_health():
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.check_neo4j_health)


@router.get("/health/alerts")
async def health_alerts(tenant: str = "default"):
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.get_alerts, tenant)


# ── Evidence Endpoints ─────────────────────────────────────────────
@router.get("/evidence/{rel_id}")
async def get_relationship_evidence(rel_id: str):
    from app.knowledge_graph.evidence_service import evidence_service
    return await asyncio.to_thread(evidence_service.validate_evidence, rel_id)


@router.post("/evidence/{entity_id}/provenance")
async def entity_provenance(entity_id: str):
    from app.knowledge_graph.evidence_service import evidence_service
    return await asyncio.to_thread(evidence_service.get_entity_provenance, entity_id)


@router.get("/evidence/summary")
async def evidence_summary(tenant: str = ""):
    from app.knowledge_graph.evidence_service import evidence_service
    return await asyncio.to_thread(evidence_service.get_evidence_summary, tenant)


@router.get("/evidence/integrity")
async def evidence_integrity(tenant: str = ""):
    from app.knowledge_graph.evidence_service import evidence_service
    return await asyncio.to_thread(evidence_service.verify_evidence_integrity, tenant)


# ── Ingestion Endpoints ────────────────────────────────────────────
@router.post("/ingest/repository")
async def ingest_repository(body: IngestReq):
    from app.knowledge_graph.indexing_service import indexing_service
    return await asyncio.to_thread(indexing_service.ingest_from_repository_index, body.tenant, body.data)


@router.post("/ingest/deployment")
async def ingest_deployment(body: IngestReq):
    from app.knowledge_graph.indexing_service import indexing_service
    return await asyncio.to_thread(indexing_service.ingest_from_deployment, body.tenant, body.data)


@router.post("/ingest/incident")
async def ingest_incident(body: IngestReq):
    from app.knowledge_graph.indexing_service import indexing_service
    return await asyncio.to_thread(indexing_service.ingest_from_incident, body.tenant, body.data)


@router.post("/ingest/security")
async def ingest_security(body: IngestReq):
    from app.knowledge_graph.indexing_service import indexing_service
    return await asyncio.to_thread(indexing_service.ingest_from_security_finding, body.tenant, body.data)


@router.post("/ingest/marketplace")
async def ingest_marketplace(body: IngestReq):
    from app.knowledge_graph.indexing_service import indexing_service
    return await asyncio.to_thread(indexing_service.ingest_from_marketplace, body.tenant, body.data)


@router.post("/ingest/manual")
async def ingest_manual(body: IngestReq):
    from app.knowledge_graph.indexing_service import indexing_service
    return await asyncio.to_thread(indexing_service.ingest_manual, body.tenant, body.data.get("entities", []), body.data.get("relationships", []))


@router.get("/ingest/status")
async def ingest_status(tenant: str = "default"):
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.get_ingestion_stats, tenant)
'''

with open(os.path.join(BASE, "app", "api", "knowledge_graph.py"), "w") as f:
    f.write(api_code)
print(f"API: {len(api_code)} bytes written")

# ── CLI ────────────────────────────────────────────────────────────────
cli_code = r'''"""Knowledge Graph Platform -- CLI (Volume 51)."""
from __future__ import annotations
import json
from typing import Any


def _print(title: str, data: Any):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, default=str))


def handle_knowledge_graph_command(args: list[str]):
    if not args:
        print("Usage: nova knowledge_graph <subcommand> [args...]")
        print("Subcommands: entity, relationship, search, traverse, resolve,")
        print("             temporal, quality, health, evidence, ingest, summary, help")
        return

    sub = args[0]
    rest = args[1:]

    if sub == "help":
        print("Knowledge Graph subcommands:")
        print("  entity     - CRUD for graph entities")
        print("  relationship - CRUD for relationships")
        print("  search     - search entities, paths, NL query")
        print("  traverse   - BFS, DFS, paths, blast radius")
        print("  resolve    - entity resolution / dedup")
        print("  temporal   - snapshots, history, consistency")
        print("  quality    - metrics, orphans, duplicates")
        print("  health     - graph health and stats")
        print("  evidence   - provenance tracking")
        print("  ingest     - sync status")
        print("  summary    - graph summary")
    elif sub == "entity":
        _handle_entity(rest)
    elif sub == "relationship":
        _handle_relationship(rest)
    elif sub == "search":
        _handle_search(rest)
    elif sub == "traverse":
        _handle_traverse(rest)
    elif sub == "resolve":
        _handle_resolve(rest)
    elif sub == "temporal":
        _handle_temporal(rest)
    elif sub == "quality":
        _handle_quality(rest)
    elif sub == "health":
        _handle_health(rest)
    elif sub == "evidence":
        _handle_evidence(rest)
    elif sub == "ingest":
        from app.knowledge_graph.health_service import health_service
        _print("Ingestion Stats", health_service.get_ingestion_stats(rest[0] if rest else "default"))
    elif sub == "summary":
        from app.knowledge_graph.health_service import health_service
        _print("Graph Summary", health_service.get_graph_summary(rest[0] if rest else "default"))
    else:
        print(f"Unknown subcommand: {sub}. Use 'nova knowledge_graph help'")


def _handle_entity(args: list[str]):
    if not args:
        print("Usage: entity <create|list|get|search|stats|delete|merge|aliases> [args...]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.entity_service import entity_service
    if sub == "create":
        if len(rest) < 2:
            print("Usage: entity create <name> <type> [tenant]")
            return
        tenant = rest[2] if len(rest) > 2 else "default"
        e = entity_service.create_entity(tenant, rest[1], rest[0])
        _print("Entity Created", e)
    elif sub == "list":
        tenant = rest[0] if rest else "default"
        _print("Entities", entity_service.list_entities(tenant, limit=20))
    elif sub == "get":
        if not rest:
            print("Usage: entity get <entity_id>")
            return
        e = entity_service.get_entity(rest[0])
        _print("Entity", e or {"error": "not found"})
    elif sub == "search":
        if not rest:
            print("Usage: entity search <query> [tenant]")
            return
        tenant = rest[1] if len(rest) > 1 else "default"
        _print("Search Results", entity_service.search_entities(tenant, rest[0]))
    elif sub == "stats":
        tenant = rest[0] if rest else "default"
        _print("Entity Stats", entity_service.get_entity_stats(tenant))
    elif sub == "delete":
        if not rest:
            print("Usage: entity delete <entity_id>")
            return
        ok = entity_service.delete_entity(rest[0])
        _print("Delete", {"deleted": ok})
    elif sub == "merge":
        if len(rest) < 2:
            print("Usage: entity merge <source_id> <target_id>")
            return
        _print("Merge", entity_service.merge_entities(rest[0], rest[1]))
    elif sub == "aliases":
        if not rest:
            print("Usage: entity aliases <entity_id>")
            return
        _print("Aliases", entity_service.list_aliases(rest[0]))


def _handle_relationship(args: list[str]):
    if not args:
        print("Usage: relationship <create|list|stats|neighborhood> [args...]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.relationship_service import relationship_service
    if sub == "create":
        if len(rest) < 3:
            print("Usage: relationship create <src_id> <tgt_id> <type> [tenant]")
            return
        tenant = rest[3] if len(rest) > 3 else "default"
        r = relationship_service.create_relationship(tenant, rest[0], rest[1], rest[2])
        _print("Relationship Created", r)
    elif sub == "list":
        tenant = rest[0] if rest else "default"
        _print("Relationships", relationship_service.list_relationships(tenant, limit=20))
    elif sub == "stats":
        tenant = rest[0] if rest else "default"
        _print("Relationship Stats", relationship_service.get_relationship_stats(tenant))
    elif sub == "neighborhood":
        if not rest:
            print("Usage: relationship neighborhood <entity_id> [depth]")
            return
        depth = int(rest[1]) if len(rest) > 1 else 2
        _print("Neighborhood", relationship_service.get_entity_neighborhood(rest[0], depth))


def _handle_search(args: list[str]):
    if not args:
        print("Usage: search <entities|paths|nl> [args...]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.search_service import search_service
    if sub == "entities":
        if not rest:
            print("Usage: search entities <query> [tenant]")
            return
        tenant = rest[1] if len(rest) > 1 else "default"
        _print("Search", search_service.search_entities(tenant, rest[0]))
    elif sub == "paths":
        if len(rest) < 2:
            print("Usage: search paths <source_id> <target_id>")
            return
        _print("Paths", search_service.search_paths("", rest[0], rest[1]))
    elif sub == "nl":
        if not rest:
            print("Usage: search nl <question> [tenant]")
            return
        tenant = rest[1] if len(rest) > 1 else "default"
        _print("NL Query", search_service.natural_language_query(tenant, rest[0]))


def _handle_traverse(args: list[str]):
    if not args:
        print("Usage: traverse <bfs|dfs|path|blast|components|cycles|communities|centrality> [args...]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.traversal_service import traversal_service
    if sub == "bfs":
        if not rest:
            print("Usage: traverse bfs <start_id> [depth]")
            return
        depth = int(rest[1]) if len(rest) > 1 else 3
        _print("BFS", traversal_service.bfs(rest[0], max_depth=depth))
    elif sub == "dfs":
        if not rest:
            print("Usage: traverse dfs <start_id> [depth]")
            return
        depth = int(rest[1]) if len(rest) > 1 else 3
        _print("DFS", traversal_service.dfs(rest[0], max_depth=depth))
    elif sub == "path":
        if len(rest) < 2:
            print("Usage: traverse path <source_id> <target_id>")
            return
        _print("Shortest Path", traversal_service.shortest_path(rest[0], rest[1]))
    elif sub == "blast":
        if not rest:
            print("Usage: traverse blast <entity_id> [depth]")
            return
        depth = int(rest[1]) if len(rest) > 1 else 5
        _print("Blast Radius", traversal_service.blast_radius(rest[0], max_depth=depth))
    elif sub == "components":
        _print("Connected Components", traversal_service.get_connected_components())
    elif sub == "cycles":
        tenant = rest[0] if rest else ""
        _print("Cycles", traversal_service.detect_cycles(tenant))
    elif sub == "communities":
        _print("Communities", traversal_service.community_detection())
    elif sub == "centrality":
        tenant = rest[0] if rest else ""
        _print("Centrality", traversal_service.get_degree_centrality(tenant))


def _handle_resolve(args: list[str]):
    if not args:
        print("Usage: resolve <detect|auto> [tenant] [threshold]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.entity_resolution_service import entity_resolution_service
    if sub == "detect":
        tenant = rest[0] if rest else "default"
        threshold = float(rest[1]) if len(rest) > 1 else 0.85
        _print("Duplicates", entity_resolution_service.find_duplicates(tenant, threshold=threshold))
    elif sub == "auto":
        tenant = rest[0] if rest else "default"
        threshold = float(rest[1]) if len(rest) > 1 else 0.9
        _print("Auto Resolve", entity_resolution_service.auto_resolve(tenant, threshold=threshold))
    elif sub == "stats":
        tenant = rest[0] if rest else "default"
        _print("Resolution Stats", entity_resolution_service.get_resolution_stats(tenant))


def _handle_temporal(args: list[str]):
    if not args:
        print("Usage: temporal <snapshot|consistency> [args...]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.temporal_service import temporal_service
    if sub == "snapshot":
        if not rest:
            print("Usage: temporal snapshot <name> [tenant]")
            return
        tenant = rest[1] if len(rest) > 1 else "default"
        _print("Snapshot", temporal_service.create_snapshot(tenant, rest[0]))
    elif sub == "consistency":
        tenant = rest[0] if rest else ""
        _print("Consistency", temporal_service.validate_temporal_consistency(tenant))


def _handle_quality(args: list[str]):
    if not args:
        print("Usage: quality <metrics|health|report|orphans|duplicates> [tenant]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.quality_service import quality_service
    tenant = rest[0] if rest else "default"
    if sub == "metrics":
        _print("Quality Metrics", quality_service.compute_quality_metrics(tenant))
    elif sub == "health":
        _print("Health Score", quality_service.get_health_score(tenant))
    elif sub == "report":
        _print("Quality Report", quality_service.get_quality_report(tenant))
    elif sub == "orphans":
        _print("Orphan Nodes", quality_service.detect_orphan_nodes(tenant))
    elif sub == "duplicates":
        _print("Duplicate Entities", quality_service.detect_duplicate_entities(tenant))


def _handle_health(args: list[str]):
    from app.knowledge_graph.health_service import health_service
    tenant = args[0] if args else "default"
    _print("Graph Health", health_service.get_health(tenant))


def _handle_evidence(args: list[str]):
    if not args:
        print("Usage: evidence <summary|integrity> [tenant]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.evidence_service import evidence_service
    tenant = rest[0] if rest else ""
    if sub == "summary":
        _print("Evidence Summary", evidence_service.get_evidence_summary(tenant))
    elif sub == "integrity":
        _print("Evidence Integrity", evidence_service.verify_evidence_integrity(tenant))
'''

with open(os.path.join(BASE, "app", "cli", "knowledge_graph_commands.py"), "w") as f:
    f.write(cli_code)
print(f"CLI: {len(cli_code)} bytes written")

# ── SDK ────────────────────────────────────────────────────────────────
sdk_code = r'''"""NovaForge Knowledge Graph Platform -- SDK (Volume 51)."""
from __future__ import annotations
from typing import Optional


class KnowledgeGraphMixin:
    """Sync SDK methods for the Knowledge Graph Platform."""

    def create_entity(self, tenant: str, entity_type: str, name: str, **kw) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/entities", json={
            "tenant": tenant, "entity_type": entity_type, "name": name, **kw})

    def list_entities(self, tenant: str = "", entity_type: str = "", provider: str = "",
                      status: str = "", name_contains: str = "", limit: int = 100, offset: int = 0) -> list:
        params: dict = {"limit": limit, "offset": offset}
        for k, v in [("tenant", tenant), ("entity_type", entity_type), ("provider", provider),
                     ("status", status), ("name_contains", name_contains)]:
            if v: params[k] = v
        return self._request("GET", "/api/v1/knowledge-graph/entities", params=params)

    def get_entity_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/entities/stats",
                             params={"tenant": tenant} if tenant else {})

    def search_entities(self, tenant: str, query: str, entity_type: str = "",
                        provider: str = "", limit: int = 50) -> list:
        params: dict = {"q": query, "limit": limit}
        for k, v in [("tenant", tenant), ("entity_type", entity_type), ("provider", provider)]:
            if v: params[k] = v
        return self._request("GET", "/api/v1/knowledge-graph/entities/search", params=params)

    def get_entity(self, entity_id: str) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}")

    def update_entity(self, entity_id: str, **kw) -> dict:
        return self._request("PUT", f"/api/v1/knowledge-graph/entities/{entity_id}", json=kw)

    def delete_entity(self, entity_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/knowledge-graph/entities/{entity_id}")

    def bulk_create_entities(self, tenant: str, entities: list[dict]) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/entities/bulk",
                             json={"tenant": tenant, "entities": entities})

    def merge_entities(self, entity_ids: list[str], merge_into: str = "") -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/entities/merge",
                             json={"entity_ids": entity_ids, "merge_into": merge_into})

    def list_entity_aliases(self, entity_id: str) -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/aliases")

    def add_alias(self, entity_id: str, alias_type: str, alias_value: str, source: str = "") -> dict:
        return self._request("POST", f"/api/v1/knowledge-graph/entities/{entity_id}/aliases",
                             json={"alias_type": alias_type, "alias_value": alias_value, "source": source})

    def remove_alias(self, entity_id: str, alias_type: str, alias_value: str) -> dict:
        return self._request("DELETE", f"/api/v1/knowledge-graph/entities/{entity_id}/aliases",
                             json={"alias_type": alias_type, "alias_value": alias_value})

    def get_entity_history(self, entity_id: str) -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/history")

    def get_entity_context(self, entity_id: str, depth: int = 2) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/context",
                             params={"depth": depth})

    def get_dependency_tree(self, entity_id: str, depth: int = 3) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/dependencies",
                             params={"depth": depth})

    def get_impact_graph(self, entity_id: str, change_type: str = "modification",
                         max_depth: int = 3) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/entities/{entity_id}/impact",
                             params={"change_type": change_type, "max_depth": max_depth})

    def create_relationship(self, tenant: str, source_entity_id: str, target_entity_id: str,
                            relationship_type: str, **kw) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/relationships", json={
            "tenant": tenant, "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id, "relationship_type": relationship_type, **kw})

    def list_relationships(self, tenant: str = "", source_entity_id: str = "",
                           target_entity_id: str = "", relationship_type: str = "",
                           limit: int = 100) -> list:
        params: dict = {"limit": limit}
        for k, v in [("tenant", tenant), ("source_entity_id", source_entity_id),
                     ("target_entity_id", target_entity_id),
                     ("relationship_type", relationship_type)]:
            if v: params[k] = v
        return self._request("GET", "/api/v1/knowledge-graph/relationships", params=params)

    def get_relationship_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/relationships/stats",
                             params={"tenant": tenant} if tenant else {})

    def get_relationship(self, rel_id: str) -> dict:
        return self._request("GET", f"/api/v1/knowledge-graph/relationships/{rel_id}")

    def update_relationship(self, rel_id: str, **kw) -> dict:
        return self._request("PUT", f"/api/v1/knowledge-graph/relationships/{rel_id}", json=kw)

    def delete_relationship(self, rel_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/knowledge-graph/relationships/{rel_id}")

    def bulk_create_relationships(self, tenant: str, relationships: list[dict]) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/relationships/bulk",
                             json={"tenant": tenant, "relationships": relationships})

    def get_relationship_evidence(self, rel_id: str) -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/relationships/{rel_id}/evidence")

    def add_evidence(self, rel_id: str, evidence_source: str, evidence_data: dict,
                     actor: str = "") -> dict:
        return self._request("POST", f"/api/v1/knowledge-graph/relationships/{rel_id}/evidence",
                             json={"evidence_source": evidence_source, "evidence_data": evidence_data, "actor": actor})

    def search_entities_advanced(self, tenant: str, query: str, entity_type: str = "",
                                 provider: str = "", limit: int = 50) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/search/entities",
                             json={"tenant": tenant, "query": query, "entity_type": entity_type,
                                   "provider": provider, "limit": limit})

    def search_paths(self, source_id: str, target_id: str, max_depth: int = 5) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/search/paths",
                             json={"source_id": source_id, "target_id": target_id, "max_depth": max_depth})

    def natural_language_query(self, tenant: str, question: str) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/search/natural-language",
                             json={"tenant": tenant, "question": question})

    def bfs(self, start_id: str, direction: str = "outgoing", max_depth: int = 3,
            relationship_types: list | None = None, limit: int = 100) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/bfs",
                             json={"start_id": start_id, "direction": direction,
                                   "max_depth": max_depth, "relationship_types": relationship_types, "limit": limit})

    def dfs(self, start_id: str, direction: str = "outgoing", max_depth: int = 3,
            relationship_types: list | None = None, limit: int = 100) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/dfs",
                             json={"start_id": start_id, "direction": direction,
                                   "max_depth": max_depth, "relationship_types": relationship_types, "limit": limit})

    def shortest_path(self, source_id: str, target_id: str, max_depth: int = 10,
                      relationship_types: list | None = None) -> list | None:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/shortest-path",
                             json={"source_id": source_id, "target_id": target_id,
                                   "max_depth": max_depth, "relationship_types": relationship_types})

    def all_paths(self, source_id: str, target_id: str, max_depth: int = 5,
                  relationship_types: list | None = None) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/all-paths",
                             json={"source_id": source_id, "target_id": target_id,
                                   "max_depth": max_depth, "relationship_types": relationship_types})

    def blast_radius(self, entity_id: str, change_type: str = "modification",
                     max_depth: int = 5, entity_types: list | None = None) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/blast-radius",
                             json={"entity_id": entity_id, "change_type": change_type,
                                   "max_depth": max_depth, "entity_types": entity_types})

    def dependency_path(self, entity_id: str, direction: str = "upstream",
                        max_depth: int = 5) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/dependency-path",
                             json={"entity_id": entity_id, "direction": direction, "max_depth": max_depth})

    def ownership_path(self, entity_id: str, max_depth: int = 3) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/ownership-path",
                             json={"entity_id": entity_id, "max_depth": max_depth})

    def deployment_path(self, entity_id: str, max_depth: int = 5) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/deployment-path",
                             json={"entity_id": entity_id, "max_depth": max_depth})

    def incident_path(self, entity_id: str, max_depth: int = 3) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/incident-path",
                             json={"entity_id": entity_id, "max_depth": max_depth})

    def get_connected_components(self) -> list:
        return self._request("GET", "/api/v1/knowledge-graph/traverse/connected-components")

    def detect_cycles(self, tenant: str = "", relationship_types: list | None = None) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/traverse/cycles",
                             json={"tenant": tenant, "relationship_types": relationship_types})

    def get_communities(self) -> list:
        return self._request("GET", "/api/v1/knowledge-graph/traverse/communities")

    def get_degree_centrality(self, tenant: str = "", entity_type: str = "") -> list:
        params: dict = {}
        if tenant: params["tenant"] = tenant
        if entity_type: params["entity_type"] = entity_type
        return self._request("GET", "/api/v1/knowledge-graph/traverse/centrality", params=params)

    def detect_duplicates(self, tenant: str = "", entity_type: str = "",
                          threshold: float = 0.85) -> list:
        return self._request("POST", "/api/v1/knowledge-graph/resolution/detect",
                             json={"tenant": tenant, "entity_type": entity_type, "threshold": threshold})

    def resolve_entities(self, tenant: str, entity_ids: list[str],
                         merge_into: str = "") -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/resolution/resolve",
                             json={"tenant": tenant, "entity_ids": entity_ids, "merge_into": merge_into})

    def auto_resolve(self, tenant: str, entity_type: str = "", threshold: float = 0.9) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/resolution/auto-resolve",
                             json={"tenant": tenant, "entity_type": entity_type, "threshold": threshold})

    def get_resolution_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/resolution/stats",
                             params={"tenant": tenant} if tenant else {})

    def get_ownership_at_time(self, entity_id: str, timestamp: str = "",
                              tenant: str = "default") -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/temporal/{entity_id}/ownership",
                             params={"timestamp": timestamp, "tenant": tenant})

    def get_deployments_at_time(self, entity_id: str, timestamp: str = "",
                                tenant: str = "default") -> list:
        return self._request("GET", f"/api/v1/knowledge-graph/temporal/{entity_id}/deployments",
                             params={"timestamp": timestamp, "tenant": tenant})

    def create_snapshot(self, tenant: str, name: str, description: str = "",
                        snapshot_type: str = "manual", **kw) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/temporal/snapshots",
                             json={"tenant": tenant, "name": name, "description": description,
                                   "snapshot_type": snapshot_type, **kw})

    def get_snapshot(self, tenant: str = "default", name: str = "") -> dict | None:
        return self._request("GET", "/api/v1/knowledge-graph/temporal/snapshots",
                             params={"tenant": tenant, "name": name})

    def validate_temporal_consistency(self, tenant: str = "") -> list:
        return self._request("GET", "/api/v1/knowledge-graph/temporal/consistency",
                             params={"tenant": tenant} if tenant else {})

    def get_quality_metrics(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/quality/metrics",
                             params={"tenant": tenant} if tenant else {})

    def get_health_score(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/quality/health-score",
                             params={"tenant": tenant} if tenant else {})

    def get_quality_report(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/quality/report",
                             params={"tenant": tenant} if tenant else {})

    def get_graph_health(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health",
                             params={"tenant": tenant} if tenant else {})

    def get_graph_stats(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/stats",
                             params={"tenant": tenant} if tenant else {})

    def get_query_performance(self) -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/performance")

    def get_graph_summary(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/summary",
                             params={"tenant": tenant} if tenant else {})

    def check_neo4j_health(self) -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/health/neo4j")

    def get_health_alerts(self, tenant: str = "") -> list:
        return self._request("GET", "/api/v1/knowledge-graph/health/alerts",
                             params={"tenant": tenant} if tenant else {})

    def ingest_from_repository(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/repository",
                             json={"tenant": tenant, "data": data})

    def ingest_from_deployment(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/deployment",
                             json={"tenant": tenant, "data": data})

    def ingest_from_incident(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/incident",
                             json={"tenant": tenant, "data": data})

    def ingest_from_security(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/security",
                             json={"tenant": tenant, "data": data})

    def ingest_from_marketplace(self, tenant: str, data: dict) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/marketplace",
                             json={"tenant": tenant, "data": data})

    def ingest_manual(self, tenant: str, entities: list[dict],
                      relationships: list[dict]) -> dict:
        return self._request("POST", "/api/v1/knowledge-graph/ingest/manual",
                             json={"tenant": tenant, "data": {
                                 "entities": entities, "relationships": relationships}})

    def get_ingestion_status(self, tenant: str = "") -> dict:
        return self._request("GET", "/api/v1/knowledge-graph/ingest/status",
                             params={"tenant": tenant} if tenant else {})


class AsyncKnowledgeGraphMixin:
    """Async SDK methods for the Knowledge Graph Platform."""

    async def create_entity(self, tenant: str, entity_type: str, name: str, **kw) -> dict:
        return await self._arequest("POST", "/api/v1/knowledge-graph/entities", json={
            "tenant": tenant, "entity_type": entity_type, "name": name, **kw})

    async def list_entities(self, tenant: str = "", entity_type: str = "", limit: int = 100) -> list:
        params: dict = {"limit": limit}
        if tenant: params["tenant"] = tenant
        if entity_type: params["entity_type"] = entity_type
        return await self._arequest("GET", "/api/v1/knowledge-graph/entities", params=params)

    async def get_entity(self, entity_id: str) -> dict:
        return await self._arequest("GET", f"/api/v1/knowledge-graph/entities/{entity_id}")

    async def search_entities(self, tenant: str, query: str, limit: int = 50) -> list:
        return await self._arequest("GET", "/api/v1/knowledge-graph/entities/search",
                                    params={"tenant": tenant, "q": query, "limit": limit})

    async def create_relationship(self, tenant: str, source: str, target: str,
                                  rel_type: str, **kw) -> dict:
        return await self._arequest("POST", "/api/v1/knowledge-graph/relationships", json={
            "tenant": tenant, "source_entity_id": source, "target_entity_id": target,
            "relationship_type": rel_type, **kw})

    async def list_relationships(self, tenant: str = "", limit: int = 100) -> list:
        params: dict = {"limit": limit}
        if tenant: params["tenant"] = tenant
        return await self._arequest("GET", "/api/v1/knowledge-graph/relationships", params=params)

    async def get_graph_health(self, tenant: str = "") -> dict:
        return await self._arequest("GET", "/api/v1/knowledge-graph/health",
                                    params={"tenant": tenant} if tenant else {})

    async def get_quality_metrics(self, tenant: str = "") -> dict:
        return await self._arequest("GET", "/api/v1/knowledge-graph/quality/metrics",
                                    params={"tenant": tenant} if tenant else {})
'''

with open(os.path.join(BASE, "sdk", "knowledge_graph.py"), "w") as f:
    f.write(sdk_code)
print(f"SDK: {len(sdk_code)} bytes written")
print("All 3 files written successfully")
