"""Marketplace manifest validation, semantic versioning and permission catalog.

This module is intentionally dependency-free (only stdlib + pydantic) so it can
be imported by the API, SDK, CLI and workers without pulling in the ORM.
"""

import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.marketplace.models import PackageType, RiskLevel


# ─── Permission catalog (transparency) ──────────────────────────────────
# Every capability a package may request is declared here. Privileged
# permissions are never hidden from the installing user.

PERMISSION_CATALOG: dict[str, dict] = {
    "repository:read": {"category": "repository", "description": "Read repositories and source code", "risk_level": RiskLevel.LOW, "requires_approval": False, "privileged": False},
    "repository:write": {"category": "repository", "description": "Write to repositories (push, edit files)", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "pull_request:write": {"category": "repository", "description": "Open and merge pull requests", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "branch:write": {"category": "repository", "description": "Create and delete branches", "risk_level": RiskLevel.MEDIUM, "requires_approval": True, "privileged": False},
    "terminal:execute": {"category": "execution", "description": "Execute shell commands on the host or sandbox", "risk_level": RiskLevel.CRITICAL, "requires_approval": True, "privileged": True},
    "browser:execute": {"category": "execution", "description": "Drive a browser and navigate arbitrary URLs", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "database:read": {"category": "data", "description": "Read from databases", "risk_level": RiskLevel.MEDIUM, "requires_approval": True, "privileged": True},
    "database:write": {"category": "data", "description": "Write to databases", "risk_level": RiskLevel.CRITICAL, "requires_approval": True, "privileged": True},
    "network:external": {"category": "network", "description": "Make outbound network requests to external hosts", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "network:internal": {"category": "network", "description": "Make outbound network requests to internal services", "risk_level": RiskLevel.MEDIUM, "requires_approval": True, "privileged": False},
    "model:use": {"category": "ai", "description": "Invoke AI models through the gateway", "risk_level": RiskLevel.LOW, "requires_approval": False, "privileged": False},
    "model:fine_tune": {"category": "ai", "description": "Fine-tune or train models", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "event:publish": {"category": "events", "description": "Publish events to the event bus", "risk_level": RiskLevel.LOW, "requires_approval": False, "privileged": False},
    "event:subscribe": {"category": "events", "description": "Subscribe to platform events", "risk_level": RiskLevel.LOW, "requires_approval": False, "privileged": False},
    "secret:read": {"category": "secrets", "description": "Read organization secrets by reference", "risk_level": RiskLevel.CRITICAL, "requires_approval": True, "privileged": True},
    "secret:write": {"category": "secrets", "description": "Write organization secrets", "risk_level": RiskLevel.CRITICAL, "requires_approval": True, "privileged": True},
    "user:read": {"category": "identity", "description": "Read user profiles", "risk_level": RiskLevel.MEDIUM, "requires_approval": True, "privileged": False},
    "organization:read": {"category": "identity", "description": "Read organization configuration", "risk_level": RiskLevel.LOW, "requires_approval": False, "privileged": False},
    "organization:admin": {"category": "identity", "description": "Administrative control of the organization", "risk_level": RiskLevel.CRITICAL, "requires_approval": True, "privileged": True},
    "filesystem:read": {"category": "filesystem", "description": "Read files from mounted storage", "risk_level": RiskLevel.MEDIUM, "requires_approval": False, "privileged": False},
    "filesystem:write": {"category": "filesystem", "description": "Write files to mounted storage", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "agent:execute": {"category": "execution", "description": "Execute autonomous agents", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "workflow:execute": {"category": "execution", "description": "Execute workflows", "risk_level": RiskLevel.MEDIUM, "requires_approval": True, "privileged": False},
    "mcp:register": {"category": "mcp", "description": "Register an MCP server and expose tools", "risk_level": RiskLevel.HIGH, "requires_approval": True, "privileged": True},
    "billing:read": {"category": "billing", "description": "Read billing and usage data", "risk_level": RiskLevel.MEDIUM, "requires_approval": True, "privileged": False},
    "governance:bypass": {"category": "governance", "description": "Bypass platform governance policies", "risk_level": RiskLevel.CRITICAL, "requires_approval": True, "privileged": True},
}

# Capabilities that are never permitted for marketplace packages.
FORBIDDEN_PERMISSIONS = {"governance:bypass"}


# ─── Semantic versioning ───────────────────────────────────────────────

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class SemVer:
    """Immutable semantic version with comparison and constraint matching."""

    __slots__ = ("major", "minor", "patch", "prerelease", "build", "raw")

    def __init__(self, major: int, minor: int, patch: int, prerelease: str = "", build: str = "", raw: str = ""):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease or ""
        self.build = build or ""
        self.raw = raw or f"{major}.{minor}.{patch}" + (f"-{prerelease}" if prerelease else "") + (f"+{build}" if build else "")

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        m = _SEMVER_RE.match(value.strip())
        if not m:
            raise ValueError(f"Invalid semantic version: {value!r}")
        return cls(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            m.group("pre") or "",
            m.group("build") or "",
            raw=value.strip(),
        )

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def _key(self):
        # Pre-releases sort lower than the associated release.
        # All segments are strings to avoid str/int comparison issues in Python 3.
        if self.prerelease:
            pre = tuple(p for p in self.prerelease.split("."))
        else:
            pre = ("~",)
        return (self.major, self.minor, self.patch, pre)

    def __eq__(self, other):
        return isinstance(other, SemVer) and self._key() == other._key()

    def __lt__(self, other):
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._key() < other._key()

    def __le__(self, other):
        return self < other or self == other

    def __gt__(self, other):
        return (not self <= other) if isinstance(other, SemVer) else NotImplemented

    def __ge__(self, other):
        return self > other or self == other

    def __hash__(self):
        return hash(self._key())

    def __repr__(self):
        return f"SemVer({self.raw})"


def parse_version(value: str) -> SemVer:
    return SemVer.parse(value)


def is_valid_version(value: str) -> bool:
    try:
        SemVer.parse(value)
        return True
    except ValueError:
        return False


def compare_versions(a: str, b: str) -> int:
    av, bv = SemVer.parse(a), SemVer.parse(b)
    if av < bv:
        return -1
    if av > bv:
        return 1
    return 0


def _satisfies_caret(version: SemVer, base: SemVer) -> bool:
    if version.major != base.major:
        return False
    if version.major == 0:
        if version.minor != base.minor:
            return False
        return version >= base
    return version >= base


def _satisfies_tilde(version: SemVer, base: SemVer) -> bool:
    if version.major != base.major:
        return False
    return version >= base


def _satisfies_operator(version: SemVer, op: str, base: SemVer) -> bool:
    if op == ">=":
        return version >= base
    if op == ">":
        return version > base
    if op == "<=":
        return version <= base
    if op == "<":
        return version < base
    if op == "==":
        return version == base
    if op == "!=":
        return version != base
    return False


def satisfies_constraint(version: str, constraint: str) -> bool:
    """Return True if ``version`` satisfies the semver ``constraint``.

    Supports: ``*``, exact ``1.2.3``, comparators (``>=``, ``<=``, ``>``,
    ``<``, ``==``, ``!=``), caret ``^1.2.3`` and tilde ``~1.2.3``. Multiple
    constraints may be comma-separated (AND).
    """
    version = SemVer.parse(version)
    constraint = constraint.strip()
    if constraint in ("*", "x", "X", ""):
        return True
    for part in constraint.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\^|~|>=|<=|>|<|==|!=)?\s*([0-9A-Za-z.\-+]+)$", part)
        if not m:
            raise ValueError(f"Invalid constraint: {part!r}")
        op, ver = m.group(1) or "", m.group(2)
        base = SemVer.parse(ver)
        if op == "^":
            if not _satisfies_caret(version, base):
                return False
        elif op == "~":
            if not _satisfies_tilde(version, base):
                return False
        else:
            if not _satisfies_operator(version, op, base):
                return False
    return True


def next_version(current: Optional[str], bump: str = "patch") -> str:
    """Compute the next version given a bump type (major/minor/patch)."""
    if not current:
        return "0.1.0" if bump != "major" else "1.0.0"
    v = SemVer.parse(current)
    if bump == "major":
        return f"{v.major + 1}.0.0"
    if bump == "minor":
        return f"{v.major}.{v.minor + 1}.0"
    return f"{v.major}.{v.minor}.{v.patch + 1}"


# ─── Manifest schema ────────────────────────────────────────────────────


class ManifestConfigField(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    type: str = Field("string", pattern="^(string|integer|number|boolean|secret|enum|json)$")
    label: str = Field("", max_length=160)
    description: str = Field("", max_length=400)
    required: bool = False
    default: Any = None
    allowed_values: Optional[list] = None
    secret: bool = False


class ManifestDependency(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    version: str = Field("*", max_length=64)
    type: str = Field("runtime", pattern="^(runtime|tool|model|integration|plugin|workflow)$")


class ManifestResourceLimits(BaseModel):
    cpu: Optional[str] = Field(None, max_length=20)
    memory: Optional[str] = Field(None, max_length=20)
    disk: Optional[str] = Field(None, max_length=20)
    network: Optional[str] = Field(None, max_length=20)
    processes: Optional[int] = Field(None, ge=0, le=1024)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=86400)


class ManifestCompatibility(BaseModel):
    novaforge_version: Optional[str] = Field(None, max_length=64)
    runtime: Optional[str] = Field(None, max_length=64)
    runtime_version: Optional[str] = Field(None, max_length=64)
    sdk_version: Optional[str] = Field(None, max_length=64)
    os: Optional[list[str]] = None
    arch: Optional[list[str]] = None
    ide_version: Optional[str] = Field(None, max_length=64)
    api_version: Optional[str] = Field(None, max_length=64)
    sdk_version_constraint: Optional[str] = Field(None, max_length=64)
    dependency_versions: Optional[dict] = None
    environment: Optional[list[str]] = None


class ManifestHealthCheck(BaseModel):
    endpoint: Optional[str] = Field(None, max_length=512)
    interval_seconds: Optional[int] = Field(None, ge=5, le=86400)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=300)
    healthy_threshold: Optional[int] = Field(None, ge=1, le=10)
    unhealthy_threshold: Optional[int] = Field(None, ge=1, le=10)


class ManifestNetworkPolicy(BaseModel):
    outbound: Optional[str] = Field("deny", pattern="^(allow|deny|restricted)$")
    allowed_hosts: list[str] = Field(default_factory=list)
    requires_approval: bool = False


class ManifestStoragePolicy(BaseModel):
    persistent: bool = False
    size_limit: Optional[str] = Field(None, max_length=20)
    mount_path: Optional[str] = Field(None, max_length=255)


class PackageManifest(BaseModel):
    """Strict, machine-readable package manifest."""

    name: str = Field(..., min_length=1, max_length=160)
    version: str = Field(..., max_length=64)
    type: PackageType
    entrypoint: Optional[str] = Field(None, max_length=255)
    runtime: Optional[str] = Field(None, max_length=64)
    permissions: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    configuration: list[ManifestConfigField] = Field(default_factory=list)
    dependencies: list[ManifestDependency] = Field(default_factory=list)
    environment: dict = Field(default_factory=dict)
    resources: ManifestResourceLimits = Field(default_factory=ManifestResourceLimits)
    compatibility: ManifestCompatibility = Field(default_factory=ManifestCompatibility)
    security_requirements: dict = Field(default_factory=dict)
    network: ManifestNetworkPolicy = Field(default_factory=ManifestNetworkPolicy)
    storage: ManifestStoragePolicy = Field(default_factory=ManifestStoragePolicy)
    secrets: list[str] = Field(default_factory=list)
    healthcheck: Optional[ManifestHealthCheck] = None
    release_channel: str = Field("stable", pattern="^(stable|beta|canary|edge)$")
    description: str = Field("", max_length=4000)
    homepage: Optional[str] = Field(None, max_length=512)
    repository: Optional[str] = Field(None, max_length=512)
    license: str = Field("MIT", max_length=64)
    tags: list[str] = Field(default_factory=list)
    category: Optional[str] = Field(None, max_length=64)
    icon: Optional[str] = Field(None, max_length=512)

    @field_validator("version")
    @classmethod
    def _version_valid(cls, v):
        if not is_valid_version(v):
            raise ValueError(f"version must be semantic (x.y.z): {v!r}")
        return v

    @field_validator("permissions")
    @classmethod
    def _permissions_valid(cls, v):
        for p in v:
            if p not in PERMISSION_CATALOG:
                raise ValueError(f"unknown permission: {p!r}")
            if p in FORBIDDEN_PERMISSIONS:
                raise ValueError(f"permission not permitted for marketplace packages: {p!r}")
        return v

    @model_validator(mode="after")
    def _cross_check(self):
        if self.type in (PackageType.TOOL, PackageType.MCP_SERVER) and not self.entrypoint:
            raise ValueError(f"package type {self.type.value} requires an entrypoint")
        if self.type == PackageType.AGENT and not self.models:
            raise ValueError("agent packages must declare at least one model")
        return self


def validate_manifest(data: dict) -> tuple[PackageManifest, list[str]]:
    """Validate a raw manifest dict. Returns (manifest, errors)."""
    try:
        manifest = PackageManifest.model_validate(data)
        return manifest, []
    except Exception as exc:  # pydantic ValidationError
        errors = []
        for err in getattr(exc, "errors", lambda: [])():
            loc = ".".join(str(x) for x in err.get("loc", []))
            errors.append(f"{loc}: {err.get('msg')}")
        if not errors:
            errors.append(str(exc))
        return None, errors
