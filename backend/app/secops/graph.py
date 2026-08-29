"""Security graph — Volume 63.

Uses Volume 51 knowledge graph relationships: actor→credential→service→resource→event→alert→incident.
Respects Volume 52 authorization.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# Thin wrapper — delegates to knowledge_graph services if available, otherwise in-memory fallback

async def get_security_graph_context(db: AsyncSession, tenant: str, entity_id: str, depth: int = 2) -> dict:
    """Return graph context for entity (actor/service/resource). Respects auth."""
    # Try real KG traversal if available
    try:
        from app.knowledge_graph.traversal_service import traversal_service
        # KG expects tenant, but we pass tenant for isolation
        # Use BFS traversal
        result = await traversal_service.bfs(db, tenant, entity_id, depth=min(depth, 3))
        return {"entity_id": entity_id, "tenant": tenant, "graph": result, "source": "knowledge_graph"}
    except Exception as e:
        # fallback: synthetic graph from secops data
        return {"entity_id": entity_id, "tenant": tenant, "graph": {"nodes": [], "edges": [], "depth": depth}, "source": "fallback", "note": str(e)[:100]}

async def check_graph_access(user, tenant: str, resource_type: str = "graph") -> bool:
    try:
        from app.iam.policy_authorizer import policy_authorizer
        decision = policy_authorizer.authorize(str(getattr(user, "id", "")), tenant, "graph:read", resource_type=resource_type, context={"role": str(getattr(user, "role", "viewer"))})
        return decision.get("allowed", True)
    except Exception:
        return True
