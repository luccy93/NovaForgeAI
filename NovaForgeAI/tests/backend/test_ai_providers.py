"""Unit tests for AI provider abstraction layer."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.providers import LLMProvider


class TestLLMProviderInterface:
    """Verify the LLMProvider interface contract."""

    def test_interface_has_required_methods(self):
        """All required abstract methods are defined."""
        import inspect
        abstract_methods = [
            m for m in dir(LLMProvider)
            if getattr(getattr(LLMProvider, m, None), '__isabstractmethod__', False)
        ]
        required = {"chat", "stream", "embeddings", "count_tokens", "health"}
        for method in required:
            assert method in abstract_methods, f"Missing abstract method: {method}"

    def test_interface_has_properties(self):
        assert hasattr(LLMProvider, "name")
        assert hasattr(LLMProvider, "model")
        assert hasattr(LLMProvider, "supports_tools")
        assert hasattr(LLMProvider, "supports_json")
        assert hasattr(LLMProvider, "supports_vision")

    def test_interface_defaults(self):
        assert LLMProvider.name == "base"
        assert LLMProvider.supports_tools is False
        assert LLMProvider.supports_json is False
        assert LLMProvider.supports_vision is False


class TestOpenAIProvider:
    def test_provider_name(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider()
        assert provider.name == "openai"
        assert provider.model == "gpt-4o-mini"
        assert provider.supports_tools is True
        assert provider.supports_json is True
        assert provider.supports_vision is True

    @pytest.mark.asyncio
    async def test_health_returns_false_without_key(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            provider = OpenAIProvider()
            result = await provider.health()
            assert result is False

    @pytest.mark.asyncio
    async def test_count_tokens_fallback(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            provider = OpenAIProvider()
            count = await provider.count_tokens("hello world")
            assert count > 0

    @pytest.mark.asyncio
    async def test_embeddings_raises_without_key(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            provider = OpenAIProvider()
            with pytest.raises(Exception):
                await provider.embeddings(["test"])


class TestAnthropicProvider:
    def test_provider_name(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider()
        assert provider.name == "anthropic"
        assert provider.model == "claude-3-5-sonnet-20241022"
        assert provider.supports_tools is True
        assert provider.supports_json is True
        assert provider.supports_vision is True

    @pytest.mark.asyncio
    async def test_health_returns_false_without_key(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            provider = AnthropicProvider()
            result = await provider.health()
            assert result is False

    @pytest.mark.asyncio
    async def test_embeddings_not_supported(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            provider = AnthropicProvider()
            with pytest.raises(NotImplementedError):
                await provider.embeddings(["test"])

    @pytest.mark.asyncio
    async def test_chat_raises_without_key(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            provider = AnthropicProvider()
            with pytest.raises(Exception):
                await provider.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_stream_raises_without_key(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            provider = AnthropicProvider()
            with pytest.raises(Exception):
                async for _ in provider.stream([{"role": "user", "content": "hi"}]):
                    pass

    @pytest.mark.asyncio
    async def test_chat_returns_structured_response(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Hello from Claude"
        mock_response.content = [mock_content]
        mock_response.usage.input_tokens = 15
        mock_response.usage.output_tokens = 8

        provider = AnthropicProvider()
        provider._client = AsyncMock()
        provider._client.messages.create = AsyncMock(return_value=mock_response)

        result = await provider.chat([{"role": "user", "content": "hi"}])
        assert result["content"] == "Hello from Claude"
        assert result["usage"]["prompt_tokens"] == 15
        assert result["usage"]["completion_tokens"] == 8

    @pytest.mark.asyncio
    async def test_chat_handles_system_message(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Roger"
        mock_response.content = [mock_content]
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 5
        mock_response.usage.output_tokens = 3

        provider = AnthropicProvider()
        provider._client = AsyncMock()
        provider._client.messages.create = AsyncMock(return_value=mock_response)

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hi"},
        ]
        result = await provider.chat(messages)
        assert result["content"] == "Roger"

    @pytest.mark.asyncio
    async def test_stream_yields_content(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider

        class FakeStream:
            def __init__(self):
                self.text_stream = self._gen()
            async def _gen(self):
                for t in ["Hello", " from", " Claude"]:
                    yield t
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass

        provider = AnthropicProvider()
        provider._client = AsyncMock()
        provider._client.messages.stream = MagicMock(return_value=FakeStream())

        chunks = []
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert chunks == ["Hello", " from", " Claude"]

    @pytest.mark.asyncio
    async def test_count_tokens_fallback_without_key(self):
        from app.ai.providers.anthropic_provider import AnthropicProvider
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            provider = AnthropicProvider()
            count = await provider.count_tokens("hello world")
            assert count > 0


class TestOpenAIProviderChatStream:
    @pytest.mark.asyncio
    async def test_chat_raises_without_key(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            provider = OpenAIProvider()
            with pytest.raises(Exception):
                await provider.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_stream_raises_without_key(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            provider = OpenAIProvider()
            with pytest.raises(Exception):
                async for _ in provider.stream([{"role": "user", "content": "hi"}]):
                    pass

    @pytest.mark.asyncio
    async def test_chat_returns_structured_response(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        provider = OpenAIProvider()
        provider._client = AsyncMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await provider.chat([{"role": "user", "content": "hi"}])
        assert result["content"] == "Hello!"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5

    @pytest.mark.asyncio
    async def test_chat_passes_model_param(self):
        from app.ai.providers.openai_provider import OpenAIProvider
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        mock_response.usage = None

        provider = OpenAIProvider()
        provider._client = AsyncMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await provider.chat([{"role": "user", "content": "hi"}], model="gpt-4")
        assert result["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_stream_yields_content(self):
        from app.ai.providers.openai_provider import OpenAIProvider

        class FakeChunk:
            def __init__(self, text):
                self.choices = [MagicMock()]
                self.choices[0].delta.content = text

        async def fake_stream():
            yield FakeChunk("Hello")
            yield FakeChunk(" World")

        provider = OpenAIProvider()
        provider._client = AsyncMock()
        provider._client.chat.completions.create = AsyncMock(return_value=fake_stream())

        chunks = []
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert chunks == ["Hello", " World"]

    @pytest.mark.asyncio
    async def test_stream_skips_empty_content(self):
        from app.ai.providers.openai_provider import OpenAIProvider

        class FakeChunk:
            def __init__(self, text):
                self.choices = [MagicMock()]
                self.choices[0].delta.content = text

        async def fake_stream():
            yield FakeChunk("A")
            yield FakeChunk("")
            yield FakeChunk("B")

        provider = OpenAIProvider()
        provider._client = AsyncMock()
        provider._client.chat.completions.create = AsyncMock(return_value=fake_stream())

        chunks = []
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert chunks == ["A", "B"]
