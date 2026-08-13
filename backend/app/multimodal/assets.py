"""Multimodal Asset Model - MIME, modality, encoding, checksum, metadata and the asset store."""
import hashlib, json, os, uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from ..common.storage import JsonFileStorage

TEXT_MIMES = {
    "text/plain", "text/markdown", "text/html", "text/xml", "text/css",
    "application/json", "application/xml", "application/javascript",
    "application/x-yaml", "text/yaml", "text/x-yaml", "application/x-sh",
    "application/sql", "text/csv", "text/x-python", "text/x-java-source",
    "text/x-c", "text/x-c++", "text/x-go-source", "text/x-rust",
    "text/x-typescript", "text/x-javascript", "application/typescript",
    "application/x-toml", "text/x-ini", "text/x-log", "application/x-httpd-php",
}

IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif",
               "image/bmp", "image/tiff", "image/svg+xml", "image/x-icon",
               "image/heic", "image/avif"}

DOCUMENT_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/msword",                                                       # doc
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",                                            # ppt
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",        # xlsx
    "application/vnd.ms-excel",                                                 # xls
    "application/vnd.oasis.opendocument.text",                                  # odt
    "application/vnd.oasis.opendocument.spreadsheet",                           # ods
    "application/vnd.oasis.opendocument.presentation",                          # odp
    "application/rtf", "text/rtf",
}

VIDEO_MIMES = {"video/mp4", "video/webm", "video/quicktime", "video/x-msvideo",
               "video/x-matroska", "video/ogg", "video/mpeg"}

AUDIO_MIMES = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/webm",
               "audio/mp4", "audio/flac", "audio/aac", "audio/x-wav"}

ARCHIVE_MIMES = {"application/zip", "application/x-tar", "application/gzip",
                 "application/x-7z-compressed", "application/x-rar-compressed"}

# Heuristic magic-byte signatures (file type spoofing guard)
MAGIC = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "application/pdf": b"%PDF-",
    "image/webp": b"RIFF",
    "image/gif": b"GIF8",
    "application/zip": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": b"PK\x03\x04",
    "audio/mpeg": b"ID3",
    "audio/wav": b"RIFF",
    "video/mp4": b"\x00\x00\x00",
    "video/webm": b"\x1aE\xdf\xa3",
}

MODALITY_BY_MIME: dict[str, str] = {m: "text" for m in TEXT_MIMES}
MODALITY_BY_MIME.update({m: "image" for m in IMAGE_MIMES})
MODALITY_BY_MIME.update({m: "document" for m in DOCUMENT_MIMES})
MODALITY_BY_MIME.update({m: "video" for m in VIDEO_MIMES})
MODALITY_BY_MIME.update({m: "audio" for m in AUDIO_MIMES})
MODALITY_BY_MIME.update({m: "archive" for m in ARCHIVE_MIMES})

EXTENSION_TO_MIME = {
    ".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown",
    ".html": "text/html", ".htm": "text/html", ".xml": "text/xml",
    ".json": "application/json", ".yaml": "text/yaml", ".yml": "text/yaml",
    ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".py": "text/x-python", ".js": "application/javascript",
    ".ts": "application/typescript", ".jsx": "text/x-javascript",
    ".tsx": "text/x-typescript", ".go": "text/x-go-source", ".rs": "text/x-rust",
    ".java": "text/x-java-source", ".c": "text/x-c", ".h": "text/x-c",
    ".cpp": "text/x-c++", ".sh": "application/x-sh", ".sql": "application/sql",
    ".toml": "application/x-toml", ".ini": "text/x-ini", ".cfg": "text/x-ini",
    ".log": "text/x-log", ".env": "text/plain", ".rst": "text/plain",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tiff": "image/tiff", ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".rtf": "application/rtf",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".avi": "video/x-msvideo", ".mkv": "video/x-matroska", ".ogv": "video/ogg",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".flac": "audio/flac", ".aac": "audio/aac", ".m4a": "audio/mp4",
    ".zip": "application/zip", ".tar": "application/x-tar",
    ".gz": "application/gzip", ".7z": "application/x-7z-compressed",
}

ALLOWED_EXTENSIONS = set(EXTENSION_TO_MIME)

MAX_FILE_BYTES = 200 * 1024 * 1024      # 200 MB default upload cap
MAX_IMAGE_BYTES = 25 * 1024 * 1024      # 25 MB images
MAX_DOCUMENT_BYTES = 100 * 1024 * 1024  # 100 MB documents
MAX_VIDEO_BYTES = 500 * 1024 * 1024     # 500 MB videos
MAX_TEXT_BYTES = 10 * 1024 * 1024       # 10 MB raw text


class Modality:
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    VIDEO = "video"
    AUDIO = "audio"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"

    ALL = [TEXT, IMAGE, DOCUMENT, VIDEO, AUDIO, ARCHIVE, UNKNOWN]


class AssetStatus:
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


@dataclass
class MultimodalAsset:
    """A single uploaded multimodal asset with full provenance metadata."""
    asset_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    repository_id: str = ""
    source: str = ""             # upload | url | repository | webhook | agent
    file_name: str = ""
    file_type: str = ""          # pdf | png | docx | ...
    mime_type: str = ""
    modality: str = Modality.UNKNOWN
    size_bytes: int = 0
    checksum_sha256: str = ""
    encoding: str = "utf-8"
    status: str = AssetStatus.UPLOADED
    storage_key: str = ""        # object-store key
    url: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    processed_at: str = ""

    def __post_init__(self):
        if not self.asset_id:
            self.asset_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MultimodalAsset":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_mime(data: bytes, file_name: str = "", declared: str = "") -> str:
    """Best-effort MIME: magic bytes first, then extension, then declared."""
    head = data[:16]
    for mime, sig in MAGIC.items():
        if head.startswith(sig):
            if mime == "image/webp" and head[8:12] != b"WEBP":
                continue
            if mime == "audio/wav" and head[8:12] != b"WAVE":
                continue
            return mime
    if declared and declared in MODALITY_BY_MIME:
        return declared
    ext = os.path.splitext(file_name)[1].lower()
    return EXTENSION_TO_MIME.get(ext, "application/octet-stream")


def modality_of(mime: str, file_name: str = "") -> str:
    if mime in MODALITY_BY_MIME:
        return MODALITY_BY_MIME[mime]
    ext = os.path.splitext(file_name)[1].lower()
    return EXTENSION_TO_MIME.get(ext, "application/octet-stream").split("/")[0] or Modality.UNKNOWN


def file_type_of(file_name: str, mime: str) -> str:
    ext = os.path.splitext(file_name)[1].lower().lstrip(".")
    if ext:
        return ext
    return mime.split("/")[-1].split("+")[-1]


def detect_encoding(data: bytes) -> str:
    """Lightweight encoding detection for text assets."""
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        data.decode("latin-1")
        return "latin-1"
    except UnicodeDecodeError:
        return "unknown"


class AssetStore:
    """Persistent registry of multimodal assets with tenant scoping."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/multimodal/assets.json")
        self._assets: dict[str, MultimodalAsset] = {}

    def put(self, asset: MultimodalAsset) -> MultimodalAsset:
        self._assets[asset.asset_id] = asset
        self._flush()
        return asset

    def get(self, asset_id: str, organization_id: str = "") -> Optional[MultimodalAsset]:
        asset = self._assets.get(asset_id)
        if asset and organization_id and asset.organization_id != organization_id:
            return None  # tenant isolation
        return asset

    def list(self, organization_id: str = "", modality: str = "",
             repository_id: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
        rows = [a for a in self._assets.values()
                if (not organization_id or a.organization_id == organization_id)
                and (not modality or a.modality == modality)
                and (not repository_id or a.repository_id == repository_id)]
        rows.sort(key=lambda a: a.created_at, reverse=True)
        return [a.to_dict() for a in rows[offset: offset + limit]]

    def delete(self, asset_id: str, organization_id: str = "") -> bool:
        asset = self.get(asset_id, organization_id)
        if not asset:
            return False
        asset.status = AssetStatus.DELETED
        self._flush()
        return True

    def count(self, organization_id: str = "") -> int:
        return len(self.list(organization_id))

    def _flush(self) -> None:
        try:
            self.storage.set("assets", {k: v.to_dict() for k, v in self._assets.items()})
        except Exception:
            pass  # persistence is best-effort; in-memory registry stays authoritative


class MultimodalIngestion:
    """Determines asset identity from raw bytes: mime, modality, encoding, checksum."""

    def __init__(self, store: Optional[AssetStore] = None):
        self.store = store or AssetStore()
        self.ingested = 0
        self.rejected = 0

    def describe(self, data: bytes, file_name: str = "", declared_mime: str = "") -> dict:
        return {
            "mime_type": detect_mime(data, file_name, declared_mime),
            "modality": modality_of(detect_mime(data, file_name, declared_mime), file_name),
            "size_bytes": len(data),
            "checksum_sha256": sha256_of(data),
            "encoding": detect_encoding(data) if not file_name.lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".mp4", ".mp3",
                 ".docx", ".xlsx", ".pptx", ".zip")) else "binary",
        }

    def register(self, organization_id: str, data: bytes, file_name: str = "",
                 source: str = "upload", declared_mime: str = "", **scope) -> MultimodalAsset:
        info = self.describe(data, file_name, declared_mime)
        asset = MultimodalAsset(
            organization_id=organization_id,
            source=source,
            file_name=file_name,
            mime_type=info["mime_type"],
            modality=info["modality"],
            size_bytes=info["size_bytes"],
            checksum_sha256=info["checksum_sha256"],
            encoding=info["encoding"],
            file_type=file_type_of(file_name, info["mime_type"]),
            storage_key=f"{organization_id}/{info['modality']}/{asset_id_hex()}",
            metadata={"declared_mime": declared_mime or "", "uploaded_at":
                      datetime.now(timezone.utc).isoformat()},
            **{k: v for k, v in scope.items() if k in MultimodalAsset.__dataclass_fields__},
        )
        self.store.put(asset)
        self.ingested += 1
        return asset


def asset_id_hex() -> str:
    return uuid.uuid4().hex[:16]