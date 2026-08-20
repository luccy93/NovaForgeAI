"""Reviews: creation, duplicate prevention, rating aggregation, moderation."""

from app.marketplace.models import ReviewStatus
from app.marketplace.schemas import PackageCreate, PublisherCreate, ReleaseCreate, ReviewCreate
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


async def test_review_aggregate(db, org_ids):
    pkg = await _pkg(db, org_ids)
    svc = MarketplaceService(db)
    await svc.add_review("demo", str(org_ids["installer"]), str(org_ids["installer"]), ReviewCreate(rating=5, title="Great", body="works"))
    await svc.add_review("demo", "another-user-id", str(org_ids["installer"]), ReviewCreate(rating=3, title="Ok", body="fine"))
    refreshed = await svc.packages.get_by_slug("demo")
    assert refreshed.rating_count == 2
    assert 3.9 <= refreshed.average_rating <= 4.1


async def test_duplicate_review_updates(db, org_ids):
    pkg = await _pkg(db, org_ids)
    svc = MarketplaceService(db)
    r1 = await svc.add_review("demo", "same-user", str(org_ids["installer"]), ReviewCreate(rating=2, title="Meh", body="x"))
    r2 = await svc.add_review("demo", "same-user", str(org_ids["installer"]), ReviewCreate(rating=4, title="Better", body="y"))
    assert r1.id == r2.id
    assert r2.rating == 4


async def test_moderate_review(db, org_ids):
    pkg = await _pkg(db, org_ids)
    svc = MarketplaceService(db)
    r = await svc.add_review("demo", "u", str(org_ids["installer"]), ReviewCreate(rating=1, title="bad", body="spam"))
    moderated = await svc.moderate_review(r.id, ReviewStatus.HIDDEN, moderator_user_id="mod", reason="spam")
    assert moderated.status == ReviewStatus.HIDDEN
