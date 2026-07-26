import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class FailoverStrategy(Enum):
    RETRY_SAME_PROVIDER = "retry_same_provider"
    FALLBACK_PROVIDER = "fallback_provider"
    CIRCUIT_BREAKER = "circuit_breaker"
    CACHE_FALLBACK = "cache_fallback"
    GRACEFUL_DEGRADE = "graceful_degrade"
    QUEUE_RETRY = "queue_retry"


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    RECOVERING = "recovering"


class FailoverReason(Enum):
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_DOWN = "provider_down"
    AUTH_ERROR = "auth_error"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    COST_EXCEEDED = "cost_exceeded"
    UNKNOWN = "unknown"


@dataclass
class FailoverConfig:
    id: str = ""
    model_id: str = ""
    primary_provider: str = ""
    fallback_providers: list[str] = field(default_factory=list)
    strategy: FailoverStrategy = FailoverStrategy.FALLBACK_PROVIDER
    max_retries: int = 3
    retry_delay_ms: int = 1000
    timeout_ms: int = 30000
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout_ms: int = 60000
    cache_fallback_ttl: int = 3600
    graceful_message: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FailoverConfig":
        if "strategy" in data:
            data["strategy"] = FailoverStrategy(data["strategy"])
        return cls(**data)


@dataclass
class CircuitBreaker:
    id: str = ""
    model_id: str = ""
    provider: str = ""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    threshold: int = 5
    timeout_ms: int = 60000
    last_failure: str = ""
    last_success: str = ""
    opened_at: str = ""
    half_open_at: str = ""
    recovery_attempts: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CircuitBreaker":
        if "state" in data:
            data["state"] = CircuitState(data["state"])
        return cls(**data)


@dataclass
class FailoverAttempt:
    id: str = ""
    request_id: str = ""
    model_id: str = ""
    primary_provider: str = ""
    fallback_provider: Optional[str] = None
    attempt: int = 1
    reason: FailoverReason = FailoverReason.UNKNOWN
    latency_ms: float = 0.0
    success: bool = False
    timestamp: str = ""
    error: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["reason"] = self.reason.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FailoverAttempt":
        if "reason" in data:
            data["reason"] = FailoverReason(data["reason"])
        return cls(**data)


@dataclass
class CacheFallback:
    id: str = ""
    request_hash: str = ""
    model: str = ""
    response: dict = field(default_factory=dict)
    created_at: str = ""
    ttl_seconds: int = 3600
    hit_count: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def is_expired(self) -> bool:
        created = datetime.fromisoformat(self.created_at)
        elapsed = (datetime.now(timezone.utc) - created).total_seconds()
        return elapsed > self.ttl_seconds

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CacheFallback":
        return cls(**data)


class CircuitBreakerManager:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/failover")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.breakers: dict[str, CircuitBreaker] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_breaker_path(self, breaker_id: str) -> Path:
        return self.storage_dir / f"breaker_{breaker_id}.json"

    def _save(self, breaker: CircuitBreaker):
        path = self._get_breaker_path(breaker.id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(breaker.to_dict(), f, indent=2)
            self.telemetry["breakers_saved"] += 1
        except Exception as e:
            logger.error("Failed to save breaker %s: %s", breaker.id, e)

    def _load(self):
        if not self.storage_dir.exists():
            return
        try:
            for path in self.storage_dir.glob("breaker_*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    breaker = CircuitBreaker.from_dict(data)
                    self.breakers[breaker.id] = breaker
                except Exception as e:
                    logger.warning("Failed to load breaker from %s: %s", path, e)
            self.telemetry["breakers_loaded"] = len(self.breakers)
        except Exception as e:
            logger.error("Failed to load breakers: %s", e)

    def create_breaker(self, model_id: str, provider: str, threshold: int = 5, timeout_ms: int = 60000) -> CircuitBreaker:
        breaker = CircuitBreaker(
            model_id=model_id,
            provider=provider,
            threshold=threshold,
            timeout_ms=timeout_ms,
        )
        self.breakers[breaker.id] = breaker
        self._save(breaker)
        self.telemetry["breakers_created"] += 1
        logger.info("Created circuit breaker %s for %s/%s", breaker.id, model_id, provider)
        return breaker

    def get_breaker(self, breaker_id: str) -> Optional[CircuitBreaker]:
        return self.breakers.get(breaker_id)

    def record_success(self, breaker_id: str):
        breaker = self.breakers.get(breaker_id)
        if not breaker:
            return
        breaker.failure_count = 0
        breaker.last_success = datetime.now(timezone.utc).isoformat()
        if breaker.state in (CircuitState.OPEN, CircuitState.HALF_OPEN, CircuitState.RECOVERING):
            breaker.state = CircuitState.CLOSED
            breaker.opened_at = ""
            breaker.half_open_at = ""
            logger.info("Circuit breaker %s closed after success", breaker_id)
        self._save(breaker)
        self.telemetry["breaker_successes"] += 1

    def record_failure(self, breaker_id: str):
        breaker = self.breakers.get(breaker_id)
        if not breaker:
            return
        breaker.failure_count += 1
        breaker.last_failure = datetime.now(timezone.utc).isoformat()
        if breaker.failure_count >= breaker.threshold and breaker.state == CircuitState.CLOSED:
            breaker.state = CircuitState.OPEN
            breaker.opened_at = datetime.now(timezone.utc).isoformat()
            logger.warning("Circuit breaker %s OPEN after %d failures", breaker_id, breaker.failure_count)
        elif breaker.state == CircuitState.HALF_OPEN:
            breaker.state = CircuitState.OPEN
            breaker.opened_at = datetime.now(timezone.utc).isoformat()
            breaker.recovery_attempts += 1
            logger.warning("Circuit breaker %s back to OPEN from HALF_OPEN", breaker_id)
        self._save(breaker)
        self.telemetry["breaker_failures"] += 1

    def is_open(self, breaker_id: str) -> bool:
        breaker = self.breakers.get(breaker_id)
        if not breaker:
            return False
        if breaker.state == CircuitState.OPEN:
            if breaker.opened_at:
                opened = datetime.fromisoformat(breaker.opened_at)
                elapsed = (datetime.now(timezone.utc) - opened).total_seconds() * 1000
                if elapsed >= breaker.timeout_ms:
                    breaker.state = CircuitState.HALF_OPEN
                    breaker.half_open_at = datetime.now(timezone.utc).isoformat()
                    self._save(breaker)
                    self.telemetry["breaker_half_open"] += 1
                    logger.info("Circuit breaker %s transitioned to HALF_OPEN", breaker_id)
                    return False
            return True
        return False

    def is_half_open(self, breaker_id: str) -> bool:
        breaker = self.breakers.get(breaker_id)
        return breaker is not None and breaker.state == CircuitState.HALF_OPEN

    def reset(self, breaker_id: str):
        breaker = self.breakers.get(breaker_id)
        if not breaker:
            return
        breaker.state = CircuitState.CLOSED
        breaker.failure_count = 0
        breaker.opened_at = ""
        breaker.half_open_at = ""
        breaker.recovery_attempts = 0
        self._save(breaker)
        self.telemetry["breakers_reset"] += 1
        logger.info("Circuit breaker %s manually reset", breaker_id)

    def get_breaker_status(self, breaker_id: str) -> dict:
        breaker = self.breakers.get(breaker_id)
        if not breaker:
            return {"error": "breaker_not_found"}
        return {
            "id": breaker.id,
            "model_id": breaker.model_id,
            "provider": breaker.provider,
            "state": breaker.state.value,
            "failure_count": breaker.failure_count,
            "threshold": breaker.threshold,
            "is_open": self.is_open(breaker_id),
            "is_half_open": self.is_half_open(breaker_id),
            "recovery_attempts": breaker.recovery_attempts,
        }

    def get_all_breakers(self) -> list[CircuitBreaker]:
        return list(self.breakers.values())


class FailoverHandler:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/failover")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.attempts: dict[str, FailoverAttempt] = {}
        self.configs: dict[str, FailoverConfig] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_attempts_path(self) -> Path:
        return self.storage_dir / "failover_attempts.json"

    def _get_configs_path(self) -> Path:
        return self.storage_dir / "failover_configs.json"

    def _save_attempts(self):
        path = self._get_attempts_path()
        try:
            data = {k: v.to_dict() for k, v in self.attempts.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save failover attempts: %s", e)

    def _save_configs(self):
        path = self._get_configs_path()
        try:
            data = {k: v.to_dict() for k, v in self.configs.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save failover configs: %s", e)

    def _load(self):
        try:
            path = self._get_attempts_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.attempts = {k: FailoverAttempt.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load failover attempts: %s", e)
        try:
            path = self._get_configs_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.configs = {k: FailoverConfig.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load failover configs: %s", e)

    def handle_failover(self, request_id: str, model_id: str, primary_provider: str,
                        reason: FailoverReason, error: str = "") -> Optional[str]:
        config = None
        for c in self.configs.values():
            if c.model_id == model_id:
                config = c
                break
        if not config:
            config = FailoverConfig(model_id=model_id, primary_provider=primary_provider)
            self.configs[config.id] = config
            self._save_configs()

        fallback = self.get_fallback_provider(model_id, primary_provider)
        attempt = FailoverAttempt(
            request_id=request_id,
            model_id=model_id,
            primary_provider=primary_provider,
            fallback_provider=fallback,
            reason=reason,
            error=error,
        )
        self.attempts[attempt.id] = attempt
        self._save_attempts()
        self.telemetry["failovers_handled"] += 1
        logger.info("Failover handled for %s: %s -> %s (reason: %s)",
                     request_id, primary_provider, fallback, reason.value)
        return fallback

    def execute_with_retry(self, model_id: str, provider: str,
                           fn: callable, max_retries: int = 3,
                           retry_delay_ms: int = 1000) -> tuple[Any, bool]:
        last_error = None
        for attempt_num in range(1, max_retries + 1):
            try:
                start = time.time()
                result = fn()
                elapsed = (time.time() - start) * 1000
                self.telemetry["retry_successes"] += 1
                return result, True
            except Exception as e:
                last_error = e
                elapsed = 0
                if attempt_num < max_retries:
                    time.sleep(retry_delay_ms / 1000)
                    self.telemetry["retries"] += 1
                    logger.warning("Retry %d/%d for %s/%s failed: %s",
                                   attempt_num, max_retries, model_id, provider, e)
        self.telemetry["retry_failures"] += 1
        logger.error("All %d retries exhausted for %s/%s: %s", max_retries, model_id, provider, last_error)
        return None, False

    def get_fallback_provider(self, model_id: str, primary_provider: str) -> Optional[str]:
        for config in self.configs.values():
            if config.model_id == model_id and config.primary_provider == primary_provider:
                if config.fallback_providers:
                    return config.fallback_providers[0]
                break
        return None

    def get_failover_history(self, request_id: Optional[str] = None) -> list[FailoverAttempt]:
        if request_id:
            return [a for a in self.attempts.values() if a.request_id == request_id]
        return list(self.attempts.values())

    def get_failover_stats(self) -> dict:
        total = len(self.attempts)
        successful = sum(1 for a in self.attempts.values() if a.success)
        failed = total - successful
        reasons = defaultdict(int)
        for a in self.attempts.values():
            reasons[a.reason.value] += 1
        return {
            "total_attempts": total,
            "successful": successful,
            "failed": failed,
            "success_rate": round(successful / total, 4) if total else 0.0,
            "reasons": dict(reasons),
            "telemetry": dict(self.telemetry),
        }

    def clear_failover_state(self):
        self.attempts.clear()
        self._save_attempts()
        self.telemetry["state_cleared"] += 1
        logger.info("Failover state cleared")


class CacheFallbackManager:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/failover")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.cache: dict[str, CacheFallback] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_cache_path(self) -> Path:
        return self.storage_dir / "cache_fallback.json"

    def _save(self):
        path = self._get_cache_path()
        try:
            data = {k: v.to_dict() for k, v in self.cache.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save cache fallback: %s", e)

    def _load(self):
        try:
            path = self._get_cache_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.cache = {k: CacheFallback.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load cache fallback: %s", e)

    def cache_response(self, request_hash: str, model: str, response: dict, ttl: int = 3600) -> CacheFallback:
        cached = CacheFallback(
            request_hash=request_hash,
            model=model,
            response=response,
            ttl_seconds=ttl,
        )
        self.cache[cached.id] = cached
        self._save()
        self.telemetry["cached_responses"] += 1
        return cached

    def get_cached(self, request_hash: str) -> Optional[dict]:
        for entry in self.cache.values():
            if entry.request_hash == request_hash:
                if entry.is_expired():
                    self.telemetry["cache_expired"] += 1
                    return None
                entry.hit_count += 1
                self._save()
                self.telemetry["cache_hits"] += 1
                return entry.response
        self.telemetry["cache_misses"] += 1
        return None

    def invalidate_cache(self, request_hash: Optional[str] = None):
        if request_hash:
            keys = [k for k, v in self.cache.items() if v.request_hash == request_hash]
            for k in keys:
                del self.cache[k]
            self.telemetry["cache_invalidated"] += len(keys)
        else:
            self.cache.clear()
            self.telemetry["cache_invalidated_all"] += 1
        self._save()

    def clear_expired(self):
        now = datetime.now(timezone.utc)
        expired = []
        for k, v in self.cache.items():
            created = datetime.fromisoformat(v.created_at)
            if (now - created).total_seconds() > v.ttl_seconds:
                expired.append(k)
        for k in expired:
            del self.cache[k]
        if expired:
            self._save()
            self.telemetry["expired_cleared"] += len(expired)
            logger.info("Cleared %d expired cache entries", len(expired))

    def get_cache_stats(self) -> dict:
        total = len(self.cache)
        expired_count = sum(1 for v in self.cache.values() if v.is_expired())
        total_hits = sum(v.hit_count for v in self.cache.values())
        return {
            "total_entries": total,
            "expired_entries": expired_count,
            "active_entries": total - expired_count,
            "total_hits": total_hits,
            "telemetry": dict(self.telemetry),
        }


class ModelFailoverManager(CircuitBreakerManager, FailoverHandler, CacheFallbackManager):
    def __init__(self, storage_dir: str = ""):
        CircuitBreakerManager.__init__(self, storage_dir)
        FailoverHandler.__init__(self, storage_dir)
        CacheFallbackManager.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)

    def execute_with_failover(self, model_id: str, provider: str, request_id: str,
                               fn: callable, request_hash: Optional[str] = None) -> tuple[Any, bool, Optional[str]]:
        config = None
        for c in self.configs.values():
            if c.model_id == model_id:
                config = c
                break

        if config and config.strategy == FailoverStrategy.CACHE_FALLBACK and request_hash:
            cached = self.get_cached(request_hash)
            if cached:
                self.telemetry["failover_cache_hit"] += 1
                return cached, True, "cache"

        if config and config.strategy == FailoverStrategy.CIRCUIT_BREAKER:
            for breaker in self.breakers.values():
                if breaker.model_id == model_id and breaker.provider == provider:
                    if self.is_open(breaker.id):
                        self.telemetry["failover_circuit_open"] += 1
                        fallback = self.get_fallback_provider(model_id, provider)
                        if fallback:
                            return self._try_fallback(model_id, fallback, request_id, fn, request_hash)
                        return None, False, "circuit_open_no_fallback"
                    break

        result, success = self.execute_with_retry(model_id, provider, fn)
        if success:
            for breaker in self.breakers.values():
                if breaker.model_id == model_id and breaker.provider == provider:
                    self.record_success(breaker.id)
                    break
            if config and config.strategy == FailoverStrategy.CACHE_FALLBACK and request_hash:
                self.cache_response(request_hash, model_id, {"result": result}, config.cache_fallback_ttl)
            self.telemetry["failover_success"] += 1
            return result, True, "primary"

        for breaker in self.breakers.values():
            if breaker.model_id == model_id and breaker.provider == provider:
                self.record_failure(breaker.id)
                break

        fallback_provider = self.get_fallback_provider(model_id, provider)
        if fallback_provider:
            self.telemetry["failover_fallback_used"] += 1
            return self._try_fallback(model_id, fallback_provider, request_id, fn, request_hash)

        self.telemetry["failover_all_failed"] += 1
        return None, False, "all_failed"

    def _try_fallback(self, model_id: str, fallback_provider: str, request_id: str,
                       fn: callable, request_hash: Optional[str] = None) -> tuple[Any, bool, Optional[str]]:
        if request_hash:
            cached = self.get_cached(request_hash)
            if cached:
                self.telemetry["failover_fallback_cache_hit"] += 1
                return cached, True, "fallback_cache"
        result, success = self.execute_with_retry(model_id, fallback_provider, fn)
        if success:
            self.telemetry["failover_fallback_success"] += 1
            return result, True, fallback_provider
        self.telemetry["failover_fallback_failed"] += 1
        return None, False, "fallback_failed"

    def get_failover_health(self) -> dict:
        breaker_count = len(self.breakers)
        open_breakers = sum(1 for b in self.breakers.values() if b.state == CircuitState.OPEN)
        cache_stats = self.get_cache_stats()
        failover_stats = self.get_failover_stats()
        return {
            "circuit_breakers": {
                "total": breaker_count,
                "open": open_breakers,
                "healthy": breaker_count - open_breakers,
            },
            "cache": cache_stats,
            "failover": failover_stats,
            "telemetry": dict(self.telemetry),
        }

    def get_system_resilience_score(self) -> float:
        total = len(self.breakers) or 1
        healthy = sum(1 for b in self.breakers.values() if b.state == CircuitState.CLOSED)
        breaker_score = healthy / total

        total_attempts = len(self.attempts) or 1
        successful = sum(1 for a in self.attempts.values() if a.success)
        failover_score = successful / total_attempts

        cache_entries = len(self.cache) or 1
        active = sum(1 for v in self.cache.values() if not v.is_expired())
        cache_score = active / cache_entries

        return round((breaker_score * 0.4 + failover_score * 0.35 + cache_score * 0.25) * 100, 2)
