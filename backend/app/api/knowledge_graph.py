"""NovaForge Knowledge Graph Platform -- API (Volume 51)."""
from __future__ import annotations
import asyncio
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/knowledge-graph", tags=["Knowledge Graph"])


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
    is_active: Optional[bool] = None
    valid_to: Optional[str] = None


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
    data: dict = Field(default_factory=dict)


class PathStepReq(BaseModel):
    entity_id: str
    direction: str = "upstream"
    max_depth: int = 5


class CyclesReq(BaseModel):
    tenant: str = ""
    relationship_types: Optional[list[str]] = None


@router.post("/entities")
async def create_entity(body: EntityCreateReq):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.create_entity, body.tenant, body.entity_type, body.name, body.external_id, body.provider, body.display_name, body.description, body.metadata_extra or None, body.aliases or None)


@router.get("/entities")
async def list_entities(tenant: str = "default", entity_type: str = "", provider: str = "", status: str = "", name_contains: str = "", limit: int = 100, offset: int = 0):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.list_entities, tenant, entity_type, provider, status, name_contains, "", limit, offset)


@router.get("/entities/stats")
async def entity_stats(tenant: str = "default"):
    from app.knowledge_graph.entity_service import entity_service
    return await asyncio.to_thread(entity_service.get_entity_stats, tenant)


@router.get("/entities/search")
async def search_entities(tenant: str = "default", q: str = "", entity_type: str = "", provider: str = "", limit: int = 50):
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
    return await asyncio.to_thread(entity_service.merge_entities, body.entity_ids[0], body.entity_ids[1], False)


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


@router.post("/relationships")
async def create_relationship(body: RelCreateReq):
    from app.knowledge_graph.relationship_service import relationship_service
    return await asyncio.to_thread(relationship_service.create_relationship, body.tenant, body.source_entity_id, body.target_entity_id, body.relationship_type, body.confidence, body.evidence or None, body.metadata_extra or None, body.valid_from, body.observed_at)


@router.get("/relationships")
async def list_relationships(tenant: str = "default", source_entity_id: str = "", target_entity_id: str = "", relationship_type: str = "", confidence: str = "", is_active: bool = True, limit: int = 100, offset: int = 0):
    from app.knowledge_graph.relationship_service import relationship_service
    return await asyncio.to_thread(relationship_service.list_relationships, tenant, source_entity_id, target_entity_id, relationship_type, confidence, is_active, limit, offset)


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
async def all_paths(body: PathReq):
    from app.knowledge_graph.traversal_service import traversal_service
    return await asyncio.to_thread(traversal_service.all_paths, body.source_id, body.target_id, body.max_depth)


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
    return await asyncio.to_thread(temporal_service.create_snapshot, body.tenant, body.name, body.description, body.snapshot_type, body.reference_id, body.reference_type)


@router.get("/temporal/snapshots")
async def get_snapshot(tenant: str = "default", name: str = ""):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(temporal_service.get_snapshot_data, tenant, name)


@router.get("/temporal/consistency")
async def validate_consistency(tenant: str = ""):
    from app.knowledge_graph.temporal_service import temporal_service
    return await asyncio.to_thread(temporal_service.validate_temporal_consistency, tenant)


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
async def ingest_manual(body: BulkEntityReq):
    from app.knowledge_graph.indexing_service import indexing_service
    return await asyncio.to_thread(indexing_service.ingest_manual, body.tenant, body.entities)


@router.get("/ingest/status")
async def ingest_status(tenant: str = "default"):
    from app.knowledge_graph.health_service import health_service
    return await asyncio.to_thread(health_service.get_ingestion_stats, tenant)
