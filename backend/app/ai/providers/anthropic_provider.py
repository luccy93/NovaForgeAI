"""Anthropic Claude provider.

Like the OpenAI provider, requests pass through a normalizing boundary:
- optional parameters with ``None``/empty values or params Anthropic does not
  support are omitted rather than sent (prevents ``invalid_request_error``);
- the caller's ``messages`` list is NEVER mutated: a system message is
  extracted into a fresh copy so the same list can be reused across failover
  retries without becoming corrupted (a corrupted message array is a common
  source of provider 400s).

Diagnostics log safe metadata only (provider, model, param names/types,
HTTP status) — never API keys, prompts, or payloads.
"""

import logging
from typing import Any, AsyncGenerator, Optional

from anthropic import AsyncAnthropic
from anthropic import APIError
from app.core.config import settings
from app.ai.providers import LLMProvider

logger = logging.getLogger(__name__)

# Parameters the Anthropic Messages API supports.
_ANTHROPIC_MESSAGE_PARAMS = {
    "max_tokens",
    "temperature",
    "top_p",
    "top_k",
    "stop_sequences",
    "stream",
    "metadata",
    "tool_choice",
    "tools",
}


def _safe_kwargs(kwargs: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    """Return only allowed params with meaningful values.

    Silently drops unsupported keys and any ``None``/empty optional value —
    the provider rejects those instead of ignoring them.
    """
    cleaned: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key not in allowed:
            logger.debug(
                "dropping unsupported parameter provider=%s param=%s type=%s",
                "anthropic",
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


def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Extract a leading system message without mutating the input list.

    Returns (system_text, body_messages) where body_messages is a new list.
    """
    system: str | None = None
    if messages:
        first = messages[0]
        if isinstance(first, dict) and first.get("role") == "system":
            system = first.get("content")
            if isinstance(system, list):
                # A system block list -> join any text blocks, as Anthropic
                # accepts a plain string for `system`.
                texts = [
                    b.get("text", "")
                    for b in system
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                system = "\n".join(t for t in texts if t).strip() or None
            if not isinstance(system, str) or system == "":
                system = None
            messages = list(messages[1:])
        else:
            messages = list(messages)
    return system, messages


def _safe_error(body: str) -> str:
    if not body:
        return ""
    return body[:300]


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    model: str = "claude-3-5-sonnet-20241022"
    supports_tools = True
    supports_json = True
    supports_vision = True

    def __init__(self) -> None:
        self._client: Optional[AsyncAnthropic] = None
        if settings.anthropic_api_key:
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

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
            raise RuntimeError("Anthropic client not configured (missing API key)")
        model = self._resolve_model(kwargs)
        system, body_messages = _split_system(messages)
        params = _safe_kwargs(kwargs, _ANTHROPIC_MESSAGE_PARAMS)
        if "max_tokens" not in params:
            params["max_tokens"] = 1024
        logger.debug(
            "anthropic chat provider=%s model=%s params=%s message_count=%s",
            self.name,
            model,
            {k: type(v).__name__ for k, v in params.items()},
            len(body_messages),
        )
        try:
            resp = await self._client.messages.create(
                model=model, messages=body_messages, system=system, **params
            )
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            request_id = getattr(exc, "request_id", None)
            logger.warning(
                "anthropic chat rejected provider=%s model=%s http_status=%s request_id=%s detail=%s",
                self.name,
                model,
                status,
                request_id,
                _safe_error(str(exc)),
            )
            raise
        return {
            "content": resp.content[0].text if resp.content else "",
            "model": model,
            "usage": {
                "prompt_tokens": resp.usage.input_tokens if resp.usage else 0,
                "completion_tokens": resp.usage.output_tokens if resp.usage else 0,
            },
            "provider": self.name,
        }

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncGenerator[str, None]:
        if not self._client:
            raise RuntimeError("Anthropic client not configured (missing API key)")
        model = self._resolve_model(kwargs)
        system, body_messages = _split_system(messages)
        params = _safe_kwargs(kwargs, _ANTHROPIC_MESSAGE_PARAMS)
        if "max_tokens" not in params:
            params["max_tokens"] = 1024
        logger.debug(
            "anthropic stream provider=%s model=%s params=%s message_count=%s",
            self.name,
            model,
            {k: type(v).__name__ for k, v in params.items()},
            len(body_messages),
        )
        async with self._client.messages.stream(
            model=model, messages=body_messages, system=system, **params
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def embeddings(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        raise NotImplementedError("Claude does not provide embeddings API")

    async def count_tokens(self, text: str) -> int:
        if not self._client:
            return len(text) // 4
        try:
            return self._client.count_tokens(text)
        except Exception:
            return len(text) // 4

    async def health(self) -> bool:
        if not self._client:
            return False
        try:
            await self._client.messages.create(
                model=self.model, max_tokens=1, messages=[{"role": "user", "content": "ping"}]
            )
            return True
        except Exception as e:
            logger.warning(
                "Anthropic health check failed model=%s http_status=%s detail=%s",
                self.model,
                getattr(e, "status_code", None),
                _safe_error(str(e)),
            )
            return False
