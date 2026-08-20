"""Registry: immutable releases, signing, governance gate."""

import pytest

from app.marketplace.models import PackageStatus, ReleaseStatus, ScanStatus
from app.marketplace.registry import PackageService, sign_release, verify_signature
from app.marketplace.schemas import PackageCreate, PublisherCreate, ReleaseCreate
from app.marketplace.service import MarketplaceService
from app.marketplace.manifest import validate_manifest


async def _seed_publisher(db, org_id):
    from app.marketplace.publishers import PublisherService

    pub = await PublisherService(db).create(PublisherCreate(name="Acme", slug="acme", publisher_type="organization", owner_organization_id=str(org_id)), owner_user_id="u1")
    return pub


async def _seed_package(db, pub, slug="demo-agent"):
    return await PackageService(db).create_package(PackageCreate(
        name="Demo Agent", slug=slug, package_type="agent", publisher_id=pub.id,
        description="demo", license="MIT",
    ), created_by="u1")


async def test_publish_release_activates_package(db, org_ids):
    pub = await _seed_publisher(db, org_ids["publisher"])
    pkg = await _seed_package(db, pub)
    svc = PackageService(db)
    rel = await svc.publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=validate_manifest({
        "name": "Demo Agent", "version": "1.0.0", "type": "agent", "entrypoint": "x:run",
        "permissions": ["model:use"], "models": ["gpt-4o"], "license": "MIT",
    })[0].model_dump()), user_id="u1")
    await db.flush()
    assert rel.release_status == ReleaseStatus.PUBLISHED
    assert rel.checksum_sha256
    assert rel.signature
    refreshed = await svc.get(pkg.id)
    assert refreshed.status == PackageStatus.ACTIVE
    assert refreshed.latest_version == "1.0.0"
    assert refreshed.security_status == ScanStatus.PASSED


async def test_release_immutability(db, org_ids):
    pub = await _seed_publisher(db, org_ids["publisher"])
    pkg = await _seed_package(db, pub)
    svc = PackageService(db)
    good = validate_manifest({"name": "Demo Agent", "version": "1.0.0", "type": "agent", "entrypoint": "x:run", "permissions": ["model:use"], "models": ["gpt-4o"], "license": "MIT"})[0].model_dump()
    await svc.publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=good), user_id="u1")
    with pytest.raises(ValueError):
        await svc.publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=good), user_id="u1")


async def test_security_blocks_publication(db, org_ids):
    pub = await _seed_publisher(db, org_ids["publisher"])
    pkg = await _seed_package(db, pub)
    svc = PackageService(db)
    bad = validate_manifest({"name": "X", "version": "1.0.0", "type": "tool", "entrypoint": "x:run", "environment": {"K": "AKIA1234567890ABCDEF"}, "license": "MIT"})[0].model_dump()
    with pytest.raises(ValueError):
        await svc.publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=bad), user_id="u1")
    refreshed = await svc.get(pkg.id)
    assert refreshed.security_status == ScanStatus.FAILED
    assert refreshed.status != PackageStatus.ACTIVE


def test_signing_roundtrip():
    manifest = {"name": "X", "version": "1.0.0"}
    sig, meta = sign_release(manifest)
    assert verify_signature(manifest, sig)
    assert not verify_signature({**manifest, "version": "2.0.0"}, sig)


async def test_permission_catalog_seeded(db):
    svc = MarketplaceService(db)
    n = await svc.ensure_catalog()
    assert n > 0
    # idempotent
    assert await svc.ensure_catalog() == 0
