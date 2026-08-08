"""OpenAI / Azure OpenAI provider."""

import logging
from typing import Any, AsyncGenerator, Optional

from openai import AsyncOpenAI
from app.core.config import settings
from app.ai.providers import LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"
    model: str = "gpt-4o-mini"
    supports_tools = True
    supports_json = True
    supports_vision = True

    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None
        if settings.openai_api_key:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._azure = bool(getattr(settings, "azure_openai_endpoint", False))

    async def chat(self, messages: list[dict], **kwargs: Any) -> dict:
        if not self._client:
            raise RuntimeError("OpenAI client not configured (missing API key)")
        model = kwargs.pop("model", self.model)
        resp = await self._client.chat.completions.create(
            model=model, messages=messages, **kwargs
        )
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
        model = kwargs.pop("model", self.model)
        stream = await self._client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                yield content

    async def embeddings(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        if not self._client:
            raise RuntimeError("OpenAI client not configured (missing API key)")
        model = kwargs.pop("model", "text-embedding-3-small")
        resp = await self._client.embeddings.create(model=model, input=texts, **kwargs)
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
            logger.warning("OpenAI health check failed: %s", e)
            return False
