import logging
import uuid
from typing import Any, Optional

from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j import AsyncDriver, AsyncSession, Record

from app.core.config import settings

logger = logging.getLogger(__name__)


class GraphStoreService:
    def __init__(self) -> None:
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    async def __aenter__(self) -> "GraphStoreService":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        await self._driver.close()

    async def execute_query(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[Record]:
        async with self._driver.session() as session:  # type: ignore[attr-defined]
            result = await session.run(query, params or {})
            records = await result.fetch()
            return records

    async def create_code_node(
        self,
        file_path: str,
        language: str,
        content_hash: str,
    ) -> dict[str, Any]:
        node_id = str(uuid.uuid4())
        query = """
        CREATE (n:CodeFile {
            id: $id,
            file_path: $file_path,
            language: $language,
            content_hash: $content_hash,
            created_at: datetime()
        })
        RETURN n
        """
        params = {
            "id": node_id,
            "file_path": file_path,
            "language": language,
            "content_hash": content_hash,
        }
        records = await self.execute_query(query, params)
        if records:
            return dict(records[0]["n"])
        return {"id": node_id}

    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        props = properties or {}
        set_clause = "SET " + ", ".join(
            f"r.{k} = ${k}" for k in props
        ) if props else ""

        query = f"""
        MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
        CREATE (a)-[r:{rel_type}]->(b)
        {set_clause}
        RETURN r
        """
        params = {"from_id": from_id, "to_id": to_id, **props}
        records = await self.execute_query(query, params)
        if records:
            return dict(records[0]["r"])
        return {"from_id": from_id, "to_id": to_id, "type": rel_type}

    async def search_by_embedding(
        self,
        vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = """
        CALL db.index.vector.queryNodes('code_embeddings', $limit, $vector)
        YIELD node, score
        RETURN node, score
        LIMIT $limit
        """
        params = {"vector": vector, "limit": limit}
        records = await self.execute_query(query, params)
        results = []
        for r in records:
            node = dict(r["node"])
            node["score"] = r["score"]
            results.append(node)
        return results

    async def get_code_graph(self, file_path: str) -> dict[str, Any]:
        query = """
        MATCH path = (root:CodeFile {file_path: $file_path})-[*1..3]-(related)
        RETURN root, nodes(path) AS all_nodes, relationships(path) AS all_rels
        LIMIT 1
        """
        params = {"file_path": file_path}
        records = await self.execute_query(query, params)
        if not records:
            return {"nodes": [], "relationships": []}

        record = records[0]
        nodes = [dict(n) for n in record["all_nodes"]]
        rels = []
        for r in record["all_rels"]:
            rels.append({
                "from": r.start_node.get("id", str(r.start_node)),
                "to": r.end_node.get("id", str(r.end_node)),
                "type": r.type,
                **dict(r),
            })
        return {"nodes": nodes, "relationships": rels}
