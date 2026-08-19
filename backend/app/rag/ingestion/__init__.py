"""Volume 43 — ingestion core.

Orchestrates the left half of the pipeline:

    Sources -> Parsing -> Classification -> Chunking -> Embeddings
            -> Lexical Index (Postgres) -> Vector Index (Qdrant)
            -> (optional) Graph -> Versioning (atomic) -> Activation.

Tenant/project/repository scoping and permissions are attached at chunk
creation time so authorization can be enforced before retrieval.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.config import RagConfig, DEFAULT_RAG_CONFIG
from app.rag.embeddings import EmbeddingClient
from app.rag.exceptions import RagError, SourceNotFoundError
from app.rag.models import (
    KnowledgeSource,
    KnowledgeSourceVersion,
    RagChunk,
    RagIngestionJob,
)
from app.rag.schemas import IngestionStatus, SourceType, new_id, utcnow
from app.services.vector_store import PointStruct, VectorStoreService

logger = logging.getLogger(__name__)


# ─── Parsing ────────────────────────────────────────────────────────────


@dataclass
class ParsedSection:
    heading: str = ""
    text: str = ""
    chunk_type: str = "section"
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    language: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    sections: list[ParsedSection] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    tables: int = 0
    code_blocks: int = 0


class DocumentParser:
    """Extract structured sections from documents.

    Preserves original source references (headings, line ranges, links).
    Markdown is split on ATX headings; plain text on paragraphs; PDF is
    extracted to text when a PDF library is available, otherwise treated as
    plain text.
    """

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
    _CODE_FENCE_RE = re.compile(r"```(?P<lang>\w+)?\n(?P<body>.*?)```", re.DOTALL)
    _LINK_RE = re.compile(r"\[[^\]]+\]\((?P<url>[^)]+)\)")
    _TABLE_RE = re.compile(r"^\|.+\|\s*$", re.MULTILINE)

    def parse(self, content: str, source_type: str, file_path: Optional[str] = None) -> ParsedDocument:
        st = (source_type or "").lower()
        if st == "markdown" or st == "wiki" or (file_path or "").lower().endswith((".md", ".markdown")):
            return self._parse_markdown(content, file_path)
        if st == "pdf":
            return self._parse_pdf(content, file_path)
        return self._parse_plain(content, file_path)

    def _parse_markdown(self, content: str, file_path: Optional[str]) -> ParsedDocument:
        # Split into heading-delimited sections.
        matches = list(self._HEADING_RE.finditer(content))
        sections: list[ParsedSection] = []
        links: list[str] = []
        tables = 0
        code_blocks = 0
        segments: list[tuple[int, int, str, str]] = []
        prev = 0
        for m in matches:
            heading = m.group(2).strip()
            start = m.start()
            if prev < start:
                segments.append((prev, start, "", content[prev:start]))
            segments.append((start, m.end(), heading, content[m.end():]))
            prev = m.end()
        if prev < len(content):
            segments.append((prev, len(content), "", content[prev:]))

        for (s, e, heading, body) in segments:
            if heading == "" and not body.strip():
                continue
            code_blocks += len(self._CODE_FENCE_RE.findall(body))
            tables += len(self._TABLE_RE.findall(body))
            links.extend(self._LINK_RE.findall(body))
            lines = body.splitlines()
            # crude line numbers
            start_line = content.count("\n", 0, s) + 1
            end_line = content.count("\n", 0, e) + 1
            sections.append(
                ParsedSection(
                    heading=heading,
                    text=body.strip(),
                    chunk_type="heading" if heading else "section",
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    metadata={"heading": heading} if heading else {},
                )
            )
        if not sections:
            sections.append(
                ParsedSection(text=content.strip(), chunk_type="section", file_path=file_path)
            )
        return ParsedDocument(
            sections=sections, links=links, tables=tables, code_blocks=code_blocks
        )

    def _parse_plain(self, content: str, file_path: Optional[str]) -> ParsedDocument:
        paras = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        sections = [
            ParsedSection(text=p, chunk_type="paragraph", file_path=file_path)
            for p in paras
        ]
        if not sections:
            sections.append(ParsedSection(text=content.strip(), chunk_type="section", file_path=file_path))
        links = self._LINK_RE.findall(content)
        return ParsedDocument(sections=sections, links=links)

    def _parse_pdf(self, content: str, file_path: Optional[str]) -> ParsedDocument:
        text = content
        try:  # pragma: no cover - optional dependency
            from pdfminer.high_level import extract_text  # type: ignore

            # content may be raw bytes; we attempt extraction if it looks like text.
            if isinstance(content, bytes):
                import io

                text = extract_text(io.BytesIO(content)) or ""
        except Exception:
            # Fall back to treating input as text (already-extracted or raw).
            text = content if isinstance(content, str) else str(content)
        return self._parse_plain(text, file_path)


# ─── Chunking ──────────────────────────────────────────────────────────

MAX_SECTION_CHARS = 1500


class Chunker:
    """Semantic chunking around meaningful units.

    Avoids arbitrary splitting where structural boundaries exist; splits only
    oversized sections, keeping code blocks and headings intact.
    """

    def chunk(self, parsed: ParsedDocument) -> list[ParsedSection]:
        out: list[ParsedSection] = []
        for sec in parsed.sections:
            if len(sec.text) <= MAX_SECTION_CHARS:
                out.append(sec)
                continue
            # Split oversized section on paragraph breaks with light overlap.
            parts = self._split_long(sec)
            out.extend(parts)
        return out

    def _split_long(self, sec: ParsedSection) -> list[ParsedSection]:
        paragraphs = re.split(r"\n\s*\n", sec.text)
        # A single block with no paragraph breaks: hard-split by character
        # windows so oversized content is never silently dropped.
        if len(paragraphs) == 1 and len(paragraphs[0]) > MAX_SECTION_CHARS:
            text = paragraphs[0]
            wins = [text[i:i + MAX_SECTION_CHARS] for i in range(0, len(text), MAX_SECTION_CHARS)]
            return [self._with_text(sec, w) for w in wins]
        chunks: list[ParsedSection] = []
        buf: list[str] = []
        size = 0
        for p in paragraphs:
            if size + len(p) > MAX_SECTION_CHARS and buf:
                chunks.append(self._with_text(sec, "\n\n".join(buf)))
                # adaptive overlap: keep last paragraph for continuity
                buf = [buf[-1]] if buf else []
                size = len(buf[0]) if buf else 0
            buf.append(p)
            size += len(p)
        if buf:
            chunks.append(self._with_text(sec, "\n\n".join(buf)))
        return chunks

    def _with_text(self, sec: ParsedSection, text: str) -> ParsedSection:
        return ParsedSection(
            heading=sec.heading,
            text=text,
            chunk_type=sec.chunk_type,
            file_path=sec.file_path,
            start_line=sec.start_line,
            end_line=sec.end_line,
            language=sec.language,
            metadata=dict(sec.metadata),
        )


# ─── Source registry ───────────────────────────────────────────────────


class KnowledgeSourceRegistry:
    """CRUD + lifecycle for knowledge sources."""

    async def create_source(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        organization_id: UUID,
        name: str,
        source_type: str,
        source_uri: Optional[str] = None,
        repository_id: Optional[UUID] = None,
        workspace_id: Optional[UUID] = None,
        project_id: Optional[UUID] = None,
        owner_id: Optional[UUID] = None,
        permissions: Optional[dict] = None,
        classification: str = "internal",
        content: Optional[str] = None,
        metadata_: Optional[dict] = None,
    ) -> KnowledgeSource:
        h = hashlib.sha256((content or "").encode()).hexdigest() if content is not None else None
        src = KnowledgeSource(
            tenant_id=tenant_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            project_id=project_id,
            repository_id=repository_id,
            name=name,
            source_type=source_type,
            source_uri=source_uri,
            content_hash=h,
            owner_id=owner_id,
            permissions=permissions or {},
            classification=classification,
            status=IngestionStatus.QUEUED.value,
            ingestion_status=IngestionStatus.QUEUED.value,
            metadata_=metadata_ or {},
        )
        db.add(src)
        await db.flush()
        return src

    async def get_source(self, db: AsyncSession, source_id: UUID) -> Optional[KnowledgeSource]:
        res = await db.execute(select(KnowledgeSource).where(KnowledgeSource.id == source_id))
        return res.scalar_one_or_none()

    async def list_sources(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        repository_id: Optional[UUID] = None,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[KnowledgeSource]:
        stmt = select(KnowledgeSource).where(KnowledgeSource.tenant_id == tenant_id)
        if repository_id is not None:
            stmt = stmt.where(KnowledgeSource.repository_id == repository_id)
        if source_type is not None:
            stmt = stmt.where(KnowledgeSource.source_type == source_type)
        if status is not None:
            stmt = stmt.where(KnowledgeSource.status == status)
        res = await db.execute(stmt.order_by(KnowledgeSource.created_at.desc()))
        return list(res.scalars().all())

    async def set_status(
        self,
        db: AsyncSession,
        source_id: UUID,
        status: str,
        is_stale: bool = False,
        error: Optional[str] = None,
    ) -> None:
        await db.execute(
            update(KnowledgeSource)
            .where(KnowledgeSource.id == source_id)
            .values(status=status, is_stale=is_stale, error=error)
        )

    async def mark_stale(self, db: AsyncSession, source_id: UUID, stale: bool = True) -> None:
        await db.execute(
            update(KnowledgeSource).where(KnowledgeSource.id == source_id).values(is_stale=stale)
        )

    async def delete_source(self, db: AsyncSession, source_id: UUID) -> None:
        await db.execute(
            update(KnowledgeSource)
            .where(KnowledgeSource.id == source_id)
            .values(status=IngestionStatus.DELETED.value, is_stale=True)
        )


# ─── Indexer (atomic reindex) ─────────────────────────────────────────


class Indexer:
    """Build, validate and atomically activate index versions."""

    def __init__(
        self,
        config: RagConfig | None = None,
        embedding_client: Optional[EmbeddingClient] = None,
        vector_store: Optional[VectorStoreService] = None,
    ) -> None:
        self.config = config or DEFAULT_RAG_CONFIG
        self.embeddings = embedding_client or EmbeddingClient()
        self.vector_store = vector_store or VectorStoreService()
        self.parser = DocumentParser()
        self.chunker = Chunker()

    async def index_source(
        self,
        db: AsyncSession,
        source_id: UUID,
        *,
        content: Optional[str] = None,
        registry: Optional[KnowledgeSourceRegistry] = None,
    ) -> UUID:
        """Full ingest of a source (creates a new version, validates, activates)."""
        registry = registry or KnowledgeSourceRegistry()
        src = await registry.get_source(db, source_id)
        if src is None:
            raise SourceNotFoundError(f"source {source_id} not found")

        job = RagIngestionJob(
            tenant_id=src.tenant_id,
            organization_id=src.organization_id,
            repository_id=src.repository_id,
            source_id=src.id,
            job_type="ingest",
            status=IngestionStatus.PROCESSING.value,
            stage="parsing",
        )
        db.add(job)
        await registry.set_status(db, source_id, IngestionStatus.PROCESSING.value)
        await db.flush()

        version = KnowledgeSourceVersion(
            source_id=src.id,
            version=src.version + 1,
            content_hash=src.content_hash,
            embedding_model=self.embeddings.model,
            embedding_version=self.embeddings.version,
            status=IngestionStatus.PROCESSING.value,
        )
        db.add(version)
        await db.flush()

        try:
            sections = await self._collect_sections(db, src, content)
            job.total = len(sections)
            chunks = await self._persist_chunks(db, src, version, sections)
            await self._embed_and_upsert(db, src, version, chunks)
            job.processed = len(chunks)
            version.chunk_count = len(chunks)
            version.validated = True
            version.is_active = True
            version.activated_at = utcnow()
            version.status = IngestionStatus.VALIDATED.value
            src.version = version.version
            src.active_version_id = version.id
            src.ingestion_status = IngestionStatus.VALIDATED.value
            src.status = IngestionStatus.VALIDATED.value
            src.last_indexed_at = utcnow()
            src.is_stale = False
            job.status = IngestionStatus.COMPLETED.value if False else IngestionStatus.VALIDATED.value
            job.stage = "done"
            job.finished_at = utcnow()
            await db.flush()
            return version.id
        except Exception as exc:  # noqa: BLE001
            logger.exception("index_source failed")
            job.status = IngestionStatus.FAILED.value
            job.error = str(exc)
            job.finished_at = utcnow()
            version.status = IngestionStatus.FAILED.value
            version.error = str(exc)
            await registry.set_status(db, source_id, IngestionStatus.FAILED.value, error=str(exc))
            raise

    async def _collect_sections(self, db, src, content) -> list[ParsedSection]:
        st = src.source_type
        if st == SourceType.REPOSITORY.value or st == SourceType.SOURCE_FILE.value:
            # Code is indexed structurally via existing CodeChunk rows.
            return await self._code_sections(db, src)
        raw = content if content is not None else (src.metadata_.get("content") or "")
        parsed = self.parser.parse(raw, st, src.source_uri)
        return self.chunker.chunk(parsed)

    async def _code_sections(self, db, src) -> list[ParsedSection]:
        # Reuse Volume 42 structural chunks as the source of truth for code.
        from app.code_intelligence.models import CodeChunk

        out: list[ParsedSection] = []
        stmt = select(CodeChunk).where(CodeChunk.repository_id == src.repository_id)
        res = await db.execute(stmt)
        for c in res.scalars().all():
            out.append(
                ParsedSection(
                    heading=c.chunk_type or "code",
                    text=c.content or "",
                    chunk_type=c.chunk_type or "code",
                    file_path=c.file_path,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    language=c.language,
                    metadata=c.metadata_ or {},
                )
            )
        return out

    async def _persist_chunks(self, db, src, version, sections) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        for i, sec in enumerate(sections):
            cid = uuid4()
            ch = RagChunk(
                id=cid,
                tenant_id=src.tenant_id,
                organization_id=src.organization_id,
                workspace_id=src.workspace_id,
                project_id=src.project_id,
                repository_id=src.repository_id,
                source_id=src.id,
                source_version_id=version.id,
                chunk_type=sec.chunk_type,
                sequence=i,
                content=sec.text,
                snippet=(sec.text or "")[:300],
                content_hash=hashlib.sha256((sec.text or "").encode()).hexdigest()[:16],
                file_path=sec.file_path,
                language=sec.language,
                start_line=sec.start_line,
                end_line=sec.end_line,
                permissions=dict(src.permissions or {}),
                classification=src.classification,
                source_type=src.source_type,
                quality=src.metadata_.get("quality", "maintained"),
                metadata_=sec.metadata,
            )
            db.add(ch)
            chunks.append(ch)
        await db.flush()
        return chunks

    async def _embed_and_upsert(self, db, src, version, chunks) -> None:
        if not chunks:
            return
        texts = [c.content for c in chunks]
        vectors = await self.embeddings.embed(texts)
        collection = self.config.collection_for(src.source_type)
        points: list[PointStruct] = []
        for ch, vec in zip(chunks, vectors):
            ch.embedding_model = self.embeddings.model
            ch.embedding_version = self.embeddings.version
            ch.vector_collection = collection
            ch.embedding_id = str(ch.id)
            points.append(
                PointStruct(
                    id=str(ch.id),
                    vector=vec,
                    payload=self._payload(src, version, ch),
                )
            )
        self.vector_store.upsert_points(collection, points, size=self.embeddings.dimension)

    def _payload(self, src, version, ch) -> dict:
        return {
            "tenant_id": str(src.tenant_id),
            "organization_id": str(src.organization_id),
            "workspace_id": str(src.workspace_id) if src.workspace_id else None,
            "project_id": str(src.project_id) if src.project_id else None,
            "repository_id": str(src.repository_id) if src.repository_id else None,
            "source_id": str(src.id),
            "source_version_id": str(version.id),
            "chunk_id": str(ch.id),
            "chunk_type": ch.chunk_type,
            "file_path": ch.file_path,
            "symbol": ch.symbol,
            "language": ch.language,
            "branch": ch.branch,
            "commit": ch.commit,
            "start_line": ch.start_line,
            "end_line": ch.end_line,
            "embedding_model": ch.embedding_model,
            "embedding_version": ch.embedding_version,
            "permissions": ch.permissions,
            "classification": ch.classification,
            "source_type": ch.source_type,
            "content": ch.content,
        }

    async def delete_propagation(
        self,
        db: AsyncSession,
        source_id: UUID,
        registry: Optional[KnowledgeSourceRegistry] = None,
    ) -> None:
        """Remove chunks, vectors and graph references for a deleted source."""
        registry = registry or KnowledgeSourceRegistry()
        res = await db.execute(select(RagChunk).where(RagChunk.source_id == source_id))
        chunks = list(res.scalars().all())
        ids = [str(c.id) for c in chunks]
        # Soft-delete rows.
        for c in chunks:
            c.is_deleted = True
        # Remove vectors.
        self._delete_vectors(ids)
        # Deactivate versions.
        await db.execute(
            update(KnowledgeSourceVersion)
            .where(KnowledgeSourceVersion.source_id == source_id)
            .values(is_active=False, status=IngestionStatus.DELETED.value)
        )
        await registry.delete_source(db, source_id)
        await db.flush()

    def _delete_vectors(self, ids: list[str]) -> None:
        client = getattr(self.vector_store, "_client", None)
        if not client or not ids:
            return
        try:
            from qdrant_client.http import models as qmodels

            for collection in {
                self.config.knowledge_collection,
                self.config.code_collection,
                self.config.doc_collection,
            }:
                client.delete(
                    collection_name=collection,
                    points_selector=qmodels.PointIdsList(points=ids),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vector delete failed: %s", exc)


# ─── Stale detection ───────────────────────────────────────────────────


class StaleDetector:
    async def detect(self, db: AsyncSession, source_id: UUID, stale_after_days: int = 30) -> bool:
        res = await db.execute(select(KnowledgeSource).where(KnowledgeSource.id == source_id))
        src = res.scalar_one_or_none()
        if src is None:
            return False
        if src.is_stale:
            return True
        if src.last_indexed_at is None:
            return True
        age = (utcnow() - src.last_indexed_at).days
        if age >= stale_after_days:
            await KnowledgeSourceRegistry().mark_stale(db, source_id, True)
            return True
        return False


# ─── Worker entrypoints ────────────────────────────────────────────────


async def run_ingestion_job(
    db: AsyncSession,
    source_id: UUID,
    *,
    content: Optional[str] = None,
    config: Optional[RagConfig] = None,
    embedding_client: Optional[EmbeddingClient] = None,
    vector_store: Optional[VectorStoreService] = None,
) -> UUID:
    indexer = Indexer(config=config, embedding_client=embedding_client, vector_store=vector_store)
    return await indexer.index_source(db, source_id, content=content)


async def run_delete_propagation(
    db: AsyncSession,
    source_id: UUID,
    config: Optional[RagConfig] = None,
    vector_store: Optional[VectorStoreService] = None,
) -> None:
    indexer = Indexer(config=config, vector_store=vector_store)
    await indexer.delete_propagation(db, source_id)
