"""Access graph — identity→role→permission→resource→action via knowledge graph."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def get_access_graph(db: AsyncSession, tenant_id: str, identity_id: str, depth: int = 2) -> dict:
    try:
        from app.knowledge_graph.traversal_service import traversal_service
        # BFS from identity
        res = await traversal_service.bfs(db, tenant_id, identity_id, depth=depth)
        # Normalize
        if isinstance(res, dict):
            nodes = res.get("nodes", []) or res.get("entities", [])
            edges = res.get("edges", []) or res.get("relationships", [])
        else:
            nodes, edges = [], []
        return {"identity": identity_id, "tenant": tenant_id, "nodes": nodes[:20], "edges": edges[:20], "depth": depth, "source": "knowledge_graph"}
    except Exception as e:
        # Fallback synthetic but hypotheses
        return {"identity": identity_id, "tenant": tenant_id, "nodes": [{"id": identity_id, "type": "identity"}, {"id": "role:member", "type": "role"}], "edges": [{"from": identity_id, "to": "role:member", "type": "has_role", "hypothesis": True}], "depth": depth, "source": "fallback", "note": str(e)[:100]}


async def analyze_paths(db: AsyncSession, tenant_id: str, from_id: str, to_id: str, depth: int = 3) -> dict:
    try:
        from app.knowledge_graph.traversal_service import traversal_service
        paths = await traversal_service.all_paths(db, tenant_id, from_id, to_id, depth=depth)
        if isinstance(paths, dict) and "paths" in paths:
            paths = paths["paths"]
        # Mark hypotheses
        for p in paths or []:
            if isinstance(p, dict):
                p["hypothesis"] = True
        return {"from": from_id, "to": to_id, "paths": (paths or [])[:5], "hypothesis": True}
    except Exception as e:
        return {"from": from_id, "to": to_id, "paths": [{"nodes": [from_id, to_id], "hypothesis": True}], "error": str(e)[:100]}


async def estimate_blast_radius(db: AsyncSession, tenant_id: str, identity_id: str) -> dict:
    graph = await get_access_graph(db, tenant_id, identity_id, depth=2)
    nodes = graph.get("nodes", [])
    # Estimate
    resources = [n for n in nodes if n.get("type") == "resource" or "resource" in str(n.get("id","")).lower()]
    return {
        "identity": identity_id,
        "tenant": tenant_id,
        "estimate": True,
        "counts": {"resources": len(resources), "nodes": len(nodes)},
        "resources": [r.get("id") for r in resources[:10]],
        "note": "Estimate — blast radius via graph hypotheses",
    }


async def blast_radius_for_session(db: AsyncSession, tenant_id: str, session_id_hash: str) -> dict:
    from app.zero_trust.sessions import get_session
    sess = await get_session(db, session_id_hash, tenant_id)
    if not sess:
        return {"error": "session not found", "estimate": True}
    identity = sess.get("identity_id")
    return await estimate_blast_radius(db, tenant_id, identity)
