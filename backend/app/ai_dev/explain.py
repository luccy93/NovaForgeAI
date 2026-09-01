"""Code explanation — Volume 67 Commit 1 (understand the repository).

Explains files, functions, modules and dependency structure using the
existing index data plus real symbol/reference evidence. Sections are
bounded and each cites file + line ranges.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import NotFoundError, resolve_repository
from app.code_intelligence.models import (
    CodeChunk,
    CodeFile,
    CodeImport,
    CodeReference,
    CodeSymbol,
)


def _symbol_card(s: CodeSymbol) -> dict:
    file_path = getattr(s, "file_path", None)
    return {
        "name": s.name,
        "qualified_name": s.qualified_name,
        "symbol_type": s.symbol_type,
        "scope": s.scope,
        "signature": s.signature,
        "docstring": (s.docstring or "")[:2000],
        "start_line": s.start_line,
        "end_line": s.end_line,
        "file_path": file_path,
        "is_async": s.is_async,
        "is_abstract": s.is_abstract,
    }


async def explain_file(db: AsyncSession, tenant: str, repository_id, file_path: str) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    file = (
        (
            await db.execute(
                select(CodeFile).where(
                    CodeFile.repository_id == repo.id,
                    CodeFile.file_path == file_path,
                )
            )
        )
        .scalars()
        .first()
    )
    if file is None:
        raise NotFoundError("file not indexed")
    symbols = (
        (
            await db.execute(
                select(CodeSymbol)
                .where(
                    CodeSymbol.repository_id == repo.id,
                    CodeSymbol.file_id == file.id,
                )
                .order_by(CodeSymbol.start_line)
                .limit(40)
            )
        )
        .scalars()
        .all()
    )
    imports = (
        (
            await db.execute(
                select(CodeImport).where(
                    CodeImport.repository_id == repo.id,
                    CodeImport.source_file_id == file.id,
                )
                .limit(30)
            )
        )
        .scalars()
        .all()
    )
    chunks = (
        (
            await db.execute(
                select(CodeChunk)
                .where(CodeChunk.repository_id == repo.id, CodeChunk.file_id == file.id)
                .order_by(CodeChunk.start_line)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    import_exprs = [imp.imported_name for imp in imports]
    return {
        "kind": "file",
        "file_path": file.file_path,
        "language": file.language,
        "line_count": file.line_count,
        "symbols": [_symbol_card(s) for s in symbols[:20]],
        "imports": import_exprs[:30],
        "snippets": [
            {
                "content": c.content[:1000],
                "line_start": c.start_line,
                "line_end": c.end_line,
            }
            for c in chunks[:10]
        ],
    }


async def explain_function(
    db: AsyncSession, tenant: str, repository_id, function_name: str
) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    rows = (
        (
            await db.execute(
                select(CodeSymbol).where(
                    CodeSymbol.repository_id == repo.id,
                    CodeSymbol.name == function_name,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise NotFoundError("function not found in index")
    calls = []
    for s in rows[:1]:
        refs = (
            (
                await db.execute(
                    select(CodeReference).where(
                        CodeReference.repository_id == repo.id,
                        CodeReference.target_name == s.qualified_name,
                    )
                )
            )
            .scalars()
            .all()
        )
        calls = [
            {
                "reference_type": r.reference_type,
                "source_line": r.source_line,
                "resolved": r.resolved,
            }
            for r in refs[:20]
        ]
    return {
        "kind": "function",
        "name": function_name,
        "matches": [_symbol_card(s) for s in rows[:5]],
        "call_sites": calls,
        "uncertain": len(rows) != 1,
    }


async def explain_architecture(
    db: AsyncSession, tenant: str, repository_id, *, top: int = 20
) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    types = (
        (
            await db.execute(
                select(CodeSymbol.symbol_type, func.count())
                .where(CodeSymbol.repository_id == repo.id)
                .group_by(CodeSymbol.symbol_type)
            )
        )
        .all()
    )
    files = await db.scalar(
        select(func.count())
        .select_from(CodeFile)
        .where(CodeFile.repository_id == repo.id)
    )
    imports = (
        (
            await db.execute(
                select(CodeImport).where(CodeImport.repository_id == repo.id).limit(500)
            )
        )
        .scalars()
        .all()
    )
    return {
        "kind": "architecture",
        "repository_id": str(repo.id),
        "file_count": int(files or 0),
        "symbols_by_type": {t: int(c) for t, c in types},
        "module_edges": len(set(imp.imported_name for imp in imports)),
        "uncertain": True,
    }


async def explain_dependency(
    db: AsyncSession, tenant: str, repository_id, file_path: str
) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    imports = (
        (
            await db.execute(
                select(CodeImport).where(CodeImport.repository_id == repo.id).limit(200)
            )
        )
        .scalars()
        .all()
    )
    file = (
        (
            await db.execute(
                select(CodeFile).where(
                    CodeFile.repository_id == repo.id,
                    CodeFile.file_path == file_path,
                )
            )
        )
        .scalars()
        .first()
    )
    edges = []
    for imp in imports:
        if getattr(imp, "source_file_id", None) == (file.id if file else None):
            edges.append(imp.imported_name)
    return {
        "kind": "dependency",
        "file_path": file_path,
        "imports": edges[:50],
        "count": len(edges),
        "uncertain": file is None,
    }


async def explain(
    db: AsyncSession,
    tenant: str,
    repository_id,
    kind: str,
    target: str,
    *,
    top: int = 20,
) -> dict:
    kind = (kind or "file").lower()
    if kind in ("file", "path"):
        return await explain_file(db, tenant, repository_id, target)
    if kind in ("function", "method"):
        return await explain_function(db, tenant, repository_id, target)
    if kind in ("architecture", "module", "repo"):
        return await explain_architecture(db, tenant, repository_id, top=top)
    if kind in ("dependency", "dependencies"):
        return await explain_dependency(db, tenant, repository_id, target or "")
    raise ValueError(f"unknown explain kind: {kind}")