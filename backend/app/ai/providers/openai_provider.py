"""OpenAI / Azure OpenAI provider.

Builds provider requests through a normalizing boundary so invalid or
provider-incompatible optional parameters are omitted rather than sent to
the wire (an explicit ``None``/``""`` or a stray OpenAI-only parameter can
otherwise produce a provider ``invalid_request_error``).

Diagnostics are logged with safe metadata only (provider, model, parameter
names/types, HTTP status) — never API keys, tokens, prompts or payloads.
"""

import logging
from typing import Any, AsyncGenerator, Optional

from openai import AsyncOpenAI
from openai import OpenAIError
from app.core.config import settings
from app.ai.providers import LLMProvider

logger = logging.getLogger(__name__)

# Parameters OpenAI's chat.completions supports. Anything else supplied by a
# caller (e.g. an Anthropic/Google-only option) is dropped before the call so
# the SDK never forwards an unsupported key.
_OPENAI_CHAT_PARAMS = {
    "temperature",
    "top_p",
    "n",
    "stream",
    "stop",
    "max_tokens",
    "max_completion_tokens",
    "presence_penalty",
    "frequency_penalty",
    "logit_bias",
    "user",
    "response_format",
    "seed",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "logprobs",
    "top_logprobs",
    "modalities",
    "audio",
    "reasoning_effort",
    "store",
    "service_tier",
}

_OPENAI_EMBEDDING_PARAMS = {"encoding_format", "dimensions", "user"}


def _safe_kwargs(kwargs: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    """Return only allowed params that have a meaningful (non-null/non-empty) value.

    Explicit ``None`` or empty-string optional parameters are omitted because
    many provider SDKs reject them instead of ignoring them.
    """
    cleaned: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key not in allowed:
            logger.debug(
                "dropping unsupported parameter provider=%s param=%s type=%s",
                "openai",
                key,
                type(value).__name__,
            )
            continue
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        cleaned[key] = value
    return cleaned


def _safe_error(body: str) -> str:
    """Return a sanitized, short provider error line for logging/telemetry."""
    if not body:
        return ""
    return body[:300]


class OpenAIProvider(LLMProvider):
    name = "openai"
    model: str = "gpt-4o-mini"
    supports_tools = True
    supports_json = True
    supports_vision = True

    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None
        self._azure = bool(getattr(settings, "azure_openai_endpoint", False))
        if settings.openai_api_key:
            base_url = getattr(settings, "azure_openai_endpoint", "") or None
            self._client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=base_url)

    def _resolve_model(self, kwargs: dict[str, Any]) -> str:
        model = kwargs.pop("model", self.model)
        if not isinstance(model, str) or not model.strip():
            logger.debug(
                "normalized empty model to default provider=%s model=%r",
                self.name,
                self.model,
            )
            return self.model
        return model.strip()

    async def chat(self, messages: list[dict], **kwargs: Any) -> dict:
        if not self._client:
            raise RuntimeError("OpenAI client not configured (missing API key)")
        model = self._resolve_model(kwargs)
        params = _safe_kwargs(kwargs, _OPENAI_CHAT_PARAMS)
        logger.debug(
            "openai chat provider=%s model=%s params=%s",
            self.name,
            model,
            {k: type(v).__name__ for k, v in params.items()},
        )
        try:
            resp = await self._client.chat.completions.create(
                model=model, messages=messages, **params
            )
        except OpenAIError as exc:
            status = getattr(exc, "status_code", None)
            request_id = getattr(exc, "request_id", None)
            logger.warning(
                "openai chat rejected provider=%s model=%s http_status=%s request_id=%s detail=%s",
                self.name,
                model,
                status,
                request_id,
                _safe_error(str(exc)),
            )
            raise
        return {
            "content": resp.choices[0].message.content or "",
            "model": model,
            "usage": {
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            },
            "provider": self.name,
        }

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncGenerator[str, None]:
        if not self._client:
            raise RuntimeError("OpenAI client not configured (missing API key)")
        model = self._resolve_model(kwargs)
        params = _safe_kwargs(kwargs, _OPENAI_CHAT_PARAMS)
        params["stream"] = True
        logger.debug(
            "openai stream provider=%s model=%s params=%s",
            self.name,
            model,
            {k: type(v).__name__ for k, v in params.items()},
        )
        stream = await self._client.chat.completions.create(
            model=model, messages=messages, **params
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                yield content

    async def embeddings(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        if not self._client:
            raise RuntimeError("OpenAI client not configured (missing API key)")
        model = kwargs.pop("model", "text-embedding-3-small")
        if not isinstance(model, str) or not model.strip():
            model = "text-embedding-3-small"
        params = _safe_kwargs(kwargs, _OPENAI_EMBEDDING_PARAMS)
        resp = await self._client.embeddings.create(model=model, input=texts, **params)
        return [e.embedding for e in resp.data]

    async def count_tokens(self, text: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model(self.model)
            return len(enc.encode(text))
        except Exception:
            return len(text) // 4

    async def health(self) -> bool:
        if not self._client:
            return False
        try:
            await self._client.models.list()
            return True
        except Exception as e:
            logger.warning("OpenAI health check failed: %s", _safe_error(str(e)))
            return False
