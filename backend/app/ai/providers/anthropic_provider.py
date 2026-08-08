"""Anthropic Claude provider."""

import logging
from typing import Any, AsyncGenerator, Optional

from anthropic import AsyncAnthropic
from app.core.config import settings
from app.ai.providers import LLMProvider

logger = logging.getLogger(__name__)


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

    async def chat(self, messages: list[dict], **kwargs: Any) -> dict:
        if not self._client:
            raise RuntimeError("Anthropic client not configured (missing API key)")
        model = kwargs.pop("model", self.model)
        system = None
        if messages and messages[0].get("role") == "system":
            system = messages.pop(0)["content"]

        kwargs.setdefault("max_tokens", 1024)
        resp = await self._client.messages.create(
            model=model, messages=messages, system=system, **kwargs
        )
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
        model = kwargs.pop("model", self.model)
        system = None
        if messages and messages[0].get("role") == "system":
            system = messages.pop(0)["content"]

        kwargs.setdefault("max_tokens", 1024)
        async with self._client.messages.stream(
            model=model, messages=messages, system=system, **kwargs
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
            logger.warning("Anthropic health check failed: %s", e)
            return False
