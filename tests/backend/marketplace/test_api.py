"""API integration via TestClient (real routes, mocked auth + DB)."""

CLEAN_MANIFEST = {
    "name": "Demo Agent", "version": "1.0.0", "type": "agent",
    "entrypoint": "x:run", "permissions": ["model:use"], "models": ["gpt-4o"],
    "license": "MIT",
}


def _publish(client):
    pub = client.post("/marketplace/publishers", json={
        "name": "Acme", "slug": "acme", "publisher_type": "organization",
    }).json()
    pkg = client.post("/marketplace/packages", json={
        "name": "Demo Agent", "slug": "demo-agent", "package_type": "agent",
        "publisher_id": pub["id"], "description": "demo", "license": "MIT",
    }).json()
    rel = client.post("/marketplace/packages/demo-agent/releases", json={
        "version": "1.0.0", "manifest": CLEAN_MANIFEST,
    })
    assert rel.status_code == 200, rel.text
    return pub, pkg


def test_publish_and_get_package(client):
    _publish(client)
    resp = client.get("/marketplace/packages/demo-agent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["latest_version"] == "1.0.0"


def test_search_discovers(client):
    _publish(client)
    resp = client.get("/marketplace/search?query=demo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(i["slug"] == "demo-agent" for i in data["items"])


def test_install_via_api(client):
    _publish(client)
    resp = client.post("/marketplace/install", json={"package_slug": "demo-agent"})
    assert resp.status_code == 200, resp.text
    inst = resp.json()
    assert inst["status"] == "active"
    org = inst["organization_id"]
    listing = client.get(f"/marketplace/installations?organization_id={org}")
    assert listing.status_code == 200
    assert any(i["id"] == inst["id"] for i in listing.json())


def test_config_validate_endpoint(client):
    resp = client.post("/marketplace/configuration/validate", json={
        "package_type": "agent",
        "configuration": [
            {"key": "max_steps", "type": "integer", "required": False},
            {"key": "api_token", "type": "secret", "required": True},
        ],
        "provided": {"max_steps": 5, "api_token": "${secret:my_token}"},
    })
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_categories_endpoint(client):
    resp = client.get("/marketplace/categories")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert "Agents" in resp.json()


def test_unpublishable_release_with_secret(client):
    _publish(client)
    bad = dict(CLEAN_MANIFEST, environment={"K": "AKIA1234567890ABCDEF"})
    resp = client.post("/marketplace/packages/demo-agent/releases", json={"version": "2.0.0", "manifest": bad})
    assert resp.status_code == 400
