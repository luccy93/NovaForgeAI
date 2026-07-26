import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    BETA = "beta"
    EXPERIMENTAL = "experimental"
    RETIRED = "retired"


class ModelCapability(Enum):
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    CODE_GENERATION = "code_generation"
    TOOL_CALLING = "tool_calling"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    AUDIO = "audio"
    REASONING = "reasoning"
    IMAGE_GENERATION = "image_generation"
    STREAMING = "streaming"
    JSON_MODE = "json_mode"
    RAG = "rag"
    LONG_CONTEXT = "long_context"


@dataclass
class ModelEntry:
    id: str
    name: str
    provider: str
    version: str
    capabilities: list[ModelCapability]
    context_window: int
    max_output_tokens: int
    embedding_dimension: int = 0
    pricing_prompt_per_million: float = 0.0
    pricing_completion_per_million: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    throughput_tps: float = 0.0
    status: ModelStatus = ModelStatus.EXPERIMENTAL
    release_date: str = ""
    license: str = ""
    tags: list[str] = field(default_factory=list)
    health_score: float = 1.0
    deprecation_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["capabilities"] = [c.value for c in self.capabilities]
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelEntry":
        data["capabilities"] = [ModelCapability(c) for c in data["capabilities"]]
        data["status"] = ModelStatus(data["status"])
        return cls(**data)


@dataclass
class ModelVersion:
    id: str
    model_id: str
    version: str
    status: ModelStatus
    changelog: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelVersion":
        data["status"] = ModelStatus(data["status"])
        return cls(**data)


@dataclass
class ProviderRegistration:
    provider_name: str
    base_url: str
    api_key_required: bool = True
    supports_streaming: bool = True
    models: list[str] = field(default_factory=list)
    health_endpoint: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderRegistration":
        return cls(**data)


@dataclass
class ModelHealthCheck:
    model_id: str
    status: str
    latency_ms: float
    error_rate: float
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ModelHealthCheck":
        return cls(**data)


class ModelRegistry:
    def __init__(self, storage_dir: str = "model_registry_data"):
        self.storage_dir = storage_dir
        self._models: dict[str, ModelEntry] = {}
        self._versions: dict[str, list[ModelVersion]] = defaultdict(list)
        self._providers: dict[str, ProviderRegistration] = {}
        self._health_checks: dict[str, list[ModelHealthCheck]] = defaultdict(list)
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _models_path(self) -> str:
        return os.path.join(self.storage_dir, "models.json")

    def _versions_path(self) -> str:
        return os.path.join(self.storage_dir, "versions.json")

    def _providers_path(self) -> str:
        return os.path.join(self.storage_dir, "providers.json")

    def _health_path(self) -> str:
        return os.path.join(self.storage_dir, "health.json")

    def _save(self) -> None:
        try:
            models_data = {mid: m.to_dict() for mid, m in self._models.items()}
            with open(self._models_path(), "w", encoding="utf-8") as f:
                json.dump(models_data, f, indent=2, default=str)

            versions_data = {mid: [v.to_dict() for v in vlist] for mid, vlist in self._versions.items()}
            with open(self._versions_path(), "w", encoding="utf-8") as f:
                json.dump(versions_data, f, indent=2, default=str)

            providers_data = {pn: p.to_dict() for pn, p in self._providers.items()}
            with open(self._providers_path(), "w", encoding="utf-8") as f:
                json.dump(providers_data, f, indent=2, default=str)

            health_data = {mid: [h.to_dict() for h in hlist] for mid, hlist in self._health_checks.items()}
            with open(self._health_path(), "w", encoding="utf-8") as f:
                json.dump(health_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save registry data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._models_path()):
                with open(self._models_path(), "r", encoding="utf-8") as f:
                    models_data = json.load(f)
                for mid, data in models_data.items():
                    try:
                        self._models[mid] = ModelEntry.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed model %s: %s", mid, e)

            if os.path.exists(self._versions_path()):
                with open(self._versions_path(), "r", encoding="utf-8") as f:
                    versions_data = json.load(f)
                for mid, vlist in versions_data.items():
                    self._versions[mid] = []
                    for vdata in vlist:
                        try:
                            self._versions[mid].append(ModelVersion.from_dict(vdata))
                        except Exception as e:
                            logger.warning("Skipping malformed version for %s: %s", mid, e)

            if os.path.exists(self._providers_path()):
                with open(self._providers_path(), "r", encoding="utf-8") as f:
                    providers_data = json.load(f)
                for pn, data in providers_data.items():
                    try:
                        self._providers[pn] = ProviderRegistration.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed provider %s: %s", pn, e)

            if os.path.exists(self._health_path()):
                with open(self._health_path(), "r", encoding="utf-8") as f:
                    health_data = json.load(f)
                for mid, hlist in health_data.items():
                    self._health_checks[mid] = []
                    for hdata in hlist:
                        try:
                            self._health_checks[mid].append(ModelHealthCheck.from_dict(hdata))
                        except Exception as e:
                            logger.warning("Skipping malformed health check for %s: %s", mid, e)
        except Exception as e:
            logger.error("Failed to load registry data: %s", e, exc_info=True)

    def register_model(self, model: ModelEntry) -> ModelEntry:
        self._telemetry["register_model_calls"] += 1
        if model.id in self._models:
            raise ValueError(f"Model with id '{model.id}' is already registered.")
        model.created_at = datetime.now(timezone.utc).isoformat()
        model.updated_at = model.created_at
        self._models[model.id] = model

        version_entry = ModelVersion(
            id=str(uuid.uuid4()),
            model_id=model.id,
            version=model.version,
            status=model.status,
            changelog="Initial registration",
        )
        self._versions[model.id].append(version_entry)

        self._save()
        logger.info("Registered model: %s (%s v%s)", model.name, model.provider, model.version)
        return model

    def get_model(self, model_id: str) -> Optional[ModelEntry]:
        self._telemetry["get_model_calls"] += 1
        return self._models.get(model_id)

    def update_model(self, model_id: str, updates: dict) -> Optional[ModelEntry]:
        self._telemetry["update_model_calls"] += 1
        model = self._models.get(model_id)
        if not model:
            logger.warning("Attempted to update unknown model: %s", model_id)
            return None
        for key, value in updates.items():
            if hasattr(model, key) and key not in ("id", "created_at"):
                if key == "capabilities":
                    setattr(model, key, [ModelCapability(c) if isinstance(c, str) else c for c in value])
                elif key == "status":
                    setattr(model, key, ModelStatus(value) if isinstance(value, str) else value)
                else:
                    setattr(model, key, value)
        model.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated model: %s", model_id)
        return model

    def deprecate_model(self, model_id: str, deprecation_date: Optional[str] = None) -> Optional[ModelEntry]:
        self._telemetry["deprecate_model_calls"] += 1
        model = self._models.get(model_id)
        if not model:
            return None
        model.status = ModelStatus.DEPRECATED
        model.deprecation_date = deprecation_date or datetime.now(timezone.utc).isoformat()
        model.updated_at = datetime.now(timezone.utc).isoformat()

        version_entry = ModelVersion(
            id=str(uuid.uuid4()),
            model_id=model.id,
            version=model.version,
            status=ModelStatus.DEPRECATED,
            changelog="Model deprecated",
        )
        self._versions[model.id].append(version_entry)
        self._save()
        logger.info("Deprecated model: %s", model_id)
        return model

    def rollback_version(self, model_id: str, target_version: str) -> Optional[ModelEntry]:
        self._telemetry["rollback_version_calls"] += 1
        model = self._models.get(model_id)
        if not model:
            return None
        model.version = target_version
        model.updated_at = datetime.now(timezone.utc).isoformat()

        version_entry = ModelVersion(
            id=str(uuid.uuid4()),
            model_id=model.id,
            version=target_version,
            status=model.status,
            changelog=f"Rolled back to version {target_version}",
        )
        self._versions[model.id].append(version_entry)
        self._save()
        logger.info("Rolled back model %s to version %s", model_id, target_version)
        return model

    def list_models(self) -> list[ModelEntry]:
        self._telemetry["list_models_calls"] += 1
        return list(self._models.values())

    def search_models(self, query: str) -> list[ModelEntry]:
        self._telemetry["search_models_calls"] += 1
        q = query.lower()
        results = []
        for model in self._models.values():
            if q in model.name.lower() or q in model.provider.lower() or q in model.id.lower():
                results.append(model)
        return results

    def get_model_by_capability(self, capability: ModelCapability) -> list[ModelEntry]:
        self._telemetry["get_model_by_capability_calls"] += 1
        return [m for m in self._models.values() if capability in m.capabilities]

    def get_model_by_provider(self, provider: str) -> list[ModelEntry]:
        self._telemetry["get_model_by_provider_calls"] += 1
        return [m for m in self._models.values() if m.provider.lower() == provider.lower()]

    def get_models_by_status(self, status: ModelStatus) -> list[ModelEntry]:
        self._telemetry["get_models_by_status_calls"] += 1
        return [m for m in self._models.values() if m.status == status]

    def check_model_health(self, model_id: str, latency_ms: float, error_rate: float, status: str = "healthy") -> ModelHealthCheck:
        self._telemetry["check_model_health_calls"] += 1
        check = ModelHealthCheck(
            model_id=model_id,
            status=status,
            latency_ms=latency_ms,
            error_rate=error_rate,
        )
        self._health_checks[model_id].append(check)
        self._save()
        return check

    def update_health_score(self, model_id: str) -> Optional[float]:
        self._telemetry["update_health_score_calls"] += 1
        checks = self._health_checks.get(model_id, [])
        if not checks:
            return None
        recent = checks[-10:]
        avg_latency = sum(c.latency_ms for c in recent) / len(recent)
        avg_error = sum(c.error_rate for c in recent) / len(recent)
        latency_score = max(0.0, 1.0 - (avg_latency / 10000.0))
        error_score = 1.0 - avg_error
        health = (latency_score * 0.4 + error_score * 0.6)
        health = max(0.0, min(1.0, health))
        model = self._models.get(model_id)
        if model:
            model.health_score = round(health, 4)
            model.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
        return round(health, 4)

    def get_version_history(self, model_id: str) -> list[ModelVersion]:
        self._telemetry["get_version_history_calls"] += 1
        return list(self._versions.get(model_id, []))

    def compare_versions(self, model_id: str, version_a: str, version_b: str) -> dict:
        self._telemetry["compare_versions_calls"] += 1
        versions = self._versions.get(model_id, [])
        va = next((v for v in versions if v.version == version_a), None)
        vb = next((v for v in versions if v.version == version_b), None)
        return {
            "model_id": model_id,
            "version_a": va.to_dict() if va else None,
            "version_b": vb.to_dict() if vb else None,
            "comparison": {
                "same_status": va.status == vb.status if va and vb else None,
                "same_version_string": va.version == vb.version if va and vb else None,
            },
        }

    def get_registry_stats(self) -> dict:
        status_counts = defaultdict(int)
        provider_counts = defaultdict(int)
        total_capabilities = 0
        for m in self._models.values():
            status_counts[m.status.value] += 1
            provider_counts[m.provider] += 1
            total_capabilities += len(m.capabilities)

        return {
            "total_models": len(self._models),
            "total_versions": sum(len(v) for v in self._versions.values()),
            "total_providers": len(self._providers),
            "total_health_checks": sum(len(h) for h in self._health_checks.values()),
            "status_distribution": dict(status_counts),
            "provider_distribution": dict(provider_counts),
            "avg_capabilities_per_model": round(total_capabilities / len(self._models), 2) if self._models else 0,
            "avg_health_score": round(sum(m.health_score for m in self._models.values()) / len(self._models), 4) if self._models else 0,
            "telemetry": dict(self._telemetry),
        }

    def register_provider(self, provider: ProviderRegistration) -> ProviderRegistration:
        self._telemetry["register_provider_calls"] += 1
        self._providers[provider.provider_name] = provider
        self._save()
        logger.info("Registered provider: %s", provider.provider_name)
        return provider

    def get_provider(self, provider_name: str) -> Optional[ProviderRegistration]:
        return self._providers.get(provider_name)
