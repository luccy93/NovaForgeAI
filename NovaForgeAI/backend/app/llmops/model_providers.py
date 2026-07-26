import json
import uuid
import time
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    VERTEX_AI = "vertex_ai"
    GROQ = "groq"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    COHERE = "cohere"
    CUSTOM = "custom"


class ProviderStatus(Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DOWN = "down"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


@dataclass
class ProviderConfig:
    id: str
    provider_type: ProviderType
    name: str
    base_url: str
    api_key: str = ""
    organization_id: str = ""
    default_model: str = ""
    models: list[str] = field(default_factory=list)
    status: ProviderStatus = ProviderStatus.UNKNOWN
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100000
    max_concurrency: int = 10
    timeout_seconds: int = 60
    retry_count: int = 3
    health_endpoint: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)
    region: str = ""
    supports_streaming: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider_type"] = self.provider_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderConfig":
        data["provider_type"] = ProviderType(data["provider_type"])
        data["status"] = ProviderStatus(data["status"])
        return cls(**data)


@dataclass
class ProviderHealth:
    provider_id: str
    status: ProviderStatus
    latency_ms: float = 0.0
    error_count: int = 0
    success_count: int = 0
    last_check: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    uptime_percent: float = 100.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderHealth":
        data["status"] = ProviderStatus(data["status"])
        return cls(**data)


@dataclass
class ProviderModelMap:
    provider_id: str
    model_name: str
    registry_model_id: str = ""
    aliases: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderModelMap":
        return cls(**data)


BUILTIN_PROVIDER_DEFAULTS: dict[ProviderType, dict] = {
    ProviderType.OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "rate_limit_rpm": 500,
        "rate_limit_tpm": 200000,
        "max_concurrency": 50,
        "timeout_seconds": 120,
        "retry_count": 3,
        "health_endpoint": "https://api.openai.com/v1/models",
        "supports_streaming": True,
    },
    ProviderType.ANTHROPIC: {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-opus-4-20250514",
        "rate_limit_rpm": 80,
        "rate_limit_tpm": 100000,
        "max_concurrency": 20,
        "timeout_seconds": 180,
        "retry_count": 3,
        "health_endpoint": "https://api.anthropic.com/v1/messages",
        "supports_streaming": True,
    },
    ProviderType.GOOGLE: {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.0-flash",
        "rate_limit_rpm": 360,
        "rate_limit_tpm": 1000000,
        "max_concurrency": 30,
        "timeout_seconds": 120,
        "retry_count": 3,
        "health_endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
        "supports_streaming": True,
    },
    ProviderType.OPENROUTER: {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o",
        "rate_limit_rpm": 200,
        "rate_limit_tpm": 200000,
        "max_concurrency": 30,
        "timeout_seconds": 120,
        "retry_count": 2,
        "health_endpoint": "https://openrouter.ai/api/v1/models",
        "supports_streaming": True,
    },
    ProviderType.OLLAMA: {
        "base_url": "http://localhost:11434",
        "default_model": "llama3.1",
        "rate_limit_rpm": 99999,
        "rate_limit_tpm": 9999999,
        "max_concurrency": 100,
        "timeout_seconds": 300,
        "retry_count": 1,
        "health_endpoint": "http://localhost:11434/api/tags",
        "supports_streaming": True,
    },
    ProviderType.LM_STUDIO: {
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "rate_limit_rpm": 99999,
        "rate_limit_tpm": 9999999,
        "max_concurrency": 50,
        "timeout_seconds": 300,
        "retry_count": 1,
        "health_endpoint": "http://localhost:1234/v1/models",
        "supports_streaming": True,
    },
    ProviderType.AZURE_OPENAI: {
        "base_url": "https://YOUR_RESOURCE.openai.azure.com",
        "default_model": "gpt-4o",
        "rate_limit_rpm": 240,
        "rate_limit_tpm": 135000,
        "max_concurrency": 30,
        "timeout_seconds": 120,
        "retry_count": 3,
        "health_endpoint": "",
        "supports_streaming": True,
    },
    ProviderType.AWS_BEDROCK: {
        "base_url": "https://bedrock-runtime.YOUR_REGION.amazonaws.com",
        "default_model": "anthropic.claude-3-5-sonnet-20241022",
        "rate_limit_rpm": 50,
        "rate_limit_tpm": 100000,
        "max_concurrency": 10,
        "timeout_seconds": 300,
        "retry_count": 3,
        "health_endpoint": "",
        "supports_streaming": True,
    },
    ProviderType.VERTEX_AI: {
        "base_url": "https://YOUR_PROJECT_ID.uc.runtime.googleapis.com",
        "default_model": "gemini-2.0-flash-001",
        "rate_limit_rpm": 300,
        "rate_limit_tpm": 500000,
        "max_concurrency": 20,
        "timeout_seconds": 180,
        "retry_count": 3,
        "health_endpoint": "",
        "supports_streaming": True,
    },
    ProviderType.GROQ: {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "rate_limit_rpm": 30,
        "rate_limit_tpm": 6000,
        "max_concurrency": 6,
        "timeout_seconds": 60,
        "retry_count": 3,
        "health_endpoint": "https://api.groq.com/openai/v1/models",
        "supports_streaming": True,
    },
    ProviderType.MISTRAL: {
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-large-latest",
        "rate_limit_rpm": 60,
        "rate_limit_tpm": 50000,
        "max_concurrency": 10,
        "timeout_seconds": 120,
        "retry_count": 3,
        "health_endpoint": "https://api.mistral.ai/v1/models",
        "supports_streaming": True,
    },
    ProviderType.DEEPSEEK: {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "rate_limit_rpm": 60,
        "rate_limit_tpm": 100000,
        "max_concurrency": 15,
        "timeout_seconds": 120,
        "retry_count": 3,
        "health_endpoint": "https://api.deepseek.com/v1/models",
        "supports_streaming": True,
    },
    ProviderType.COHERE: {
        "base_url": "https://api.cohere.com/v1",
        "default_model": "command-r-plus",
        "rate_limit_rpm": 40,
        "rate_limit_tpm": 50000,
        "max_concurrency": 10,
        "timeout_seconds": 60,
        "retry_count": 3,
        "health_endpoint": "https://api.cohere.com/v1/models",
        "supports_streaming": True,
    },
    ProviderType.CUSTOM: {
        "base_url": "",
        "default_model": "",
        "rate_limit_rpm": 60,
        "rate_limit_tpm": 50000,
        "max_concurrency": 10,
        "timeout_seconds": 60,
        "retry_count": 2,
        "health_endpoint": "",
        "supports_streaming": True,
    },
}


class ProviderRegistry:
    def __init__(self, storage_dir: str = "provider_registry_data"):
        self.storage_dir = storage_dir
        self._providers: dict[str, ProviderConfig] = {}
        self._health: dict[str, list[ProviderHealth]] = defaultdict(list)
        self._model_maps: dict[str, list[ProviderModelMap]] = defaultdict(list)
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _providers_path(self) -> str:
        return os.path.join(self.storage_dir, "providers.json")

    def _health_path(self) -> str:
        return os.path.join(self.storage_dir, "provider_health.json")

    def _model_maps_path(self) -> str:
        return os.path.join(self.storage_dir, "model_maps.json")

    def _save(self) -> None:
        try:
            providers_data = {pid: p.to_dict() for pid, p in self._providers.items()}
            with open(self._providers_path(), "w", encoding="utf-8") as f:
                json.dump(providers_data, f, indent=2, default=str)

            health_data = {pid: [h.to_dict() for h in hlist] for pid, hlist in self._health.items()}
            with open(self._health_path(), "w", encoding="utf-8") as f:
                json.dump(health_data, f, indent=2, default=str)

            maps_data = {pid: [m.to_dict() for m in mlist] for pid, mlist in self._model_maps.items()}
            with open(self._model_maps_path(), "w", encoding="utf-8") as f:
                json.dump(maps_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save provider data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._providers_path()):
                with open(self._providers_path(), "r", encoding="utf-8") as f:
                    providers_data = json.load(f)
                for pid, data in providers_data.items():
                    try:
                        self._providers[pid] = ProviderConfig.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed provider %s: %s", pid, e)

            if os.path.exists(self._health_path()):
                with open(self._health_path(), "r", encoding="utf-8") as f:
                    health_data = json.load(f)
                for pid, hlist in health_data.items():
                    self._health[pid] = []
                    for hdata in hlist:
                        try:
                            self._health[pid].append(ProviderHealth.from_dict(hdata))
                        except Exception as e:
                            logger.warning("Skipping malformed health entry for %s: %s", pid, e)

            if os.path.exists(self._model_maps_path()):
                with open(self._model_maps_path(), "r", encoding="utf-8") as f:
                    maps_data = json.load(f)
                for pid, mlist in maps_data.items():
                    self._model_maps[pid] = []
                    for mdata in mlist:
                        try:
                            self._model_maps[pid].append(ProviderModelMap.from_dict(mdata))
                        except Exception as e:
                            logger.warning("Skipping malformed model map for %s: %s", pid, e)
        except Exception as e:
            logger.error("Failed to load provider data: %s", e, exc_info=True)

    def register_provider(self, config: ProviderConfig) -> ProviderConfig:
        self._telemetry["register_provider_calls"] += 1
        if config.id in self._providers:
            raise ValueError(f"Provider with id '{config.id}' is already registered.")
        config.created_at = datetime.now(timezone.utc).isoformat()
        config.updated_at = config.created_at
        self._providers[config.id] = config
        self._save()
        logger.info("Registered provider: %s (%s)", config.name, config.provider_type.value)
        return config

    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        self._telemetry["get_provider_calls"] += 1
        return self._providers.get(provider_id)

    def update_provider(self, provider_id: str, updates: dict) -> Optional[ProviderConfig]:
        self._telemetry["update_provider_calls"] += 1
        config = self._providers.get(provider_id)
        if not config:
            logger.warning("Attempted to update unknown provider: %s", provider_id)
            return None
        for key, value in updates.items():
            if hasattr(config, key) and key not in ("id", "created_at"):
                if key == "provider_type":
                    setattr(config, key, ProviderType(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(config, key, ProviderStatus(value) if isinstance(value, str) else value)
                else:
                    setattr(config, key, value)
        config.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated provider: %s", provider_id)
        return config

    def remove_provider(self, provider_id: str) -> bool:
        self._telemetry["remove_provider_calls"] += 1
        if provider_id in self._providers:
            del self._providers[provider_id]
            self._health.pop(provider_id, None)
            self._model_maps.pop(provider_id, None)
            self._save()
            logger.info("Removed provider: %s", provider_id)
            return True
        return False

    def list_providers(self) -> list[ProviderConfig]:
        self._telemetry["list_providers_calls"] += 1
        return list(self._providers.values())

    def get_providers_by_type(self, provider_type: ProviderType) -> list[ProviderConfig]:
        self._telemetry["get_providers_by_type_calls"] += 1
        return [p for p in self._providers.values() if p.provider_type == provider_type]

    def get_healthy_providers(self) -> list[ProviderConfig]:
        self._telemetry["get_healthy_providers_calls"] += 1
        return [p for p in self._providers.values() if p.status == ProviderStatus.ACTIVE]

    def check_provider_health(self, provider_id: str, latency_ms: float, success: bool) -> ProviderHealth:
        self._telemetry["check_provider_health_calls"] += 1
        prev = self._health.get(provider_id, [])
        error_count = 0
        success_count = 0
        for h in prev[-50:]:
            error_count += h.error_count
            success_count += h.success_count
        if success:
            success_count += 1
        else:
            error_count += 1
        total = error_count + success_count
        uptime = (success_count / total * 100.0) if total > 0 else 100.0

        status = ProviderStatus.ACTIVE
        if uptime < 90.0:
            status = ProviderStatus.DEGRADED
        if error_count > 10:
            status = ProviderStatus.DOWN

        health = ProviderHealth(
            provider_id=provider_id,
            status=status,
            latency_ms=latency_ms,
            error_count=error_count,
            success_count=success_count,
            uptime_percent=round(uptime, 2),
        )
        self._health[provider_id].append(health)
        self._save()
        return health

    def update_provider_status(self, provider_id: str, status: ProviderStatus) -> Optional[ProviderConfig]:
        self._telemetry["update_provider_status_calls"] += 1
        config = self._providers.get(provider_id)
        if not config:
            return None
        config.status = status
        config.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated provider %s status to %s", provider_id, status.value)
        return config

    def get_provider_stats(self) -> dict:
        type_counts = defaultdict(int)
        status_counts = defaultdict(int)
        for p in self._providers.values():
            type_counts[p.provider_type.value] += 1
            status_counts[p.status.value] += 1
        total_checks = sum(len(h) for h in self._health.values())
        avg_latency = 0.0
        if total_checks > 0:
            all_latencies = [h.latency_ms for hl in self._health.values() for h in hl]
            avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
        return {
            "total_providers": len(self._providers),
            "type_distribution": dict(type_counts),
            "status_distribution": dict(status_counts),
            "total_health_checks": total_checks,
            "avg_latency_ms": round(avg_latency, 2),
            "total_model_maps": sum(len(m) for m in self._model_maps.values()),
            "telemetry": dict(self._telemetry),
        }

    def add_model_map(self, model_map: ProviderModelMap) -> ProviderModelMap:
        self._model_maps[model_map.provider_id].append(model_map)
        self._save()
        return model_map

    def get_model_maps(self, provider_id: str) -> list[ProviderModelMap]:
        return list(self._model_maps.get(provider_id, []))


class ProviderFactory:
    def __init__(self, registry: ProviderRegistry):
        self._registry = registry
        self._telemetry: dict[str, int] = defaultdict(int)

    def get_client(self, provider_id: str) -> dict:
        self._telemetry["get_client_calls"] += 1
        config = self._registry.get_provider(provider_id)
        if not config:
            raise ValueError(f"No provider found with id '{provider_id}'")
        return {
            "provider_type": config.provider_type.value,
            "base_url": config.base_url,
            "api_key": config.api_key,
            "organization_id": config.organization_id,
            "timeout_seconds": config.timeout_seconds,
            "retry_count": config.retry_count,
            "supports_streaming": config.supports_streaming,
            "default_model": config.default_model,
            "max_concurrency": config.max_concurrency,
        }

    def get_embedding_client(self, provider_id: str) -> dict:
        self._telemetry["get_embedding_client_calls"] += 1
        config = self._registry.get_provider(provider_id)
        if not config:
            raise ValueError(f"No provider found with id '{provider_id}'")
        return {
            "provider_type": config.provider_type.value,
            "base_url": config.base_url.rstrip("/") + "/embeddings" if not config.base_url.endswith("/embeddings") else config.base_url,
            "api_key": config.api_key,
            "timeout_seconds": config.timeout_seconds,
            "retry_count": config.retry_count,
        }

    def get_streaming_client(self, provider_id: str) -> dict:
        self._telemetry["get_streaming_client_calls"] += 1
        config = self._registry.get_provider(provider_id)
        if not config:
            raise ValueError(f"No provider found with id '{provider_id}'")
        if not config.supports_streaming:
            raise ValueError(f"Provider '{config.name}' does not support streaming.")
        return {
            "provider_type": config.provider_type.value,
            "base_url": config.base_url,
            "api_key": config.api_key,
            "timeout_seconds": config.timeout_seconds * 2,
            "stream": True,
        }

    def test_connection(self, provider_id: str) -> dict:
        self._telemetry["test_connection_calls"] += 1
        config = self._registry.get_provider(provider_id)
        if not config:
            return {"success": False, "error": "Provider not found"}
        start = time.time()
        try:
            import urllib.request
            endpoint = config.health_endpoint or config.base_url
            req = urllib.request.Request(endpoint, method="HEAD")
            urllib.request.urlopen(req, timeout=config.timeout_seconds)
            latency = (time.time() - start) * 1000
            self._registry.check_provider_health(provider_id, latency, True)
            return {"success": True, "latency_ms": round(latency, 2), "provider": config.name}
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._registry.check_provider_health(provider_id, latency, False)
            return {"success": False, "error": str(e), "latency_ms": round(latency, 2)}

    def list_available_models(self, provider_id: str) -> list[dict]:
        self._telemetry["list_available_models_calls"] += 1
        config = self._registry.get_provider(provider_id)
        if not config:
            raise ValueError(f"No provider found with id '{provider_id}'")
        return [{"model_name": m, "provider": config.name} for m in config.models]


class ModelProviderManager(ProviderRegistry, ProviderFactory):
    def __init__(self, storage_dir: str = "provider_registry_data"):
        ProviderRegistry.__init__(self, storage_dir=storage_dir)
        ProviderFactory.__init__(self, registry=self)

    def auto_discover_providers(self, provider_types: Optional[list[ProviderType]] = None) -> list[ProviderConfig]:
        self._telemetry["auto_discover_providers_calls"] += 1
        discovered = []
        types_to_check = provider_types or list(ProviderType.__members__.values())
        for ptype in types_to_check:
            defaults = BUILTIN_PROVIDER_DEFAULTS.get(ptype)
            if not defaults:
                continue
            existing = self.get_providers_by_type(ptype)
            if existing:
                continue
            pid = f"{ptype.value}_{uuid.uuid4().hex[:8]}"
            config = ProviderConfig(
                id=pid,
                provider_type=ptype,
                name=ptype.value.replace("_", " ").title(),
                **defaults,
            )
            self.register_provider(config)
            discovered.append(config)
            logger.info("Auto-discovered and registered provider: %s", config.name)
        return discovered

    def sync_models(self, provider_id: str, model_names: list[str]) -> list[ProviderModelMap]:
        self._telemetry["sync_models_calls"] += 1
        config = self.get_provider(provider_id)
        if not config:
            raise ValueError(f"No provider found with id '{provider_id}'")
        config.models = list(set(config.models + model_names))
        config.updated_at = datetime.now(timezone.utc).isoformat()
        maps = []
        for mname in model_names:
            mmap = ProviderModelMap(
                provider_id=provider_id,
                model_name=mname,
            )
            self.add_model_map(mmap)
            maps.append(mmap)
        self._save()
        logger.info("Synced %d models for provider %s", len(model_names), provider_id)
        return maps

    def get_provider_for_model(self, model_name: str) -> Optional[ProviderConfig]:
        self._telemetry["get_provider_for_model_calls"] += 1
        for pid, maps in self._model_maps.items():
            for m in maps:
                if m.model_name == model_name or model_name in m.aliases:
                    return self._providers.get(pid)
        for config in self._providers.values():
            if model_name in config.models or config.default_model == model_name:
                return config
        return None
