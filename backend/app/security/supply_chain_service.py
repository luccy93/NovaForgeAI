"""Supply-chain security service (Volume 47).

Provenance graph (source->commit->build->artifact->deployment),
SLSA level verification, dependency provenance, artifact signing,
and package reputation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.models import SecurityProvenance, SecurityFingerprint
from app.security.findings_service import findings_service

logger = logging.getLogger(__name__)

SLSA_LEVELS = {
    1: {"requirements": ["build_platform"], "description": "Build process is fully scripted/automated"},
    2: {"requirements": ["build_platform", "hosted_build"], "description": "Build runs on hosted platform, generates provenance"},
    3: {"requirements": ["build_platform", "hosted_build", "hardened_build", "non_falsifiable_provenance"], "description": "Hardened build platform, non-falsifiable provenance"},
    4: {"requirements": ["build_platform", "hosted_build", "hardened_build", "non_falsifiable_provenance", "hermetic_build", "reproducible"], "description": "Hermetic, reproducible builds with two-party review"},
}

TRUSTED_BUILDERS = {"github-actions", "gitlab-ci", "google-cloud-build", "circleci", "buildkite", "tekton"}


class SupplyChainService:
    """Provenance graph, SLSA verification, artifact signing, reputation."""

    async def record_provenance(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        chain_id: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relationship: str,
        commit_sha: str = "",
        build_id: str = "",
        artifact_hash: str = "",
        signed: bool = False,
        signature_valid: bool = False,
        builder: str = "",
        pipeline_id: str = "",
        deployment_id: str = "",
        metadata_extra: Optional[dict] = None,
    ) -> SecurityProvenance:
        rec = SecurityProvenance(
            tenant=tenant,
            chain_id=chain_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relationship=relationship,
            commit_sha=commit_sha,
            build_id=build_id,
            artifact_hash=artifact_hash,
            signed=signed,
            signature_valid=signature_valid,
            builder=builder,
            pipeline_id=pipeline_id,
            deployment_id=deployment_id,
            metadata_extra=metadata_extra or {},
        )
        db.add(rec)
        await db.flush()
        return rec

    async def get_provenance_chain(self, db: AsyncSession, tenant: str, chain_id: str) -> list[SecurityProvenance]:
        stmt = (
            select(SecurityProvenance)
            .where(SecurityProvenance.tenant == tenant, SecurityProvenance.chain_id == chain_id)
            .order_by(SecurityProvenance.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def verify_slsa(self, db: AsyncSession, tenant: str, chain_id: str) -> dict:
        chain = await self.get_provenance_chain(db, tenant, chain_id)
        if not chain:
            return {"level": 0, "verified": False, "error": "No provenance chain found"}

        has_build_platform = any(r.builder for r in chain)
        has_hosted = any(r.builder in TRUSTED_BUILDERS for r in chain)
        has_signed = all(r.signed and r.signature_valid for r in chain if r.target_type == "artifact")
        has_hardened = has_hosted and has_signed

        level = 0
        if has_build_platform:
            level = 1
        if has_hosted:
            level = 2
        if has_hardened:
            level = 3

        return {
            "level": level,
            "verified": level >= 2,
            "has_build_platform": has_build_platform,
            "has_hosted_build": has_hosted,
            "has_signed_artifacts": has_signed,
            "has_hardened_build": has_hardened,
            "chain_length": len(chain),
        }

    async def verify_artifact_signing(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        artifact_type: str,
        artifact_id: str,
        signed: bool,
        signature_valid: bool,
        builder: str = "",
        scan_id=None,
    ) -> list:
        created = []
        if not signed:
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="supply_chain", finding_type="supply_chain",
                severity="high", rule="unsigned_artifact",
                message=f"Artifact {artifact_type}:{artifact_id} is not signed",
                file_path=artifact_id, confidence="high", scan_id=scan_id,
                cwe_id="CWE-345",
            )
            created.append(finding)
        elif not signature_valid:
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="supply_chain", finding_type="supply_chain",
                severity="critical", rule="invalid_signature",
                message=f"Artifact {artifact_type}:{artifact_id} has invalid signature",
                file_path=artifact_id, confidence="high", scan_id=scan_id,
                cwe_id="CWE-345",
            )
            created.append(finding)
        return created

    async def check_package_reputation(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        packages: list[dict],
        scan_id=None,
    ) -> list:
        created = []
        for pkg in packages:
            name = pkg.get("name", "")
            downloads = pkg.get("downloads", 0)
            maintainer_count = pkg.get("maintainer_count", 0)
            last_publish_days = pkg.get("last_publish_days", 0)
            has_scripts = pkg.get("has_install_scripts", False)

            if downloads < 100 and maintainer_count <= 1:
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="supply_chain", finding_type="supply_chain",
                    severity="medium", rule="low_download_package",
                    message=f"Package {name} has very few downloads ({downloads}) with single maintainer",
                    dependency_name=name, confidence="medium", scan_id=scan_id,
                    cwe_id="CWE-1395",
                )
                created.append(finding)

            if last_publish_days > 365 * 3:
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="supply_chain", finding_type="supply_chain",
                    severity="low", rule="stale_package",
                    message=f"Package {name} not updated in {last_publish_days} days",
                    dependency_name=name, confidence="low", scan_id=scan_id,
                )
                created.append(finding)

            if has_scripts and downloads < 1000:
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="supply_chain", finding_type="supply_chain",
                    severity="high", rule="suspicious_install_scripts",
                    message=f"Package {name} has install scripts but very few downloads",
                    dependency_name=name, confidence="medium", scan_id=scan_id,
                    cwe_id="CWE-749",
                )
                created.append(finding)

        return created

    async def get_dependency_provenance(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        dependency_name: str,
        ecosystem: str = "pypi",
    ) -> dict:
        stmt = (
            select(SecurityFingerprint)
            .where(
                SecurityFingerprint.dependency == dependency_name,
                SecurityFingerprint.active == True,
            )
            .order_by(SecurityFingerprint.last_seen.desc())
            .limit(10)
        )
        result = await db.execute(stmt)
        fingerprints = list(result.scalars().all())
        return {
            "dependency": dependency_name,
            "ecosystem": ecosystem,
            "known_findings": len(fingerprints),
            "first_seen": fingerprints[-1].first_seen.isoformat() if fingerprints else None,
            "last_seen": fingerprints[0].last_seen.isoformat() if fingerprints else None,
        }


supply_chain_service = SupplyChainService()
