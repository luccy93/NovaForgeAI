"""Volume 55 lifecycle integration tests — DB-backed, focused."""

import pytest

from app.marketplace.schemas import PackageCreate, PublisherCreate, ReleaseCreate
from app.marketplace.publishers import PublisherService
from app.marketplace.registry import PackageService
from app.marketplace.installation import InstallationService
from app.marketplace.manifest import validate_manifest
from app.marketplace.models import AccessScope


async def _make_pub_pkg(db, org_ids, slug="lifecycle-pkg", license="MIT", pkg_type="tool"):
    pub_svc = PublisherService(db)
    pub = await pub_svc.create(PublisherCreate(name="PubCo", slug=f"pubco-{slug}", publisher_type="organization", owner_organization_id=str(org_ids["publisher"])), owner_user_id="u1")
    pkg_svc = PackageService(db)
    pkg = await pkg_svc.create_package(PackageCreate(name=slug, slug=slug, package_type=pkg_type, publisher_id=pub.id, license=license), created_by="u1")
    manifest, errs = validate_manifest({"name": slug, "version": "1.0.0", "type": pkg_type, "entrypoint": "main.py", "license": license})
    assert errs == [], errs
    rel = await pkg_svc.publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=manifest.model_dump()), user_id="u1")
    await db.flush()
    # Activate package for installation (default is DRAFT -> need ACTIVE)
    from app.marketplace.models import PackageStatus, ApprovalStatus, ScanStatus
    pkg.status = PackageStatus.ACTIVE
    pkg.governance_status = ApprovalStatus.APPROVED
    pkg.security_status = ScanStatus.PASSED
    pkg.latest_version = "1.0.0"
    await db.flush()
    return pub, pkg


async def test_install_success(db, org_ids):
    pub, pkg = await _make_pub_pkg(db, org_ids, slug="install-ok", license="MIT")
    svc = InstallationService(db)
    from app.marketplace.schemas import InstallationCreate
    from app.marketplace.models import EnvironmentType
    inst = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="install-ok", environment=EnvironmentType.DEVELOPMENT), user_id="u1")
    assert inst.package_id == pkg.id
    assert inst.current_version == "1.0.0"


async def test_install_private_blocked_for_other_org(db, org_ids):
    pub, pkg = await _make_pub_pkg(db, org_ids, slug="priv-block", license="MIT")
    # Make private to publisher org
    pkg.access_scope = AccessScope.PRIVATE
    pkg.organization_id = str(org_ids["publisher"])
    await db.flush()
    svc = InstallationService(db)
    from app.marketplace.schemas import InstallationCreate
    from app.marketplace.models import EnvironmentType
    with pytest.raises(Exception, match="private to another organization"):
        await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="priv-block", environment=EnvironmentType.DEVELOPMENT), user_id="u1")


async def test_license_policy_blocks_denied(db, org_ids):
    pub, pkg = await _make_pub_pkg(db, org_ids, slug="lic-block", license="GPL-3.0")
    from app.marketplace.license_policy import LicensePolicyService
    lic_svc = LicensePolicyService(db)
    await lic_svc.create_policy(str(org_ids["installer"]), name="deny-gpl", denied_licenses=["GPL-3.0"])
    await db.flush()
    # License check is inside InstallationService.install — should block
    svc = InstallationService(db)
    from app.marketplace.schemas import InstallationCreate
    from app.marketplace.models import EnvironmentType
    with pytest.raises(Exception, match="denied"):
        await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="lic-block", environment=EnvironmentType.DEVELOPMENT), user_id="u1")


async def test_emergency_block_blocks_install(db, org_ids):
    pub, pkg = await _make_pub_pkg(db, org_ids, slug="block-pkg", license="MIT")
    from app.marketplace.emergency_block import EmergencyBlockService
    blk_svc = EmergencyBlockService(db)
    await blk_svc.create_block(target_type="package", target_id=str(pkg.id), reason="malware", scope="global", created_by="admin")
    await db.flush()
    svc = InstallationService(db)
    from app.marketplace.schemas import InstallationCreate
    from app.marketplace.models import EnvironmentType
    with pytest.raises(Exception, match="emergency-blocked"):
        await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="block-pkg", environment=EnvironmentType.DEVELOPMENT), user_id="u1")


async def test_update_and_rollback(db, org_ids):
    pub, pkg = await _make_pub_pkg(db, org_ids, slug="update-pkg", license="MIT")
    # Publish second version
    pkg_svc = PackageService(db)
    manifest2, _ = validate_manifest({"name": "update-pkg", "version": "1.1.0", "type": "tool", "entrypoint": "main.py", "license": "MIT"})
    await pkg_svc.publish_release(pkg.id, ReleaseCreate(version="1.1.0", manifest=manifest2.model_dump()), user_id="u1")
    pkg.latest_version = "1.1.0"
    await db.flush()
    svc = InstallationService(db)
    from app.marketplace.schemas import InstallationCreate
    from app.marketplace.models import EnvironmentType
    inst = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="update-pkg", environment=EnvironmentType.DEVELOPMENT, version="1.0.0"), user_id="u1")
    assert inst.current_version == "1.0.0"
    updated = await svc.update(str(inst.id), version="1.1.0", user_id="u1")
    assert updated.current_version == "1.1.0"
    rolled = await svc.rollback(str(inst.id), version="1.0.0", user_id="u1")
    assert rolled.current_version == "1.0.0"


async def test_dependency_lock_prevents_upgrade(db, org_ids):
    pub, pkg = await _make_pub_pkg(db, org_ids, slug="lock-pkg", license="MIT")
    pkg_svc = PackageService(db)
    manifest2, _ = validate_manifest({"name": "lock-pkg", "version": "1.1.0", "type": "tool", "entrypoint": "main.py", "license": "MIT"})
    await pkg_svc.publish_release(pkg.id, ReleaseCreate(version="1.1.0", manifest=manifest2.model_dump()), user_id="u1")
    pkg.latest_version = "1.1.0"
    await db.flush()
    svc = InstallationService(db)
    from app.marketplace.schemas import InstallationCreate
    from app.marketplace.models import EnvironmentType
    inst = await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="lock-pkg", environment=EnvironmentType.DEVELOPMENT, version="1.0.0", dependency_lock={"locked_version": "1.0.0"}), user_id="u1")
    assert inst.dependency_lock == {"locked_version": "1.0.0"}
    with pytest.raises(Exception, match="dependency locked"):
        await svc.install(str(org_ids["installer"]), InstallationCreate(package_slug="lock-pkg", environment=EnvironmentType.DEVELOPMENT, version="1.1.0", dependency_lock={"locked_version": "1.0.0"}), user_id="u1")
