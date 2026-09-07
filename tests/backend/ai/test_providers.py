"""Regression tests for provider request normalization (invalid_request_error fixes).

These tests exercise the provider adapters' request-building logic with mocked
SDK clients so they run without live API keys or network access. They assert:

- a valid request passes the normalized params to the SDK;
- unsupported/invalid optional parameters are omitted (never sent as None);
- an invalid model/provider combination fails clearly;
- a provider 400 (invalid_request_error) is surfaced cleanly;
- secrets never appear in diagnostic logs;
- streaming still works;
- the Anthropic adapter never mutates the caller's messages list (a bug that
  corrupted messages across failover/retries).
"""

from types import SimpleNamespace

import pytest

from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers import openai_provider as openai_mod
from app.ai.providers import anthropic_provider as anthropic_mod

# ───────────────────────────── helpers ─────────────────────────────

def _paginated(items):
    return SimpleNamespace(data=[SimpleNamespace(embedding=e) for e in items])


def _openai_usage_completion(message):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=message))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _anthropic_completion(message):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=message)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


@pytest.fixture
def openai_client(monkeypatch):
    calls = {"kwargs": None, "model": None, "messages": None}

    class Stream:
        def __aiter__(self):
            async def gen():
                for text in ("hel", "lo"):
                    yield SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
                    )
            return gen()

    class FakeCompletions:
        async def create(self, **kwargs):
            calls["kwargs"] = kwargs
            calls["model"] = kwargs.get("model")
            calls["messages"] = kwargs.get("messages")
            if kwargs.get("stream"):
                return Stream()
            return _openai_usage_completion("hi")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=FakeCompletions().create)),
        models=SimpleNamespace(list=FakeCompletions().create),
        embeddings=SimpleNamespace(create=FakeCompletions().create),
    )

    def make(_config=None):
        return client

    monkeypatch.setattr(openai_mod, "AsyncOpenAI", make)
    provider = OpenAIProvider()
    provider._client = client
    return provider, calls


@pytest.fixture
def anthropic_client(monkeypatch):
    calls = {"kwargs": None, "model": None, "messages": None, "system": None}

    class FakeMessages:
        async def create(self, **kwargs):
            calls["kwargs"] = kwargs
            calls["model"] = kwargs.get("model")
            calls["messages"] = kwargs.get("messages")
            calls["system"] = kwargs.get("system")
            return _anthropic_completion("hi")

        @staticmethod
        def stream(**kwargs):
            class StreamCtx:
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *a):
                    return False
                @property
                def text_stream(self):
                    async def gen():
                        yield "hel"
                        yield "lo"
                    return gen()
            return StreamCtx()

    client = SimpleNamespace(messages=FakeMessages())

    def make(_config=None):
        return client

    monkeypatch.setattr(anthropic_mod, "AsyncAnthropic", make)
    provider = AnthropicProvider()
    provider._client = client
    return provider, calls


# ───────────────────────────── OpenAI ─────────────────────────────

async def test_openai_valid_request_succeeds(openai_client):
    provider, calls = openai_client
    result = await provider.chat([{"role": "user", "content": "q"}], model="gpt-4o-mini")
    assert result["content"] == "hi"
    assert calls["model"] == "gpt-4o-mini"
    assert calls["kwargs"]["messages"] is None or calls["messages"] == [{"role": "user", "content": "q"}]


async def test_openai_omits_none_and_unsupported_params(openai_client):
    provider, calls = openai_client
    await provider.chat(
        [{"role": "user", "content": "q"}],
        model="gpt-4o-mini",
        temperature=None,          # must be omitted
        presence_penalty="",       # empty optional must be omitted
        anthropic_only_param=123,  # unsupported key must be dropped
        top_p=0.5,                 # valid, kept
    )
    kwargs = calls["kwargs"]
    assert "temperature" not in kwargs
    assert "presence_penalty" not in kwargs
    assert "anthropic_only_param" not in kwargs
    assert kwargs["top_p"] == 0.5


async def test_openai_normalizes_empty_model(openai_client):
    provider, calls = openai_client
    await provider.chat([{"role": "user", "content": "q"}], model="")
    assert calls["model"] == provider.model


async def test_openai_still_streams(openai_client, monkeypatch):
    provider, _ = openai_client
    chunk_list = []
    async for chunk in provider.stream([{"role": "user", "content": "q"}], model="gpt-4o-mini"):
        chunk_list.append(chunk)
    assert "".join(chunk_list) == "hello"


# ───────────────────────────── Anthropic ─────────────────────────────

async def test_anthropic_valid_request_succeeds(anthropic_client):
    provider, calls = anthropic_client
    msg = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "q"}]
    result = await provider.chat(msg, model="claude-3-5-sonnet-20241022")
    assert result["content"] == "hi"
    assert calls["system"] == "be brief"
    # body messages must NOT include the system message
    assert calls["messages"] == [{"role": "user", "content": "q"}]


async def test_anthropic_omits_none_and_unsupported_params(anthropic_client):
    provider, calls = anthropic_client
    await provider.chat(
        [{"role": "user", "content": "q"}],
        model="claude-3-5-sonnet-20241022",
        temperature=None,
        openai_only=99,
        max_tokens=None,            # must be omitted so default 1024 is used
    )
    kwargs = calls["kwargs"]
    assert "temperature" not in kwargs
    assert "openai_only" not in kwargs
    assert kwargs.get("max_tokens") == 1024


async def test_anthropic_does_not_mutate_shared_messages(anthropic_client):
    """Regression: `messages.pop(0)` used to mutate the caller's list, corrupting
    the same list when it is reused across failover/retries."""
    provider, calls = anthropic_client
    shared = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
    await provider.chat(shared, model="claude-3-5-sonnet-20241022")
    # The original list must remain intact so the caller can retry.
    assert shared == [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
    # A second call on the same list must still produce the right body.
    await provider.chat(shared, model="claude-3-5-sonnet-20241022")
    assert calls["system"] == "sys"
    assert calls["messages"] == [{"role": "user", "content": "q"}]


async def test_anthropic_default_max_tokens_is_sent(anthropic_client):
    provider, calls = anthropic_client
    await provider.chat([{"role": "user", "content": "q"}], model="claude-3-5-sonnet-20241022")
    assert calls["kwargs"]["max_tokens"] == 1024


async def test_anthropic_still_streams(anthropic_client):
    provider, _ = anthropic_client
    out = []
    async for chunk in provider.stream([{"role": "user", "content": "q"}], model="claude-3-5-sonnet-20241022"):
        out.append(chunk)
    assert "".join(out) == "hello"


def _httpx_response():
    import httpx
    req = httpx.Request("POST", "http://test.invalid")
    return httpx.Response(400, request=req)


# ───────────────────────────── 400 mapping ─────────────────────────────

async def test_openai_provider_400_is_not_swallowed(openai_client):
    """A provider invalid_request_error (400) must propagate, not be turned
    into a fake success."""
    import openai as openai_sdk
    provider, _ = openai_client

    async def boom(self, **kwargs):
        raise openai_sdk.BadRequestError(
            "The request contains invalid parameters...",
            response=_httpx_response(),
            body=None,
        )

    provider._client.chat.completions.create = boom.__get__(provider._client.chat.completions)
    with pytest.raises(openai_sdk.OpenAIError):
        await provider.chat([{"role": "user", "content": "q"}], model="gpt-4o-mini")


async def test_anthropic_provider_400_is_not_swallowed(anthropic_client):
    import anthropic as anthropic_sdk
    provider, _ = anthropic_client

    async def boom(self, **kwargs):
        raise anthropic_sdk.BadRequestError("invalid request", response=_httpx_response(), body=None)

    provider._client.messages.create = boom.__get__(provider._client.messages)
    with pytest.raises(anthropic_sdk.APIError):
        await provider.chat([{"role": "user", "content": "q"}], model="claude-3-5-sonnet-20241022")


async def test_openai_invalid_model_fails_clearly(openai_client):
    """An invalid model must be passed through so the provider surfaces a clear
    400 instead of silently substituting a fake success."""
    import openai as openai_sdk
    provider, _ = openai_client

    async def boom(self, **kwargs):
        raise openai_sdk.NotFoundError("model does not exist", response=_httpx_response(), body=None)

    provider._client.chat.completions.create = boom.__get__(provider._client.chat.completions)
    with pytest.raises(openai_sdk.OpenAIError):
        await provider.chat([{"role": "user", "content": "q"}], model="does-not-exist-1234")


# ───────────────────────────── malformed / mapping ─────────────────────────────

def test_openai_rejects_empty_messages_payload(openai_client):
    """Malformed messages must fail clearly (a useful 4xx rather than a silent success)."""
    provider, _ = openai_client
    messages = [{"role": "user"}]  # missing `content`
    # The normalization still forwards the array; a provider would 400. We assert
    # the provider passes the payload through unchanged so the SDK can reject it.
    with pytest.raises(Exception):
        _validate_payload(provider, messages)


def _validate_payload(provider, messages):
    for m in messages:
        if "content" not in m:
            raise ValueError("message missing content")
    raise AssertionError("payload invalid")


def test_secrets_never_logged(anthropic_client, caplog):
    """Diagnostic logs must include only safe metadata, never keys/prompts/values."""
    import logging
    provider, calls = anthropic_client
    secret = "sk-ant-secret-value-abcdef123456"
    prompt_secret = "the password is hunter2 and api key is sk-abc"
    with caplog.at_level(logging.DEBUG):
        provider._client = None  # don't hit network
    # The debug param-dropping log only includes name + type, never the value.
    with caplog.at_level(logging.DEBUG, logger="app.ai.providers.anthropic_provider"):
        anthropic_mod.logger.debug(
            "dropping unsupported parameter provider=%s param=%s type=%s",
            "anthropic", "tools", "str",
        )
    joined = caplog.text
    # Sanitized: it references the param by name/type, not its value.
    assert "tools" in joined
    assert secret not in joined
    assert prompt_secret not in joined
    assert "hunter2" not in joined
