"""Retrieval context assembly for the developer assistant — Volume 67.

Bounds retrieval by an explicit token budget and returns citations
(file + line ranges) alongside every item so assistant answers can be
verified against the repository.
"""

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_SYMBOLS,
    DEFAULT_TOKEN_BUDGET,
    estimate_tokens,
    resolve_repository,
)
from app.code_intelligence.models import (
    CodeChunk,
    CodeFile,
    CodeHistory,
    CodeSymbol,
    CodeTest,
)


def _citation(file_path: str, line_start: Optional[int], line_end: Optional[int]) -> dict:
    return {
        "file": file_path,
        "line_start": line_start,
        "line_end": line_end,
    }


async def _recent_changes(db, repository_id, limit: int = 5) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(CodeHistory)
                .where(CodeHistory.repository_id == repository_id)
                .order_by(desc(CodeHistory.commit_date))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "file_path": h.file_path,
            "commit_sha": h.commit_sha,
            "author_email": h.author_email,
            "change_type": h.change_type,
            "lines_added": h.lines_added,
            "lines_deleted": h.lines_deleted,
            "message": h.message,
        }
        for h in rows
    ]


async def _tests_for(db, repository_id, file_path: str, limit: int = 10) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(CodeTest)
                .where(
                    CodeTest.repository_id == repository_id,
                    CodeTest.source_file_path == file_path,
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "test_name": t.test_name,
            "test_type": t.test_type,
            "framework": t.framework,
        }
        for t in rows
    ]


async def build_context(
    db: AsyncSession,
    tenant: str,
    repository_id,
    query: str,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    max_files: int = DEFAULT_MAX_FILES,
    max_symbols: int = DEFAULT_MAX_SYMBOLS,
) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)

    symbol_rows = (
        (
            await db.execute(
                select(CodeSymbol)
                .where(
                    CodeSymbol.repository_id == repo.id,
                    CodeSymbol.name.ilike(f"%{query}%"),
                )
                .order_by(CodeSymbol.name)
                .limit(max_symbols)
            )
        )
        .scalars()
        .all()
    )
    chunk_rows = (
        (
            await db.execute(
                select(CodeChunk)
                .where(
                    CodeChunk.repository_id == repo.id,
                    CodeChunk.content.ilike(f"%{query}%"),
                )
                .limit(max_files * 2)
            )
        )
        .scalars()
        .all()
    )
    file_rows = (
        (
            await db.execute(
                select(CodeFile)
                .where(
                    CodeFile.repository_id == repo.id,
                    CodeFile.file_path.ilike(f"%{query}%"),
                )
                .order_by(CodeFile.file_path)
                .limit(max_files)
            )
        )
        .scalars()
        .all()
    )

    items: list[dict] = []
    for s in symbol_rows[:max_symbols]:
        items.append(
            {
                "kind": s.symbol_type,
                "text": (s.signature or s.qualified_name or s.name)[:500],
                "citation": _citation(
                    s.file_path if hasattr(s, "file_path") else None, s.start_line, s.end_line
                ),
            }
        )
    for c in chunk_rows:
        items.append(
            {
                "kind": "CHUNK",
                "text": c.content[:800],
                "citation": _citation(
                    c.file_path if hasattr(c, "file_path") else None, c.start_line, c.end_line
                ),
            }
        )
    for f in file_rows:
        items.append(
            {
                "kind": "FILE",
                "text": f"{f.file_path} ({f.line_count} lines, {f.language or 'unknown'})",
                "citation": _citation(f.file_path, 1, f.line_count),
            }
        )

    recent = await _recent_changes(db, repo.id)
    used = 0
    truncated = False
    final_items: list[dict] = []
    for item in items:
        cost = estimate_tokens(item["text"])
        if used + cost > token_budget:
            truncated = True
            continue
        used += cost
        final_items.append(item)

    return {
        "repository_id": str(repo.id),
        "query": query,
        "tokens_used": used,
        "token_budget": token_budget,
        "truncated": truncated,
        "items": final_items,
        "recent_changes": recent,
        "test_mapping": {
            str(f.id): await _tests_for(db, repo.id, f.file_path)
            for f in file_rows[: max_files]
        },
    }