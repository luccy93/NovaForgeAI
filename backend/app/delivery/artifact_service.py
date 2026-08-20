"""Artifact lifecycle: create, verify, sign, promote, retain."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryArtifact

logger = logging.getLogger(__name__)


class ArtifactService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, name: str, artifact_type: str, hash_val: str, repository: str = "",
                     commit_sha: str = "", version: str = "0.0.0", size_bytes: int = 0,
                     storage_url: str = "", content_type: str = "application/octet-stream",
                     provenance: Optional[dict] = None, sbom: Optional[dict] = None,
                     tenant: str = "", retention_days: int = 90,
                     pipeline_run_id: Optional[UUID] = None) -> DeliveryArtifact:
        artifact = DeliveryArtifact(
            name=name, artifact_type=artifact_type, hash=hash_val,
            repository=repository, commit_sha=commit_sha, version=version,
            size_bytes=size_bytes, storage_url=storage_url, content_type=content_type,
            provenance=provenance or {}, sbom=sbom, tenant=tenant,
            retention_days=retention_days, pipeline_run_id=pipeline_run_id,
        )
        self.db.add(artifact)
        await self.db.flush()
        return artifact

    async def get(self, artifact_id: UUID) -> Optional[DeliveryArtifact]:
        return await self.db.get(DeliveryArtifact, artifact_id)

    async def get_by_hash(self, hash_val: str) -> Optional[DeliveryArtifact]:
        res = await self.db.execute(
            select(DeliveryArtifact).where(DeliveryArtifact.hash == hash_val).limit(1)
        )
        return res.scalar_one_or_none()

    async def list_artifacts(self, tenant: Optional[str] = None, repository: Optional[str] = None,
                              artifact_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> tuple[list, int]:
        stmt = select(DeliveryArtifact)
        count_stmt = select(func.count()).select_from(DeliveryArtifact)
        if tenant:
            stmt = stmt.where(DeliveryArtifact.tenant == tenant)
            count_stmt = count_stmt.where(DeliveryArtifact.tenant == tenant)
        if repository:
            stmt = stmt.where(DeliveryArtifact.repository == repository)
            count_stmt = count_stmt.where(DeliveryArtifact.repository == repository)
        if artifact_type:
            stmt = stmt.where(DeliveryArtifact.artifact_type == artifact_type)
            count_stmt = count_stmt.where(DeliveryArtifact.artifact_type == artifact_type)
        total = await self.db.scalar(count_stmt)
        rows = (await self.db.execute(stmt.order_by(DeliveryArtifact.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return list(rows), total or 0

    async def sign(self, artifact_id: UUID, signature: str) -> DeliveryArtifact:
        artifact = await self.get(artifact_id)
        if not artifact:
            raise ValueError(f"artifact {artifact_id} not found")
        artifact.signed = True
        artifact.signature = signature
        await self.db.flush()
        return artifact

    async def verify_integrity(self, artifact_id: UUID, expected_hash: str) -> dict:
        artifact = await self.get(artifact_id)
        if not artifact:
            return {"valid": False, "error": "not found"}
        if artifact.hash != expected_hash:
            return {"valid": False, "error": "hash mismatch", "expected": expected_hash, "actual": artifact.hash}
        if not artifact.immutable:
            return {"valid": False, "error": "artifact is not immutable"}
        return {"valid": True, "hash": artifact.hash, "immutable": artifact.immutable}

    async def set_legal_hold(self, artifact_id: UUID, hold: bool = True) -> DeliveryArtifact:
        artifact = await self.get(artifact_id)
        if not artifact:
            raise ValueError(f"artifact {artifact_id} not found")
        artifact.legal_hold = hold
        await self.db.flush()
        return artifact

    async def count_retained(self, tenant: str) -> int:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        res = await self.db.execute(
            select(func.count()).select_from(DeliveryArtifact).where(
                DeliveryArtifact.tenant == tenant,
                DeliveryArtifact.legal_hold == False,
                DeliveryArtifact.created_at < cutoff,
            )
        )
        return res.scalar() or 0
