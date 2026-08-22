"""NovaForge Knowledge Graph Platform -- Neo4j graph store service (Volume 51).

Wraps the ``GraphStoreService`` interaction pattern and adds knowledge-graph
node/relationship management: entity upserts, relationship merges, traversal
queries, search, indexing, subgraph extraction and Postgres sync.

The ``neo4j`` package is imported lazily so the module remains importable
(and constructible in a disconnected state) without the driver installed.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from app.knowledge_graph.constants import (
    MAXResultLimit,
    MAXTraversalDepth,
    RelationshipType,
)

logger = logging.getLogger(__name__)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _sanitize_label(value: Any) -> str:
    cleaned = "".join(ch for ch in str(value or "") if ch.isalnum() or ch == "_")
    cleaned = cleaned.strip("_") or "Entity"
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned.upper()


def _sanitize_rel_type(value: Any) -> str:
    return _sanitize_label(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _property_value(value: Any) -> Any:
    """Coerce a Python value into a Neo4j-storable property value."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, (bool, int, float, str)) for item in value):
            return list(value)
        return json.dumps(value, default=str)
    return str(value)


def _convert_value(value: Any) -> Any:
    """Convert neo4j driver values (nodes, relationships, paths) to plain dicts."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    labels = getattr(value, "labels", None)
    if labels is not None and hasattr(value, "items"):
        converted = {key: _convert_value(val) for key, val in value.items()}
        converted["_labels"] = sorted(str(label) for label in labels)
        return converted
    if hasattr(value, "start_node") and hasattr(value, "end_node"):
        converted = {key: _convert_value(val) for key, val in value.items()}
        start = getattr(value, "start_node", None)
        end = getattr(value, "end_node", None)
        converted["relationship_type"] = str(getattr(value, "type", "") or "")
        converted["source"] = str(start.get("id")) if start is not None and start.get("id") is not None else ""
        converted["target"] = str(end.get("id")) if end is not None and end.get("id") is not None else ""
        return converted
    if hasattr(value, "nodes") and hasattr(value, "relationships"):
        return {
            "nodes": [_convert_value(node) for node in value.nodes],
            "relationships": [_convert_value(rel) for rel in value.relationships],
        }
    if isinstance(value, dict):
        return {key: _convert_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_convert_value(item) for item in value]
    return str(value)


def _score_text_match(entity: dict, query_lower: str) -> float:
    name = str(entity.get("name") or "").lower()
    display = str(entity.get("display_name") or "").lower()
    aliases = [str(alias).lower() for alias in (entity.get("aliases") or [])]
    external = str(entity.get("external_id") or "").lower()
    if query_lower == external or query_lower == str(entity.get("id") or "").lower():
        return 1.0
    if query_lower in aliases:
        return 0.95
    if query_lower == name or query_lower == display:
        return 0.9
    if name.startswith(query_lower) or display.startswith(query_lower):
        return 0.8
    if any(alias.startswith(query_lower) for alias in aliases):
        return 0.78
    if query_lower in name:
        return 0.7
    if query_lower in display:
        return 0.65
    if any(query_lower in alias for alias in aliases):
        return 0.6
    if query_lower in str(entity.get("description") or "").lower():
        return 0.5
    return 0.0


class Neo4jKnowledgeGraphService:
    """Neo4j-backed knowledge graph store.

    Follows the existing ``GraphStoreService`` conventions (async driver,
    ``execute_query`` core, dict-in/dict-out) while adding knowledge-graph
    semantics: typed entity nodes, typed relationships, traversal helpers,
    search, index management and batch synchronization from Postgres.
    """

    def __init__(self, uri: str = "", user: str = "", password: str = "") -> None:
        self._uri = uri or ""
        self._user = user or ""
        self._password = password or ""
        self._driver: Any = None
        if self._uri:
            self._initialize_driver()

    def _initialize_driver(self) -> None:
        try:
            from neo4j import AsyncGraphDatabase
        except Exception as exc:
            logger.warning("neo4j driver unavailable, running disconnected: %s", exc)
            self._driver = None
            return
        auth = None
        if self._user or self._password:
            auth = (self._user, self._password)
        try:
            self._driver = AsyncGraphDatabase.driver(self._uri, auth=auth)
        except Exception as exc:
            logger.warning("failed to initialize neo4j driver: %s", exc)
            self._driver = None

    def is_connected(self) -> bool:
        return self._driver is not None

    async def close(self) -> None:
        if self._driver is not None:
            try:
                await self._driver.close()
            finally:
                self._driver = None

    async def __aenter__(self) -> "Neo4jKnowledgeGraphService":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def execute_query(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict]:
        """Run a Cypher statement and return rows as plain dictionaries."""
        if self._driver is None:
            raise RuntimeError(
                "Neo4j driver is not initialized; construct the service with a URI to connect."
            )
        async with self._driver.session() as session:
            result = await session.run(query, params or {})
            rows = await result.data()
        return [{key: _convert_value(value) for key, value in row.items()} for row in rows]

    async def upsert_entity(self, entity: dict) -> dict:
        """MERGE an entity node by id under its entity_type label and set all properties."""
        data = dict(entity or {})
        entity_id = str(data.get("id") or uuid.uuid4())
        entity_type = str(data.get("entity_type") or "").strip()
        label = _sanitize_label(entity_type or "Entity")
        props: dict[str, Any] = {}
        for key, value in data.items():
            coerced = _property_value(value)
            if coerced is not None:
                props[key] = coerced
        props["id"] = entity_id
        props.setdefault("entity_type", entity_type.lower() or label.lower())
        props["updated_at"] = _utc_now()
        props.setdefault("created_at", props["updated_at"])
        query = (
            f"MERGE (n:Entity:`{label}` {{id: $id}}) "
            f"SET n += $props "
            f"RETURN n"
        )
        rows = await self.execute_query(query, {"id": entity_id, "props": props})
        if rows and isinstance(rows[0].get("n"), dict):
            return rows[0]["n"]
        return props

    async def upsert_relationship(
        self,
        source_id: Any,
        target_id: Any,
        rel_type: str,
        properties: Optional[dict] = None,
    ) -> dict:
        """MERGE a typed relationship between two entity nodes."""
        rel_name = _sanitize_rel_type(rel_type)
        props: dict[str, Any] = {}
        for key, value in (properties or {}).items():
            coerced = _property_value(value)
            if coerced is not None:
                props[key] = coerced
        props.setdefault("relationship_type", str(rel_type))
        props["updated_at"] = _utc_now()
        query = (
            f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
            f"MERGE (a)-[r:`{rel_name}`]->(b) "
            f"SET r += $props "
            f"RETURN r, a.id AS source_id, b.id AS target_id"
        )
        rows = await self.execute_query(
            query,
            {"source_id": str(source_id), "target_id": str(target_id), "props": props},
        )
        if rows and isinstance(rows[0].get("r"), dict):
            rel = rows[0]["r"]
            rel.setdefault("source", str(source_id))
            rel.setdefault("target", str(target_id))
            return rel
        return {"source": str(source_id), "target": str(target_id), **props}

    async def delete_entity(self, entity_id: Any) -> bool:
        """Delete a node and all of its relationships (DETACH DELETE)."""
        rows = await self.execute_query(
            "MATCH (n {id: $id}) DETACH DELETE n RETURN count(n) AS deleted",
            {"id": str(entity_id)},
        )
        return bool(rows and rows[0].get("deleted"))

    async def delete_relationship(self, source_id: Any, target_id: Any, rel_type: str) -> bool:
        rel_name = _sanitize_rel_type(rel_type)
        rows = await self.execute_query(
            (
                f"MATCH (a {{id: $source_id}})-[r:`{rel_name}`]->(b {{id: $target_id}}) "
                f"DELETE r RETURN count(r) AS deleted"
            ),
            {"source_id": str(source_id), "target_id": str(target_id)},
        )
        return bool(rows and rows[0].get("deleted"))

    async def get_entity(self, entity_id: Any) -> Optional[dict]:
        rows = await self.execute_query(
            "MATCH (n {id: $id}) RETURN n LIMIT 1",
            {"id": str(entity_id)},
        )
        if rows and isinstance(rows[0].get("n"), dict):
            return rows[0]["n"]
        return None

    def _traverse_arrow(self, direction: str, rel_types: Optional[Iterable[str]], depth: int) -> str:
        type_pattern = ""
        if rel_types:
            unique: list[str] = []
            for rel_type in rel_types:
                sanitized = _sanitize_rel_type(rel_type)
                if sanitized and sanitized not in unique:
                    unique.append(sanitized)
            if unique:
                type_pattern = ":" + "|".join(f"`{name}`" for name in unique)
        bound = _clamp_int(depth, 1, 1, MAXTraversalDepth)
        if direction == "incoming":
            return f"<-[r{type_pattern}*1..{bound}]-"
        if direction == "both":
            return f"-[r{type_pattern}*1..{bound}]-"
        return f"-[r{type_pattern}*1..{bound}]->"

    async def get_neighbors(
        self,
        entity_id: Any,
        depth: int = 1,
        direction: str = "outgoing",
        rel_types: Optional[Iterable[str]] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Traverse paths from an entity and return deduplicated neighbors."""
        arrow = self._traverse_arrow(direction, rel_types, depth)
        bound_limit = _clamp_int(limit, 100, 1, MAXResultLimit)
        query = (
            f"MATCH p = (n {{id: $id}}){arrow}(m) "
            f"WHERE m.id IS NOT NULL AND m.id <> $id "
            f"RETURN m AS neighbor, [t IN relationships(p) | type(t)] AS rel_types, length(p) AS hops "
            f"ORDER BY hops "
            f"LIMIT $limit"
        )
        rows = await self.execute_query(query, {"id": str(entity_id), "limit": bound_limit})
        results: dict[str, dict] = {}
        for row in rows:
            neighbor = row.get("neighbor")
            if not isinstance(neighbor, dict):
                continue
            neighbor_id = str(neighbor.get("id") or "")
            if not neighbor_id or neighbor_id == str(entity_id):
                continue
            hops = _clamp_int(row.get("hops"), 1, 1, MAXTraversalDepth)
            found_types = [str(t) for t in (row.get("rel_types") or [])]
            existing = results.get(neighbor_id)
            if existing is None:
                neighbor["hops"] = hops
                neighbor["relationship_types"] = found_types
                results[neighbor_id] = neighbor
            else:
                if hops < existing.get("hops", hops):
                    existing["hops"] = hops
                for rel_name in found_types:
                    if rel_name not in existing["relationship_types"]:
                        existing["relationship_types"].append(rel_name)
        return list(results.values())

    async def find_shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        rel_types: Optional[Iterable[str]] = None,
        max_depth: int = 10,
    ) -> Optional[list[dict]]:
        arrow = self._traverse_arrow("outgoing", rel_types, max_depth)
        query = (
            f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
            f"MATCH p = shortestPath((a){arrow}(b)) "
            f"RETURN nodes(p) AS nodes, relationships(p) AS relationships"
        )
        rows = await self.execute_query(
            query, {"source_id": str(source_id), "target_id": str(target_id)}
        )
        if not rows:
            return None
        nodes = rows[0].get("nodes")
        if not isinstance(nodes, list):
            return None
        return [node for node in nodes if isinstance(node, dict)]

    async def find_all_paths(
        self,
        source_id: Any,
        target_id: Any,
        rel_types: Optional[Iterable[str]] = None,
        max_depth: int = 5,
    ) -> list[list[dict]]:
        arrow = self._traverse_arrow("outgoing", rel_types, max_depth)
        query = (
            f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
            f"MATCH p = allShortestPaths((a){arrow}(b)) "
            f"RETURN nodes(p) AS nodes "
            f"ORDER BY length(p)"
        )
        rows = await self.execute_query(
            query, {"source_id": str(source_id), "target_id": str(target_id)}
        )
        paths: list[list[dict]] = []
        for row in rows:
            nodes = row.get("nodes")
            if isinstance(nodes, list):
                paths.append([node for node in nodes if isinstance(node, dict)])
        return paths

    async def search_entities(
        self,
        query: str,
        entity_type: str = "",
        tenant: str = "",
        limit: int = 50,
    ) -> list[dict]:
        needle = str(query or "").strip().lower()
        if not needle:
            return []
        bound_limit = _clamp_int(limit, 50, 1, MAXResultLimit)
        fetch_cap = min(bound_limit * 4, MAXResultLimit)
        cypher = (
            "MATCH (n) "
            "WHERE (toLower(coalesce(n.name, '')) CONTAINS $q "
            "OR toLower(coalesce(n.display_name, '')) CONTAINS $q "
            "OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS $q)) "
            "AND ($tenant = '' OR coalesce(n.tenant, '') = $tenant) "
            "AND ($etype = '' OR coalesce(n.entity_type, '') = $etype) "
            "RETURN n LIMIT $cap"
        )
        rows = await self.execute_query(
            cypher,
            {"q": needle, "tenant": tenant or "", "etype": entity_type or "", "cap": fetch_cap},
        )
        scored: list[tuple[float, dict]] = []
        for row in rows:
            node = row.get("n")
            if not isinstance(node, dict):
                continue
            score = _score_text_match(node, needle)
            if score > 0.0:
                node["search_score"] = round(score, 4)
                scored.append((score, node))
        scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
        return [node for _, node in scored[:bound_limit]]

    async def get_entity_count(self, tenant: str = "", entity_type: str = "") -> int:
        rows = await self.execute_query(
            (
                "MATCH (n) "
                "WHERE ($tenant = '' OR coalesce(n.tenant, '') = $tenant) "
                "AND ($etype = '' OR coalesce(n.entity_type, '') = $etype) "
                "RETURN count(n) AS total"
            ),
            {"tenant": tenant or "", "etype": entity_type or ""},
        )
        return int(rows[0].get("total") or 0) if rows else 0

    async def get_relationship_count(self, tenant: str = "", rel_type: str = "") -> int:
        type_pattern = ""
        if rel_type:
            type_pattern = f":`{_sanitize_rel_type(rel_type)}`"
        rows = await self.execute_query(
            (
                f"MATCH ()-[r{type_pattern}]->() "
                f"WHERE ($tenant = '' OR coalesce(r.tenant, '') = $tenant) "
                f"RETURN count(r) AS total"
            ),
            {"tenant": tenant or ""},
        )
        return int(rows[0].get("total") or 0) if rows else 0

    async def create_indexes(self) -> dict:
        """Create uniqueness and range indexes for entities and relationship types."""
        statements = [
            "CREATE INDEX kg_entity_id_unique IF NOT EXISTS FOR (n:Entity) ON (n.id)",
            "CREATE INDEX kg_entity_tenant_idx IF NOT EXISTS FOR (n:Entity) ON (n.tenant)",
            "CREATE INDEX kg_entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)",
            "CREATE INDEX kg_entity_name_idx IF NOT EXISTS FOR (n:Entity) ON (n.name)",
            "CREATE INDEX kg_entity_external_id_idx IF NOT EXISTS FOR (n:Entity) ON (n.external_id)",
        ]
        for rel_enum in RelationshipType:
            index_name = f"kg_rel_{_sanitize_rel_type(rel_enum.value).lower()}_idx"
            statements.append(
                f"CREATE INDEX {index_name} IF NOT EXISTS "
                f"FOR ()-[r:`{rel_enum.value}`]-() ON (r.tenant)"
            )
        created: list[str] = []
        failed: list[dict] = []
        for statement in statements:
            try:
                await self.execute_query(statement)
                created.append(statement)
            except Exception as exc:
                failed.append({"statement": statement, "error": str(exc)})
                logger.warning("index creation failed: %s -- %s", statement, exc)
        return {"created": created, "failed": failed, "total": len(created)}

    async def get_subgraph(self, entity_id: Any, depth: int = 2) -> dict:
        bound_depth = _clamp_int(depth, 2, 1, MAXTraversalDepth)
        nodes_by_id: dict[str, dict] = {}
        relationships_by_key: dict[tuple, dict] = {}
        center = await self.get_entity(entity_id)
        if isinstance(center, dict) and center.get("id") is not None:
            nodes_by_id[str(center["id"])] = center
        query = (
            f"MATCH p = (c {{id: $id}})-[*1..{bound_depth}]-(m) "
            f"RETURN nodes(p) AS ns, relationships(p) AS rs "
            f"LIMIT {MAXResultLimit}"
        )
        rows = await self.execute_query(query, {"id": str(entity_id)})
        for row in rows:
            for node in row.get("ns") or []:
                if isinstance(node, dict) and node.get("id") is not None:
                    nodes_by_id.setdefault(str(node["id"]), node)
            for rel in row.get("rs") or []:
                if not isinstance(rel, dict):
                    continue
                key = (
                    str(rel.get("source") or ""),
                    str(rel.get("target") or ""),
                    str(rel.get("relationship_type") or ""),
                )
                relationships_by_key.setdefault(key, rel)
        return {
            "root_id": str(entity_id),
            "depth": bound_depth,
            "nodes": list(nodes_by_id.values()),
            "relationships": list(relationships_by_key.values()),
            "node_count": len(nodes_by_id),
            "relationship_count": len(relationships_by_key),
        }

    async def sync_from_postgres(
        self,
        entities: Iterable[dict],
        relationships: Iterable[dict],
    ) -> dict:
        """Batch-upsert entities and relationships sourced from Postgres."""
        stats = {
            "entities_processed": 0,
            "entities_synced": 0,
            "relationships_processed": 0,
            "relationships_synced": 0,
            "errors": [],
            "status": "completed",
        }
        for entity in entities or []:
            stats["entities_processed"] += 1
            try:
                await self.upsert_entity(dict(entity or {}))
                stats["entities_synced"] += 1
            except Exception as exc:
                if len(stats["errors"]) < 50:
                    stats["errors"].append(
                        {"kind": "entity", "id": str((entity or {}).get("id")), "error": str(exc)}
                    )
        for relationship in relationships or []:
            stats["relationships_processed"] += 1
            data = dict(relationship or {})
            source_id = data.pop("source_entity_id", None) or data.pop("source_id", None)
            target_id = data.pop("target_entity_id", None) or data.pop("target_id", None)
            rel_type = data.pop("relationship_type", None) or data.pop("rel_type", None)
            try:
                if not source_id or not target_id or not rel_type:
                    raise ValueError("relationship requires source, target and type")
                await self.upsert_relationship(source_id, target_id, rel_type, data)
                stats["relationships_synced"] += 1
            except Exception as exc:
                if len(stats["errors"]) < 50:
                    stats["errors"].append({"kind": "relationship", "error": str(exc)})
        if stats["errors"]:
            stats["status"] = "partial" if (
                stats["entities_synced"] or stats["relationships_synced"]
            ) else "failed"
        return stats
