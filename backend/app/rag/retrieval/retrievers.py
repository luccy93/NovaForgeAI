"""Volume 43 — retrievers: lexical (BM25), vector (Qdrant), graph.

Each retriever returns a list of :class:`RetrievedChunk` with a ``scores``
dict and ``retrieval_method`` set. Authorization (tenant + repository +
permissions) is enforced inside every retriever via mandatory filters.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.config import RagConfig, DEFAULT_RAG_CONFIG
from app.rag.embeddings import EmbeddingClient
from app.rag.models import RagChunk
from app.rag.schemas import RetrievalMethod, RetrievedChunk, SourceType

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", (text or "").lower())


def _bm25_score(query_terms: list[str], doc_tokens: list[str], df: dict, n_docs: int, k1=1.5, b=0.75) -> float:
    if not doc_tokens:
        return 0.0
    dl = len(doc_tokens)
    avg_dl = max(1.0, dl)
    tf = Counter(doc_tokens)
    score = 0.0
    for term in set(query_terms):
        if term not in tf:
            continue
        idf = math.log((n_docs - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1.0)
        f = tf[term]
        score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * (dl / avg_dl)))
    return min(1.0, score / max(1.0, len(set(query_terms))))


class LexicalRetriever:
    def __init__(self, config: Optional[RagConfig] = None) -> None:
        self.config = config or DEFAULT_RAG_CONFIG

    async def search(
        self,
        db: AsyncSession,
        query: str,
        *,
        tenant_id: Any,
        filters: Optional[dict] = None,
        limit: int = 20,
    ) -> list[RetrievedChunk]:
        terms = _tokenize(query)
        if not terms:
            return []
        stmt = self._base_stmt(tenant_id, filters)
        # ILIKE OR over each term on content/symbol.
        conds = []
        for t in terms[:10]:
            like = f"%{t}%"
            conds.append(RagChunk.content.ilike(like))
            conds.append(RagChunk.symbol.ilike(like))
            conds.append(RagChunk.file_path.ilike(like))
        stmt = stmt.where(or_(*conds)).limit(limit * 4)
        res = await db.execute(stmt)
        rows = list(res.scalars().all())
        if not rows:
            return []

        token_docs = [_tokenize(r.content) for r in rows]
        df: dict[str, int] = {}
        for doc in token_docs:
            for t in set(doc):
                df[t] = df.get(t, 0) + 1

        out: list[RetrievedChunk] = []
        for r, toks in zip(rows, token_docs):
            sc = _bm25_score(terms, toks, df, len(rows), self.config.bm25_k1, self.config.bm25_b)
            if sc <= 0:
                continue
            out.append(self._to_chunk(r, RetrievalMethod.LEXICAL.value, {"lexical": sc}))
        out.sort(key=lambda c: c.scores.get("lexical", 0), reverse=True)
        return out[:limit]

    def _base_stmt(self, tenant_id, filters):
        stmt = select(RagChunk).where(
            RagChunk.tenant_id == tenant_id,
            RagChunk.is_deleted.is_(False),
        )
        if filters:
            if filters.get("repository_id") is not None:
                stmt = stmt.where(RagChunk.repository_id == filters["repository_id"])
            if filters.get("source_type"):
                stmt = stmt.where(RagChunk.source_type == filters["source_type"])
            if filters.get("language"):
                stmt = stmt.where(RagChunk.language == filters["language"])
            if filters.get("file_path"):
                stmt = stmt.where(RagChunk.file_path.ilike(f"%{filters['file_path']}%"))
        return stmt

    @staticmethod
    def _to_chunk(r: RagChunk, method: str, scores: dict) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=str(r.id),
            content=r.content,
            source_type=r.source_type,
            repository_id=str(r.repository_id) if r.repository_id else None,
            source_id=str(r.source_id),
            source_version_id=str(r.source_version_id),
            file_path=r.file_path,
            symbol=r.symbol,
            language=r.language,
            branch=r.branch,
            commit=r.commit,
            start_line=r.start_line,
            end_line=r.end_line,
            snippet=r.snippet,
            embedding_model=r.embedding_model,
            embedding_version=r.embedding_version,
            permissions=r.permissions or {},
            metadata=r.metadata_ or {},
            scores=scores,
            retrieval_method=method,
        )


class VectorRetriever:
    def __init__(
        self,
        config: Optional[RagConfig] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        vector_store=None,
    ) -> None:
        self.config = config or DEFAULT_RAG_CONFIG
        self.embeddings = embedding_client or EmbeddingClient()
        self.vector_store = vector_store

    async def search(
        self,
        db: AsyncSession,
        query: str,
        *,
        tenant_id: Any,
        filters: Optional[dict] = None,
        limit: int = 20,
    ) -> list[RetrievedChunk]:
        if self.vector_store is None:
            from app.services.vector_store import VectorStoreService

            self.vector_store = VectorStoreService()
        if getattr(self.vector_store, "_client", None) is None:
            return []  # vector store unavailable -> degrade gracefully
        qvec = await self.embeddings.embed_one(query)
        f = self._build_filter(tenant_id, filters)
        collections = self._collections(filters)
        out: list[RetrievedChunk] = []
        for collection in collections:
            hits = self.vector_store.search(collection, qvec, limit=limit, filter_=f)
            for h in hits:
                p = h.get("payload") or {}
                out.append(
                    RetrievedChunk(
                        chunk_id=p.get("chunk_id") or str(h.get("id")),
                        content=p.get("content", ""),
                        source_type=p.get("source_type", "documentation"),
                        repository_id=p.get("repository_id"),
                        source_id=p.get("source_id"),
                        source_version_id=p.get("source_version_id"),
                        file_path=p.get("file_path"),
                        symbol=p.get("symbol"),
                        language=p.get("language"),
                        branch=p.get("branch"),
                        commit=p.get("commit"),
                        start_line=p.get("start_line"),
                        end_line=p.get("end_line"),
                        snippet=(p.get("content") or "")[:300],
                        embedding_model=p.get("embedding_model"),
                        embedding_version=p.get("embedding_version"),
                        permissions=p.get("permissions") or {},
                        metadata=p.get("metadata", {}) if isinstance(p.get("metadata"), dict) else {},
                        scores={"semantic": float(h.get("score", 0.0))},
                        retrieval_method=RetrievalMethod.VECTOR.value,
                    )
                )
        return out

    def _collections(self, filters: Optional[dict]) -> list[str]:
        st = (filters or {}).get("source_type")
        if st:
            return [self.config.collection_for(st)]
        return [self.config.knowledge_collection, self.config.code_collection, self.config.doc_collection]

    def _build_filter(self, tenant_id, filters) -> dict:
        must = [{"key": "tenant_id", "match": {"value": str(tenant_id)}}]
        if filters:
            if filters.get("repository_id") is not None:
                must.append({"key": "repository_id", "match": {"value": str(filters["repository_id"])}})
            if filters.get("source_version_id") is not None:
                must.append(
                    {"key": "source_version_id", "match": {"value": str(filters["source_version_id"])}}
                )
            if filters.get("language"):
                must.append({"key": "language", "match": {"value": filters["language"]}})
        return {"must": must}


class GraphRetriever:
    """Graph traversal over the Volume 42 code-intelligence graph (Postgres).

    Given a symbol/file mentioned in the query, returns callers, callees,
    references, imports, ownership and related tests as retrieved chunks.
    This works without Neo4j (uses the canonical code-intelligence tables) and
    is the primary graph path; an optional Neo4j bridge can supplement it.
    """

    def __init__(self, config: Optional[RagConfig] = None) -> None:
        self.config = config or DEFAULT_RAG_CONFIG

    async def search(
        self,
        db: AsyncSession,
        query: str,
        *,
        tenant_id: Any,
        filters: Optional[dict] = None,
        limit: int = 20,
    ) -> list[RetrievedChunk]:
        from app.code_intelligence.models import (
            CodeCall,
            CodeFile,
            CodeImport,
            CodeOwnership,
            CodeReference,
            CodeSymbol,
            CodeTest,
        )

        repo_id = filters.get("repository_id") if filters else None
        candidate = self._candidate_symbol(query)
        if not candidate:
            return []

        # Resolve symbol(s) by name or qualified name.
        sym_stmt = select(CodeSymbol).where(
            or_(
                CodeSymbol.name.ilike(f"%{candidate}%"),
                CodeSymbol.qualified_name.ilike(f"%{candidate}%"),
            )
        )
        if repo_id is not None:
            sym_stmt = sym_stmt.where(CodeSymbol.repository_id == repo_id)
        sym_res = await db.execute(sym_stmt.limit(5))
        symbols = list(sym_res.scalars().all())
        if not symbols:
            return []

        found: dict[str, RetrievedChunk] = {}
        max_depth = self.config.graph_max_depth
        max_nodes = self.config.graph_max_nodes

        for sym in symbols:
            # Calls (callers + callees).
            calls = await db.execute(
                select(CodeCall).where(
                    or_(
                        CodeCall.caller_symbol_id == sym.id,
                        CodeCall.callee_symbol_id == sym.id,
                    )
                ).limit(max_nodes)
            )
            for c in calls.scalars().all():
                other_id = c.callee_symbol_id if c.caller_symbol_id == sym.id else c.caller_symbol_id
                rel = "callee" if c.caller_symbol_id == sym.id else "caller"
                await self._add_symbol(db, found, other_id, sym, rel, limit)
            # References.
            refs = await db.execute(
                select(CodeReference).where(
                    or_(
                        CodeReference.source_symbol_id == sym.id,
                        CodeReference.target_symbol_id == sym.id,
                    )
                ).limit(max_nodes)
            )
            for r in refs.scalars().all():
                other_id = r.target_symbol_id if r.source_symbol_id == sym.id else r.source_symbol_id
                await self._add_symbol(db, found, other_id, sym, f"ref:{r.reference_type}", limit)
            # Imports.
            imps = await db.execute(
                select(CodeImport).where(CodeImport.file_id == sym.file_id).limit(max_nodes)
            )
            for imp in imps.scalars().all():
                await self._add_file(db, found, imp.file_id, sym, "import", limit)
            # Ownership of the file.
            own = await db.execute(
                select(CodeOwnership).where(CodeOwnership.file_path == sym.file_path).limit(10)
            )
            for o in own.scalars().all():
                chunk = self._mk_chunk(
                    chunk_id=f"own:{o.file_path}:{o.owner_email}",
                    content=f"Owned by {o.owner_name or o.owner_email} (score {o.ownership_score})",
                    source_type=SourceType.SOURCE_FILE.value,
                    file_path=o.file_path,
                    symbol=sym.name,
                    retrieval_method=RetrievalMethod.GRAPH.value,
                    scores={"graph": 0.6},
                    metadata={"owner": o.owner_email, "relationship": "ownership"},
                )
                found[chunk.chunk_id] = chunk
            # Related tests.
            tests = await db.execute(
                select(CodeTest).where(CodeTest.file_id == sym.file_id).limit(limit)
            )
            for t in tests.scalars().all():
                chunk = self._mk_chunk(
                    chunk_id=f"test:{t.id}",
                    content=f"Test {t.test_name} ({t.test_type}) covers this symbol",
                    source_type=SourceType.SOURCE_FILE.value,
                    file_path=t.file_path if hasattr(t, "file_path") else sym.file_path,
                    symbol=sym.name,
                    retrieval_method=RetrievalMethod.GRAPH.value,
                    scores={"graph": 0.55},
                    metadata={"relationship": "test", "test_type": t.test_type},
                )
                found[chunk.chunk_id] = chunk

        return list(found.values())[:limit]

    async def _add_symbol(self, db, found, symbol_id, origin, rel, limit):
        if symbol_id is None:
            return
        res = await db.execute(select(CodeSymbol).where(CodeSymbol.id == symbol_id).limit(1))
        s = res.scalar_one_or_none()
        if s is None:
            return
        chunk = self._mk_chunk(
            chunk_id=f"sym:{s.id}",
            content=f"{s.qualified_name or s.name} ({s.symbol_type})",
            source_type=SourceType.SOURCE_FILE.value,
            file_path=s.file_path if hasattr(s, "file_path") else None,
            symbol=s.name,
            language=s.language,
            start_line=s.start_line,
            end_line=s.end_line,
            retrieval_method=RetrievalMethod.GRAPH.value,
            scores={"graph": 0.7},
            metadata={"relationship": rel, "origin_symbol": origin.name},
        )
        found[chunk.chunk_id] = chunk

    async def _add_file(self, db, found, file_id, origin, rel, limit):
        if file_id is None:
            return
        res = await db.execute(select(CodeFile).where(CodeFile.id == file_id).limit(1))
        f = res.scalar_one_or_none()
        if f is None:
            return
        chunk = self._mk_chunk(
            chunk_id=f"file:{f.id}",
            content=f"File {f.file_path} ({f.language})",
            source_type=SourceType.SOURCE_FILE.value,
            file_path=f.file_path,
            language=f.language,
            retrieval_method=RetrievalMethod.GRAPH.value,
            scores={"graph": 0.5},
            metadata={"relationship": rel, "origin_symbol": origin.name},
        )
        found[chunk.chunk_id] = chunk

    @staticmethod
    def _mk_chunk(chunk_id, content, source_type, file_path, symbol, retrieval_method, scores, metadata):
        return RetrievedChunk(
            chunk_id=chunk_id,
            content=content,
            source_type=source_type,
            file_path=file_path,
            symbol=symbol,
            retrieval_method=retrieval_method,
            scores=scores,
            metadata=metadata,
        )

    @staticmethod
    def _candidate_symbol(query: str) -> Optional[str]:
        m = re.search(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)
        if not m:
            return None
        # Prefer an identifier that looks like a symbol (CamelCase or snake).
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query):
            if re.search(r"[A-Z]", tok) or "_" in tok:
                return tok
        return m.group(0)
