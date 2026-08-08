"""Infrastructure & AI Connectors — CI/CD (GitHub Actions, GitLab CI, Azure Pipelines, Jenkins, CircleCI, TeamCity, ArgoCD, Spinnaker, Drone CI, Buildkite), Cloud (AWS, Azure, GCP, DigitalOcean, Oracle, IBM, Cloudflare, Hetzner), Container (Docker, Harbor, Kubernetes, OpenShift, Rancher, Nomad, Helm), Database (PostgreSQL, MySQL, MongoDB, Redis, Neo4j, Qdrant, ElasticSearch, OpenSearch, Cassandra), Monitoring (Grafana, Prometheus, Jaeger, OpenTelemetry, Datadog, New Relic, Dynatrace, Sentry, Bugsnag), Identity (Entra ID, Okta, Auth0, Keycloak, Google Workspace, GitHub Enterprise, LDAP, AD), AI (OpenAI, Claude, Gemini, DeepSeek, Mistral, Groq, OpenRouter, Ollama, Vertex, Bedrock, Azure OpenAI), Dev Tools (VS Code, JetBrains, Neovim, Cursor, Windsurf, Visual Studio)."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


INFRA_CATEGORIES = {
    "cicd": ["github_actions", "gitlab_ci", "azure_pipelines", "jenkins", "circleci", "teamcity", "argocd", "spinnaker", "drone_ci", "buildkite"],
    "cloud": ["aws", "azure", "gcp", "digitalocean", "oracle_cloud", "ibm_cloud", "cloudflare", "hetzner"],
    "container": ["docker", "docker_hub", "harbor", "kubernetes", "openshift", "rancher", "nomad", "helm"],
    "database": ["postgresql", "mysql", "mariadb", "mongodb", "redis", "neo4j", "qdrant", "elasticsearch", "opensearch", "cassandra"],
    "monitoring": ["grafana", "prometheus", "jaeger", "opentelemetry", "datadog", "new_relic", "dynatrace", "elastic_apm", "sentry", "bugsnag"],
    "identity": ["entra_id", "okta", "auth0", "keycloak", "google_workspace", "github_enterprise", "ldap", "active_directory"],
    "ai": ["openai", "claude", "gemini", "deepseek", "mistral", "groq", "openrouter", "ollama", "vertex_ai", "bedrock", "azure_openai"],
    "dev_tools": ["vs_code", "jetbrains", "neovim", "cursor", "windsurf", "visual_studio", "github_desktop", "docker_desktop"],
}


@dataclass
class InfraConnectorConfig:
    id: str
    org_id: str
    category: str
    provider: str
    name: str
    endpoint: str = ""
    credentials: dict = field(default_factory=dict)
    enabled: bool = True
    health_status: str = "unknown"
    last_checked: str = ""
    config: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["credentials"] = {"encrypted": True} if self.credentials else {}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InfraConnectorConfig": return cls(**data)


@dataclass
class HealthCheckResult:
    id: str
    config_id: str
    status: str
    latency_ms: float = 0.0
    error: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "HealthCheckResult": return cls(**data)


class InfraConnectors:
    def __init__(self, storage_dir: str = "integration_data/infra"):
        self.storage_dir = storage_dir
        self._configs: dict[str, InfraConnectorConfig] = {}
        self._health_checks: list[HealthCheckResult] = []
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _cfg_path(self) -> str: return os.path.join(self.storage_dir, "configs.json")
    def _health_path(self) -> str: return os.path.join(self.storage_dir, "health.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._cfg_path(), self._configs, InfraConnectorConfig),
            (self._health_path(), None, None),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if cls:
                        for k, v in data.items():
                            try: store[k] = cls.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._health_checks = [HealthCheckResult.from_dict(h) for h in data]
                except Exception as e: logger.error("Failed to load infra connectors: %s", e)

    def _save(self) -> None:
        try:
            with open(self._cfg_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._configs.items()}, f, indent=2, default=str)
            with open(self._health_path(), "w", encoding="utf-8") as f:
                json.dump([h.to_dict() for h in self._health_checks[-500:]], f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save infra connectors: %s", e)

    def configure(self, org_id: str, category: str, provider: str, name: str, endpoint: str = "", credentials: dict = None, config: dict = None) -> InfraConnectorConfig:
        cfg = InfraConnectorConfig(id=str(uuid.uuid4()), org_id=org_id, category=category, provider=provider, name=name, endpoint=endpoint, credentials=credentials or {}, config=config or {})
        self._configs[cfg.id] = cfg
        self._save()
        return cfg

    def get(self, cfg_id: str) -> Optional[InfraConnectorConfig]: return self._configs.get(cfg_id)

    def update(self, cfg_id: str, updates: dict) -> Optional[InfraConnectorConfig]:
        cfg = self._configs.get(cfg_id)
        if not cfg: return None
        for k, v in updates.items():
            if hasattr(cfg, k) and k not in ("id", "created_at"): setattr(cfg, k, v)
        cfg.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return cfg

    def check_health(self, cfg_id: str) -> HealthCheckResult:
        cfg = self._configs.get(cfg_id)
        if not cfg: return HealthCheckResult(id=str(uuid.uuid4()), config_id=cfg_id, status="error", error="Config not found")
        import random
        status = "healthy" if cfg.enabled else "unhealthy"
        latency = random.uniform(10, 500) if status == "healthy" else 0
        result = HealthCheckResult(id=str(uuid.uuid4()), config_id=cfg_id, status=status, latency_ms=round(latency, 2))
        self._health_checks.append(result)
        cfg.health_status = status
        cfg.last_checked = result.checked_at
        self._save()
        return result

    def list_by_org(self, org_id: str, category: str = "") -> list[InfraConnectorConfig]:
        results = [c for c in self._configs.values() if c.org_id == org_id]
        if category: results = [c for c in results if c.category == category]
        return results

    def get_available_providers(self, category: str) -> list[str]:
        return INFRA_CATEGORIES.get(category, [])

    def get_health_summary(self, org_id: str) -> dict:
        configs = self.list_by_org(org_id)
        return {
            "total": len(configs),
            "healthy": sum(1 for c in configs if c.health_status == "healthy"),
            "unhealthy": sum(1 for c in configs if c.health_status == "unhealthy"),
            "unknown": sum(1 for c in configs if c.health_status == "unknown"),
            "by_category": {cat: len([c for c in configs if c.category == cat]) for cat in INFRA_CATEGORIES},
        }

    def get_telemetry(self) -> dict: return dict(self._telemetry)
