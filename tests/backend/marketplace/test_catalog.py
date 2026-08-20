"""Catalog discovery respects status, access scope and tenant visibility."""

from app.marketplace.catalog import CatalogService
from app.marketplace.models import AccessScope, PackageStatus, PackageType
from app.marketplace.schemas import PackageCreate, PublisherCreate, ReleaseCreate, SearchFilters
from app.marketplace.publishers import PublisherService
from app.marketplace.registry import PackageService
from app.marketplace.manifest import validate_manifest


async def _publish(db, org_ids, slug, scope="public", org=None):
    pub_svc = PublisherService(db)
    pub = await pub_svc.get_by_slug("acme")
    if not pub:
        pub = await pub_svc.create(PublisherCreate(name="Acme", slug="acme", publisher_type="organization", owner_organization_id=str(org_ids["publisher"])), owner_user_id="u1")
    pkg = await PackageService(db).create_package(PackageCreate(
        name=slug, slug=slug, package_type="agent", publisher_id=pub.id,
        access_scope=AccessScope(scope), organization_id=str(org), category="Agents",
    ), created_by="u1")
    m = validate_manifest({"name": slug, "version": "1.0.0", "type": "agent", "entrypoint": "x:run", "permissions": ["model:use"], "models": ["gpt-4o"], "license": "MIT", "tags": ["agents"]})[0].model_dump()
    await PackageService(db).publish_release(pkg.id, ReleaseCreate(version="1.0.0", manifest=m), user_id="u1")
    await db.flush()
    return pkg


async def test_public_visible_private_hidden(db, org_ids):
    await _publish(db, org_ids, "pub-pkg", scope="public")
    await _publish(db, org_ids, "priv-pkg", scope="private", org=org_ids["publisher"])
    svc = CatalogService(db)
    items, total = await svc.search(SearchFilters(), organization_id=str(org_ids["installer"]))
    slugs = {i.slug for i in items}
    assert "pub-pkg" in slugs
    assert "priv-pkg" not in slugs


async def test_include_private_shows_owned(db, org_ids):
    await _publish(db, org_ids, "priv-pkg", scope="private", org=org_ids["publisher"])
    svc = CatalogService(db)
    items, _ = await svc.search(SearchFilters(include_private=True), organization_id=str(org_ids["publisher"]))
    assert any(i.slug == "priv-pkg" for i in items)


async def test_search_query_and_category(db, org_ids):
    await _publish(db, org_ids, "alpha-agent", scope="public")
    svc = CatalogService(db)
    by_q, _ = await svc.search(SearchFilters(query="alpha"), organization_id=str(org_ids["installer"]))
    assert any(i.slug == "alpha-agent" for i in by_q)
    by_cat, _ = await svc.search(SearchFilters(category="Agents"), organization_id=str(org_ids["installer"]))
    assert any(i.slug == "alpha-agent" for i in by_cat)


async def test_draft_not_discoverable(db, org_ids):
    pub = await PublisherService(db).create(PublisherCreate(name="Acme", slug="acme2", publisher_type="organization", owner_organization_id=str(org_ids["publisher"])), owner_user_id="u1")
    await PackageService(db).create_package(PackageCreate(name="draft", slug="draft-pkg", package_type="agent", publisher_id=pub.id), created_by="u1")
    await db.flush()
    svc = CatalogService(db)
    items, _ = await svc.search(SearchFilters(), organization_id=str(org_ids["installer"]))
    assert not any(i.slug == "draft-pkg" for i in items)
