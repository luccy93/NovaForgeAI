"""Source adapters — normalize content from NovaForge subsystems into the Knowledge layer.

Each adapter produces normalized document dicts:
    {"external_id", "title", "doc_type", "content", "summary", "language",
     "classification", "tags", "attribution", "metadata"}
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import compute_content_hash

logger = logging.getLogger(__name__)


# ─── Base adapter ─────────────────────────────────────────────────────────


class SourceAdapter(ABC):
    """Base class for all knowledge source adapters."""

    source_type: str = ""

    @abstractmethod
    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        ...

    @abstractmethod
    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        ...

    @staticmethod
    def _normalize(
        *,
        external_id: str,
        title: str,
        doc_type: str,
        content: str,
        summary: str = "",
        language: str = "",
        classification: str = "INTERNAL",
        tags: list[str] | None = None,
        attribution: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        return {
            "external_id": external_id,
            "title": title,
            "doc_type": doc_type,
            "content": content or "",
            "summary": summary or "",
            "language": language or "",
            "classification": classification or "INTERNAL",
            "tags": tags or [],
            "attribution": attribution or {},
            "metadata": metadata or {},
            "content_hash": compute_content_hash(content or ""),
        }


# ─── Code Intelligence adapter ────────────────────────────────────────────


class CodeIntelligenceAdapter(SourceAdapter):
    source_type = "code_intelligence"

    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.code_intelligence.models import CodeFile, CodeSymbol
            from app.models.repository import Repository

            repo_id = getattr(source, "connector_config", {}) or {}
            repo_uuid = repo_id.get("repository_id") if isinstance(repo_id, dict) else None

            if repo_uuid:
                q = (
                    select(CodeFile)
                    .where(CodeFile.repository_id == repo_uuid)
                    .order_by(CodeFile.updated_at.desc())
                )
            else:
                q = (
                    select(CodeFile)
                    .join(Repository, CodeFile.repository_id == Repository.id)
                    .where(Repository.organization_id == tenant)
                    .order_by(CodeFile.updated_at.desc())
                )
            res = await db.execute(q)
            for cf in res.scalars().all():
                content = getattr(cf, "content", None) or ""
                if not content:
                    continue
                lang = getattr(cf, "language", "") or ""
                tags = [lang] if lang else []
                try:
                    sq = (
                        select(CodeSymbol)
                        .where(CodeSymbol.file_id == cf.id)
                        .limit(20)
                    )
                    sym_res = await db.execute(sq)
                    for sym in sym_res.scalars().all():
                        st = getattr(sym, "symbol_type", "")
                        if st:
                            tags.append(st)
                except Exception:
                    pass
                docs.append(
                    self._normalize(
                        external_id=str(cf.id),
                        title=getattr(cf, "file_name", "") or getattr(cf, "file_path", ""),
                        doc_type="code_file",
                        content=content,
                        summary=f"{lang} file: {getattr(cf, 'file_path', '')}",
                        language=lang,
                        tags=list(set(tags)),
                        attribution={
                            "repository_id": str(cf.repository_id),
                            "file_path": getattr(cf, "file_path", ""),
                        },
                        metadata={
                            "file_hash": getattr(cf, "file_hash", ""),
                            "size_bytes": getattr(cf, "size_bytes", 0),
                            "line_count": getattr(cf, "line_count", 0),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("CodeIntelligenceAdapter.fetch_documents failed: %s", exc)
        return docs

    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.code_intelligence.models import CodeFile
            from app.models.repository import Repository

            q = (
                select(CodeFile)
                .join(Repository, CodeFile.repository_id == Repository.id)
                .where(
                    Repository.organization_id == tenant,
                    CodeFile.updated_at >= since,
                )
                .order_by(CodeFile.updated_at.desc())
            )
            res = await db.execute(q)
            for cf in res.scalars().all():
                content = getattr(cf, "content", None) or ""
                if not content:
                    continue
                lang = getattr(cf, "language", "") or ""
                docs.append(
                    self._normalize(
                        external_id=str(cf.id),
                        title=getattr(cf, "file_name", "") or getattr(cf, "file_path", ""),
                        doc_type="code_file",
                        content=content,
                        summary=f"{lang} file: {getattr(cf, 'file_path', '')}",
                        language=lang,
                        tags=[lang] if lang else [],
                        attribution={
                            "repository_id": str(cf.repository_id),
                            "file_path": getattr(cf, "file_path", ""),
                        },
                        metadata={
                            "file_hash": getattr(cf, "file_hash", ""),
                            "size_bytes": getattr(cf, "size_bytes", 0),
                            "line_count": getattr(cf, "line_count", 0),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("CodeIntelligenceAdapter.fetch_incremental failed: %s", exc)
        return docs


# ─── Data Catalog adapter ─────────────────────────────────────────────────


class DataCatalogAdapter(SourceAdapter):
    source_type = "data_catalog"

    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.data_platform.models import DataDataset

            q = (
                select(DataDataset)
                .where(DataDataset.tenant == tenant)
                .order_by(DataDataset.updated_at.desc())
            )
            res = await db.execute(q)
            for ds in res.scalars().all():
                desc = getattr(ds, "description", None) or ""
                name = getattr(ds, "name", "")
                classification = getattr(ds, "classification", "INTERNAL")
                storage_tier = getattr(ds, "storage_tier", "")
                tags = [classification, storage_tier] if storage_tier else [classification]
                content = f"Dataset: {name}\n{desc}"
                docs.append(
                    self._normalize(
                        external_id=str(ds.id),
                        title=name,
                        doc_type="dataset",
                        content=content,
                        summary=desc[:500] if desc else f"Dataset {name}",
                        classification=classification,
                        tags=tags,
                        attribution={
                            "owner": getattr(ds, "owner", ""),
                            "team": getattr(ds, "team", ""),
                        },
                        metadata={
                            "storage_tier": storage_tier,
                            "schema_version": getattr(ds, "schema_version", ""),
                            "region": getattr(ds, "region", ""),
                            "status": getattr(ds, "status", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("DataCatalogAdapter.fetch_documents failed: %s", exc)
        return docs

    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.data_platform.models import DataDataset

            q = (
                select(DataDataset)
                .where(DataDataset.tenant == tenant, DataDataset.updated_at >= since)
                .order_by(DataDataset.updated_at.desc())
            )
            res = await db.execute(q)
            for ds in res.scalars().all():
                desc = getattr(ds, "description", None) or ""
                name = getattr(ds, "name", "")
                classification = getattr(ds, "classification", "INTERNAL")
                storage_tier = getattr(ds, "storage_tier", "")
                tags = [classification, storage_tier] if storage_tier else [classification]
                content = f"Dataset: {name}\n{desc}"
                docs.append(
                    self._normalize(
                        external_id=str(ds.id),
                        title=name,
                        doc_type="dataset",
                        content=content,
                        summary=desc[:500] if desc else f"Dataset {name}",
                        classification=classification,
                        tags=tags,
                        attribution={
                            "owner": getattr(ds, "owner", ""),
                            "team": getattr(ds, "team", ""),
                        },
                        metadata={
                            "storage_tier": storage_tier,
                            "schema_version": getattr(ds, "schema_version", ""),
                            "region": getattr(ds, "region", ""),
                            "status": getattr(ds, "status", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("DataCatalogAdapter.fetch_incremental failed: %s", exc)
        return docs


# ─── Workflow adapter ──────────────────────────────────────────────────────


class WorkflowAdapter(SourceAdapter):
    source_type = "workflows"

    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.workflow.models import WorkflowDefinition

            q = (
                select(WorkflowDefinition)
                .where(WorkflowDefinition.tenant == tenant)
                .order_by(WorkflowDefinition.updated_at.desc())
            )
            res = await db.execute(q)
            for wf in res.scalars().all():
                desc = getattr(wf, "description", None) or ""
                name = getattr(wf, "name", "")
                status = getattr(wf, "status", "")
                content = f"Workflow: {name}\nStatus: {status}\n{desc}"
                docs.append(
                    self._normalize(
                        external_id=str(wf.id),
                        title=name,
                        doc_type="workflow",
                        content=content,
                        summary=desc[:500] if desc else f"Workflow {name}",
                        tags=[status] if status else [],
                        attribution={"owner": getattr(wf, "owner", "")},
                        metadata={
                            "version": getattr(wf, "version", ""),
                            "status": status,
                        },
                    )
                )
        except Exception as exc:
            logger.warning("WorkflowAdapter.fetch_documents failed: %s", exc)
        return docs

    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.workflow.models import WorkflowDefinition

            q = (
                select(WorkflowDefinition)
                .where(
                    WorkflowDefinition.tenant == tenant,
                    WorkflowDefinition.updated_at >= since,
                )
                .order_by(WorkflowDefinition.updated_at.desc())
            )
            res = await db.execute(q)
            for wf in res.scalars().all():
                desc = getattr(wf, "description", None) or ""
                name = getattr(wf, "name", "")
                status = getattr(wf, "status", "")
                content = f"Workflow: {name}\nStatus: {status}\n{desc}"
                docs.append(
                    self._normalize(
                        external_id=str(wf.id),
                        title=name,
                        doc_type="workflow",
                        content=content,
                        summary=desc[:500] if desc else f"Workflow {name}",
                        tags=[status] if status else [],
                        attribution={"owner": getattr(wf, "owner", "")},
                        metadata={
                            "version": getattr(wf, "version", ""),
                            "status": status,
                        },
                    )
                )
        except Exception as exc:
            logger.warning("WorkflowAdapter.fetch_incremental failed: %s", exc)
        return docs


# ─── Incident adapter ──────────────────────────────────────────────────────


class IncidentAdapter(SourceAdapter):
    source_type = "incidents"

    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.incident.models import Incident

            q = (
                select(Incident)
                .where(Incident.tenant == tenant)
                .order_by(Incident.created_at.desc())
            )
            res = await db.execute(q)
            for inc in res.scalars().all():
                title = getattr(inc, "title", "")
                severity = getattr(inc, "severity", "")
                status = getattr(inc, "status", "")
                description = getattr(inc, "description", "") or ""
                root_cause = getattr(inc, "root_cause", "") or ""
                remediation = getattr(inc, "remediation", "") or ""
                parts = [f"Incident: {title}", f"Severity: {severity}", f"Status: {status}"]
                if description:
                    parts.append(description)
                if root_cause:
                    parts.append(f"Root Cause: {root_cause}")
                if remediation:
                    parts.append(f"Remediation: {remediation}")
                content = "\n".join(parts)
                docs.append(
                    self._normalize(
                        external_id=str(inc.id),
                        title=title,
                        doc_type="incident",
                        content=content,
                        summary=f"[{severity}] {title}",
                        tags=[severity, status],
                        attribution={
                            "commander": getattr(inc, "commander", ""),
                            "service": getattr(inc, "service", ""),
                        },
                        metadata={
                            "incident_type": getattr(inc, "incident_type", ""),
                            "environment": getattr(inc, "environment", ""),
                            "source": getattr(inc, "source", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("IncidentAdapter.fetch_documents failed: %s", exc)
        return docs

    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.incident.models import Incident

            q = (
                select(Incident)
                .where(Incident.tenant == tenant, Incident.created_at >= since)
                .order_by(Incident.created_at.desc())
            )
            res = await db.execute(q)
            for inc in res.scalars().all():
                title = getattr(inc, "title", "")
                severity = getattr(inc, "severity", "")
                status = getattr(inc, "status", "")
                description = getattr(inc, "description", "") or ""
                content = f"Incident: {title}\nSeverity: {severity}\nStatus: {status}\n{description}"
                docs.append(
                    self._normalize(
                        external_id=str(inc.id),
                        title=title,
                        doc_type="incident",
                        content=content,
                        summary=f"[{severity}] {title}",
                        tags=[severity, status],
                        attribution={
                            "commander": getattr(inc, "commander", ""),
                            "service": getattr(inc, "service", ""),
                        },
                        metadata={
                            "incident_type": getattr(inc, "incident_type", ""),
                            "environment": getattr(inc, "environment", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("IncidentAdapter.fetch_incremental failed: %s", exc)
        return docs


# ─── Security adapter ──────────────────────────────────────────────────────


class SecurityAdapter(SourceAdapter):
    source_type = "security"

    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.security.models import SecurityFinding

            q = (
                select(SecurityFinding)
                .where(SecurityFinding.tenant == tenant)
                .order_by(SecurityFinding.created_at.desc())
            )
            res = await db.execute(q)
            for sf in res.scalars().all():
                rule = getattr(sf, "rule", "")
                severity = getattr(sf, "severity", "")
                message = getattr(sf, "message", "") or ""
                evidence = getattr(sf, "evidence", "") or ""
                remediation = getattr(sf, "remediation", "") or ""
                parts = [
                    f"Security Finding: {rule}",
                    f"Severity: {severity}",
                    f"Type: {getattr(sf, 'finding_type', '')}",
                    f"Source: {getattr(sf, 'source', '')}",
                ]
                if message:
                    parts.append(message)
                if evidence:
                    parts.append(f"Evidence: {evidence}")
                if remediation:
                    parts.append(f"Remediation: {remediation}")
                content = "\n".join(parts)
                docs.append(
                    self._normalize(
                        external_id=str(sf.id),
                        title=f"[{severity}] {rule}",
                        doc_type="security_finding",
                        content=content,
                        summary=message[:500] if message else f"Security finding: {rule}",
                        tags=[severity, getattr(sf, "finding_type", ""), getattr(sf, "source", "")],
                        attribution={
                            "repository": getattr(sf, "repository", ""),
                            "file_path": getattr(sf, "file_path", ""),
                        },
                        metadata={
                            "severity": severity,
                            "confidence": getattr(sf, "confidence", ""),
                            "cve_id": getattr(sf, "cve_id", ""),
                            "cwe_id": getattr(sf, "cwe_id", ""),
                            "status": getattr(sf, "status", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("SecurityAdapter.fetch_documents failed: %s", exc)
        return docs

    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.security.models import SecurityFinding

            q = (
                select(SecurityFinding)
                .where(SecurityFinding.tenant == tenant, SecurityFinding.created_at >= since)
                .order_by(SecurityFinding.created_at.desc())
            )
            res = await db.execute(q)
            for sf in res.scalars().all():
                rule = getattr(sf, "rule", "")
                severity = getattr(sf, "severity", "")
                message = getattr(sf, "message", "") or ""
                content = f"Security Finding: {rule}\nSeverity: {severity}\n{message}"
                docs.append(
                    self._normalize(
                        external_id=str(sf.id),
                        title=f"[{severity}] {rule}",
                        doc_type="security_finding",
                        content=content,
                        summary=message[:500] if message else f"Security finding: {rule}",
                        tags=[severity, getattr(sf, "finding_type", "")],
                        attribution={
                            "repository": getattr(sf, "repository", ""),
                            "file_path": getattr(sf, "file_path", ""),
                        },
                        metadata={
                            "severity": severity,
                            "cve_id": getattr(sf, "cve_id", ""),
                            "status": getattr(sf, "status", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("SecurityAdapter.fetch_incremental failed: %s", exc)
        return docs


# ─── Conversation adapter ─────────────────────────────────────────────────


class ConversationAdapter(SourceAdapter):
    source_type = "conversations"

    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.models.conversation import Conversation, Message

            q = (
                select(Conversation)
                .where(Conversation.organization_id == tenant)
                .order_by(Conversation.updated_at.desc())
            )
            res = await db.execute(q)
            for conv in res.scalars().all():
                title = getattr(conv, "title", "") or "Untitled Conversation"
                mq = (
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.asc())
                    .limit(100)
                )
                msg_res = await db.execute(mq)
                messages = msg_res.scalars().all()
                parts = [f"Conversation: {title}"]
                for msg in messages:
                    role = getattr(msg, "role", "user")
                    role_val = role.value if hasattr(role, "value") else str(role)
                    parts.append(f"[{role_val}] {getattr(msg, 'content', '')}")
                content = "\n".join(parts)
                if len(content) < 10:
                    continue
                docs.append(
                    self._normalize(
                        external_id=str(conv.id),
                        title=title,
                        doc_type="conversation",
                        content=content,
                        summary=f"Conversation with {len(messages)} messages",
                        tags=[],
                        attribution={
                            "session_id": getattr(conv, "session_id", ""),
                            "model": getattr(conv, "model", ""),
                        },
                        metadata={
                            "message_count": len(messages),
                            "is_archived": getattr(conv, "is_archived", False),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("ConversationAdapter.fetch_documents failed: %s", exc)
        return docs

    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            from app.models.conversation import Conversation, Message

            q = (
                select(Conversation)
                .where(
                    Conversation.organization_id == tenant,
                    Conversation.updated_at >= since,
                )
                .order_by(Conversation.updated_at.desc())
            )
            res = await db.execute(q)
            for conv in res.scalars().all():
                title = getattr(conv, "title", "") or "Untitled Conversation"
                mq = (
                    select(Message)
                    .where(
                        Message.conversation_id == conv.id,
                        Message.created_at >= since,
                    )
                    .order_by(Message.created_at.asc())
                )
                msg_res = await db.execute(mq)
                messages = msg_res.scalars().all()
                parts = [f"Conversation: {title}"]
                for msg in messages:
                    role = getattr(msg, "role", "user")
                    role_val = role.value if hasattr(role, "value") else str(role)
                    parts.append(f"[{role_val}] {getattr(msg, 'content', '')}")
                content = "\n".join(parts)
                docs.append(
                    self._normalize(
                        external_id=str(conv.id),
                        title=title,
                        doc_type="conversation",
                        content=content,
                        summary=f"Conversation with {len(messages)} messages",
                        tags=[],
                        attribution={
                            "session_id": getattr(conv, "session_id", ""),
                            "model": getattr(conv, "model", ""),
                        },
                        metadata={
                            "message_count": len(messages),
                            "is_archived": getattr(conv, "is_archived", False),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("ConversationAdapter.fetch_incremental failed: %s", exc)
        return docs


# ─── External adapter ──────────────────────────────────────────────────────


class ExternalAdapter(SourceAdapter):
    source_type = "external"

    async def fetch_documents(
        self, db: AsyncSession, tenant: str, source: Any
    ) -> list[dict]:
        docs: list[dict] = []
        try:
            import aiohttp

            config = getattr(source, "connector_config", None) or {}
            if isinstance(config, dict):
                url = config.get("url", "")
            else:
                url = getattr(config, "url", "")

            if not url:
                logger.warning("ExternalAdapter: no URL configured for source %s", source)
                return docs

            from app.integrations.network_policy import validate_url
            try:
                validate_url(url)
            except Exception as exc:
                logger.warning("ExternalAdapter: blocked URL (%s)", type(exc).__name__)
                return docs
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("ExternalAdapter: HTTP %d from %s", resp.status, url)
                        return docs
                    text = await resp.text()

            source_id = str(getattr(source, "id", "")) if hasattr(source, "id") else ""
            title = getattr(source, "name", "") or "External Source"
            docs.append(
                self._normalize(
                    external_id=source_id or url,
                    title=title,
                    doc_type="external",
                    content=text,
                    summary=f"External content from {url}",
                    tags=["external"],
                    attribution={"url": url},
                    metadata={
                        "content_length": len(text),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
        except Exception as exc:
            logger.warning("ExternalAdapter.fetch_documents failed: %s", exc)
        return docs

    async def fetch_incremental(
        self, db: AsyncSession, tenant: str, source: Any, since: datetime
    ) -> list[dict]:
        return await self.fetch_documents(db, tenant, source)


# ─── Factory ───────────────────────────────────────────────────────────────

_ADAPTER_MAP: dict[str, type[SourceAdapter]] = {
    "code_intelligence": CodeIntelligenceAdapter,
    "data_catalog": DataCatalogAdapter,
    "workflows": WorkflowAdapter,
    "incidents": IncidentAdapter,
    "security": SecurityAdapter,
    "conversations": ConversationAdapter,
    "external": ExternalAdapter,
}


def get_adapter(source_type: str) -> SourceAdapter:
    """Return an adapter instance for *source_type*.

    Raises ``ValueError`` for unknown source types.
    """
    cls = _ADAPTER_MAP.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown source type: {source_type!r}")
    return cls()
