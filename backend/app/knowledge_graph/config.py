"""Knowledge Graph configuration (Volume 51)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KnowledgeGraphConfig:
    """Configuration for the unified organizational knowledge graph."""

    neo4j_enabled: bool = True
    neo4j_uri: str = ""
    entity_resolution_enabled: bool = True
    entity_resolution_similarity_threshold: float = 0.85
    temporal_tracking_enabled: bool = True
    max_traversal_depth: int = 10
    default_traversal_depth: int = 3
    max_result_limit: int = 1000
    default_page_size: int = 50
    stale_threshold_days: int = 90
    snapshot_retention_days: int = 365
    ingestion_batch_size: int = 100
    quality_check_interval_hours: int = 24
    search_min_score: float = 0.3
    graph_cache_ttl_seconds: int = 300
    enable_evidence_tracking: bool = True
    enable_confidence_scoring: bool = True
    enable_temporal_graph: bool = True
    authorization_enforced: bool = True
    cycle_detection_enabled: bool = True
    orphan_detection_enabled: bool = True
    max_concurrent_ingestion: int = 10


_config: Optional[KnowledgeGraphConfig] = None


def get_config() -> KnowledgeGraphConfig:
    """Return the knowledge graph configuration.

    Reads overrides from ``app.core.config.settings`` when available,
    falling back to dataclass defaults otherwise.
    """
    global _config
    if _config is not None:
        return _config

    try:
        from app.core.config import settings as app_settings
    except Exception:
        _config = KnowledgeGraphConfig()
        return _config

    _config = KnowledgeGraphConfig(
        neo4j_uri=getattr(app_settings, "neo4j_uri", "") or "",
    )
    return _config
