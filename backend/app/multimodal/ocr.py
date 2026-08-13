"""OCR Engine - provider-abstraction (tesseract, paddle, cloud, vision-LLM) with caching."""
import io, logging, re, time, zlib
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    engine: str
    text: str
    confidence: float = 0.0
    pages: int = 1
    latency_ms: float = 0.0
    boxes: list[dict] = field(default_factory=list)  # [{x,y,w,h,text,conf}]
    cached: bool = False

    def to_dict(self) -> dict:
        return {"engine": self.engine, "text": self.text[:200000],
                "confidence": round(self.confidence, 4), "pages": self.pages,
                "latency_ms": round(self.latency_ms, 2),
                "boxes": self.boxes[:5000], "cached": self.cached}


class TesseractOCR:
    """Tesseract via pytesseract when installed; honest unavailability otherwise."""
    name = "tesseract"

    def __init__(self, lang: str = "eng"):
        self.lang = lang
        self.available = False
        try:
            import pytesseract  # noqa: F401
            self.available = True
        except ImportError:
            logger.info("pytesseract not installed; tesseract engine unavailable")

    def ocr(self, image_bytes: bytes) -> str:
        if not self.available:
            raise RuntimeError("tesseract unavailable (pytesseract not installed)")
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(image_bytes)), lang=self.lang)


class PaddleOCR:
    name = "paddle"

    def __init__(self):
        self.available = False
        try:
            from paddleocr import PaddleOCR as _P  # noqa: F401
            self.available = True
        except ImportError:
            logger.info("paddleocr not installed; paddle engine unavailable")

    def ocr(self, image_bytes: bytes) -> str:
        if not self.available:
            raise RuntimeError("paddle unavailable (paddleocr not installed)")
        from paddleocr import PaddleOCR
        from PIL import Image
        import numpy as np
        engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        img = np.array(Image.open(io.BytesIO(image_bytes)))
        result = engine.ocr(img, cls=True)
        lines = []
        for page in result or []:
            for box, (text, _conf) in page or []:
                lines.append(text)
        return "\n".join(lines)


class CloudVisionOCR:
    """Cloud OCR through the configured vision gateway - provider-independent."""
    name = "vision_llm"

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.available = False
        if gateway is not None:
            self.available = any(
                p.available and p.name != "local_heuristic"
                for p in getattr(gateway, "providers", []))

    def ocr(self, image_bytes: bytes) -> str:
        if self.gateway is None:
            raise RuntimeError("vision gateway not attached")
        from .vision_gateway import VisionRequest
        result = self.gateway.analyze(
            VisionRequest(prompt="Extract all visible text verbatim from this image. "
                                 "Return only the extracted text, line by line.",
                          image_data=image_bytes, image_mime="image/png",
                          temperature=0.0), task="ocr")
        if result.error or not result.text or result.provider == "local_heuristic":
            raise RuntimeError("no external vision OCR provider available")
        return result.text


class OCRDetector:
    """Provides OCR via a pluggable chain; caches deterministic results per asset+tenant."""

    def __init__(self, gateway=None, engines: Optional[list] = None,
                 cache=None):
        self.gateway = gateway
        self._engines = engines or []
        self.cache = cache  # deterministic_op_cache (per-tenant keyed)
        self.calls = 0
        self.failures = 0
        self.cache_hits = 0
        if not self._engines:
            for cls in (TesseractOCR, PaddleOCR, CloudVisionOCR):
                inst = cls(gateway=gateway) if cls is CloudVisionOCR else cls()
                self._engines.append(inst)

    def available_engines(self) -> list[str]:
        return [e.name for e in self._engines if e.available]

    def ocr(self, image_bytes: bytes, organization_id: str = "",
            asset_id: str = "", force: bool = False) -> OCRResult:
        start = time.time()
        if self.cache and not force and organization_id and asset_id:
            cached = self.cache.get(f"ocr:{organization_id}:{asset_id}:{hash(image_bytes) & 0xffffffff}")
            if cached is not None:
                self.cache_hits += 1
                return OCRResult(engine=cached.get("engine", "cache"), text=cached["text"],
                                 confidence=cached.get("confidence", 0.0),
                                 cached=True, latency_ms=0.0)
        text = ""
        used_engine = ""
        last_error = ""
        for engine in self._engines:
            try:
                self.calls += 1
                text = engine.ocr(image_bytes)
                used_engine = engine.name
                break
            except Exception as exc:
                last_error = f"{last_error} [{engine.name}: {exc}]"
        if not used_engine:
            self.failures += 1
            raise RuntimeError(f"all OCR engines failed:{last_error}")
        latency = (time.time() - start) * 1000
        result = OCRResult(engine=used_engine, text=text, latency_ms=latency)
        if self.cache and organization_id and asset_id:
            self.cache.put(f"ocr:{organization_id}:{asset_id}:{hash(image_bytes) & 0xffffffff}",
                           {"text": text, "engine": used_engine, "confidence": 0.0})
        return result

    def pdf_text_layer(self, pdf_bytes: bytes) -> str:
        """Extracts the embedded text layer (OCR-free) using the built-in parser."""
        from .pdf_parser import extract_text
        return extract_text(pdf_bytes)

    def health(self) -> dict:
        return {"engines": self.available_engines(), "calls": self.calls,
                "failures": self.failures, "cache_hits": self.cache_hits}