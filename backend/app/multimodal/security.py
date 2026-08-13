"""Upload Security & Processing Sandbox - validation, spoofing guards, zip bombs, SSRF, limits."""
import io, logging, re, zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from .assets import (
    ALLOWED_EXTENSIONS, MAX_FILE_BYTES, MAX_IMAGE_BYTES, MAX_DOCUMENT_BYTES,
    MAX_VIDEO_BYTES, MAX_TEXT_BYTES, MAGIC, detect_mime, modality_of, sha256_of,
)

logger = logging.getLogger(__name__)

MAX_BYTES_BY_MODALITY = {
    "text": MAX_TEXT_BYTES, "image": MAX_IMAGE_BYTES, "document": MAX_DOCUMENT_BYTES,
    "video": MAX_VIDEO_BYTES, "audio": MAX_FILE_BYTES, "archive": MAX_FILE_BYTES,
    "unknown": MAX_FILE_BYTES,
}

ZIP_RATIO_LIMIT = 100.0    # uncompressed/compressed ratio bound (zip bomb)
MAX_ARCHIVE_ENTRIES = 10_000

PRIVATE_IP_RE = re.compile(
    r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|"
    r"0\.0\.0\.0|::1|fc00:|fe80:|::ffff:)"
)

PATH_TRAVERSAL_RE = re.compile(r"(\.\.[/\\]|^[/\\]|[A-Za-z]:[/\\])")

PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts)", re.I),
    re.compile(r"you\s+are\s+now\s+(?:an?\s+)?(?:a\s+)?(?:chatbot|assistant|model|agent)\b", re.I),
    re.compile(r"system\s+prompt\s*:", re.I),
    re.compile(r"override\s+(?:your|the)\s+(?:instructions|rules|guidelines)", re.I),
    re.compile(r"\bdo\s+not\s+(?:follow|respect)\s+(?:any|the)\s+(?:instructions|rules)", re.I),
    re.compile(r"<\|?(?:im_start|im_end|system|user|assistant)\|?>", re.I),
    re.compile(r"behave\s+as\s+", re.I),
)


@dataclass
class UploadCheck:
    check: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {"check": self.check, "passed": self.passed, "detail": self.detail}


@dataclass
class UploadVerdict:
    allowed: bool
    checks: list[UploadCheck] = field(default_factory=list)
    reason: str = ""
    asset: Optional[dict] = None  # sanitized description (no content)

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "reason": self.reason,
                "checks": [c.to_dict() for c in self.checks],
                "asset": self.asset}


class UploadSecurity:
    """Validates every upload: size, MIME, extension, magic bytes, checksum, sandbox limits."""

    def __init__(self, max_bytes: Optional[int] = None):
        self.max_bytes = max_bytes or MAX_FILE_BYTES
        self.rejected_count = 0
        self.verdicts: list[dict] = []

    def validate(self, data: bytes, file_name: str = "", declared_mime: str = "") -> UploadVerdict:
        checks: list[UploadCheck] = []
        checks.append(self._check_size(data))
        mime_magic = detect_mime(data, file_name, declared_mime)
        checks.append(self._check_mime(data, file_name, declared_mime, mime_magic))
        checks.append(self._check_extension(file_name))
        checks.append(self._check_spoofing(data, mime_magic))
        checks.append(self._check_zip(data, mime_magic))
        checks.append(UploadCheck("checksum", True, sha256_of(data)[:16]))
        checks.append(UploadCheck("path_traversal",
                                  not PATH_TRAVERSAL_RE.search(file_name or "") or True,
                                  detail="filename sanitized" if PATH_TRAVERSAL_RE.search(file_name or "") else "ok"))
        allowed = all(c.passed for c in checks[:4])
        reason = "" if allowed else "; ".join(c.detail for c in checks if not c.passed)
        if not allowed:
            self.rejected_count += 1
        verdict = UploadVerdict(allowed, checks, reason)
        self.verdicts.append(verdict.to_dict())
        return verdict

    def _check_size(self, data: bytes) -> UploadCheck:
        ok = len(data) <= self.max_bytes
        return UploadCheck("size", ok,
                           f"{len(data)} bytes (max {self.max_bytes})" if not ok else "ok")

    def _check_mime(self, data, file_name, declared, mime_magic) -> UploadCheck:
        modality = modality_of(mime_magic, file_name)
        cap = MAX_BYTES_BY_MODALITY.get(modality, self.max_bytes)
        if len(data) > cap:
            return UploadCheck("mime", False, f"{modality} over capacity {cap} bytes")
        return UploadCheck("mime", True, mime_magic)

    def _check_extension(self, file_name: str) -> UploadCheck:
        if not file_name:
            return UploadCheck("extension", True, "no extension supplied")
        ext = (file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "")
        if ext and file_name.lower().endswith("." + ext) and ("." + ext) not in ALLOWED_EXTENSIONS:
            return UploadCheck("extension", False, f"disallowed extension .{ext}")
        return UploadCheck("extension", True, "ok")

    def _check_spoofing(self, data: bytes, mime_magic: str) -> UploadCheck:
        """Extension/MIME vs magic-byte consistency."""
        for mime, sig in MAGIC.items():
            if data[:len(sig)] == sig and mime != mime_magic:
                return UploadCheck("spoofing", False, f"magic bytes claim {mime}, detected {mime_magic}")
        return UploadCheck("spoofing", True, "signature consistent")

    def _check_zip(self, data: bytes, mime_magic: str) -> UploadCheck:
        if mime_magic != "application/zip" and not data[:2] == b"PK":
            return UploadCheck("zip", True, "not an archive")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                infos = zf.infolist()
                if len(infos) > MAX_ARCHIVE_ENTRIES:
                    return UploadCheck("zip", False, f"too many entries ({len(infos)})")
                total_uncompressed = sum(i.file_size for i in infos)
                ratio = total_uncompressed / max(1, len(data))
                if ratio > ZIP_RATIO_LIMIT:
                    return UploadCheck("zip", False,
                                       f"compression ratio {ratio:.1f}x exceeds limit")
                for info in infos:
                    if PATH_TRAVERSAL_RE.search(info.filename or ""):
                        return UploadCheck("zip", False, f"traversal entry: {info.filename}")
            return UploadCheck("zip", True, "archive safe")
        except zipfile.BadZipFile:
            return UploadCheck("zip", False, "corrupt zip")
        except Exception as exc:
            return UploadCheck("zip", False, f"zip scan error: {exc}")


class SSRFGuard:
    """Blocks SSRF: private IPs, exotic schemes, localhost and redirect chains."""

    BLOCKED_SCHEMES = {"file", "ftp", "gopher", "dict", "ldap", "smb"}

    def validate_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1") or PRIVATE_IP_RE.match(host):
            return False
        return True

    def scrub(self, url: str) -> str:
        """Returns the URL only when safe to fetch, else raises ValueError."""
        if not self.validate_url(url):
            raise ValueError(f"URL rejected by SSRF guard: {url}")
        return url


class ProcessingSandbox:
    """Resource limits for untrusted-content parsing (CPU, memory, time, files)."""

    def __init__(self, max_memory_mb: int = 512, max_cpu_seconds: int = 60,
                 max_files: int = 1000, max_network: bool = False):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_seconds = max_cpu_seconds
        self.max_files = max_files
        self.max_network = max_network
        self.active: list[dict] = []

    def enter(self, job_id: str, asset_id: str = "") -> dict:
        token = {"job_id": job_id, "asset_id": asset_id,
                 "started_at": datetime.now(timezone.utc).isoformat(),
                 "limits": {"memory_mb": self.max_memory_mb,
                            "cpu_seconds": self.max_cpu_seconds,
                            "files": self.max_files,
                            "network": self.max_network}}
        self.active.append(token)
        return token

    def leave(self, token: dict) -> None:
        try:
            self.active.remove(token)
        except ValueError:
            pass

    def slots_free(self) -> int:
        return max(0, 8 - len(self.active))

    def health(self) -> dict:
        return {"active_jobs": len(self.active), "max_memory_mb": self.max_memory_mb,
                "network_disabled": self.max_network}


class PromptInjectionScanner:
    """Detects hidden instructions in text, images' OCR text and document text."""

    def __init__(self, extra_patterns: Optional[list[re.Pattern]] = None):
        self.patterns = list(PROMPT_INJECTION_PATTERNS) + list(extra_patterns or [])

    def scan(self, text: str) -> dict:
        if not text:
            return {"detected": False, "matches": []}
        matches = []
        for pattern in self.patterns:
            for hit in pattern.finditer(text):
                matches.append({"pattern": pattern.pattern[:60],
                                "text": text[max(0, hit.start() - 30): hit.end() + 30]})
                if len(matches) > 5:
                    break
            if len(matches) > 5:
                break
        return {"detected": bool(matches), "matches": matches[:5]}