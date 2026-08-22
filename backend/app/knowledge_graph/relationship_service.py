"""Relationship CRUD service for the Knowledge Graph."""
from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RelationshipService:
    """In-memory relationship store keyed by UUID string."""

    def __init__(self) -> None:
        self._relationships: dict[str, dict] = {}

    # ── CRUD ────────────────────────────────────────────────────────
    def create_relationship(
        self,
        tenant: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        confidence: str = "confirmed",
        evidence: list[dict] | None = None,
        metadata_extra: dict | None = None,
        valid_from: str = "",
        observed_at: str = "",
    ) -> dict:
        rel_id = str(uuid.uuid4())
        now = _now()
        rel: dict = {
            "id": rel_id,
            "tenant": tenant,
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "relationship_type": relationship_type,
            "confidence": confidence,
            "evidence": evidence or [],
            "metadata_json": metadata_extra or {},
            "is_active": True,
            "valid_from": valid_from or now,
            "valid_to": "",
            "observed_at": observed_at or now,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        self._relationships[rel_id] = rel
        return rel

    def get_relationship(self, relationship_id: str) -> dict | None:
        return self._relationships.get(relationship_id)

    def update_relationship(self, relationship_id: str, **kwargs: object) -> dict | None:
        rel = self._relationships.get(relationship_id)
        if not rel:
            return None
        for key in ("confidence", "metadata_extra", "is_active", "valid_to", "observed_at"):
            if key in kwargs and kwargs[key] is not None:
                field = "metadata_json" if key == "metadata_extra" else key
                rel[field] = kwargs[key]
        rel["version"] = rel.get("version", 1) + 1
        rel["updated_at"] = _now()
        return rel

    def delete_relationship(self, relationship_id: str) -> bool:
        rel = self._relationships.get(relationship_id)
        if not rel:
            return False
        rel["is_active"] = False
        rel["updated_at"] = _now()
        return True

    # ── Query ───────────────────────────────────────────────────────
    def list_relationships(
        self,
        tenant: str = "",
        source_entity_id: str = "",
        target_entity_id: str = "",
        relationship_type: str = "",
        confidence: str = "",
        is_active: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        results: list[dict] = []
        for r in self._relationships.values():
            if tenant and r["tenant"] != tenant:
                continue
            if source_entity_id and r["source_entity_id"] != source_entity_id:
                continue
            if target_entity_id and r["target_entity_id"] != target_entity_id:
                continue
            if relationship_type and r["relationship_type"] != relationship_type:
                continue
            if confidence and r["confidence"] != confidence:
                continue
            if is_active is not None and r["is_active"] != is_active:
                continue
            results.append(r)
        return results[offset : offset + limit]

    def get_relationships_for_entity(
        self,
        entity_id: str,
        direction: str = "both",
        relationship_type: str = "",
        limit: int = 100,
    ) -> list[dict]:
        results: list[dict] = []
        for r in self._relationships.values():
            if not r["is_active"]:
                continue
            src = r["source_entity_id"]
            tgt = r["target_entity_id"]
            matches = False
            if direction in ("outgoing", "both") and src == entity_id:
                matches = True
            if direction in ("incoming", "both") and tgt == entity_id:
                matches = True
            if not matches:
                continue
            if relationship_type and r["relationship_type"] != relationship_type:
                continue
            results.append(r)
            if len(results) >= limit:
                break
        return results

    # ── Traversal ───────────────────────────────────────────────────
    def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        direction: str = "outgoing",
        relationship_type: str = "",
        limit: int = 100,
    ) -> list[dict]:
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])
        results: list[dict] = []
        while queue and len(results) < limit:
            current, d = queue.popleft()
            if current in visited or d > depth:
                continue
            visited.add(current)
            for r in self._relationships.values():
                if not r["is_active"]:
                    continue
                if relationship_type and r["relationship_type"] != relationship_type:
                    continue
                neighbor = None
                hop_dir = ""
                if direction in ("outgoing", "both") and r["source_entity_id"] == current:
                    neighbor = r["target_entity_id"]
                    hop_dir = "outgoing"
                elif direction in ("incoming", "both") and r["target_entity_id"] == current:
                    neighbor = r["source_entity_id"]
                    hop_dir = "incoming"
                if neighbor and neighbor not in visited:
                    results.append(
                        {
                            "entity_id": neighbor,
                            "relationship_type": r["relationship_type"],
                            "direction": hop_dir,
                            "hop": d + 1,
                            "relationship_id": r["id"],
                        }
                    )
                    if d + 1 < depth:
                        queue.append((neighbor, d + 1))
        return results

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        relationship_types: list[str] | None = None,
    ) -> list[dict] | None:
        if source_id == target_id:
            return [{"entity_id": source_id}]
        visited: dict[str, tuple[str | None, str]] = {}
        queue: deque[tuple[str, int]] = deque([(source_id, 0)])
        visited[source_id] = (None, "")
        while queue:
            current, d = queue.popleft()
            if d >= max_depth:
                continue
            for r in self._relationships.values():
                if not r["is_active"]:
                    continue
                if relationship_types and r["relationship_type"] not in relationship_types:
                    continue
                neighbor = None
                if r["source_entity_id"] == current:
                    neighbor = r["target_entity_id"]
                elif r["target_entity_id"] == current:
                    neighbor = r["source_entity_id"]
                if neighbor and neighbor not in visited:
                    visited[neighbor] = (current, r["relationship_type"])
                    queue.append((neighbor, d + 1))
                    if neighbor == target_id:
                        path: list[dict] = []
                        node = target_id
                        while node and node in visited:
                            parent, rel_type = visited[node]
                            path.append({"entity_id": node, "relationship_type": rel_type})
                            node = parent  # type: ignore[assignment]
                        path.reverse()
                        return path
        return None

    # ── Bulk / Stats ────────────────────────────────────────────────
    def bulk_create_relationships(
        self, tenant: str, relationships: list[dict], source: str = "bulk"
    ) -> dict:
        created = 0
        skipped = 0
        errors: list[str] = []
        for data in relationships:
            try:
                src = data.get("source_entity_id", "")
                tgt = data.get("target_entity_id", "")
                rt = data.get("relationship_type", "")
                if not src or not tgt or not rt:
                    skipped += 1
                    continue
                self.create_relationship(
                    tenant=tenant,
                    source_entity_id=src,
                    target_entity_id=tgt,
                    relationship_type=rt,
                    confidence=data.get("confidence", "confirmed"),
                    evidence=data.get("evidence"),
                    metadata_extra=data.get("metadata_extra"),
                )
                created += 1
            except Exception as exc:
                errors.append(str(exc))
        return {"created": created, "skipped": skipped, "errors": errors}

    def get_relationship_stats(self, tenant: str = "") -> dict:
        by_type: dict[str, int] = {}
        by_confidence: dict[str, int] = {}
        active = 0
        inactive = 0
        total = 0
        for r in self._relationships.values():
            if tenant and r["tenant"] != tenant:
                continue
            total += 1
            if r["is_active"]:
                active += 1
            else:
                inactive += 1
            by_type[r["relationship_type"]] = by_type.get(r["relationship_type"], 0) + 1
            by_confidence[r["confidence"]] = by_confidence.get(r["confidence"], 0) + 1
        return {
            "total": total,
            "active": active,
            "inactive": inactive,
            "by_type": by_type,
            "by_confidence": by_confidence,
        }

    # ── Evidence ────────────────────────────────────────────────────
    def add_evidence(
        self, relationship_id: str, evidence_source: str, evidence_data: dict, actor: str = ""
    ) -> dict:
        rel = self._relationships.get(relationship_id)
        if not rel:
            return {"error": "relationship not found"}
        entry = {
            "source": evidence_source,
            "data": evidence_data,
            "actor": actor,
            "timestamp": _now(),
        }
        rel.setdefault("evidence", []).append(entry)
        rel["updated_at"] = _now()
        return entry

    def get_entity_neighborhood(self, entity_id: str, depth: int = 2, limit: int = 50) -> dict:
        neighbors = self.get_neighbors(entity_id, depth=depth, direction="both", limit=limit)
        node_ids: set[str] = {entity_id}
        for n in neighbors:
            node_ids.add(n["entity_id"])
        edges: list[dict] = []
        for r in self._relationships.values():
            if not r["is_active"]:
                continue
            if r["source_entity_id"] in node_ids and r["target_entity_id"] in node_ids:
                edges.append(
                    {
                        "source": r["source_entity_id"],
                        "target": r["target_entity_id"],
                        "type": r["relationship_type"],
                        "id": r["id"],
                    }
                )
        return {"nodes": list(node_ids), "edges": edges}

    # ── Cycles ──────────────────────────────────────────────────────
    def detect_cycles(self, tenant: str = "", entity_type: str = "") -> list[list[str]]:
        rels = [
            r
            for r in self._relationships.values()
            if r["is_active"] and (not tenant or r["tenant"] == tenant)
        ]
        adj: dict[str, list[tuple[str, str]]] = {}
        for r in rels:
            adj.setdefault(r["source_entity_id"], []).append(
                (r["target_entity_id"], r["relationship_type"])
            )
        cycles: list[list[str]] = []
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {}
        parent: dict[str, str | None] = {}
        for node in list(adj.keys()):
            if node in color:
                continue
            stack: list[tuple[str, str | None]] = [(node, None)]
            while stack:
                v, par = stack[-1]
                if v not in color:
                    color[v] = GRAY
                    parent[v] = par
                    for nbr, _ in adj.get(v, []):
                        if nbr not in color:
                            stack.append((nbr, v))
                        elif color.get(nbr) == GRAY:
                            cycle: list[str] = [nbr, v]
                            p = v
                            while p != nbr:
                                p = parent.get(p)  # type: ignore[assignment]
                                if p is None:
                                    break
                                cycle.append(p)
                            cycle.reverse()
                            if len(cycle) > 2:
                                cycles.append(cycle)
                else:
                    stack.pop()
                    if color[v] == GRAY:
                        color[v] = BLACK
        return cycles


relationship_service = RelationshipService()
