"""Knowledge Graph Platform -- CLI (Volume 51)."""
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
        _print("Help", {"subcommands": ["entity", "relationship", "search", "traverse", "resolve", "temporal", "quality", "health", "evidence", "ingest", "summary"]})
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
        from app.knowledge_graph.health_service import health_service
        _print("Graph Health", health_service.get_health(rest[0] if rest else "default"))
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
        print("Usage: entity <create|list|get|search|stats|delete|merge> [args...]")
        return
    sub = args[0]
    rest = args[1:]
    from app.knowledge_graph.entity_service import entity_service
    if sub == "create":
        if len(rest) < 2:
            print("Usage: entity create <name> <type> [tenant]")
            return
        e = entity_service.create_entity(rest[2] if len(rest) > 2 else "default", rest[1], rest[0])
        _print("Entity Created", e)
    elif sub == "list":
        _print("Entities", entity_service.list_entities(rest[0] if rest else "default", limit=20))
    elif sub == "get":
        if not rest:
            print("Usage: entity get <entity_id>")
            return
        _print("Entity", entity_service.get_entity(rest[0]) or {"error": "not found"})
    elif sub == "search":
        if not rest:
            print("Usage: entity search <query> [tenant]")
            return
        _print("Search", entity_service.search_entities(rest[1] if len(rest) > 1 else "default", rest[0]))
    elif sub == "stats":
        _print("Stats", entity_service.get_entity_stats(rest[0] if rest else "default"))
    elif sub == "delete":
        if not rest:
            print("Usage: entity delete <entity_id>")
            return
        _print("Delete", {"deleted": entity_service.delete_entity(rest[0])})
    elif sub == "merge":
        if len(rest) < 2:
            print("Usage: entity merge <source_id> <target_id>")
            return
        _print("Merge", entity_service.merge_entities(rest[0], rest[1]))


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
        _print("Relationship", relationship_service.create_relationship(rest[3] if len(rest) > 3 else "default", rest[0], rest[1], rest[2]))
    elif sub == "list":
        _print("Relationships", relationship_service.list_relationships(rest[0] if rest else "default", limit=20))
    elif sub == "stats":
        _print("Stats", relationship_service.get_relationship_stats(rest[0] if rest else "default"))
    elif sub == "neighborhood":
        if not rest:
            print("Usage: relationship neighborhood <entity_id> [depth]")
            return
        _print("Neighborhood", relationship_service.get_entity_neighborhood(rest[0], int(rest[1]) if len(rest) > 1 else 2))


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
        _print("Search", search_service.search_entities(rest[1] if len(rest) > 1 else "default", rest[0]))
    elif sub == "paths":
        if len(rest) < 2:
            print("Usage: search paths <source_id> <target_id>")
            return
        _print("Paths", search_service.search_paths("", rest[0], rest[1]))
    elif sub == "nl":
        if not rest:
            print("Usage: search nl <question> [tenant]")
            return
        _print("NL Query", search_service.natural_language_query(rest[1] if len(rest) > 1 else "default", rest[0]))


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
        _print("BFS", traversal_service.bfs(rest[0], max_depth=int(rest[1]) if len(rest) > 1 else 3))
    elif sub == "dfs":
        if not rest:
            print("Usage: traverse dfs <start_id> [depth]")
            return
        _print("DFS", traversal_service.dfs(rest[0], max_depth=int(rest[1]) if len(rest) > 1 else 3))
    elif sub == "path":
        if len(rest) < 2:
            print("Usage: traverse path <source_id> <target_id>")
            return
        _print("Shortest Path", traversal_service.shortest_path(rest[0], rest[1]))
    elif sub == "blast":
        if not rest:
            print("Usage: traverse blast <entity_id> [depth]")
            return
        _print("Blast Radius", traversal_service.blast_radius(rest[0], max_depth=int(rest[1]) if len(rest) > 1 else 5))
    elif sub == "components":
        _print("Connected Components", traversal_service.get_connected_components())
    elif sub == "cycles":
        _print("Cycles", traversal_service.detect_cycles(rest[0] if rest else ""))
    elif sub == "communities":
        _print("Communities", traversal_service.community_detection())
    elif sub == "centrality":
        _print("Centrality", traversal_service.get_degree_centrality(rest[0] if rest else ""))


def _handle_resolve(args: list[str]):
    if not args:
        print("Usage: resolve <detect|auto|stats> [tenant] [threshold]")
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
        _print("Stats", entity_resolution_service.get_resolution_stats(rest[0] if rest else "default"))


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
        _print("Snapshot", temporal_service.create_snapshot(rest[1] if len(rest) > 1 else "default", rest[0]))
    elif sub == "consistency":
        _print("Consistency", temporal_service.validate_temporal_consistency(rest[0] if rest else ""))


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
