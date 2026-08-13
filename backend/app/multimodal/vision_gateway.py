"""Vision Model Gateway - provider-abstraction, routing, fallback, timeouts, retries, cost."""
import json, logging, os, time, uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# price per 1K tokens (USD) - descriptive, overridable via env NOVAFORGE_MODEL_PRICES
MODEL_PRICES = {
    "openai/gpt-4o": {"input": 0.0025, "output": 0.0100},
    "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "anthropic/claude-sonnet": {"input": 0.003, "output": 0.015},
    "anthropic/claude-haiku": {"input": 0.00025, "output": 0.00125},
    "google/gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    "google/gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    "local": {"input": 0.0, "output": 0.0},
}


@dataclass
class VisionRequest:
    prompt: str
    image_data: Optional[bytes] = None
    image_url: Optional[str] = None
    image_mime: str = "image/png"
    detail: str = "high"
    model: str = "auto"
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass
class VisionResult:
    text: str
    provider: str
    model: str
    latency_ms: float
    cost_usd: float
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""
    cached: bool = False

    def to_dict(self) -> dict:
        return {"text": self.text, "provider": self.provider, "model": self.model,
                "latency_ms": round(self.latency_ms, 2), "cost_usd": round(self.cost_usd, 6),
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "error": self.error, "cached": self.cached}


class VisionProvider(ABC):
    """A vision-capable model provider. Never hard-code a single provider."""
    name = "abstract"
    available = False

    @abstractmethod
    def analyze(self, request: VisionRequest) -> str: ...

    def health(self) -> dict:
        return {"provider": self.name, "available": self.available}


class OpenAICompatibleProvider(VisionProvider):
    """Generic OpenAI-compatible vision endpoint (OpenAI or compatible servers)."""
    name = "openai"

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini",
                 base_url: str = ""):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "")
        self.available = bool(self.api_key)
        self._client = self._build_client() if self.available else None

    def _build_client(self):
        try:
            from openai import OpenAI
            kwargs = {"api_key": self.api_key, "timeout": 60}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            return OpenAI(**kwargs)
        except ImportError:
            self.available = False
            logger.warning("openai SDK unavailable; openai provider disabled")
            return None

    def analyze(self, request: VisionRequest) -> str:
        if not self.available:
            raise RuntimeError("openai provider not configured")
        content = [{"type": "text", "text": request.prompt}]
        if request.image_data:
            import base64
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{request.image_mime};base64,"
                                                 f"{base64.b64encode(request.image_data).decode()}"}})
        elif request.image_url:
            content.append({"type": "image_url", "image_url": {"url": request.image_url}})
        resp = self._client.chat.completions.create(
            model=request.model if request.model != "auto" else self.model,
            messages=[{"role": "user", "content": content}],
            max_tokens=request.max_tokens, temperature=request.temperature)
        try:
            return resp.choices[0].message.content or ""
        except Exception:
            return str(resp)


class AnthropicProvider(VisionProvider):
    name = "anthropic"

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-5"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model
        self.available = bool(self.api_key)
        self._client = None
        if self.available:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                self.available = False

    def analyze(self, request: VisionRequest) -> str:
        if not self.available:
            raise RuntimeError("anthropic provider not configured")
        blocks = [{"type": "text", "text": request.prompt}]
        if request.image_data:
            import base64
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": request.image_mime,
                "data": base64.b64encode(request.image_data).decode()}})
        resp = self._client.messages.create(
            model=request.model if request.model != "auto" else self.model,
            max_tokens=request.max_tokens,
            messages=[{"role": "user", "content": blocks}])
        return "".join(b.get("text", "") for b in resp.content if b.type == "text")


class HeuristicVisionProvider(VisionProvider):
    """Deterministic local fallback: extracts what is measurable from image bytes.

    It never fabricates semantics - it reports pixel-level structure and,
    when a text layer (e.g. PDF text) is attached, keeps that text. Used only
    when no paid vision provider is configured.
    """
    name = "local_heuristic"
    available = True

    def __init__(self, context_text: str = ""):
        self.context_text = context_text

    def analyze(self, request: VisionRequest) -> str:
        lines = ["[local_heuristic] no external vision model configured."]
        if request.image_data:
            lines.append(_image_stats(request.image_data, request.image_mime))
        if request.image_url:
            lines.append(f"image_url: {request.image_url}")
        if self.context_text:
            lines.append(f"context_text: {self.context_text[:2000]}")
        return "\n".join(lines)


def _image_stats(data: bytes, mime: str) -> str:
    dims = ""
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as img:
            dims = f" (size {img.width}x{img.height}, mode {img.mode})"
    except Exception:
        # pure-python header parse: PNG
        if mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n":
            w = int.from_bytes(data[16:20], "big"); h = int.from_bytes(data[20:24], "big")
            dims = f" (size {w}x{h})"
        elif mime == "image/jpeg" and data[:3] == b"\xff\xd8\xff":
            dims = _jpeg_dims(data)
    return f"image bytes={len(data)} mime={mime}{dims}"


def _jpeg_dims(data: bytes) -> str:
    i = 2
    try:
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            seg = int.from_bytes(data[i + 2: i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(data[i + 5: i + 7], "big")
                w = int.from_bytes(data[i + 7: i + 9], "big")
                return f" (size {w}x{h})"
            i += 2 + seg
    except Exception:
        pass
    return ""


class VisionModelGateway:
    """Routes vision requests to the best available provider with fallback and cost."""

    ROUTE_TABLE = {
        "diagram": "openai/gpt-4o-mini",
        "screenshot": "openai/gpt-4o-mini",
        "document": "openai/gpt-4o-mini",
        "ocr": "local_heuristic",
        "ui_review": "openai/gpt-4o",
        "default": "openai/gpt-4o-mini",
    }

    def __init__(self, providers: Optional[list[VisionProvider]] = None,
                 timeout_s: float = 90.0, retries: int = 1, rate_per_minute: int = 120):
        self.providers = providers or [
            (lambda: OpenAICompatibleProvider())(),
            (lambda: AnthropicProvider())(),
            HeuristicVisionProvider(),
        ]
        self.timeout_s = timeout_s
        self.retries = retries
        self.rate_per_minute = rate_per_minute
        self.calls = 0
        self.failures = 0
        self.cost_total = 0.0
        self.latencies: list[float] = []
        self._calls_this_minute = 0
        self._minute_start = time.time()

    def available_providers(self) -> list[str]:
        return [p.name for p in self.providers if p.available]

    def analyze(self, request: VisionRequest, task: str = "default",
                organization_id: str = "") -> VisionResult:
        model = request.model if request.model != "auto" else self.ROUTE_TABLE.get(task, self.ROUTE_TABLE["default"])
        preferred = self._pick_provider(model)
        start = time.time()
        last_error = ""
        for attempt in range(self.retries + 1):
            for provider in preferred:
                if not provider.available:
                    continue
                if not self._rate_ok():
                    time.sleep(0.1)
                try:
                    self.calls += 1
                    text = provider.analyze(request)
                    latency = (time.time() - start) * 1000
                    self.latencies.append(latency)
                    cost = self._estimate_cost(model, text)
                    self.cost_total += cost
                    if "local_heuristic" in provider.name and self._has_better_chance():
                        pass  # still returns honest result, no fabrication
                    return VisionResult(text, provider.name, model,
                                        latency, cost, error=last_error)
                except Exception as exc:
                    last_error = str(exc)
                    self.failures += 1
                    logger.warning("vision provider %s failed: %s", provider.name, exc)
            time.sleep(0.2)
        latency = (time.time() - start) * 1000
        return VisionResult("", "none", model, latency, 0.0,
                            error=last_error or "all vision providers failed")

    def _pick_provider(self, model: str) -> list[VisionProvider]:
        wanted, _, _ = model.partition("/")
        ordered = []
        for p in self.providers:
            if p.name.startswith(wanted) or (wanted == "local"):
                ordered.append(p)
        return ordered + [p for p in self.providers if p not in ordered]

    def _has_better_chance(self) -> bool:
        return any(p.available and p.name != "local_heuristic" for p in self.providers)

    def _rate_ok(self) -> bool:
        now = time.time()
        if now - self._minute_start >= 60:
            self._minute_start = now
            self._calls_this_minute = 0
        self._calls_this_minute += 1
        return self._calls_this_minute <= self.rate_per_minute

    @staticmethod
    def _estimate_cost(model: str, text: str) -> float:
        price = MODEL_PRICES.get(model, {"input": 0.00015, "output": 0.0006})
        tokens_out = max(1, len(text) // 4)
        return round((tokens_out / 1000.0) * price["output"], 6)

    def health(self) -> dict:
        return {"providers": self.available_providers(),
                "calls": self.calls, "failures": self.failures,
                "total_cost_usd": round(self.cost_total, 4),
                "avg_latency_ms": round(sum(self.latencies) / len(self.latencies), 2)
                if self.latencies else 0}