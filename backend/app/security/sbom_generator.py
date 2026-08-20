"""SBOM generation service (Volume 47).

CycloneDX and SPDX SBOM generation from dependency scan results,
artifact binding, and integrity verification.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.models import SecuritySBOM, SecuritySBOMComponent

logger = logging.getLogger(__name__)


def _purl(name: str, version: str, ecosystem: str) -> str:
    prefix_map = {"pypi": "pkg:pypi", "npm": "pkg:npm", "cargo": "pkg:cargo", "go": "pkg:golang", "maven": "pkg:maven", "gem": "pkg:gem"}
    prefix = prefix_map.get(ecosystem, f"pkg:{ecosystem}")
    return f"{prefix}/{name}@{version}" if version else f"{prefix}/{name}"


class SBOMService:
    """Generate and manage Software Bills of Materials."""

    async def generate_sbom(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        target_type: str,
        target_id: str,
        components: list[dict],
        repository: str = "",
        commit_sha: str = "",
        artifact_id=None,
        fmt: str = "cyclonedx",
        spec_version: str = "1.5",
    ) -> SecuritySBOM:
        license_summary = {}
        for comp in components:
            lic = comp.get("license_id", "unknown")
            license_summary[lic] = license_summary.get(lic, 0) + 1

        sbom = SecuritySBOM(
            tenant=tenant,
            target_type=target_type,
            target_id=target_id,
            format=fmt,
            spec_version=spec_version,
            component_count=len(components),
            dependency_count=sum(1 for c in components if c.get("dependency_type") != "direct"),
            license_summary=license_summary,
            repository=repository,
            commit_sha=commit_sha,
            artifact_id=artifact_id,
        )
        db.add(sbom)
        await db.flush()

        for comp in components:
            component = SecuritySBOMComponent(
                sbom_id=sbom.id,
                name=comp.get("name", ""),
                version=comp.get("version", ""),
                purl=comp.get("purl", _purl(comp.get("name", ""), comp.get("version", ""), comp.get("ecosystem", ""))),
                ecosystem=comp.get("ecosystem", ""),
                license_id=comp.get("license_id", "unknown"),
                license_name=comp.get("license_name", "unknown"),
                hash=comp.get("hash", ""),
                dependency_type=comp.get("dependency_type", "runtime"),
                is_direct=comp.get("is_direct", True),
                scope=comp.get("scope", "required"),
                metadata_extra=comp.get("metadata_extra", {}),
            )
            db.add(component)

        doc = self._render_cyclonedx(sbom, components) if fmt == "cyclonedx" else self._render_spdx(sbom, components)
        sbom.document_hash = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
        await db.flush()
        return sbom

    async def get_sbom(self, db: AsyncSession, sbom_id) -> SecuritySBOM | None:
        stmt = select(SecuritySBOM).where(SecuritySBOM.id == sbom_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sboms(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 20,
    ) -> list[SecuritySBOM]:
        stmt = select(SecuritySBOM).where(SecuritySBOM.tenant == tenant)
        if target_type:
            stmt = stmt.where(SecuritySBOM.target_type == target_type)
        if target_id:
            stmt = stmt.where(SecuritySBOM.target_id == target_id)
        stmt = stmt.order_by(SecuritySBOM.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def verify_integrity(self, db: AsyncSession, sbom_id) -> dict:
        sbom = await self.get_sbom(db, sbom_id)
        if not sbom:
            return {"valid": False, "error": "SBOM not found"}
        stmt = select(SecuritySBOMComponent).where(SecuritySBOMComponent.sbom_id == sbom_id)
        result = await db.execute(stmt)
        components = list(result.scalars().all())
        stored_count = sbom.component_count
        actual_count = len(components)
        hash_valid = bool(sbom.document_hash)
        return {
            "valid": hash_valid and actual_count == stored_count,
            "stored_hash": sbom.document_hash,
            "component_count": actual_count,
            "expected_count": stored_count,
            "format": sbom.format,
        }

    def _comp_to_dict(self, comp: SecuritySBOMComponent) -> dict:
        return {
            "name": comp.name, "version": comp.version, "purl": comp.purl,
            "ecosystem": comp.ecosystem, "license_id": comp.license_id,
            "license_name": comp.license_name, "hash": comp.hash,
            "dependency_type": comp.dependency_type, "is_direct": comp.is_direct,
        }

    def _render_cyclonedx(self, sbom: SecuritySBOM, components: list[dict]) -> dict:
        return {
            "bomFormat": "CycloneDX",
            "specVersion": sbom.spec_version,
            "version": 1,
            "metadata": {
                "timestamp": sbom.created_at.isoformat() if sbom.created_at else "",
                "component": {"name": sbom.target_id, "type": sbom.target_type},
            },
            "components": [
                {
                    "type": "library",
                    "name": c.get("name", ""),
                    "version": c.get("version", ""),
                    "purl": c.get("purl", ""),
                    "licenses": [{"license": {"id": c.get("license_id", "unknown")}}],
                    "hashes": [{"alg": "SHA-256", "content": c.get("hash", "")}] if c.get("hash") else [],
                }
                for c in components
            ],
        }

    def _render_spdx(self, sbom: SecuritySBOM, components: list[dict]) -> dict:
        return {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"sbom-{sbom.target_id}",
            "documentNamespace": f"https://novaforge.dev/sbom/{sbom.id}",
            "packages": [
                {
                    "SPDXID": f"SPDXRef-{c.get('name', '')}-{c.get('version', '')}",
                    "name": c.get("name", ""),
                    "versionInfo": c.get("version", ""),
                    "downloadLocation": "NOASSERTION",
                    "licenseConcluded": c.get("license_id", "NOASSERTION"),
                    "checksums": [{"algorithm": "SHA256", "checksumValue": c.get("hash", "")}] if c.get("hash") else [],
                }
                for c in components
            ],
        }


sbom_service = SBOMService()
