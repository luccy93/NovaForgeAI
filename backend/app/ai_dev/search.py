"""Code search over the existing index — Volume 67 Commit 1.

Reuses the code_intelligence index data (code_symbols, code_chunks,
code_files, code_references) directly — no duplicate index. Search is
scoped to a tenant-owned repository (authorization checked before and
scoped after retrieval). Semantic results are never fabricated; when a
vector backend is unavailable, searches fall back to lexical matching
and report `semantic: false`.
"""

import logging
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import resolve_repository
from app.code_intelligence.models import (
    CodeChunk,
    CodeFile,
    CodeReference,
    CodeSymbol,
)

logger = logging.getLogger(__name__)


def _symbol_payload(s: CodeSymbol) -> dict:
    return {
        "kind": s.symbol_type,
        "name": s.name,
        "qualified_name": s.qualified_name,
        "file_path": s.file_path if hasattr(s, "file_path") else None,
        "scope": s.scope,
        "signature": s.signature,
        "docstring": s.docstring,
        "line_start": s.start_line,
        "line_end": s.end_line,
        "is_async": s.is_async,
    }


def _chunk_payload(c: CodeChunk) -> dict:
    return {
        "kind": c.chunk_type,
        "content": c.content[:2000],
        "file_path": c.file_path if hasattr(c, "file_path") else None,
        "line_start": c.start_line,
        "line_end": c.end_line,
        "language": c.language,
    }


def _file_payload(f: CodeFile) -> dict:
    return {
        "kind": "FILE",
        "name": f.file_name,
        "file_path": f.file_path,
        "language": f.language,
        "line_count": f.line_count,
        "size_bytes": f.size_bytes,
        "is_test_file": f.is_test_file,
        "is_config_file": f.is_config_file,
        "is_documentation": f.is_documentation,
        "symbol_count": f.symbol_count,
    }


async def symbol_search(
    db: AsyncSession,
    tenant: str,
    repository_id,
    query: str,
    *,
    symbol_type: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    repo = await resolve_repository(db, tenant, repository_id)
    stmt = (
        select(CodeSymbol)
        .where(CodeSymbol.repository_id == repo.id)
        .where(
            or_(
                CodeSymbol.name.ilike(f"%{query}%"),
                CodeSymbol.qualified_name.ilike(f"%{query}%"),
            )
        )
        .order_by(CodeSymbol.name)
        .limit(limit)
    )
    if symbol_type:
        stmt = stmt.where(CodeSymbol.symbol_type == symbol_type.upper())
    rows = (await db.execute(stmt)).scalars().all()
    return [_symbol_payload(s) for s in rows]


async def text_search(
    db: AsyncSession,
    tenant: str,
    repository_id,
    query: str,
    *,
    limit: int = 20,
) -> list[dict]:
    repo = await resolve_repository(db, tenant, repository_id)
    stmt = (
        select(CodeChunk)
        .where(CodeChunk.repository_id == repo.id)
        .where(CodeChunk.content.ilike(f"%{query}%"))
        .order_by(CodeChunk.content)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_chunk_payload(c) for c in rows]


async def file_search(
    db: AsyncSession,
    tenant: str,
    repository_id,
    query: str,
    *,
    limit: int = 20,
) -> list[dict]:
    repo = await resolve_repository(db, tenant, repository_id)
    stmt = (
        select(CodeFile)
        .where(CodeFile.repository_id == repo.id)
        .where(
            or_(
                CodeFile.file_path.ilike(f"%{query}%"),
                CodeFile.file_name.ilike(f"%{query}%"),
            )
        )
        .order_by(CodeFile.file_path)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_file_payload(f) for f in rows]


async def reference_search(
    db: AsyncSession,
    tenant: str,
    repository_id,
    target_name: str,
    *,
    limit: int = 20,
) -> list[dict]:
    repo = await resolve_repository(db, tenant, repository_id)
    stmt = (
        select(CodeReference)
        .where(CodeReference.repository_id == repo.id)
        .where(
            or_(
                CodeReference.target_name.ilike(f"%{target_name}%"),
                CodeReference.reference_type == "IMPORT",
            )
        )
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "kind": "REFERENCE",
            "reference_type": r.reference_type,
            "target_name": r.target_name,
            "source_file_id": str(r.source_file_id),
            "line": r.source_line,
            "column": r.source_column,
            "resolved": r.resolved,
            "confidence": r.confidence,
        }
        for r in rows
    ]


async def hybrid_search(
    db: AsyncSession,
    tenant: str,
    repository_id,
    query: str,
    *,
    symbol_type: Optional[str] = None,
    limit: int = 12,
    include_text: bool = True,
) -> dict:
    """Deterministic hybrid search: symbol + file + (optional) text rank.

    Honest about capability: `semantic` is only true if a vector backend
    actually answered; here lexical/symbol ranking is used and
    `semantic` is reported false.
    """
    symbols = await symbol_search(
        db, tenant, repository_id, query, symbol_type=symbol_type, limit=limit
    )
    files = await file_search(db, tenant, repository_id, query, limit=limit)
    results: list[dict] = []
    seen = set()
    for hit in symbols + files:
        key = (hit.get("file_path") or "", hit.get("name") or hit.get("qualified_name") or "")
        if key in seen:
            continue
        seen.add(key)
        results.append(hit)
    # text chunks append-only when include_text
    if include_text:
        chunks = await text_search(db, tenant, repository_id, query, limit=limit)
        for hit in chunks:
            if len(results) >= limit * 2:
                break
            results.append(hit)
    return {
        "query": query,
        "results": results[: limit * 2],
        "semantic": False,
        "truncated": len(results) > limit * 2,
    }


async def search_all(
    db: AsyncSession,
    tenant: str,
    repository_id,
    query: str,
    *,
    symbol_type: Optional[str] = None,
    limit: int = 12,
) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    return await hybrid_search(
        db, tenant, repo.id, query, symbol_type=symbol_type, limit=limit
    )