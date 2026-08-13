"""Screenshot capture for visual regression testing (Volume 32).

Capture is honest: when no headless browser automation (Playwright/Selenium)
is installed, `available` is False with an explicit reason - no fabricated
screenshots. Captured screenshots persist to JSON (ScreenshotStore) and
bytes land under data/multimodal/screenshots/.
"""
import logging, os, time, uuid
from dataclasses import dataclass, field
from typing import Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = "data/multimodal/screenshots"
DEFAULT_VIEWPORT = (1280, 800)


@dataclass
class ScreenshotResult:
    id: str
    organization_id: str = ""
    url: str = ""
    viewport: str = ""
    width: int = 0
    height: int = 0
    format: str = "png"
    size_bytes: int = 0
    file_path: str = ""
    available: bool = False
    reason: str = ""
    captured_at: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "organization_id": self.organization_id,
                "url": self.url, "viewport": self.viewport,
                "width": self.width, "height": self.height,
                "format": self.format, "size_bytes": self.size_bytes,
                "file_path": self.file_path, "available": self.available,
                "reason": self.reason, "captured_at": self.captured_at,
                "latency_ms": round(self.latency_ms, 2)}


class ScreenshotStore:
    """Tenant-scoped registry of screenshot records (bytes live on disk)."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/multimodal/screenshots.json")
        self._shots: dict[str, dict] = {}

    def put(self, record: ScreenshotResult) -> ScreenshotResult:
        self._shots[record.id] = record.to_dict()
        try:
            self.storage.set("screenshots", self._shots)
        except Exception as exc:
            logger.warning("screenshot store flush failed: %s", exc)
        return record

    def get(self, shot_id: str, organization_id: str = "") -> Optional[ScreenshotResult]:
        row = self._shots.get(shot_id)
        if row and organization_id and row.get("organization_id") != organization_id:
            return None  # tenant isolation
        if not row:
            return None
        return ScreenshotResult(**{k: v for k, v in row.items()
                                   if k in ScreenshotResult.__dataclass_fields__})

    def list(self, organization_id: str = "", limit: int = 100) -> list[dict]:
        rows = [r for r in self._shots.values()
                if not organization_id or r.get("organization_id") == organization_id]
        rows.sort(key=lambda r: r.get("captured_at", ""), reverse=True)
        return rows[:limit]

    def count(self, organization_id: str = "") -> int:
        return len(self.list(organization_id))


class ScreenshotCapture:
    """Captures screenshots of web URLs for visual regression testing.

    Uses Playwright's sync API when installed, then Selenium. Both absent ->
    every capture reports `available: False` with a reason. URLs are run
    through an SSRF guard (private/loopback ranges are rejected) before any
    capture attempt.
    """

    def __init__(self, store: Optional[ScreenshotStore] = None,
                 guard=None, timeout_s: int = 30):
        self.store = store or ScreenshotStore()
        self.guard = guard  # SSRFGuard: validate_url(url) -> bool
        self.timeout_s = timeout_s
        self._browser = self._probe_browser()
        self.captures = 0
        self.failures = 0

    def _probe_browser(self) -> Optional[str]:
        try:
            import playwright  # noqa: F401
            return "playwright"
        except ImportError:
            pass
        try:
            import selenium  # noqa: F401
            return "selenium"
        except ImportError:
            pass
        return None

    @property
    def available(self) -> bool:
        return self._browser is not None

    def availability(self) -> dict:
        return {"available": self.available,
                "browser": self._browser or "none",
                "reason": "" if self.available else (
                    "no headless browser automation installed "
                    "(pip install playwright && playwright install chromium)")}

    def capture(self, url: str, organization_id: str = "",
                viewport: tuple[int, int] = DEFAULT_VIEWPORT) -> ScreenshotResult:
        """Validate the URL (SSRF guard) and capture a screenshot.

        Honest result: when no browser backend exists, the returned record
        carries `available: False` + reason (never fabricates pixels).
        """
        start = time.time()
        record = ScreenshotResult(
            id=uuid.uuid4().hex[:16], organization_id=organization_id,
            url=url, viewport=f"{viewport[0]}x{viewport[1]}")
        if not url:
            record.reason = "url required"
            return record
        if self.guard is not None and not self.guard.validate_url(url):
            self.failures += 1
            record.reason = "URL rejected by SSRF guard (private/loopback)"
            return record
        if not self.available:
            self.failures += 1
            record.reason = self.availability()["reason"]
            return record
        try:
            record = self._capture_with_browser(url, viewport, record)
            self.captures += 1
        except Exception as exc:
            self.failures += 1
            record.reason = f"capture failed: {exc}"
            logger.warning("screenshot capture failed for %s: %s", url, exc)
        record.latency_ms = (time.time() - start) * 1000
        self.store.put(record)
        return record

    def _capture_with_browser(self, url: str, viewport: tuple[int, int],
                              record: ScreenshotResult) -> ScreenshotResult:
        if self._browser == "playwright":
            from playwright.sync_api import sync_playwright
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            file_path = os.path.join(SCREENSHOT_DIR, f"{record.id}.png")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(viewport={"width": viewport[0],
                                                      "height": viewport[1]})
                    page.goto(url, timeout=self.timeout_s * 1000,
                              wait_until="networkidle")
                    page.screenshot(path=file_path, full_page=True)
                    size = os.path.getsize(file_path)
                finally:
                    browser.close()
            return self._finalize(record, file_path, size)
        # selenium fallback
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        file_path = os.path.join(SCREENSHOT_DIR, f"{record.id}.png")
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument(f"--window-size={viewport[0]},{viewport[1]}")
        driver = webdriver.Chrome(options=opts)
        try:
            driver.get(url)
            driver.save_screenshot(file_path)
            size = os.path.getsize(file_path)
        finally:
            driver.quit()
        return self._finalize(record, file_path, size)

    @staticmethod
    def _finalize(record: ScreenshotResult, file_path: str,
                  size_bytes: int) -> ScreenshotResult:
        from PIL import Image
        record.file_path = file_path
        record.size_bytes = size_bytes
        record.available = True
        record.captured_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            with Image.open(file_path) as img:
                record.width, record.height = img.size
        except Exception:
            pass
        return record

    def capture_many(self, urls: list[str], organization_id: str = "",
                     viewport: tuple[int, int] = DEFAULT_VIEWPORT) -> list[dict]:
        return [self.capture(u, organization_id, viewport).to_dict() for u in urls]

    def health(self) -> dict:
        h = self.availability()
        h["captures"] = self.captures
        h["failures"] = self.failures
        h["stored"] = self.store.count()
        return h


class ComparisonStore:
    """Persistent record of visual-comparison verdicts (VRT).

    Columns mirror the `multimodal_comparisons` table: mean_delta,
    diff_ratio, diff_pixels, verdict, changed_bbox.
    """

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/multimodal/comparisons.json")
        self._rows: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            rows = self.storage.get("comparisons") or {}
            self._rows = {k: v for k, v in rows.items() if isinstance(v, dict)}
        except Exception as exc:
            logger.warning("comparison store load failed: %s", exc)

    def _flush(self) -> None:
        try:
            self.storage.set("comparisons", self._rows)
        except Exception as exc:
            logger.warning("comparison store flush failed: %s", exc)

    def record(self, organization_id: str, baseline_id: str, candidate_id: str,
               verdict: dict) -> dict:
        id_ = uuid.uuid4().hex[:16]
        row = {"id": id_, "organization_id": organization_id,
               "baseline_id": baseline_id, "candidate_id": candidate_id,
               "mean_delta": verdict.get("mean_delta", 0.0),
               "diff_ratio": verdict.get("diff_ratio", 0.0),
               "diff_pixels": verdict.get("diff_pixels", 0),
               "verdict": verdict.get("verdict", "unknown"),
               "changed_bbox": verdict.get("changed_bbox"),
               "supported": verdict.get("supported", True),
               "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self._rows[id_] = row
        self._flush()
        return row

    def list(self, organization_id: str = "", limit: int = 100) -> list[dict]:
        rows = [r for r in self._rows.values()
                if not organization_id or r.get("organization_id") == organization_id]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def count(self, organization_id: str = "") -> int:
        return len(self.list(organization_id))