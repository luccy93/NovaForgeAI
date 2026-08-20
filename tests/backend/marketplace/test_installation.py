"""Installation lifecycle: idempotency, entitlement, approval, rollback."""

import pytest

from app.marketplace.installation import CompatibilityError, EntitlementError
from app.marketplace.models import AccessScope, ApprovalStatus, InstallationStatus, PackageType
from app.marketplace.schemas import InstallationCreate, PackageCreate, PublisherCreate, ReleaseCreate
from app.marketplace.service import MarketplaceService
from app.marketplace.manifest import validate_manifest


async def _publish(db, org_ids, perms, access_scope="public", org=None):
    from app.marketplace.publishers import PublisherService
    from app.marketplace.registry import PackageService

    pub = await PublisherService(db).create(PublisherCreate(name="Acme", slug="acme", publisher_type="organization", owner_organization_id=str(org_ids["publisher"])), owner_user_id="u1")
    pkg = await PackageService(db).create_package(PackageCreate(
        name="Demo", slug="demo", package_type="agent", publisher_id=pub.id,
        access_scope=AccessScope(access_scope), organization_id=str(org),
    ), created_by="u1")
    m = validate_manifest({"name": "Demo", "version": "1.0.0", "type": "agent", "entrypoint": "x:run", "permissions": perms, "models": ["gpt-4o"], "license": "MIT"})[0].model_dump()
    await PackageService(db).publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=m), user_id="u1")
    await db.flush()
    return pkg


async def test_install_free_package_active(db, org_ids):
    pkg = await _publish(db, org_ids, ["model:use"])
    svc = MarketplaceService(db)
    inst = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="demo"), user_id="u1")
    assert inst.status == InstallationStatus.ACTIVE
    assert inst.approval_status == ApprovalStatus.APPROVED


async def test_install_idempotent(db, org_ids):
    pkg = await _publish(db, org_ids, ["model:use"])
    svc = MarketplaceService(db)
    a = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="demo"), user_id="u1")
    b = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="demo"), user_id="u1")
    assert a.id == b.id
    rows = await svc.installations.list_for_org(str(org_ids["installer"]))
    assert len(rows) == 1


async def test_private_package_blocks_other_org(db, org_ids):
    pkg = await _publish(db, org_ids, ["model:use"], access_scope="private", org=org_ids["publisher"])
    svc = MarketplaceService(db)
    with pytest.raises(EntitlementError):
        await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="demo"), user_id="u1")


async def test_high_risk_requires_approval(db, org_ids):
    pkg = await _publish(db, org_ids, ["terminal:execute"])
    svc = MarketplaceService(db)
    inst = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="demo"), user_id="u1")
    assert inst.approval_status == ApprovalStatus.PENDING
    assert inst.status == InstallationStatus.INSTALLED
    approved = await svc.approve_installation(inst.id, True, admin_user_id="admin")
    assert approved.status == InstallationStatus.ACTIVE
    assert approved.approval_status == ApprovalStatus.APPROVED


async def test_rollback_and_update(db, org_ids):
    from app.marketplace.registry import PackageService

    pkg = await _publish(db, org_ids, ["model:use"])
    svc = MarketplaceService(db)
    ps = PackageService(db)
    # publish a second version
    m2 = validate_manifest({"name": "Demo", "version": "1.1.0", "type": "agent", "entrypoint": "x:run", "permissions": ["model:use"], "models": ["gpt-4o"], "license": "MIT"})[0].model_dump()
    await ps.publish_release(pkg.id, ReleaseCreate(version="1.1.0", manifest=m2), user_id="u1")
    inst = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="demo", version="1.0.0"), user_id="u1")
    updated = await svc.update_installation(inst.id, "1.1.0", user_id="u1")
    assert updated.current_version == "1.1.0"
    assert updated.previous_version == "1.0.0"
    rolled = await svc.rollback_installation(inst.id, "1.0.0", user_id="u1")
    assert rolled.current_version == "1.0.0"
    assert rolled.previous_version == "1.1.0"


async def test_uninstall_idempotent(db, org_ids):
    pkg = await _publish(db, org_ids, ["model:use"])
    svc = MarketplaceService(db)
    inst = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="demo"), user_id="u1")
    await svc.uninstall(inst.id, user_id="u1")
    again = await svc.uninstall(inst.id, user_id="u1")
    assert again.status == InstallationStatus.UNINSTALLED
