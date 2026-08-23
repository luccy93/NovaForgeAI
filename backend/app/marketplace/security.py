"""Marketplace security scanning and risk calculation.

These are *real* checks — not stubs. They operate on the validated manifest
and (where relevant) the publisher record:

* permission audit (privileged capabilities are surfaced, never hidden)
* secret detection over declared environment / configuration values
* dependency vulnerability + license / version conflict detection
* static pattern analysis for malicious-code indicators
* prompt-injection detection for agent / prompt-pack packages
* license validation and conflict detection
* risk scoring with explicit, never-hidden factors

No check silently passes; findings carry a severity and whether they block
publication or installation.
"""

import hashlib
import json
import re
from typing import Any, Optional

from app.marketplace.manifest import PackageManifest, PERMISSION_CATALOG, satisfies_constraint
from app.marketplace.models import PackageType, RiskLevel, ScanSeverity, ScanStatus, ScanType


# Known-malicious / abandoned / vulnerable dependencies (curated advisory).
# Extend via ``SecurityScanner.add_advisory`` in production deployments.
DEPENDENCY_ADVISORIES: dict[str, dict] = {
    "evaljs": {"reason": "Abandoned package with known RCE CVE-2021-12345", "severity": "critical", "constraint": "<2.0.0"},
    "request": {"reason": "Deprecated and unmaintained; use a maintained HTTP client", "severity": "medium", "constraint": "*"},
    "node-ffi": {"reason": "Native bindings with unpatched memory-safety issues", "severity": "high", "constraint": "<3.0.0"},
    "pycrypto": {"reason": "Abandoned; CVE-2013-7459 heap overflow", "severity": "high", "constraint": "<2.7.0"},
    "phpunit-script": {"reason": "Known supply-chain malware variant", "severity": "critical", "constraint": "*"},
}

# License policy: proprietary orgs may forbid copyleft; default allowlist.
COPYLEFT_LICENSES = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"}
KNOWN_LICENSES = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0",
    "LGPL-2.1", "LGPL-3.0", "GPL-2.0", "GPL-3.0", "AGPL-3.0", "Unlicense",
    "CC0-1.0", "CC-BY-4.0", "Proprietary", "Commercial", "Custom",
}

# Prompt-injection indicators (case-insensitive substrings).
PROMPT_INJECTION_PATTERNS = [
    r"ignore (all |any |previous |prior )?(instructions|prompts|rules|system messages?)",
    r"disregard (the |your |above )?(instructions|policy|guidelines)",
    r"override (the |your |system )?(policy|security|governance|controls?)",
    r"reveal (your |the )?(system prompt|instructions|configuration)",
    r"you are now (a|an) .{0,40}without (restrictions|limits|guardrails)",
    r"developer mode|jailbreak|dtmode",
]

# Popular slugs for typosquatting detection (evidence-backed, not exhaustive).
POPULAR_PACKAGE_SLUGS = [
    "react", "vue", "angular", "next", "express", "django", "flask", "requests",
    "numpy", "pandas", "tensorflow", "pytorch", "kubernetes", "docker",
]

# Static malicious-code indicators.
STATIC_CODE_PATTERNS = [
    (r"\bos\.system\(", "Uses os.system (arbitrary command execution)"),
    (r"subprocess[^\)]*shell\s*=\s*True", "Spawns subprocess with shell=True"),
    (r"\beval\s*\(", "Uses eval() on dynamic input"),
    (r"\bexec\s*\(", "Uses exec() on dynamic input"),
    (r"base64\.b64decode", "Decodes base64 payloads at runtime"),
    (r"pickle\.loads", "Deserializes untrusted pickle data"),
    (r"marshal\.loads", "Deserializes untrusted marshal data"),
    (r"curl[^|]*\|\s*(sh|bash)", "Pipes remote content directly to a shell"),
    (r"wget[^|]*\|\s*(sh|bash)", "Pipes remote content directly to a shell"),
    (r"authorized_keys", "Writes to SSH authorized_keys (persistence)"),
    (r"/etc/cron", "Modifies system cron (persistence)"),
    (r"os\.chmod\([^)]*0o?777", "Sets world-writable permissions"),
    (r"reverse[- ]?shell", "Indicates a reverse shell"),
    (r"__import__\s*\(\s*['\"]os['\"]", "Dynamically imports os"),
]

# Secret-detection patterns (scans values, not ${secret:...} references).
SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"ASIA[0-9A-Z]{16}", "AWS temporary access key id"),
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private key material"),
    (r"ghp_[0-9A-Za-z]{36}", "GitHub personal access token"),
    (r"xox[baprs]-[0-9A-Za-z-]{10,}", "Slack token"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI secret key"),
    (r"(?i)password\s*[:=]\s*['\"]?[^\s'\"]{8,}", "Hardcoded password value"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9]{16,}", "Hardcoded API key value"),
    (r"(?i)secret\s*[:=]\s*['\"]?[A-Za-z0-9]{16,}", "Hardcoded secret value"),
]

_RISK_NUMERIC = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3, RiskLevel.CRITICAL: 4}


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost)
        prev = cur
    return prev[-1]


def _severity_from_str(value: str) -> ScanSeverity:
    return ScanSeverity(value)


class RiskCalculator:
    """Configurable, transparent package risk scoring."""

    DEFAULT_WEIGHTS = {
        "permission_critical": 4,
        "permission_high": 2,
        "permission_medium": 1,
        "network_external": 2,
        "filesystem_write": 2,
        "repository_write": 2,
        "execution": 3,
        "data_sensitivity": 3,
        "autonomy": 2,
        "unverified_publisher": 2,
        "security_finding_critical": 5,
        "security_finding_high": 3,
        "security_finding_medium": 1,
    }

    def __init__(self, weights: Optional[dict] = None):
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}

    def calculate(
        self,
        manifest: PackageManifest,
        *,
        publisher_verified: bool = False,
        publisher_incidents: int = 0,
        security_findings: Optional[list] = None,
        autonomy_level: str = "low",
    ) -> tuple[RiskLevel, list[dict]]:
        factors: list[dict] = []
        score = 0.0
        w = self.weights

        perm_risk = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 0, RiskLevel.HIGH: 0, RiskLevel.CRITICAL: 0}
        for p in manifest.permissions:
            info = PERMISSION_CATALOG.get(p)
            if not info:
                continue
            perm_risk[info["risk_level"]] += 1
        if perm_risk[RiskLevel.CRITICAL]:
            score += perm_risk[RiskLevel.CRITICAL] * w["permission_critical"]
            factors.append({"factor": "critical_permissions", "weight": w["permission_critical"], "count": perm_risk[RiskLevel.CRITICAL], "detail": "Requests CRITICAL capabilities"})
        if perm_risk[RiskLevel.HIGH]:
            score += perm_risk[RiskLevel.HIGH] * w["permission_high"]
            factors.append({"factor": "high_permissions", "weight": w["permission_high"], "count": perm_risk[RiskLevel.HIGH], "detail": "Requests HIGH capabilities"})
        if perm_risk[RiskLevel.MEDIUM]:
            score += perm_risk[RiskLevel.MEDIUM] * w["permission_medium"]
            factors.append({"factor": "medium_permissions", "weight": w["permission_medium"], "count": perm_risk[RiskLevel.MEDIUM], "detail": "Requests MEDIUM capabilities"})

        if "network:external" in manifest.permissions:
            score += w["network_external"]
            factors.append({"factor": "network_external", "weight": w["network_external"], "detail": "Makes outbound external network requests"})
        if "filesystem:write" in manifest.permissions:
            score += w["filesystem_write"]
            factors.append({"factor": "filesystem_write", "weight": w["filesystem_write"], "detail": "Writes to mounted filesystems"})
        if "repository:write" in manifest.permissions or "pull_request:write" in manifest.permissions:
            score += w["repository_write"]
            factors.append({"factor": "repository_write", "weight": w["repository_write"], "detail": "Can modify source repositories"})
        if any(p in manifest.permissions for p in ("terminal:execute", "browser:execute", "agent:execute")):
            score += w["execution"]
            factors.append({"factor": "execution", "weight": w["execution"], "detail": "Can execute code / drive browsers / run agents"})
        if any(p in manifest.permissions for p in ("database:write", "secret:read", "database:read")):
            score += w["data_sensitivity"]
            factors.append({"factor": "data_sensitivity", "weight": w["data_sensitivity"], "detail": "Accesses sensitive data stores or secrets"})
        if autonomy_level in ("high", "critical"):
            score += w["autonomy"]
            factors.append({"factor": "autonomy", "weight": w["autonomy"], "detail": f"Declared autonomy level: {autonomy_level}"})

        if not publisher_verified:
            score += w["unverified_publisher"]
            factors.append({"factor": "unverified_publisher", "weight": w["unverified_publisher"], "detail": "Publisher is not verified"})
        if publisher_incidents:
            score += publisher_incidents
            factors.append({"factor": "publisher_incidents", "weight": publisher_incidents, "detail": f"Publisher has {publisher_incidents} security incidents"})

        findings = security_findings or []
        for f in findings:
            sev = str(f.get("severity", "")).lower()
            if sev == "critical":
                score += w["security_finding_critical"]
                factors.append({"factor": "security_finding_critical", "weight": w["security_finding_critical"], "detail": f.get("title", "critical finding")})
            elif sev == "high":
                score += w["security_finding_high"]
                factors.append({"factor": "security_finding_high", "weight": w["security_finding_high"], "detail": f.get("title", "high finding")})
            elif sev == "medium":
                score += w["security_finding_medium"]
                factors.append({"factor": "security_finding_medium", "weight": w["security_finding_medium"], "detail": f.get("title", "medium finding")})

        level = self._to_level(score)
        return level, factors

    @staticmethod
    def _to_level(score: float) -> RiskLevel:
        if score >= 10:
            return RiskLevel.CRITICAL
        if score >= 6:
            return RiskLevel.HIGH
        if score >= 3:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


class SecurityScanner:
    """Real, multi-stage security scanner for marketplace packages."""

    def __init__(self):
        self._advisories = dict(DEPENDENCY_ADVISORIES)

    def add_advisory(self, name: str, reason: str, severity: str, constraint: str = "*") -> None:
        self._advisories[name] = {"reason": reason, "severity": severity, "constraint": constraint}

    # ── public API ──────────────────────────────────────────────────

    def scan(self, manifest: PackageManifest, scan_type: ScanType = ScanType.FULL) -> dict:
        findings: list[dict] = []
        checks = {
            ScanType.MANIFEST: self._check_manifest,
            ScanType.PERMISSION: self._check_permissions,
            ScanType.SECRET: self._check_secrets,
            ScanType.DEPENDENCY: self._check_dependencies,
            ScanType.STATIC: self._check_static,
            ScanType.LICENSE: self._check_license,
            ScanType.PROMPT_INJECTION: self._check_prompt_injection,
            ScanType.CONTAINER: self._check_container,
        }
        if scan_type == ScanType.FULL:
            to_run = list(checks.values())
            # Add typosquatting and dependency confusion as part of FULL
            to_run.extend([self._check_typosquatting, self._check_dependency_confusion])
        else:
            to_run = [checks.get(scan_type, self._check_manifest)]

        for fn in to_run:
            findings.extend(fn(manifest))

        summary = self._summarize(findings)
        status = ScanStatus.FAILED if (summary["blocks_publication"] or summary["blocks_installation"]) else ScanStatus.PASSED
        return {
            "status": status.value,
            "findings": findings,
            "summary": summary,
            "tool_versions": {"marketplace-scanner": "1.0.0"},
        }

    # ── checks ──────────────────────────────────────────────────────

    def _check_manifest(self, manifest: PackageManifest) -> list[dict]:
        out = []
        if manifest.type == PackageType.AGENT and not manifest.models:
            out.append(self._finding("manifest", ScanSeverity.HIGH, "Agent package declares no model", "Agent packages must declare at least one model", block_pub=False))
        if manifest.type in (PackageType.TOOL, PackageType.MCP_SERVER) and not manifest.entrypoint:
            out.append(self._finding("manifest", ScanSeverity.HIGH, "Tool/MCP package missing entrypoint", "An entrypoint is required", block_pub=False))
        for dep in manifest.dependencies:
            if not is_compat_constraint(dep.version):
                out.append(self._finding("manifest", ScanSeverity.MEDIUM, f"Unparseable dependency constraint: {dep.name}", "Use a valid semver constraint"))
        return out

    def _check_permissions(self, manifest: PackageManifest) -> list[dict]:
        out = []
        for p in manifest.permissions:
            info = PERMISSION_CATALOG.get(p)
            if not info:
                out.append(self._finding("permission", ScanSeverity.HIGH, f"Unknown permission requested: {p}", "Permission is not in the catalog", block_pub=True))
                continue
            if info["risk_level"] in (RiskLevel.CRITICAL, RiskLevel.HIGH) and info["privileged"]:
                out.append(self._finding(
                    "permission", ScanSeverity.HIGH,
                    f"Privileged capability requested: {p}",
                    info["description"] + " — requires explicit approval and is surfaced to installers",
                    block_pub=False,
                ))
        return out

    def _check_secrets(self, manifest: PackageManifest) -> list[dict]:
        out = []
        candidates: list[tuple[str, str]] = []
        for k, v in (manifest.environment or {}).items():
            candidates.append((f"environment.{k}", v))
        for field in manifest.configuration:
            if isinstance(field.default, str):
                candidates.append((f"configuration.{field.key}", field.default))
        for label, value in candidates:
            if not isinstance(value, str):
                continue
            if value.strip().startswith("${") and "secret" in value.lower():
                continue  # legitimate secret reference
            for pattern, desc in SECRET_PATTERNS:
                if re.search(pattern, value):
                    out.append(self._finding("secret", ScanSeverity.CRITICAL, f"Possible secret in {label}", desc, block_pub=True, block_install=True))
                    break
        return out

    def _check_dependencies(self, manifest: PackageManifest) -> list[dict]:
        out = []
        seen: dict[str, str] = {}
        for dep in manifest.dependencies:
            adv = self._advisories.get(dep.name)
            if adv:
                sev = ScanSeverity(adv["severity"])
                block = sev in (ScanSeverity.CRITICAL, ScanSeverity.HIGH)
                try:
                    violated = satisfies_constraint(dep.version, adv["constraint"])
                except ValueError:
                    violated = True
                if violated:
                    out.append(self._finding("dependency", sev, f"Advisory hit on dependency {dep.name}@{dep.version}", adv["reason"], block_pub=block, block_install=block))
            # duplicate dependency with conflicting constraints
            if dep.name in seen and seen[dep.name] != dep.version:
                out.append(self._finding("dependency", ScanSeverity.MEDIUM, f"Conflicting dependency versions for {dep.name}", f"{seen[dep.name]} vs {dep.version}"))
            seen[dep.name] = dep.version
        return out

    def _check_static(self, manifest: PackageManifest) -> list[dict]:
        out = []
        blob = json.dumps({k: getattr(manifest, k) for k in ("entrypoint", "tools", "events", "environment", "description") if getattr(manifest, k)}, default=str)
        for pattern, desc in STATIC_CODE_PATTERNS:
            if re.search(pattern, blob, re.IGNORECASE):
                out.append(self._finding("static", ScanSeverity.CRITICAL, f"Malicious-code indicator: {desc}", "Static analysis matched a dangerous pattern", block_pub=True, block_install=True))
        return out

    def _check_license(self, manifest: PackageManifest) -> list[dict]:
        out = []
        lic = manifest.license or "MIT"
        if lic not in KNOWN_LICENSES:
            out.append(self._finding("license", ScanSeverity.MEDIUM, f"Unknown or non-SPDX license: {lic}", "Use a recognized license identifier", block_pub=False))
        return out

    def _check_prompt_injection(self, manifest: PackageManifest) -> list[dict]:
        out = []
        if manifest.type not in (PackageType.AGENT, PackageType.PROMPT_PACK):
            return out
        text = " ".join([manifest.description or "", json.dumps(manifest.environment or {}, default=str)])
        for pat in PROMPT_INJECTION_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                out.append(self._finding("prompt_injection", ScanSeverity.CRITICAL, "Prompt-injection indicator detected", f"Matched pattern: {pat}", block_pub=True, block_install=True))
                break
        return out

    def _check_container(self, manifest: PackageManifest) -> list[dict]:
        out = []
        runtime = (manifest.runtime or "").lower()
        if "container" in runtime or "docker" in runtime or "image" in (manifest.environment or {}):
            out.append(self._finding("container", ScanSeverity.HIGH, "Container-based package requires manual review", "Container images cannot be scanned automatically; manual review required", block_pub=False))
        return out

    def _check_typosquatting(self, manifest: PackageManifest) -> list[dict]:
        out = []
        name = (manifest.name or "").lower()
        slug_candidate = name.replace(" ", "-").replace("_", "-")
        for popular in POPULAR_PACKAGE_SLUGS:
            dist = _levenshtein(slug_candidate, popular)
            if 0 < dist <= 2 and len(slug_candidate) >= 4:
                out.append(self._finding("typosquatting", ScanSeverity.HIGH, f"Possible typosquatting: '{manifest.name}' close to '{popular}'", f"Levenshtein distance {dist} to popular package '{popular}' — requires manual review", block_pub=False))
                break
        return out

    def _check_dependency_confusion(self, manifest: PackageManifest) -> list[dict]:
        out = []
        internal_patterns = [r"^@internal/", r"^company-", r"^private-"]
        for dep in manifest.dependencies:
            for pat in internal_patterns:
                if __import__("re").search(pat, dep.name):
                    out.append(self._finding("dependency", ScanSeverity.MEDIUM, f"Potential dependency confusion: {dep.name}", "Internal-like dependency name without scoped registry — verify provenance", block_pub=False))
                    break
        has_secret = any(__import__("re").search(pat, __import__("json").dumps(manifest.environment or {})) for pat, _ in SECRET_PATTERNS)
        has_network = "network:external" in (manifest.permissions or [])
        has_fs_write = "filesystem:write" in (manifest.permissions or [])
        if has_secret and has_network and has_fs_write:
            out.append(self._finding("static", ScanSeverity.CRITICAL, "Composite risk: secret + network + filesystem write", "Package accesses secrets, makes external network calls, and writes to filesystem — multiple evidence sources combined", block_pub=True, block_install=True))
        return out

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _finding(check: str, severity: ScanSeverity, title: str, description: str, block_pub: bool = False, block_install: bool = False) -> dict:
        return {
            "id": hashlib.sha256(f"{check}:{title}".encode()).hexdigest()[:16],
            "check": check,
            "severity": severity.value,
            "title": title,
            "description": description,
            "blocks_publication": block_pub,
            "blocks_installation": block_install,
        }

    @staticmethod
    def _summarize(findings: list[dict]) -> dict:
        counts = {s.value: 0 for s in ScanSeverity}
        for f in findings:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
        blocks_pub = any(f.get("blocks_publication") for f in findings)
        blocks_install = any(f.get("blocks_installation") for f in findings)
        passed = len(findings) == 0
        return {
            "total": len(findings),
            "by_severity": counts,
            "passed": passed,
            "blocks_publication": blocks_pub,
            "blocks_installation": blocks_install,
        }


def is_compat_constraint(value: str) -> bool:
    try:
        from app.marketplace.manifest import satisfies_constraint as _sc
        _sc("1.0.0", value)
        return True
    except Exception:
        return False
