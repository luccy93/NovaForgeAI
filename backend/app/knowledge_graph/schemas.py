"""Knowledge Graph schemas (Volume 51)."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Optional


# ── Entity ─────────────────────────────────────────────────────────────

class EntityCreate(BaseModel):
    tenant: str = "default"
    entity_type: str
    external_id: str = ""
    provider: str = ""
    name: str
    display_name: str = ""
    description: str = ""
    metadata_extra: dict = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    metadata_extra: Optional[dict] = None
    status: Optional[str] = None
    aliases: Optional[list[str]] = None


class EntityQuery(BaseModel):
    tenant: str = "default"
    entity_type: str = ""
    provider: str = ""
    status: str = ""
    name_contains: str = ""
    external_id: str = ""
    limit: int = 100
    offset: int = 0


# ── Relationship ───────────────────────────────────────────────────────

class RelationshipCreate(BaseModel):
    tenant: str = "default"
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    confidence: str = "confirmed"
    evidence: list[dict] = Field(default_factory=list)
    metadata_extra: dict = Field(default_factory=dict)
    valid_from: str = ""
    observed_at: str = ""


class RelationshipUpdate(BaseModel):
    confidence: Optional[str] = None
    metadata_extra: Optional[dict] = None
    is_active: Optional[bool] = None
    valid_to: Optional[str] = None


class RelationshipQuery(BaseModel):
    tenant: str = "default"
    source_entity_id: str = ""
    target_entity_id: str = ""
    relationship_type: str = ""
    confidence: str = ""
    is_active: bool = True
    limit: int = 100
    offset: int = 0


# ── Search ─────────────────────────────────────────────────────────────

class EntitySearch(BaseModel):
    tenant: str = "default"
    query: str
    entity_type: str = ""
    provider: str = ""
    limit: int = 50


class PathQuery(BaseModel):
    tenant: str = "default"
    source_entity_id: str
    target_entity_id: str = ""
    relationship_types: list[str] = Field(default_factory=list)
    traversal_type: str = "shortest_path"
    max_depth: int = 5
    direction: str = "both"


class DependencyQuery(BaseModel):
    tenant: str = "default"
    entity_id: str
    depth: int = 3
    direction: str = "both"
    include_transitive: bool = True


class ImpactQuery(BaseModel):
    tenant: str = "default"
    entity_id: str
    change_type: str = "modification"
    max_depth: int = 5
    entity_types: list[str] = Field(default_factory=list)


# ── Architecture ───────────────────────────────────────────────────────

class ArchitectureQuery(BaseModel):
    tenant: str = "default"
    project: str = ""
    repository: str = ""
    service: str = ""
    depth: int = 3


# ── Ownership ──────────────────────────────────────────────────────────

class OwnershipQuery(BaseModel):
    tenant: str = "default"
    entity_id: str = ""
    entity_type: str = ""
    ownership_type: str = ""
    limit: int = 100


class OwnershipAssign(BaseModel):
    tenant: str = "default"
    entity_id: str
    owner_type: str  # user, team
    owner_id: str
    ownership_type: str  # CODEOWNER, MAINTAINER, etc.
    source: str = "administrator_assignment"


# ── History ────────────────────────────────────────────────────────────

class HistoryQuery(BaseModel):
    tenant: str = "default"
    entity_id: str
    entity_type: str = ""
    start_time: str = ""
    end_time: str = ""
    limit: int = 100


# ── Snapshot ───────────────────────────────────────────────────────────

class SnapshotCreate(BaseModel):
    tenant: str = "default"
    name: str
    description: str = ""
    snapshot_type: str = "manual"
    reference_id: str = ""
    reference_type: str = ""


# ── Ingestion ──────────────────────────────────────────────────────────

class IngestEntitiesRequest(BaseModel):
    tenant: str = "default"
    source: str = "manual_assignment"
    entities: list[dict] = Field(default_factory=list)


class IngestRelationshipsRequest(BaseModel):
    tenant: str = "default"
    source: str = "manual_assignment"
    relationships: list[dict] = Field(default_factory=list)


# ── Quality ────────────────────────────────────────────────────────────

class QualityQuery(BaseModel):
    tenant: str = "default"
    metric_name: str = ""
    entity_type: str = ""
    limit: int = 100


class QualityIssueQuery(BaseModel):
    tenant: str = "default"
    issue_type: str = ""
    entity_type: str = ""
    limit: int = 100


# ── Dashboard / Health ────────────────────────────────────────────────

class GraphDashboardQuery(BaseModel):
    tenant: str = "default"
    include_quality: bool = True
    include_health: bool = True
    include_stats: bool = True


# ── Entity Resolution ─────────────────────────────────────────────────

class ResolveEntitiesRequest(BaseModel):
    tenant: str = "default"
    entity_ids: list[str] = Field(default_factory=list)
    merge_into: str = ""  # if empty, auto-merge


# ── Blast Radius ──────────────────────────────────────────────────────

class BlastRadiusQuery(BaseModel):
    tenant: str = "default"
    entity_id: str
    entity_type: str = ""
    max_depth: int = 5
    include_indirect: bool = True
