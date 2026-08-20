"""Reports: submission, resolution, and moderation action."""

from app.marketplace.models import ReportStatus, ReportType
from app.marketplace.schemas import PackageCreate, PublisherCreate, ReleaseCreate, ReportCreate
from app.marketplace.publishers import PublisherService
from app.marketplace.registry import PackageService
from app.marketplace.service import MarketplaceService
from app.marketplace.manifest import validate_manifest


async def _pkg(db, org_ids):
    pub = await PublisherService(db).create(PublisherCreate(name="Acme", slug="acme", publisher_type="organization", owner_organization_id=str(org_ids["publisher"])), owner_user_id="u1")
    pkg = await PackageService(db).create_package(PackageCreate(name="Demo", slug="demo", package_type="agent", publisher_id=pub.id), created_by="u1")
    m = validate_manifest({"name": "Demo", "version": "1.0.0", "type": "agent", "entrypoint": "x:run", "permissions": ["model:use"], "models": ["gpt-4o"], "license": "MIT"})[0].model_dump()
    await PackageService(db).publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=m), user_id="u1")
    await db.flush()
    return pkg


async def test_report_create_and_list(db, org_ids):
    pkg = await _pkg(db, org_ids)
    svc = MarketplaceService(db)
    rep = await svc.submit_report(str(org_ids["installer"]), ReportCreate(report_type=ReportType.SECURITY, subject_type="package", subject_id=pkg.id, reason="unsafe", description="x"), reporter_user_id="u1")
    assert rep.status == ReportStatus.OPEN
    items = await svc.list_reports(status=ReportStatus.OPEN)
    assert any(i.id == rep.id for i in items)


async def test_report_resolve(db, org_ids):
    pkg = await _pkg(db, org_ids)
    svc = MarketplaceService(db)
    rep = await svc.submit_report(str(org_ids["installer"]), ReportCreate(report_type=ReportType.ABUSE, subject_type="package", subject_id=pkg.id, reason="abuse"), reporter_user_id="u1")
    resolved = await svc.resolve_report(rep.id, moderator_user_id="mod", resolution="no action")
    assert resolved.status == ReportStatus.RESOLVED


async def test_report_action_suspends_package(db, org_ids):
    pkg = await _pkg(db, org_ids)
    svc = MarketplaceService(db)
    rep = await svc.submit_report(str(org_ids["installer"]), ReportCreate(report_type=ReportType.SECURITY, subject_type="package", subject_id=pkg.id, reason="critical vuln"), reporter_user_id="u1")
    acted = await svc.act_on_report(rep.id, action="suspend", moderator_user_id="mod", notes="suspended pending fix")
    assert acted.status == ReportStatus.RESOLVED
    refreshed = await svc.packages.get_by_slug("demo")
    assert refreshed.status.value == "suspended"
