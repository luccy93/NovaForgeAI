"""Package registry: immutable releases, checksums, signing, governance gate."""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.marketplace.manifest import (
    PackageManifest,
    PERMISSION_CATALOG,
    RiskLevel,
    validate_manifest,
)
from app.marketplace.models import (
    ApprovalStatus,
    DependencyType,
    MarketplaceDependency,
    MarketplacePackage,
    MarketplacePermission,
    MarketplacePublisher,
    MarketplaceRelease,
    MarketplaceSecurityScan,
    PackageStatus,
    ReleaseStatus,
    ScanStatus,
    ScanType,
)
from app.marketplace.security import RiskCalculator, SecurityScanner


SIGNING_SECRET = os.environ.get("MARKETPLACE_SIGNING_SECRET", "novaforge-marketplace-dev-signing")


def _canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, default=str).encode()


def sign_release(manifest: dict, secret: str = SIGNING_SECRET) -> tuple[str, dict]:
    payload = _canonical(manifest)
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    meta = {
        "algorithm": "hmac-sha256",
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_hash": hashlib.sha256(payload).hexdigest(),
    }
    return sig, meta


def verify_signature(manifest: dict, signature: str, secret: str = SIGNING_SECRET) -> bool:
    expected, _ = sign_release(manifest, secret)
    return hmac.compare_digest(expected, signature)


def release_checksum(manifest: dict, artifacts: list) -> str:
    h = hashlib.sha256()
    h.update(_canonical(manifest))
    for a in sorted(artifacts, key=lambda x: x.get("name", "")):
        h.update((a.get("name", "") + (a.get("checksum_sha256") or "")).encode())
    return h.hexdigest()


async def ensure_permission_catalog(db: AsyncSession) -> int:
    """Idempotently seed the permission catalog from the manifest definitions."""
    count = 0
    for key, info in PERMISSION_CATALOG.items():
        existing = await db.execute(select(MarketplacePermission).where(MarketplacePermission.key == key))
        if existing.scalar_one_or_none():
            continue
        db.add(MarketplacePermission(
            key=key,
            category=info["category"],
            description=info["description"],
            risk_level=info["risk_level"],
            requires_approval=info["requires_approval"],
            privileged=info["privileged"],
        ))
        count += 1
    await db.flush()
    return count


class DependencyResolver:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record(self, package_id, release_id, manifest: PackageManifest) -> list[MarketplaceDependency]:
        created = []
        for dep in manifest.dependencies:
            row = MarketplaceDependency(
                package_id=package_id,
                release_id=release_id,
                depends_on_slug=dep.name,
                constraint=dep.version,
                dependency_type=DependencyType(dep.type),
            )
            self.db.add(row)
            created.append(row)
        await self.db.flush()
        return created

    async def detect_conflicts(self, package_id) -> list[dict]:
        """Detect unresolved / conflicting dependency versions for a package."""
        res = await self.db.execute(
            select(MarketplaceDependency).where(MarketplaceDependency.package_id == package_id)
        )
        deps = res.scalars().all()
        by_name: dict[str, list[str]] = {}
        for d in deps:
            by_name.setdefault(d.depends_on_slug, []).append(d.constraint)
        conflicts = []
        for name, constraints in by_name.items():
            if len(constraints) > 1 and len(set(constraints)) > 1:
                conflicts.append({"name": name, "constraints": constraints, "detail": "Conflicting dependency constraints"})
        return conflicts


class PackageService:
    def __init__(self, db: AsyncSession, scanner: Optional[SecurityScanner] = None, risk_calc: Optional[RiskCalculator] = None):
        self.db = db
        self.scanner = scanner or SecurityScanner()
        self.risk_calc = risk_calc or RiskCalculator()

    async def create_package(self, data, created_by: Optional[str] = None) -> MarketplacePackage:
        pkg = MarketplacePackage(
            slug=data.slug,
            name=data.name,
            publisher_id=data.publisher_id,
            package_type=data.package_type,
            description=data.description,
            latest_version=None,
            status=PackageStatus.DRAFT,
            governance_status=ApprovalStatus.APPROVED,
            security_status=ScanStatus.PENDING,
            pricing_type=data.pricing_type,
            price=data.price,
            currency=data.currency,
            billing_period=data.billing_period,
            license=data.license,
            documentation=data.documentation,
            access_scope=data.access_scope,
            organization_id=data.organization_id,
            region=data.region,
            category=data.category,
            tags=data.tags,
            icon_url=data.icon_url,
            homepage=data.homepage,
            repository_url=data.repository_url,
            created_by=created_by,
        )
        self.db.add(pkg)
        await self.db.flush()
        pkg = (
            await self.db.execute(
                select(MarketplacePackage)
                .options(selectinload(MarketplacePackage.publisher))
                .where(MarketplacePackage.id == pkg.id)
            )
        ).scalar_one()
        return pkg

    async def get(self, package_id) -> Optional[MarketplacePackage]:
        return await self.db.get(
            MarketplacePackage, package_id, options=selectinload(MarketplacePackage.publisher)
        )

    async def get_by_slug(self, slug: str) -> Optional[MarketplacePackage]:
        res = await self.db.execute(
            select(MarketplacePackage)
            .options(selectinload(MarketplacePackage.publisher))
            .where(MarketplacePackage.slug == slug)
        )
        return res.scalar_one_or_none()

    async def list(self, package_type=None, status=None, publisher_id=None, limit=50, offset=0):
        from sqlalchemy import func

        stmt = select(MarketplacePackage).options(selectinload(MarketplacePackage.publisher))
        if package_type:
            stmt = stmt.where(MarketplacePackage.package_type == package_type)
        if status:
            stmt = stmt.where(MarketplacePackage.status == status)
        if publisher_id:
            stmt = stmt.where(MarketplacePackage.publisher_id == publisher_id)
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (await self.db.execute(stmt.order_by(MarketplacePackage.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return rows, total

    async def publish_release(self, package_id, data, user_id: Optional[str] = None) -> MarketplaceRelease:
        pkg = await self.get(package_id)
        if not pkg:
            raise ValueError("package not found")

        manifest, errors = validate_manifest(data.manifest)
        if errors:
            raise ValueError("invalid manifest: " + "; ".join(errors))

        # Immutable releases — never overwrite an existing version.
        existing = await self.db.execute(
            select(MarketplaceRelease).where(
                MarketplaceRelease.package_id == package_id, MarketplaceRelease.version == data.version
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"release {data.version} already exists and is immutable")

        scan_result = self.scanner.scan(manifest, ScanType.FULL)
        scan = MarketplaceSecurityScan(
            package_id=package_id,
            scan_type=ScanType.FULL,
            status=ScanStatus.PASSED if scan_result["status"] == "passed" else ScanStatus.FAILED,
            findings=scan_result["findings"],
            summary=scan_result["summary"],
            tool_versions=scan_result["tool_versions"],
            triggered_by=user_id,
        )
        self.db.add(scan)
        await self.db.flush()

        sig, sig_meta = sign_release(data.manifest)
        checksum = release_checksum(data.manifest, [a.model_dump() for a in data.artifacts])

        release = MarketplaceRelease(
            package_id=package_id,
            version=data.version,
            release_status=ReleaseStatus.DRAFT,
            checksum_sha256=checksum,
            signature=sig,
            signature_metadata=sig_meta,
            build_metadata=data.build_metadata,
            manifest=data.manifest,
            artifacts=[a.model_dump() for a in data.artifacts],
            changelog=data.changelog,
            is_yanked=data.yank,
            published_at=None,
            published_by=user_id,
            security_scan_id=scan.id,
        )
        self.db.add(release)
        await self.db.flush()

        if scan_result["summary"]["blocks_publication"]:
            pkg.security_status = ScanStatus.FAILED
            await self.db.flush()
            raise ValueError("security scan blocks publication: " + "; ".join(f["title"] for f in scan_result["findings"] if f.get("blocks_publication")))

        # Governance gate: privileged / high-risk packages need review.
        autonomy = str(data.manifest.get("security_requirements", {}).get("autonomy", "low"))
        publisher = await self.db.get(MarketplacePublisher, pkg.publisher_id)
        verified = publisher is not None and publisher.verification_status.value.endswith("verified")
        risk_level, _ = self.risk_calc.calculate(
            manifest, publisher_verified=verified, security_findings=scan_result["findings"], autonomy_level=autonomy
        )
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) or any(
            PERMISSION_CATALOG.get(p, {}).get("privileged") for p in manifest.permissions
        ):
            pkg.governance_status = ApprovalStatus.PENDING

        release.release_status = ReleaseStatus.PUBLISHED
        release.published_at = datetime.now(timezone.utc)
        pkg.latest_version = data.version
        pkg.status = PackageStatus.ACTIVE
        pkg.security_status = ScanStatus.PASSED
        await self.db.flush()

        await DependencyResolver(self.db).record(package_id, release.id, manifest)
        return release

    async def yank_release(self, package_id, version: str, reason: str = "") -> None:
        res = await self.db.execute(
            select(MarketplaceRelease).where(
                MarketplaceRelease.package_id == package_id, MarketplaceRelease.version == version
            )
        )
        rel = res.scalar_one_or_none()
        if not rel:
            raise ValueError("release not found")
        rel.is_yanked = True
        rel.release_status = ReleaseStatus.YANKED
        rel.changelog = (rel.changelog or "") + f"\nYANKED: {reason}"
        await self.db.flush()

    async def deprecate_package(self, package_id) -> None:
        pkg = await self.get(package_id)
        if not pkg:
            raise ValueError("package not found")
        pkg.status = PackageStatus.DEPRECATED
        await self.db.flush()
