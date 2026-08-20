"""Manifest validation, semantic versioning and permission catalog."""

import pytest

from app.marketplace.manifest import (
    PackageManifest,
    PERMISSION_CATALOG,
    is_valid_version,
    satisfies_constraint,
    validate_manifest,
)


def test_semver_parsing():
    from app.marketplace.manifest import SemVer

    v = SemVer.parse("1.2.3")
    assert (v.major, v.minor, v.patch) == (1, 2, 3)
    assert not v.is_prerelease
    assert SemVer.parse("2.0.0-rc.1").is_prerelease
    assert is_valid_version("10.20.30")
    assert not is_valid_version("1.2")
    assert not is_valid_version("v1.0.0")


def test_semver_ordering():
    from app.marketplace.manifest import SemVer
    assert SemVer.parse("1.0.0") < SemVer.parse("1.0.1")
    assert SemVer.parse("1.0.0") < SemVer.parse("1.1.0")
    assert SemVer.parse("2.0.0") > SemVer.parse("1.9.9")
    assert SemVer.parse("1.0.0-rc.1") < SemVer.parse("1.0.0")


def test_constraint_matching():
    assert satisfies_constraint("1.4.0", "^1.2.3")
    assert not satisfies_constraint("2.0.0", "^1.2.3")
    assert satisfies_constraint("1.5.0", "~1.2.0")
    assert satisfies_constraint("1.2.5", ">=1.0.0")
    assert satisfies_constraint("1.0.0", "*")
    assert not satisfies_constraint("0.9.0", ">=1.0.0")


def test_manifest_valid():
    m, errors = validate_manifest({
        "name": "X", "version": "1.0.0", "type": "tool",
        "entrypoint": "x:run", "permissions": ["model:use"],
    })
    assert m is not None and errors == []


def test_manifest_invalid_version():
    m, errors = validate_manifest({"name": "X", "version": "1.0", "type": "tool", "entrypoint": "x"})
    assert m is None and any("version" in e for e in errors)


def test_manifest_unknown_permission_rejected():
    m, errors = validate_manifest({
        "name": "X", "version": "1.0.0", "type": "tool", "entrypoint": "x",
        "permissions": ["does:not:exist"],
    })
    assert m is None and any("unknown permission" in e for e in errors)


def test_forbidden_permission_rejected():
    m, errors = validate_manifest({
        "name": "X", "version": "1.0.0", "type": "tool", "entrypoint": "x",
        "permissions": ["governance:bypass"],
    })
    assert m is None and any("not permitted" in e for e in errors)


def test_agent_requires_model():
    m, errors = validate_manifest({"name": "X", "version": "1.0.0", "type": "agent", "entrypoint": "x"})
    assert m is None and any("model" in e for e in errors)


def test_permission_catalog_present():
    assert "terminal:execute" in PERMISSION_CATALOG
    assert PERMISSION_CATALOG["terminal:execute"]["privileged"] is True
