"""NovaForge Knowledge Graph Platform -- Quality Service (Volume 51).

Graph quality metrics, validation and remediation for the unified
organizational knowledge graph. Detects orphan nodes, duplicate entities,
stale relationships, missing evidence, invalid edges, dependency cycles
and conflicting ownership, computes a weighted health score and can
propose (or apply) fixes.

All operations are in-memory against the injected ``entity_service`` /
``relationship_service`` stores, with optional evidence lookup through
``evidence_service``.

Expected collaborator interfaces (duck-typed)::

    entity_service.get_entity(tenant, entity_id) -> dict | None
    entity_service.find_entities(tenant, entity_type="", external_id="",
                                 name="", status="", limit=0) -> list[dict]
    entity_service.update_entity(tenant, entity_id, updates) -> dict | None

    relationship_service.list_relationships(tenant, source_entity_id="",
        target_entity_id="", relationship_type="", limit=0) -> list[dict]
    relationship_service.update_relationship(tenant, relationship_id,
                                             updates) -> dict | None
    relationship_service.delete_relationship(tenant, relationship_id) -> bool
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.knowledge_graph.constants import (
    DEFAULT_TENANT,
    MAXResultLimit,
    STALE_THRESHOLD_DAYS,
    Confidence,
    EntityStatus,
    OwnershipType,
    QualityIssueType,
    RelationshipType,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None


def _normalize_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in value.lower())
    return " ".join(cleaned.split())


def _bigrams(value: str) -> set[str]:
    tokens = _normalize_name(value).replace(" ", "")
    if len(tokens) < 2:
        return {tokens} if tokens else set()
    return {tokens[i:i + 2] for i in range(len(tokens) - 1)}


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a.strip().lower() == b.strip().lower():
        return 1.0
    grams_a, grams_b = _bigrams(a), _bigrams(b)
    if not grams_a or not grams_b:
        return 0.0
    overlap = len(grams_a & grams_b)
    return (2.0 * overlap) / (len(grams_a) + len(grams_b))


class GraphQualityService:
    """Computes quality metrics and validates knowledge graph integrity."""

    WEIGHT_EVIDENCE = 0.30
    WEIGHT_ORPHANS = 0.20
    WEIGHT_DUPLICATES = 0.20
    WEIGHT_STALENESS = 0.15
    WEIGHT_INVALID_EDGES = 0.15

    def __init__(self, entity_service, relationship_service, evidence_service=None):
        self.entity_service = entity_service
        self.relationship_service = relationship_service
        self.evidence_service = evidence_service
        self._metrics: list[dict[str, Any]] = []

    # ── Metrics ───────────────────────────────────────────────────────

    def compute_quality_metrics(self, tenant: str = "") -> dict:
        tenant = tenant or DEFAULT_TENANT
        entities = self.entity_service.find_entities(tenant)
        relationships = self.relationship_service.list_relationships(tenant)

        entity_types: dict[str, int] = {}
        for ent in entities:
            etype = str(ent.get("entity_type", "unknown"))
            entity_types[etype] = entity_types.get(etype, 0) + 1

        rel_types: dict[str, int] = {}
        confidence_dist: dict[str, int] = {
            c.value: 0 for c in Confidence
        }
        for rel in relationships:
            rtype = str(rel.get("relationship_type", "UNKNOWN"))
            rel_types[rtype] = rel_types.get(rtype, 0) + 1
            conf = str(rel.get("confidence", Confidence.UNKNOWN.value)).upper()
            confidence_dist[conf] = confidence_dist.get(conf, 0) + 1

        orphans = self.detect_orphan_nodes(tenant)
        duplicates = self.detect_duplicate_entities(tenant)
        stale = self.detect_stale_relationships(tenant)
        invalid = self.detect_invalid_edges(tenant)
        missing_evidence = self.detect_missing_evidence(tenant)

        entity_count = len(entities)
        rel_count = len(relationships)
        covered = rel_count - len(missing_evidence)
        coverage_pct = round((covered / rel_count) * 100.0, 2) if rel_count else 100.0
        avg_rels = round(rel_count / entity_count, 3) if entity_count else 0.0

        return {
            "tenant": tenant,
            "computed_at": _now_iso(),
            "entity_count": entity_count,
            "relationship_count": rel_count,
            "entity_types_distribution": dict(
                sorted(entity_types.items(), key=lambda kv: kv[1], reverse=True)),
            "relationship_types_distribution": dict(
                sorted(rel_types.items(), key=lambda kv: kv[1], reverse=True)),
            "avg_relationships_per_entity": avg_rels,
            "orphans_count": len(orphans),
            "duplicates_count": len(duplicates),
            "stale_count": len(stale),
            "invalid_edges_count": len(invalid),
            "missing_evidence_count": len(missing_evidence),
            "evidence_coverage_pct": coverage_pct,
            "confidence_distribution": confidence_dist,
        }

    # ── Detectors ─────────────────────────────────────────────────────

    def detect_orphan_nodes(self, tenant: str = "") -> list[dict]:
        tenant = tenant or DEFAULT_TENANT
        entities = self.entity_service.find_entities(tenant)
        relationships = self.relationship_service.list_relationships(tenant)

        degree: dict[str, int] = {}
        for rel in relationships:
            src = str(rel.get("source_entity_id", ""))
            tgt = str(rel.get("target_entity_id", ""))
            degree[src] = degree.get(src, 0) + 1
            degree[tgt] = degree.get(tgt, 0) + 1

        orphans: list[dict] = []
        for ent in entities:
            entity_id = str(ent.get("id") or ent.get("entity_id") or "")
            status = str(ent.get("status", EntityStatus.ACTIVE.value)).lower()
            if status == EntityStatus.DELETED.value:
                continue
            if degree.get(entity_id, 0) == 0:
                orphans.append({
                    "issue_type": QualityIssueType.ORPHAN_NODE.value,
                    "entity_id": entity_id,
                    "entity_type": ent.get("entity_type", ""),
                    "name": ent.get("name", ""),
                    "tenant": tenant,
                })
        return orphans[:MAXResultLimit]

    def detect_duplicate_entities(self, tenant: str = "", threshold: float = 0.85) -> list[dict]:
        tenant = tenant or DEFAULT_TENANT
        entities = self.entity_service.find_entities(tenant)

        by_type: dict[str, list[dict]] = {}
        for ent in entities:
            etype = str(ent.get("entity_type", "unknown"))
            by_type.setdefault(etype, []).append(ent)

        duplicates: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()
        for etype, group in sorted(by_type.items()):
            ordered = sorted(group, key=lambda e: str(e.get("id") or ""))
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    if len(duplicates) >= MAXResultLimit:
                        return duplicates
                    a, b = ordered[i], ordered[j]
                    id_a = str(a.get("id") or "")
                    id_b = str(b.get("id") or "")
                    pair_key = tuple(sorted((id_a, id_b)))
                    if pair_key in seen_pairs:
                        continue
                    ext_a = str(a.get("external_id") or "")
                    ext_b = str(b.get("external_id") or "")
                    score = 0.0
                    reason = "name_similarity"
                    if ext_a and ext_b and ext_a == ext_b:
                        score = 1.0
                        reason = "identical_external_id"
                    else:
                        score = _name_similarity(
                            str(a.get("name", "")), str(b.get("name", "")))
                    if score >= threshold:
                        seen_pairs.add(pair_key)
                        duplicates.append({
                            "issue_type": QualityIssueType.DUPLICATE_ENTITY.value,
                            "entity_a_id": id_a,
                            "entity_b_id": id_b,
                            "entity_type": etype,
                            "names": [a.get("name", ""), b.get("name", "")],
                            "similarity": round(score, 4),
                            "reason": reason,
                            "tenant": tenant,
                        })
        return duplicates

    def detect_stale_relationships(self, tenant: str = "",
                                   stale_days: int = STALE_THRESHOLD_DAYS) -> list[dict]:
        tenant = tenant or DEFAULT_TENANT
        relationships = self.relationship_service.list_relationships(tenant)
        now = datetime.now(timezone.utc)
        stale: list[dict] = []
        for rel in relationships:
            if rel.get("is_active") is False:
                continue
            observed = _parse_ts(
                rel.get("observed_at") or rel.get("updated_at")
                or rel.get("created_at"))
            if observed is None:
                age_days = float("inf")
            else:
                age_days = (now - observed).total_seconds() / 86400.0
            if age_days > stale_days:
                stale.append({
                    "issue_type": QualityIssueType.STALE_RELATIONSHIP.value,
                    "relationship_id": str(rel.get("id")
                                           or rel.get("relationship_id") or ""),
                    "relationship_type": rel.get("relationship_type", ""),
                    "source_entity_id": rel.get("source_entity_id", ""),
                    "target_entity_id": rel.get("target_entity_id", ""),
                    "age_days": round(age_days, 1) if age_days != float("inf") else -1,
                    "last_observed_at": str(rel.get("observed_at")
                                            or rel.get("created_at") or ""),
                    "tenant": tenant,
                })
        stale.sort(key=lambda item: item["age_days"], reverse=True)
        return stale[:MAXResultLimit]

    def detect_missing_evidence(self, tenant: str = "") -> list[dict]:
        tenant = tenant or DEFAULT_TENANT
        relationships = self.relationship_service.list_relationships(tenant)
        missing: list[dict] = []
        for rel in relationships:
            evidence = rel.get("evidence") or []
            if not evidence:
                missing.append({
                    "issue_type": QualityIssueType.MISSING_EVIDENCE.value,
                    "relationship_id": str(rel.get("id")
                                           or rel.get("relationship_id") or ""),
                    "relationship_type": rel.get("relationship_type", ""),
                    "source_entity_id": rel.get("source_entity_id", ""),
                    "target_entity_id": rel.get("target_entity_id", ""),
                    "tenant": tenant,
                })
        return missing[:MAXResultLimit]

    def detect_invalid_edges(self, tenant: str = "") -> list[dict]:
        tenant = tenant or DEFAULT_TENANT
        entities = self.entity_service.find_entities(tenant)
        relationships = self.relationship_service.list_relationships(tenant)

        known_ids = {
            str(e.get("id") or e.get("entity_id") or "") for e in entities
        }
        invalid: list[dict] = []
        for rel in relationships:
            src = str(rel.get("source_entity_id", ""))
            tgt = str(rel.get("target_entity_id", ""))
            problems = []
            if src not in known_ids:
                problems.append("missing_source")
            if tgt not in known_ids:
                problems.append("missing_target")
            if src and src == tgt:
                problems.append("self_reference")
            if problems:
                invalid.append({
                    "issue_type": QualityIssueType.INVALID_EDGE.value,
                    "relationship_id": str(rel.get("id")
                                           or rel.get("relationship_id") or ""),
                    "relationship_type": rel.get("relationship_type", ""),
                    "source_entity_id": src,
                    "target_entity_id": tgt,
                    "problems": problems,
                    "tenant": tenant,
                })
        return invalid[:MAXResultLimit]

    def detect_cycles(self, tenant: str = "",
                      relationship_types: list[str] | None = None) -> list[list[str]]:
        tenant = tenant or DEFAULT_TENANT
        relationships = self.relationship_service.list_relationships(tenant)

        adjacency: dict[str, list[str]] = {}
        nodes: set[str] = set()
        type_filter = set(relationship_types or [])
        for rel in relationships:
            if rel.get("is_active") is False:
                continue
            rtype = str(rel.get("relationship_type", ""))
            if type_filter and rtype not in type_filter:
                continue
            src = str(rel.get("source_entity_id", ""))
            tgt = str(rel.get("target_entity_id", ""))
            if not src or not tgt:
                continue
            nodes.update((src, tgt))
            adjacency.setdefault(src, []).append(tgt)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node: WHITE for node in nodes}
        cycles: list[list[str]] = []
        seen_canonical: set[tuple[str, ...]] = set()

        for start in sorted(nodes):
            if color[start] != WHITE:
                continue
            color[start] = GRAY
            path = [start]
            stack = [(start, iter(adjacency.get(start, [])))]
            while stack:
                node, neighbors = stack[-1]
                advanced = False
                for nxt in neighbors:
                    if color[nxt] == WHITE:
                        color[nxt] = GRAY
                        path.append(nxt)
                        stack.append((nxt, iter(adjacency.get(nxt, []))))
                        advanced = True
                        break
                    if color[nxt] == GRAY:
                        idx = path.index(nxt)
                        cycle = path[idx:]
                        canonical = self._canonical_cycle(cycle)
                        if canonical not in seen_canonical:
                            seen_canonical.add(canonical)
                            cycles.append(cycle)
                if not advanced:
                    stack.pop()
                    color[node] = BLACK
                    path.pop()
            if len(cycles) >= MAXResultLimit:
                break
        return cycles

    def detect_conflicting_ownership(self, tenant: str = "") -> list[dict]:
        tenant = tenant or DEFAULT_TENANT
        relationships = self.relationship_service.list_relationships(
            tenant, relationship_type=RelationshipType.OWNS.value)

        ownership: dict[str, dict[str, set[str]]] = {}
        for rel in relationships:
            meta = rel.get("metadata_extra") or rel.get("metadata_json") or {}
            ownership_type = str(meta.get("ownership_type", "")).upper()
            if ownership_type and ownership_type != OwnershipType.TEAM_OWNER.value:
                continue
            target = str(rel.get("target_entity_id", ""))
            source = str(rel.get("source_entity_id", ""))
            if not target or not source:
                continue
            entry = ownership.setdefault(target, {"owners": set(), "types": set()})
            entry["owners"].add(source)
            entry["types"].add(ownership_type or OwnershipType.TEAM_OWNER.value)

        conflicts: list[dict] = []
        for target, entry in sorted(ownership.items()):
            if len(entry["owners"]) > 1:
                conflicts.append({
                    "issue_type": QualityIssueType.CONFLICTING_OWNERSHIP.value,
                    "entity_id": target,
                    "owner_entity_ids": sorted(entry["owners"]),
                    "owner_count": len(entry["owners"]),
                    "ownership_types": sorted(entry["types"]),
                    "tenant": tenant,
                })
        return conflicts[:MAXResultLimit]

    # ── Health score ──────────────────────────────────────────────────

    def get_health_score(self, tenant: str = "") -> dict:
        tenant = tenant or DEFAULT_TENANT
        metrics = self.compute_quality_metrics(tenant)

        entity_count = metrics["entity_count"]
        rel_count = metrics["relationship_count"]

        evidence_component = (metrics["evidence_coverage_pct"] / 100.0) \
            * self.WEIGHT_EVIDENCE * 100.0

        orphan_ratio = (metrics["orphans_count"] / entity_count) if entity_count else 0.0
        orphan_component = (1.0 - min(orphan_ratio, 1.0)) * self.WEIGHT_ORPHANS * 100.0

        dup_ratio = (metrics["duplicates_count"] / entity_count) if entity_count else 0.0
        dup_component = (1.0 - min(dup_ratio, 1.0)) * self.WEIGHT_DUPLICATES * 100.0

        stale_ratio = (metrics["stale_count"] / rel_count) if rel_count else 0.0
        stale_component = (1.0 - min(stale_ratio, 1.0)) * self.WEIGHT_STALENESS * 100.0

        invalid_ratio = (metrics["invalid_edges_count"] / rel_count) if rel_count else 0.0
        invalid_component = (1.0 - min(invalid_ratio, 1.0)) \
            * self.WEIGHT_INVALID_EDGES * 100.0

        score = round(
            evidence_component + orphan_component + dup_component
            + stale_component + invalid_component, 1)

        return {
            "tenant": tenant,
            "score": score,
            "grade": self._grade(score),
            "components": {
                "evidence_coverage": round(evidence_component, 2),
                "orphans": round(orphan_component, 2),
                "duplicates": round(dup_component, 2),
                "staleness": round(stale_component, 2),
                "invalid_edges": round(invalid_component, 2),
            },
            "weights": {
                "evidence_coverage_pct": self.WEIGHT_EVIDENCE * 100,
                "orphans_pct": self.WEIGHT_ORPHANS * 100,
                "duplicates_pct": self.WEIGHT_DUPLICATES * 100,
                "staleness_pct": self.WEIGHT_STALENESS * 100,
                "invalid_edges_pct": self.WEIGHT_INVALID_EDGES * 100,
            },
            "empty_graph": entity_count == 0,
            "computed_at": _now_iso(),
        }

    def get_quality_report(self, tenant: str = "") -> dict:
        tenant = tenant or DEFAULT_TENANT
        metrics = self.compute_quality_metrics(tenant)
        health = self.get_health_score(tenant)

        detectors: dict[str, list[Any]] = {
            "orphan_nodes": self.detect_orphan_nodes(tenant),
            "duplicate_entities": self.detect_duplicate_entities(tenant),
            "stale_relationships": self.detect_stale_relationships(tenant),
            "missing_evidence": self.detect_missing_evidence(tenant),
            "invalid_edges": self.detect_invalid_edges(tenant),
            "cycles": [
                {"issue_type": QualityIssueType.CYCLE_DETECTED.value,
                 "path": cycle}
                for cycle in self.detect_cycles(tenant)
            ],
            "conflicting_ownership": self.detect_conflicting_ownership(tenant),
        }

        issues: list[dict] = []
        issue_counts: dict[str, int] = {}
        for detector_name, findings in detectors.items():
            issue_counts[detector_name] = len(findings)
            issues.extend(findings)

        return {
            "tenant": tenant,
            "generated_at": _now_iso(),
            "metrics": metrics,
            "health_score": health,
            "total_issues": len(issues),
            "issue_counts": issue_counts,
            "issues": issues[:MAXResultLimit],
        }

    # ── Metric recording ──────────────────────────────────────────────

    def record_metric(self, tenant: str, metric_name: str, metric_value: float,
                      entity_type: str = "", dimensions: dict | None = None) -> dict:
        record = {
            "id": f"metric-{uuid.uuid4().hex[:12]}",
            "tenant": tenant or DEFAULT_TENANT,
            "metric_name": metric_name,
            "metric_value": float(metric_value),
            "entity_type": entity_type,
            "dimensions": dict(dimensions or {}),
            "measured_at": _now_iso(),
        }
        self._metrics.append(record)
        return record

    def get_metric_history(self, tenant: str, metric_name: str,
                           limit: int = 100) -> list[dict]:
        tenant = tenant or DEFAULT_TENANT
        history = [
            m for m in self._metrics
            if m["tenant"] == tenant and m["metric_name"] == metric_name
        ]
        history.sort(key=lambda m: m["measured_at"], reverse=True)
        return history[:max(int(limit), 0)]

    # ── Auto fix ──────────────────────────────────────────────────────

    def auto_fix(self, tenant: str = "", dry_run: bool = True) -> dict:
        tenant = tenant or DEFAULT_TENANT
        actions: list[dict] = []

        for edge in self.detect_invalid_edges(tenant):
            actions.append({
                "issue_type": QualityIssueType.INVALID_EDGE.value,
                "action": "delete_relationship",
                "target_id": edge["relationship_id"],
                "auto_applicable": True,
                "details": edge.get("problems", []),
            })

        for dup in self.detect_duplicate_entities(tenant):
            keep, merge = self._pick_merge_candidate(tenant, dup)
            actions.append({
                "issue_type": QualityIssueType.DUPLICATE_ENTITY.value,
                "action": "merge_entities",
                "keep_entity_id": keep,
                "merge_entity_id": merge,
                "auto_applicable": False,
                "similarity": dup.get("similarity"),
            })

        for orphan in self.detect_orphan_nodes(tenant):
            actions.append({
                "issue_type": QualityIssueType.ORPHAN_NODE.value,
                "action": "archive_entity",
                "target_id": orphan["entity_id"],
                "auto_applicable": True,
                "details": {"name": orphan.get("name", "")},
            })

        for stale in self.detect_stale_relationships(tenant):
            actions.append({
                "issue_type": QualityIssueType.STALE_RELATIONSHIP.value,
                "action": "refresh_observation",
                "target_id": stale["relationship_id"],
                "auto_applicable": True,
                "details": {"age_days": stale.get("age_days")},
            })

        for missing in self.detect_missing_evidence(tenant):
            actions.append({
                "issue_type": QualityIssueType.MISSING_EVIDENCE.value,
                "action": "flag_for_review",
                "target_id": missing["relationship_id"],
                "auto_applicable": False,
            })

        applied, failed, deferred = 0, 0, 0
        if not dry_run:
            for action in actions:
                try:
                    if not action["auto_applicable"]:
                        deferred += 1
                        continue
                    applied += self._apply_action(tenant, action)
                except Exception:
                    failed += 1

        return {
            "tenant": tenant,
            "dry_run": dry_run,
            "total_issues": len(actions),
            "actions": actions,
            "applied": applied,
            "failed": failed,
            "deferred": deferred,
            "executed_at": _now_iso(),
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _apply_action(self, tenant: str, action: dict) -> int:
        action_kind = action["action"]
        target_id = action.get("target_id", "")
        if action_kind == "delete_relationship":
            self.relationship_service.delete_relationship(tenant, target_id)
            return 1
        if action_kind == "archive_entity":
            self.entity_service.update_entity(tenant, target_id, {
                "status": EntityStatus.INACTIVE.value.lower(),
            })
            return 1
        if action_kind == "refresh_observation":
            self.relationship_service.update_relationship(tenant, target_id, {
                "observed_at": _now_iso(),
            })
            return 1
        return 0

    def _pick_merge_candidate(self, tenant: str, duplicate: dict) -> tuple[str, str]:
        id_a = duplicate.get("entity_a_id", "")
        id_b = duplicate.get("entity_b_id", "")
        ent_a = self.entity_service.get_entity(tenant, id_a)
        ent_b = self.entity_service.get_entity(tenant, id_b)
        created_a = _parse_ts(ent_a.get("created_at")) if ent_a else None
        created_b = _parse_ts(ent_b.get("created_at")) if ent_b else None
        if created_a is not None and (created_b is None or created_a <= created_b):
            return id_a, id_b
        return id_b, id_a

    @staticmethod
    def _canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
        rotations = [tuple(cycle[i:] + cycle[:i]) for i in range(len(cycle))]
        return min(rotations)

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 90:
            return "excellent"
        if score >= 75:
            return "good"
        if score >= 60:
            return "fair"
        return "poor"


__all__ = ["GraphQualityService"]
