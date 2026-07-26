"""LLM provider abstraction layer.

Every provider implements the LLMProvider interface.
Changing providers does not change business logic.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Optional


class LLMProvider(ABC):
    """Common interface for all LLM providers."""

    name: str = "base"
    model: str = ""
    supports_tools: bool = False
    supports_json: bool = False
    supports_vision: bool = False

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs: Any) -> dict:
        ...

    @abstractmethod
    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncGenerator[str, None]:
        ...

    @abstractmethod
    async def embeddings(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        ...

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        ...

    @abstractmethod
    async def health(self) -> bool:
        ...
