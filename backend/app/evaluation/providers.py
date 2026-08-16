"""Model gateway adapter for evaluation (Volume 34).

Resolves providers through the existing NovaForge LLM provider layer
(app.ai.providers) without hard-coding any vendor. When no provider is
available (no API keys / offline), an evaluation-grade deterministic
reference model is used so benchmarks, judges and regression gates always
run. The reference model is not a real LLM — it is an explicit, labelled
fallback that keeps the platform operational in restricted environments.
"""
import logging
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_PROVIDER_CACHE: dict[str, Any] = {}


def resolve_provider(name: str = "") -> Any:
    """Resolve an LLMProvider from the existing provider registry by name."""
    if name in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[name]
    provider = None
    try:
        from app.ai.providers.openai_provider import OpenAIProvider
        from app.ai.providers.anthropic_provider import AnthropicProvider

        registry: dict[str, Any] = {}
        try:
            provider = OpenAIProvider()
            registry["openai"] = provider
        except Exception as exc:  # noqa: BLE001
            logger.debug("openai provider unavailable: %s", exc)
        try:
            provider = AnthropicProvider()
            registry["anthropic"] = provider
        except Exception as exc:  # noqa: BLE001
            logger.debug("anthropic provider unavailable: %s", exc)
        if name and name in registry:
            provider = registry[name]
        elif registry:
            provider = next(iter(registry.values()))
        _PROVIDER_CACHE[name] = provider
    except Exception as exc:  # noqa: BLE001
        logger.debug("no LLM providers resolvable: %s", exc)
        provider = None
    _PROVIDER_CACHE[name] = provider
    return provider


def _reference_score(expected: str, actual: str) -> float:
    """Deterministic, explainable similarity used by the reference model."""
    if not expected:
        return 0.5
    exp_tokens = set(re.findall(r"[a-z0-9_]+", expected.lower()))
    act_tokens = set(re.findall(r"[a-z0-9_]+", actual.lower()))
    if not exp_tokens:
        return 0.5
    overlap = len(exp_tokens & act_tokens)
    precision = overlap / max(1, len(act_tokens))
    recall = overlap / len(exp_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


class EvalModel:
    """Uniform scoring interface over any provider, with offline fallback."""

    def __init__(self, name: str = "", provider: Optional[Any] = None,
                 scorer: Optional[Callable[[str, str], float]] = None):
        self.name = name or "reference"
        self.provider = provider
        self.scorer = scorer or _reference_score
        self._mode = "provider" if provider is not None else "reference"

    @property
    def offline(self) -> bool:
        return self._mode == "reference"

    def model_id(self) -> str:
        if self.provider is not None:
            return getattr(self.provider, "model", "") or self.name
        return self.name

    async def complete(self, prompt: str, max_tokens: int = 1024,
                       temperature: float = 0.0) -> dict:
        if self.provider is not None:
            try:
                resp = await self.provider.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=max_tokens, temperature=temperature)
                return {"text": resp.get("content") or resp.get("text") or "",
                        "model": self.model_id(), "provider": True,
                        "usage": resp.get("usage", {})}
            except Exception as exc:  # noqa: BLE001
                logger.warning("provider call failed (%s); falling back to reference: %s",
                               self.model_id(), exc)
        return {"text": f"[reference:{self.name}] {prompt[:512]}",
                "model": self.name, "provider": False, "usage": {}}

    def score(self, expected: str, actual: str) -> float:
        """0..1 similarity used for rule-based evaluation."""
        return round(self.scorer(expected, actual), 4)

    def health(self) -> dict:
        return {"model": self.model_id(), "mode": self._mode,
                "offline": self.offline}


def get_model(name: str = "") -> EvalModel:
    """Get an EvalModel for the given model name ('' → reference)."""
    provider = resolve_provider(name) if name else None
    return EvalModel(name=name, provider=provider)
