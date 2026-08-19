"""
Configuration Analysis Engine.

Parses package manifests, Dockerfiles, Kubernetes YAML, CI/CD pipelines,
environment templates, and application configuration files.
Provides metadata-only ingestion without exposing actual secrets.
"""

import ast
import json
import logging
import re
import tomllib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CodeFile, CodeIndex

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret detection patterns (names only, not values)
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:api[_-]?key|apikey)\s*[=:]\s*\S+", re.I),
    re.compile(r"(?:secret|secret[_-]?key)\s*[=:]\s*\S+", re.I),
    re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*\S+", re.I),
    re.compile(r"(?:token|access[_-]?token)\s*[=:]\s*\S+", re.I),
    re.compile(r"(?:private[_-]?key)\s*[=:]\s*\S+", re.I),
    re.compile(r"(?:aws[_-]?(?:access[_-]?key|secret))\s*[=:]\s*\S+", re.I),
    re.compile(r"(?:DATABASE_URL|REDIS_URL|MONGO_URI)\s*[=:]\s*\S+", re.I),
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", re.I),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"xox[bpsa]-[A-Za-z0-9-]+"),
]


# ---------------------------------------------------------------------------
# Framework signatures
# ---------------------------------------------------------------------------
_FRAMEWORK_SIGNATURES: dict[str, dict[str, Any]] = {
    "django": {
        "indicators": ["django", "djangorestframework"],
        "config_files": ["settings.py", "wsgi.py", "asgi.py"],
        "language": "python",
    },
    "fastapi": {
        "indicators": ["fastapi"],
        "config_files": ["main.py"],
        "language": "python",
    },
    "flask": {
        "indicators": ["flask"],
        "config_files": ["app.py"],
        "language": "python",
    },
    "express": {
        "indicators": ["express"],
        "config_files": ["app.js", "server.js"],
        "language": "javascript",
    },
    "nextjs": {
        "indicators": ["next"],
        "config_files": ["next.config.js", "next.config.mjs"],
        "language": "javascript",
    },
    "react": {
        "indicators": ["react", "react-dom"],
        "config_files": ["App.tsx", "App.jsx"],
        "language": "typescript",
    },
    "vue": {
        "indicators": ["vue"],
        "config_files": ["vue.config.js", "nuxt.config.js"],
        "language": "typescript",
    },
    "angular": {
        "indicators": ["@angular/core"],
        "config_files": ["angular.json"],
        "language": "typescript",
    },
    "spring": {
        "indicators": ["spring-boot", "spring-web"],
        "config_files": ["application.properties", "application.yml"],
        "language": "java",
    },
    "rails": {
        "indicators": ["rails"],
        "config_files": ["Gemfile"],
        "language": "ruby",
    },
    "laravel": {
        "indicators": ["laravel/framework"],
        "config_files": ["artisan"],
        "language": "php",
    },
    "sinatra": {
        "indicators": ["sinatra"],
        "config_files": ["config.ru"],
        "language": "ruby",
    },
    "go-echo": {
        "indicators": ["github.com/labstack/echo"],
        "config_files": ["go.mod"],
        "language": "go",
    },
    "go-gin": {
        "indicators": ["github.com/gin-gonic/gin"],
        "config_files": ["go.mod"],
        "language": "go",
    },
    "actix": {
        "indicators": ["actix-web"],
        "config_files": ["Cargo.toml"],
        "language": "rust",
    },
    "rocket": {
        "indicators": ["rocket"],
        "config_files": ["Cargo.toml"],
        "language": "rust",
    },
    "blazor": {
        "indicators": ["Microsoft.AspNetCore.Components.WebAssembly"],
        "config_files": ["Program.cs", "*.csproj"],
        "language": "csharp",
    },
    "svelte": {
        "indicators": ["svelte"],
        "config_files": ["svelte.config.js"],
        "language": "javascript",
    },
    "nuxt": {
        "indicators": ["nuxt"],
        "config_files": ["nuxt.config.js", "nuxt.config.ts"],
        "language": "typescript",
    },
    "remix": {
        "indicators": ["@remix-run"],
        "config_files": ["remix.config.js"],
        "language": "typescript",
    },
}


# ---------------------------------------------------------------------------
# Dataclasses for structured results
# ---------------------------------------------------------------------------
@dataclass
class ManifestInfo:
    path: str
    manifest_type: str
    name: str | None = None
    version: str | None = None
    description: str | None = None
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)
    engines: dict[str, str] = field(default_factory=dict)
    license: str | None = None
    authors: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DockerInfo:
    path: str
    base_image: str | None = None
    stages: list[str] = field(default_factory=list)
    exposed_ports: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)
    run_commands: list[str] = field(default_factory=list)
    has_healthcheck: bool = False
    user: str | None = None
    secrets_detected: list[str] = field(default_factory=list)


@dataclass
class KubernetesInfo:
    path: str
    kind: str | None = None
    api_version: str | None = None
    name: str | None = None
    namespace: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    containers: list[dict[str, str]] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    config_maps: list[str] = field(default_factory=list)
    secrets_detected: list[str] = field(default_factory=list)


@dataclass
class CiCdInfo:
    path: str
    platform: str | None = None
    triggers: list[str] = field(default_factory=list)
    jobs: list[str] = field(default_factory=list)
    steps_count: int = 0
    uses_actions: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    secrets_detected: list[str] = field(default_factory=list)


@dataclass
class EnvTemplateInfo:
    path: str
    variables: list[str] = field(default_factory=list)
    has_defaults: int = 0
    has_optional: int = 0
    secrets_detected: list[str] = field(default_factory=list)


@dataclass
class AppConfigInfo:
    path: str
    config_type: str | None = None
    keys: list[str] = field(default_factory=list)
    nested_depth: int = 0
    secrets_detected: list[str] = field(default_factory=list)


@dataclass
class BuildCommandInfo:
    commands: list[str] = field(default_factory=list)
    has_multi_stage: bool = False
    targets: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)


@dataclass
class SecretDetection:
    file_path: str
    line_number: int
    pattern_name: str
    severity: str = "warning"


@dataclass
class DependencySummary:
    total: int = 0
    direct: int = 0
    dev: int = 0
    by_ecosystem: dict[str, int] = field(default_factory=dict)
    outdated_known: list[str] = field(default_factory=list)


@dataclass
class FrameworkInfo:
    name: str
    confidence: float
    language: str | None = None
    version_constraint: str | None = None


@dataclass
class ConfigurationSummary:
    total_config_files: int = 0
    manifest_count: int = 0
    docker_count: int = 0
    kubernetes_count: int = 0
    cicd_count: int = 0
    env_template_count: int = 0
    app_config_count: int = 0
    secrets_total: int = 0
    frameworks_detected: list[FrameworkInfo] = field(default_factory=list)
    dependency_summary: DependencySummary = field(default_factory=DependencySummary)


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------
_MANIFEST_PARSERS: dict[str, Any] = {}


def _register_manifest(ext: str, parser_fn: Any) -> None:
    _MANIFEST_PARSERS[ext] = parser_fn


def _safe_json(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def _safe_toml(raw: bytes) -> dict[str, Any] | None:
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None


def _safe_yaml(raw: str) -> dict[str, Any] | None:
    try:
        return yaml.safe_load(raw)
    except (yaml.YAMLError, ValueError):
        return None


def _detect_secrets(text: str, file_path: str) -> list[SecretDetection]:
    detections: list[SecretDetection] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern in _SECRET_PATTERNS:
            if pattern.search(line):
                detections.append(
                    SecretDetection(
                        file_path=file_path,
                        line_number=i,
                        pattern_name=pattern.pattern[:40],
                    )
                )
    return detections


def _sanitize_value(value: str) -> str:
    if re.search(r"(?:key|secret|password|token)", value, re.I):
        return "[REDACTED]"
    return value


# ---------------------------------------------------------------------------
# Manifest parsers
# ---------------------------------------------------------------------------
def _parse_package_json(data: dict[str, Any], path: str) -> ManifestInfo:
    deps = list(data.get("dependencies", {}).keys())
    dev_deps = list(data.get("devDependencies", {}).keys())
    return ManifestInfo(
        path=path,
        manifest_type="package.json",
        name=data.get("name"),
        version=data.get("version"),
        description=data.get("description"),
        dependencies=deps,
        dev_dependencies=dev_deps,
        scripts={k: _sanitize_value(v) for k, v in data.get("scripts", {}).items()},
        engines={k: str(v) for k, v in data.get("engines", {}).items()},
        license=data.get("license"),
        authors=[
            a.get("name", "") if isinstance(a, dict) else str(a)
            for a in (data.get("author") or ([] if not isinstance(data.get("author"), dict) else [data["author"]]))
        ],
        extra={
            "workspaces": data.get("workspaces"),
            "private": data.get("private", False),
        },
    )


def _parse_requirements_txt(raw: str, path: str) -> ManifestInfo:
    deps: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("-"):
            deps.append(line.split("==")[0].split(">=")[0].split("<=")[0].strip())
    return ManifestInfo(
        path=path,
        manifest_type="requirements.txt",
        dependencies=deps,
    )


def _parse_setup_py(raw: str, path: str) -> ManifestInfo:
    deps: list[str] = []
    name: str | None = None
    version: str | None = None
    for line in raw.splitlines():
        if "install_requires" in line:
            match = re.search(r"\[(.+?)\]", line)
            if match:
                deps = [d.strip().strip("'\"") for d in match.group(1).split(",")]
        if re.match(r'\s*name\s*=', line):
            m = re.search(r"['\"](.+?)['\"]", line)
            if m:
                name = m.group(1)
        if re.match(r'\s*version\s*=', line):
            m = re.search(r"['\"](.+?)['\"]", line)
            if m:
                version = m.group(1)
    return ManifestInfo(
        path=path, manifest_type="setup.py", name=name, version=version, dependencies=deps
    )


def _parse_pyproject_toml(data: dict[str, Any], path: str) -> ManifestInfo:
    project = data.get("project", {})
    deps = project.get("dependencies", [])
    name = project.get("name")
    version = project.get("version")
    scripts = project.get("scripts", {})
    return ManifestInfo(
        path=path,
        manifest_type="pyproject.toml",
        name=name,
        version=version,
        description=project.get("description"),
        dependencies=deps,
        scripts={k: _sanitize_value(v) for k, v in scripts.items()} if scripts else {},
        license=project.get("license") if isinstance(project.get("license"), str) else None,
    )


def _parse_cargo_toml(data: dict[str, Any], path: str) -> ManifestInfo:
    pkg = data.get("package", {})
    deps = list(data.get("dependencies", {}).keys())
    dev_deps = list(data.get("dev-dependencies", {}).keys())
    return ManifestInfo(
        path=path,
        manifest_type="Cargo.toml",
        name=pkg.get("name"),
        version=pkg.get("version"),
        description=pkg.get("description"),
        dependencies=deps,
        dev_dependencies=dev_deps,
        license=pkg.get("license"),
    )


def _parse_go_mod(raw: str, path: str) -> ManifestInfo:
    module_name: str | None = None
    deps: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("module "):
            module_name = line.split(None, 1)[-1] if len(line.split(None, 1)) > 1 else None
        elif re.match(r"require\s+\(", line) or line.startswith("\t"):
            m = re.match(r"\s+([\w./@-]+)\s+v", line)
            if m:
                deps.append(m.group(1))
    return ManifestInfo(path=path, manifest_type="go.mod", name=module_name, dependencies=deps)


def _parse_pom_xml(raw: str, path: str) -> ManifestInfo:
    deps: list[str] = []
    name_match = re.search(r"<artifactId>(.+?)</artifactId>", raw)
    version_match = re.search(r"<version>(.+?)</version>", raw)
    for m in re.finditer(r"<dependency>\s*<groupId>(.+?)</groupId>\s*<artifactId>(.+?)</artifactId>", raw):
        deps.append(f"{m.group(1)}:{m.group(2)}")
    return ManifestInfo(
        path=path,
        manifest_type="pom.xml",
        name=name_match.group(1) if name_match else None,
        version=version_match.group(1) if version_match else None,
        dependencies=deps,
    )


def _parse_build_gradle(raw: str, path: str) -> ManifestInfo:
    deps: list[str] = []
    for m in re.finditer(r"implementation\s+['\"](.+?)['\"]", raw):
        deps.append(m.group(1))
    name_match = re.search(r"rootProject\.name\s*=\s*['\"](.+?)['\"]", raw)
    return ManifestInfo(
        path=path, manifest_type="build.gradle", name=name_match.group(1) if name_match else None, dependencies=deps
    )


def _parse_gemfile(raw: str, path: str) -> ManifestInfo:
    deps: list[str] = []
    for m in re.finditer(r"gem\s+['\"](.+?)['\"]", raw):
        deps.append(m.group(1))
    ruby_match = re.search(r"ruby\s+['\"](.+?)['\"]", raw)
    extra: dict[str, Any] = {}
    if ruby_match:
        extra["ruby_version"] = ruby_match.group(1)
    return ManifestInfo(path=path, manifest_type="Gemfile", dependencies=deps, extra=extra)


def _parse_composer_json(data: dict[str, Any], path: str) -> ManifestInfo:
    deps = list(data.get("require", {}).keys())
    dev_deps = list(data.get("require-dev", {}).keys())
    scripts = {k: v if isinstance(v, str) else str(v) for k, v in data.get("scripts", {}).items()}
    return ManifestInfo(
        path=path,
        manifest_type="composer.json",
        name=data.get("name"),
        version=data.get("version"),
        dependencies=deps,
        dev_dependencies=dev_deps,
        scripts=scripts,
    )


def _parse_pubspec_yaml(data: dict[str, Any], path: str) -> ManifestInfo:
    deps = list(data.get("dependencies", {}).keys())
    dev_deps = list(data.get("dev_dependencies", {}).keys())
    return ManifestInfo(
        path=path,
        manifest_type="pubspec.yaml",
        name=data.get("name"),
        version=data.get("version"),
        description=data.get("description"),
        dependencies=deps,
        dev_dependencies=dev_deps,
    )


def _parse_package_swift(raw: str, path: str) -> ManifestInfo:
    deps: list[str] = []
    for m in re.finditer(r'\.package\s*\(\s*url:\s*["\'](.+?)["\']', raw):
        deps.append(m.group(1))
    name_match = re.search(r'name:\s*["\'](.+?)["\']', raw)
    return ManifestInfo(
        path=path, manifest_type="Package.swift", name=name_match.group(1) if name_match else None, dependencies=deps
    )


def _parse_cmake_lists(raw: str, path: str) -> ManifestInfo:
    name_match = re.search(r"project\s*\(\s*(\S+)", raw)
    deps: list[str] = []
    for m in re.finditer(r"find_package\s*\(\s*(\S+)", raw):
        deps.append(m.group(1))
    return ManifestInfo(
        path=path, manifest_type="CMakeLists.txt", name=name_match.group(1) if name_match else None, dependencies=deps
    )


# Register parsers
_register_manifest("package.json", lambda d, p: _parse_package_json(d, p))
_register_manifest("requirements.txt", lambda d, p: _parse_requirements_txt(d if isinstance(d, str) else "", p))
_register_manifest("setup.py", lambda d, p: _parse_setup_py(d if isinstance(d, str) else "", p))
_register_manifest("pyproject.toml", lambda d, p: _parse_pyproject_toml(d, p))
_register_manifest("Cargo.toml", lambda d, p: _parse_cargo_toml(d, p))
_register_manifest("go.mod", lambda d, p: _parse_go_mod(d if isinstance(d, str) else "", p))
_register_manifest("pom.xml", lambda d, p: _parse_pom_xml(d if isinstance(d, str) else "", p))
_register_manifest("build.gradle", lambda d, p: _parse_build_gradle(d if isinstance(d, str) else "", p))
_register_manifest("Gemfile", lambda d, p: _parse_gemfile(d if isinstance(d, str) else "", p))
_register_manifest("composer.json", lambda d, p: _parse_composer_json(d, p))
_register_manifest("pubspec.yaml", lambda d, p: _parse_pubspec_yaml(d, p))
_register_manifest("Package.swift", lambda d, p: _parse_package_swift(d if isinstance(d, str) else "", p))
_register_manifest("CMakeLists.txt", lambda d, p: _parse_cmake_lists(d if isinstance(d, str) else "", p))


# ---------------------------------------------------------------------------
# Dockerfile parser
# ---------------------------------------------------------------------------
def _parse_dockerfile(raw: str, path: str) -> DockerInfo:
    info = DockerInfo(path=path)
    stages: list[str] = []
    current_stage: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            if "AS" in [p.upper() for p in parts]:
                idx = next(i for i, p in enumerate(parts) if p.upper() == "AS")
                current_stage = parts[idx + 1] if idx + 1 < len(parts) else None
            elif len(parts) >= 2 and parts[1] not in ("AS", "as"):
                current_stage = parts[1].split(":")[0]
            if current_stage:
                stages.append(current_stage)
            base = parts[1].split(" AS ")[0].split(" as ")[0] if len(parts) >= 2 else parts[0]
            info.base_image = info.base_image or base
        elif stripped.upper().startswith("EXPOSE "):
            info.exposed_ports.extend(stripped.split()[1:])
        elif stripped.upper().startswith("ENV "):
            m = re.match(r"ENV\s+(\w+)=", stripped)
            if m:
                info.env_vars.append(m.group(1))
        elif stripped.upper().startswith("VOLUME "):
            info.volumes.append(stripped.split(None, 1)[-1])
        elif stripped.upper().startswith("RUN "):
            info.run_commands.append(stripped[4:])
        elif stripped.upper().startswith("HEALTHCHECK "):
            info.has_healthcheck = True
        elif stripped.upper().startswith("USER "):
            info.user = stripped.split()[1]
    info.stages = stages
    secrets = _detect_secrets(raw, path)
    info.secrets_detected = [s.pattern_name for s in secrets]
    return info


# ---------------------------------------------------------------------------
# Kubernetes YAML parser
# ---------------------------------------------------------------------------
def _parse_k8s_yaml(data: dict[str, Any], path: str) -> KubernetesInfo:
    info = KubernetesInfo(
        path=path,
        kind=data.get("kind"),
        api_version=data.get("apiVersion"),
        name=data.get("metadata", {}).get("name"),
        namespace=data.get("metadata", {}).get("namespace"),
        labels=data.get("metadata", {}).get("labels", {}),
    )
    spec = data.get("spec", {})
    containers = spec.get("template", spec).get("spec", {}).get("containers", [])
    if not containers:
        containers = spec.get("containers", [])
    for c in containers:
        info.containers.append({
            "name": c.get("name", ""),
            "image": c.get("image", ""),
        })
    if data.get("kind") == "Service":
        info.services.append(data.get("metadata", {}).get("name", ""))
    if data.get("kind") == "ConfigMap":
        info.config_maps.append(data.get("metadata", {}).get("name", ""))
    raw_text = json.dumps(data)
    secrets = _detect_secrets(raw_text, path)
    info.secrets_detected = [s.pattern_name for s in secrets]
    return info


# ---------------------------------------------------------------------------
# CI/CD parser
# ---------------------------------------------------------------------------
_CI_PLATFORMS: dict[str, list[str]] = {
    "github_actions": [".github/workflows/"],
    "gitlab_ci": [".gitlab-ci.yml"],
    "jenkins": ["Jenkinsfile"],
    "circleci": [".circleci/"],
    "travis": [".travis.yml"],
    "azure_pipelines": ["azure-pipelines.yml"],
}


def _detect_ci_platform(file_path: str) -> str | None:
    for platform, patterns in _CI_PLATFORMS.items():
        for pat in patterns:
            if pat in file_path:
                return platform
    return None


def _parse_github_actions(raw: str, path: str) -> CiCdInfo:
    data = _safe_yaml(raw)
    if not data:
        return CiCdInfo(path=path, platform="github_actions")
    triggers = list(data.get("on", {}).keys()) if isinstance(data.get("on"), dict) else []
    jobs = list(data.get("jobs", {}).keys())
    steps_count = 0
    actions: list[str] = []
    env_vars: list[str] = []
    for job_def in data.get("jobs", {}).values():
        for step in job_def.get("steps", []):
            steps_count += 1
            if "uses" in step:
                actions.append(step["uses"])
            env = step.get("env", {})
            env_vars.extend(env.keys())
    secrets = _detect_secrets(raw, path)
    return CiCdInfo(
        path=path,
        platform="github_actions",
        triggers=triggers,
        jobs=jobs,
        steps_count=steps_count,
        uses_actions=actions,
        env_vars=env_vars,
        secrets_detected=[s.pattern_name for s in secrets],
    )


def _parse_gitlab_ci(raw: str, path: str) -> CiCdInfo:
    data = _safe_yaml(raw)
    if not data:
        return CiCdInfo(path=path, platform="gitlab_ci")
    stages = data.get("stages", [])
    jobs = [k for k in data.keys() if k != "stages"]
    secrets = _detect_secrets(raw, path)
    return CiCdInfo(
        path=path, platform="gitlab_ci", triggers=stages, jobs=jobs, secrets_detected=[s.pattern_name for s in secrets]
    )


def _parse_generic_ci(raw: str, path: str) -> CiCdInfo:
    secrets = _detect_secrets(raw, path)
    return CiCdInfo(path=path, secrets_detected=[s.pattern_name for s in secrets])


# ---------------------------------------------------------------------------
# Environment template parser
# ---------------------------------------------------------------------------
def _parse_env_template(raw: str, path: str) -> EnvTemplateInfo:
    info = EnvTemplateInfo(path=path)
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key = line.split("=", 1)[0].strip()
            value = line.split("=", 1)[1].strip()
            info.variables.append(key)
            if value:
                info.has_defaults += 1
            else:
                info.has_optional += 1
    secrets = _detect_secrets(raw, path)
    info.secrets_detected = [s.pattern_name for s in secrets]
    return info


# ---------------------------------------------------------------------------
# Application config parser
# ---------------------------------------------------------------------------
_CONFIG_EXTENSIONS = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".xml", ".properties"}


def _parse_app_config(raw: str, path: str) -> AppConfigInfo:
    info = AppConfigInfo(path=path)
    ext = Path(path).suffix.lower()
    data: dict[str, Any] | None = None
    if ext in (".yaml", ".yml"):
        data = _safe_yaml(raw)
        info.config_type = "yaml"
    elif ext == ".json":
        data = _safe_json(raw)
        info.config_type = "json"
    elif ext == ".toml":
        data = _safe_toml(raw.encode())
        info.config_type = "toml"
    elif ext in (".ini", ".cfg", ".conf"):
        info.config_type = "ini"
        info.keys = [line.split("=")[0].strip() for line in raw.splitlines() if "=" in line and not line.strip().startswith(("#", "["))]
        return info
    elif ext == ".properties":
        info.config_type = "properties"
        info.keys = [line.split("=")[0].strip() for line in raw.splitlines() if "=" in line and not line.strip().startswith("#")]
        return info
    elif ext == ".xml":
        info.config_type = "xml"
        info.keys = re.findall(r"<(\w+)[\s/>]", raw)
        return info

    if data:
        info.keys = list(data.keys()) if isinstance(data, dict) else []
        info.nested_depth = _dict_depth(data) if isinstance(data, dict) else 0
    secrets = _detect_secrets(raw, path)
    info.secrets_detected = [s.pattern_name for s in secrets]
    return info


def _dict_depth(d: Any, current: int = 0) -> int:
    if not isinstance(d, dict) or not d:
        return current
    return max(_dict_depth(v, current + 1) for v in d.values())


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------
class ConfigurationAnalyzer:
    """Analyze repository configuration files and provide structured summaries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- file discovery --
    async def detect_config_files(self, repo_id: uuid.UUID) -> list[CodeFile]:
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == repo_id)
            .where(
                CodeFile.file_path.ilike("%.json")
                | CodeFile.file_path.ilike("%.yaml")
                | CodeFile.file_path.ilike("%.yml")
                |                 CodeFile.file_path.ilike("%.toml")
                | CodeFile.file_path.ilike("%.txt")
                | CodeFile.file_path.ilike("Dockerfile%")
                | CodeFile.file_path.ilike("%.env%")
                | CodeFile.file_path.ilike("%Jenkinsfile")
                | CodeFile.file_path.ilike("%.gradle")
                | CodeFile.file_path.ilike("%.xml")
                | CodeFile.file_path.ilike("%.ini")
                | CodeFile.file_path.ilike("%.cfg")
                | CodeFile.file_path.ilike("%.conf")
                | CodeFile.file_path.ilike("%.properties")
            )
        )
        result = await self._session.execute(stmt)
        files = list(result.scalars().all())
        logger.info("Found %d potential config files for repo %s", len(files), repo_id)
        return files

    # -- manifest parsing --
    async def parse_manifest(self, file_id: uuid.UUID) -> ManifestInfo | None:
        file = await self._get_file(file_id)
        if not file:
            return None
        filename = Path(file.file_path).name
        parser = _MANIFEST_PARSERS.get(filename)
        if not parser:
            logger.debug("No manifest parser for %s", filename)
            return None
        content = file.content or ""
        try:
            if filename.endswith(".json"):
                data = _safe_json(content)
                if data is None:
                    return None
                return parser(data, file.file_path)
            elif filename.endswith((".toml",)) and filename != "Cargo.toml":
                data = _safe_toml(content.encode())
                if data is None:
                    return None
                return parser(data, file.file_path)
            elif filename.endswith((".yaml", ".yml")):
                data = _safe_yaml(content)
                if data is None:
                    return None
                return parser(data, file.file_path)
            else:
                return parser(content, file.file_path)
        except Exception:
            logger.exception("Error parsing manifest %s", file.file_path)
            return None

    # -- Dockerfile --
    async def parse_dockerfile(self, file_id: uuid.UUID) -> DockerInfo | None:
        file = await self._get_file(file_id)
        if not file or not file.content:
            return None
        filename = Path(file.file_path).name
        if not (filename == "Dockerfile" or filename.startswith("Dockerfile.")):
            return None
        return _parse_dockerfile(file.content, file.file_path)

    # -- Kubernetes --
    async def parse_kubernetes_yaml(self, file_id: uuid.UUID) -> list[KubernetesInfo]:
        file = await self._get_file(file_id)
        if not file or not file.content:
            return []
        filename = Path(file.file_path).name
        if not filename.endswith((".yaml", ".yml")):
            return []
        data = _safe_yaml(file.content)
        if data is None:
            return []
        if data.get("kind") in ("Deployment", "Service", "ConfigMap", "Secret", "StatefulSet", "DaemonSet", "Ingress", "Job", "CronJob", "Pod"):
            return [_parse_k8s_yaml(data, file.file_path)]
        if isinstance(data, dict) and "apiVersion" in data:
            return [_parse_k8s_yaml(data, file.file_path)]
        return []

    # -- CI/CD --
    async def parse_ci_cd(self, file_id: uuid.UUID) -> CiCdInfo | None:
        file = await self._get_file(file_id)
        if not file or not file.content:
            return None
        platform = _detect_ci_platform(file.file_path)
        if platform == "github_actions":
            return _parse_github_actions(file.content, file.file_path)
        elif platform == "gitlab_ci":
            return _parse_gitlab_ci(file.content, file.file_path)
        elif platform:
            return _parse_generic_ci(file.content, file.file_path)
        return None

    # -- env template --
    async def parse_env_template(self, file_id: uuid.UUID) -> EnvTemplateInfo | None:
        file = await self._get_file(file_id)
        if not file or not file.content:
            return None
        filename = Path(file.file_path).name
        if not (filename.startswith(".env") or filename.endswith(".env")):
            return None
        return _parse_env_template(file.content, file.file_path)

    # -- build commands --
    async def extract_build_commands(self, repo_id: uuid.UUID) -> BuildCommandInfo:
        info = BuildCommandInfo()
        dockerfiles = await self.detect_config_files(repo_id)
        for f in dockerfiles:
            if Path(f.file_path).name.startswith("Dockerfile"):
                docker = await self.parse_dockerfile(f.id)
                if docker:
                    info.commands.extend(docker.run_commands)
                    if len(docker.stages) > 1:
                        info.has_multi_stage = True
        manifest_files = [f for f in dockerfiles if Path(f.file_path).name in _MANIFEST_PARSERS]
        for f in manifest_files:
            manifest = await self.parse_manifest(f.id)
            if manifest and manifest.scripts:
                info.scripts.update(manifest.scripts)
        logger.info("Extracted %d build commands and %d scripts", len(info.commands), len(info.scripts))
        return info

    # -- secrets --
    async def detect_secrets(self, repo_id: uuid.UUID) -> list[SecretDetection]:
        all_detections: list[SecretDetection] = []
        files = await self.detect_config_files(repo_id)
        for f in files:
            if f.content:
                detections = _detect_secrets(f.content, f.file_path)
                all_detections.extend(detections)
        logger.info("Detected %d potential secrets across %d config files", len(all_detections), len(files))
        return all_detections

    # -- dependency summary --
    async def get_dependency_summary(self, repo_id: uuid.UUID) -> DependencySummary:
        summary = DependencySummary()
        ecosystem_counts: dict[str, int] = {}
        files = await self.detect_config_files(repo_id)
        manifest_files = [f for f in files if Path(f.file_path).name in _MANIFEST_PARSERS]
        for f in manifest_files:
            manifest = await self.parse_manifest(f.id)
            if manifest:
                summary.direct += len(manifest.dependencies)
                summary.dev += len(manifest.dev_dependencies)
                ecosystem = manifest.manifest_type
                ecosystem_counts[ecosystem] = ecosystem_counts.get(ecosystem, 0) + len(manifest.dependencies)
        summary.total = summary.direct + summary.dev
        summary.by_ecosystem = ecosystem_counts
        logger.info("Dependency summary: %d total across %d ecosystems", summary.total, len(ecosystem_counts))
        return summary

    # -- framework detection --
    async def get_framework_detection(self, repo_id: uuid.UUID) -> list[FrameworkInfo]:
        frameworks: list[FrameworkInfo] = []
        files = await self.detect_config_files(repo_id)
        all_content = ""
        all_filenames: list[str] = []
        for f in files:
            if f.content:
                all_content += f.content + "\n"
            all_filenames.append(Path(f.file_path).name)
        for fw_name, sig in _FRAMEWORK_SIGNATURES.items():
            confidence = 0.0
            indicator_hits = sum(1 for ind in sig["indicators"] if ind.lower() in all_content.lower())
            config_hits = sum(1 for cfg in sig["config_files"] if cfg in all_filenames)
            if indicator_hits > 0:
                confidence += 0.4 * min(indicator_hits / max(len(sig["indicators"]), 1), 1.0)
            if config_hits > 0:
                confidence += 0.3 * min(config_hits / max(len(sig["config_files"]), 1), 1.0)
            if confidence >= 0.3:
                frameworks.append(FrameworkInfo(
                    name=fw_name, confidence=round(confidence, 2), language=sig.get("language")
                ))
        frameworks.sort(key=lambda fw: fw.confidence, reverse=True)
        logger.info("Detected %d frameworks", len(frameworks))
        return frameworks

    # -- full summary --
    async def get_configuration_summary(self, repo_id: uuid.UUID) -> ConfigurationSummary:
        files = await self.detect_config_files(repo_id)
        summary = ConfigurationSummary(total_config_files=len(files))
        for f in files:
            filename = Path(f.file_path).name
            if filename in _MANIFEST_PARSERS:
                summary.manifest_count += 1
            elif filename.startswith("Dockerfile"):
                summary.docker_count += 1
            elif filename.endswith((".yaml", ".yml")) and f.content:
                data = _safe_yaml(f.content) if f.content else None
                if data and isinstance(data, dict) and "kind" in data:
                    summary.kubernetes_count += 1
                else:
                    summary.app_config_count += 1
            elif _detect_ci_platform(f.file_path):
                summary.cicd_count += 1
            elif filename.startswith(".env"):
                summary.env_template_count += 1
            else:
                summary.app_config_count += 1
        secrets = await self.detect_secrets(repo_id)
        summary.secrets_total = len(secrets)
        summary.frameworks_detected = await self.get_framework_detection(repo_id)
        summary.dependency_summary = await self.get_dependency_summary(repo_id)
        return summary

    # -- full repository analysis --
    async def analyze_repository(self, repo_id: uuid.UUID) -> dict[str, Any]:
        logger.info("Starting full configuration analysis for repo %s", repo_id)
        files = await self.detect_config_files(repo_id)
        results: dict[str, Any] = {
            "repo_id": str(repo_id),
            "total_config_files": len(files),
            "manifests": [],
            "dockerfiles": [],
            "kubernetes": [],
            "cicd": [],
            "env_templates": [],
            "secrets": [],
        }
        for f in files:
            filename = Path(f.file_path).name
            try:
                if filename in _MANIFEST_PARSERS:
                    manifest = await self.parse_manifest(f.id)
                    if manifest:
                        results["manifests"].append(manifest.__dict__)
                elif filename.startswith("Dockerfile"):
                    docker = await self.parse_dockerfile(f.id)
                    if docker:
                        results["dockerfiles"].append(docker.__dict__)
                elif filename.endswith((".yaml", ".yml")):
                    k8s_items = await self.parse_kubernetes_yaml(f.id)
                    if k8s_items:
                        for item in k8s_items:
                            results["kubernetes"].append(item.__dict__)
                ci_cd = await self.parse_ci_cd(f.id)
                if ci_cd and ci_cd.platform:
                    results["cicd"].append(ci_cd.__dict__)
                if filename.startswith(".env"):
                    env_info = await self.parse_env_template(f.id)
                    if env_info:
                        results["env_templates"].append(env_info.__dict__)
            except Exception:
                logger.exception("Error analyzing config file %s", f.file_path)
        secrets = await self.detect_secrets(repo_id)
        results["secrets"] = [
            {"file": s.file_path, "line": s.line_number, "pattern": s.pattern_name}
            for s in secrets
        ]
        results["summary"] = (await self.get_configuration_summary(repo_id)).__dict__
        logger.info("Configuration analysis complete for repo %s", repo_id)
        return results

    # -- internal --
    async def _get_file(self, file_id: uuid.UUID) -> CodeFile | None:
        stmt = select(CodeFile).where(CodeFile.id == file_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
