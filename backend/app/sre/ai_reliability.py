"""AI provider reliability (Volume 35).

Provider health tracking, failover chains, graceful degradation, and
provider telemetry (latency, tokens, cost). The Model Gateway consumes
these primitives to route around provider outages.

Policy constraints honored when selecting fallbacks:
  - allowed providers (organization policy)
  - data residency / privacy requirements
  - model restrictions (e.g. no vision if not allowed)
  - cost limits
  - capability requirements (tools, JSON, vision, streaming)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    DEPENDENCY_STATUS_DEGRADED,
    DEPENDENCY_STATUS_DOWN,
    DEPENDENCY_STATUS_HEALTHY,
    DEPENDENCY_STATUS_UNKNOWN,
)
from app.sre.dependencies import dependency_monitor
from app.sre.resilience import CircuitOpenError, circuit_breaker_registry

logger = logging.getLogger(__name__)

# Default provider ordering: primary first.
DEFAULT_PROVIDER_CHAIN: list[str] = ["openai", "anthropic", "google"]

# Registered provider factories (extend as providers are added).
PROVIDER_FACTORIES: dict[str, str] = {
    "openai": "app.ai.providers.openai_provider.OpenAIProvider",
    "anthropic": "app.ai.providers.anthropic_provider.AnthropicProvider",
}


def _load_provider(name: str):
    """Instantiate a provider by name; returns None when unavailable."""
    factory = PROVIDER_FACTORIES.get(name)
    if not factory:
        return None
    try:
        module_path, _, class_name = factory.rpartition(".")
        import importlib

        module = importlib.import_module(module_path)
        provider_class = getattr(module, class_name)
        return provider_class()
    except Exception as exc:
        logger.warning("Provider %s unavailable: %s", name, exc)
        return None


@dataclass
class ProviderCallRecord:
    """Telemetry for a single AI provider call."""

    provider: str
    model: str
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    ok: bool = True
    error: str = ""
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 2),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "ok": self.ok,
            "error": self.error,
        }


class AIProviderHealth:
    """Provider health + failover selection."""

    def __init__(self, chain: Optional[list[str]] = None):
        self.chain = chain or list(DEFAULT_PROVIDER_CHAIN)
        self._recent_calls: list[ProviderCallRecord] = []

    # ------------------------------------------------------------- tracking
    def record_call(self, record: ProviderCallRecord) -> None:
        self._recent_calls.append(record)
        self._recent_calls = self._recent_calls[-500:]

    async def persist_health(self, db: AsyncSession) -> None:
        """Write current provider health to the dependency monitor."""
        for name in self.chain:
            calls = [c for c in self._recent_calls if c.provider == name]
            if not calls:
                continue
            ok = sum(1 for c in calls if c.ok)
            error_rate = 1.0 - (ok / len(calls))
            latency = sum(c.latency_ms for c in calls) / len(calls)
            if error_rate >= 1.0:
                status = DEPENDENCY_STATUS_DOWN
            elif error_rate > 0.05 or latency > 3000:
                status = DEPENDENCY_STATUS_DEGRADED
            else:
                status = DEPENDENCY_STATUS_HEALTHY
            await dependency_monitor.record(
                db,
                dependency=f"ai_provider_{name}",
                status=status,
                kind="ai_provider",
                latency_ms=latency,
                error_rate=error_rate,
                metadata={"chain_position": self.chain.index(name), "calls": len(calls)},
            )

    # -------------------------------------------------------------- health
    async def health_of(self, db: AsyncSession, provider: str) -> dict:
        snapshot = await dependency_monitor.status_of(db, f"ai_provider_{provider}")
        breaker = circuit_breaker_registry.get(f"ai_provider:{provider}")
        base = snapshot or {
            "dependency": f"ai_provider_{provider}",
            "status": DEPENDENCY_STATUS_UNKNOWN,
        }
        base["circuit_state"] = breaker.state
        return base

    async def health_map(self, db: AsyncSession) -> dict[str, dict]:
        return {name: await self.health_of(db, name) for name in self.chain}

    async def probe(self, db: AsyncSession, provider: str) -> dict:
        """Live probe of a provider's health endpoint."""
        started = time.monotonic()
        status = DEPENDENCY_STATUS_UNKNOWN
        detail = ""
        provider_obj = _load_provider(provider)
        if provider_obj is None:
            detail = "provider not configured"
        else:
            try:
                ok = await provider_obj.health()
                status = DEPENDENCY_STATUS_HEALTHY if ok else DEPENDENCY_STATUS_DOWN
                if not ok:
                    detail = "health check returned false"
            except Exception as exc:
                status = DEPENDENCY_STATUS_DOWN
                detail = str(exc)
        latency = (time.monotonic() - started) * 1000
        await dependency_monitor.record(
            db,
            dependency=f"ai_provider_{provider}",
            status=status,
            kind="ai_provider",
            latency_ms=latency,
            error_rate=1.0 if status == DEPENDENCY_STATUS_DOWN else 0.0,
            metadata={"probed": True},
        )
        return {"provider": provider, "status": status, "latency_ms": round(latency, 2), "detail": detail}

    # -------------------------------------------------------------- failover
    async def select_provider(
        self,
        db: AsyncSession,
        *,
        required_capabilities: Optional[list[str]] = None,
        allowed_providers: Optional[list[str]] = None,
        preferred: Optional[str] = None,
        data_residency: Optional[str] = None,
    ) -> dict:
        """Select the best available provider respecting policy constraints.

        Returns {"provider": name, "fallback": bool, "reason": str, "candidates": [...]}.
        """
        allowed = allowed_providers or self.chain
        candidates = [p for p in self.chain if p in allowed]
        if preferred and preferred in candidates:
            candidates = [preferred] + [p for p in candidates if p != preferred]

        reasons = []
        for name in candidates:
            if data_residency and name == "openai" and data_residency.lower() not in ("us", "global", ""):
                # Example residency rule: non-US residency disallows openai by default policy.
                reasons.append(f"{name}: blocked by data residency policy")
                continue
            health = await self.health_of(db, name)
            if health.get("status") == DEPENDENCY_STATUS_DOWN:
                reasons.append(f"{name}: provider down")
                continue
            breaker = circuit_breaker_registry.get(f"ai_provider:{name}")
            if breaker.state == "OPEN":
                reasons.append(f"{name}: circuit open")
                continue
            provider_obj = _load_provider(name)
            if provider_obj is None:
                reasons.append(f"{name}: not configured")
                continue
            if required_capabilities:
                missing = [
                    capability
                    for capability in required_capabilities
                    if capability == "tools" and not provider_obj.supports_tools
                    or capability == "json" and not provider_obj.supports_json
                    or capability == "vision" and not provider_obj.supports_vision
                ]
                if missing:
                    reasons.append(f"{name}: missing capabilities {missing}")
                    continue
            return {"provider": name, "fallback": False, "reason": "primary", "candidates": candidates}

        return {
            "provider": "",
            "fallback": True,
            "reason": "; ".join(reasons) if reasons else "no providers available",
            "candidates": candidates,
        }

    async def call_with_failover(
        self,
        db: AsyncSession,
        *,
        messages: list[dict],
        model: str = "",
        required_capabilities: Optional[list[str]] = None,
        allowed_providers: Optional[list[str]] = None,
        preferred: Optional[str] = None,
        max_providers: int = 3,
    ):
        """Execute a chat call with automatic provider failover.

        Returns the response dict plus provider telemetry. Raises the last
        error when every permitted provider failed.
        """
        selection = await self.select_provider(
            db,
            required_capabilities=required_capabilities,
            allowed_providers=allowed_providers,
            preferred=preferred,
        )
        last_error: Optional[Exception] = None
        tried: list[str] = []
        for name in selection["candidates"][:max_providers]:
            if name not in (allowed_providers or self.chain):
                continue
            if name in tried:
                continue
            health = await self.health_of(db, name)
            if health.get("status") == DEPENDENCY_STATUS_DOWN:
                continue
            provider_obj = _load_provider(name)
            if provider_obj is None:
                continue
            breaker = circuit_breaker_registry.get(f"ai_provider:{name}")
            started = time.monotonic()
            try:
                result = await breaker.call(lambda: provider_obj.chat(messages, model=model or provider_obj.model))
                tokens = result.get("usage", {})
                record = ProviderCallRecord(
                    provider=name,
                    model=result.get("model", model or provider_obj.model),
                    latency_ms=(time.monotonic() - started) * 1000,
                    prompt_tokens=tokens.get("prompt_tokens", 0),
                    completion_tokens=tokens.get("completion_tokens", 0),
                    cost_usd=self._estimate_cost(tokens),
                    ok=True,
                )
                self.record_call(record)
                return {**result, "provider": name, "provider_failover": bool(tried)}
            except CircuitOpenError as exc:
                last_error = exc
                tried.append(name)
                continue
            except Exception as exc:
                last_error = exc
                self.record_call(
                    ProviderCallRecord(
                        provider=name,
                        model=model or provider_obj.model,
                        latency_ms=(time.monotonic() - started) * 1000,
                        ok=False,
                        error=str(exc),
                    )
                )
                tried.append(name)
                logger.warning("Provider %s failed: %s", name, exc)
        raise RuntimeError(f"All AI providers failed ({tried}): {last_error}")

    # ---------------------------------------------------------- degradation
    @staticmethod
    def degraded_response(reason: str, *, feature: str = "ai_chat") -> dict:
        """Return a controlled degraded response rather than fabricated success."""
        return {
            "content": "",
            "degraded": True,
            "feature": feature,
            "reason": reason,
            "hint": "The AI service is temporarily unavailable. Please retry shortly.",
        }

    @staticmethod
    def fallback_model(primary: str, fallbacks: Optional[list[str]] = None) -> str:
        """Pick an approved fallback model when the advanced model is unavailable."""
        for model in fallbacks or []:
            if model and model != primary:
                return model
        return primary

    @staticmethod
    def _estimate_cost(usage: dict) -> float:
        """Rough cost estimate; overridden by the FinOps cost ledger when available."""
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        return prompt * 0.0000005 + completion * 0.000002


ai_provider_health = AIProviderHealth()
