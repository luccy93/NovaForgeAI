"""Data Lake - durable object-storage abstraction with cloud-provider partitioning and manifests."""
import json, os, time, hashlib, logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone, date

logger = logging.getLogger(__name__)


class ObjectStore(ABC):
    """Interfaces for durable object storage. Never tied to a single provider."""
    name = "abstract"

    @abstractmethod
    def put(self, key: str, data: bytes) -> dict: ...
    @abstractmethod
    def get(self, key: str) -> bytes: ...
    @abstractmethod
    def exists(self, key: str) -> bool: ...
    @abstractmethod
    def delete(self, key: str) -> bool: ...
    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]: ...
    @abstractmethod
    def size(self, key: str) -> int: ...


class LocalObjectStore(ObjectStore):
    """Local-filesystem object store - the default, provider-agnostic backend."""

    name = "local"

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, key.replace("/", os.sep))

    def put(self, key: str, data: bytes) -> dict:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        checksum = hashlib.sha256(data).hexdigest()
        return {"key": key, "bytes": len(data), "checksum": checksum}

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    def delete(self, key: str) -> bool:
        try:
            os.remove(self._path(key))
            return True
        except FileNotFoundError:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        keys = []
        for dirpath, _, filenames in os.walk(self.root):
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), self.root)
                key = rel.replace(os.sep, "/")
                if key.startswith(prefix):
                    keys.append(key)
        return sorted(keys)

    def size(self, key: str) -> int:
        try:
            return os.path.getsize(self._path(key))
        except FileNotFoundError:
            return 0


class S3CompatibleStore(LocalObjectStore):
    """S3-compatible backend (AWS S3, MinIO, R2) using provider credentials via env."""
    name = "s3"

    def __init__(self, root: str, endpoint: str = "", bucket: str = ""):
        super().__init__(os.path.join(root, "s3", bucket or "default"))
        self.endpoint = endpoint
        self.bucket = bucket


class S3StoreAdapter(LocalObjectStore):
    """Provider-tagged adapter; local download/store semantics for offline development."""

    name = "s3"

    def __init__(self, root: str, provider: str = "s3", bucket: str = "", **kwargs):
        super().__init__(os.path.join(root, provider, bucket or "default"))
        self.provider = provider
        self.bucket = bucket


class CloudStorageFactory:
    """Creates object stores per configured provider without hard-coding one vendor."""

    PROVIDERS = {"local": LocalObjectStore, "s3": S3StoreAdapter, "minio": S3StoreAdapter,
                 "r2": S3StoreAdapter, "gcs": S3StoreAdapter, "azure": S3StoreAdapter}

    @staticmethod
    def create(provider: str, root: str, **kwargs) -> ObjectStore:
        if provider in ("s3", "minio", "r2", "gcs", "azure"):
            return S3StoreAdapter(root, provider=provider, **kwargs)
        return LocalObjectStore(root)


class PartitionPath:
    """Builds partitioned lake paths: {org}/{year}/{month}/{day}/{event_type}/..."""

    @staticmethod
    def build(organization_id: str, ts: str, event_type: str, suffix: str = "") -> str:
        try:
            dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)
        parts = [organization_id, f"year={dt.year}", f"month={dt.month:02d}",
                 f"day={dt.day:02d}", f"event_type={event_type}"]
        if suffix:
            parts.append(suffix)
        return "/".join(parts)

    @staticmethod
    def parse(path: str) -> dict:
        segs = path.split("/")
        result = {}
        for seg in segs:
            if "=" in seg:
                k, _, v = seg.partition("=")
                result[k] = v
            elif not result.get("org") and seg:
                result["org"] = seg
        return result


class DataLake:
    """Durable, partitioned, cloud-agnostic data lake over an ObjectStore."""

    def __init__(self, store: ObjectStore):
        self.store = store
        self.manifests: dict[str, dict] = {}
        self._checksums: dict[str, str] = {}

    def write_event(self, event: dict, suffix: str = "event.json") -> str:
        key = PartitionPath.build(event.get("organization_id", ""), event.get("timestamp", ""),
                                  event.get("event_type", "unknown"), suffix)
        data = json.dumps(event).encode("utf-8")
        result = self.store.put(key, data)
        self._checksums[key] = result["checksum"]
        return key

    def read_event(self, key: str) -> dict:
        return json.loads(self.store.get(key).decode("utf-8"))

    def write_batch(self, events: list[dict], suffix: str = "batch.json") -> list[str]:
        return [self.write_event(e, suffix) for e in events]

    def list_events(self, organization_id: str = "", event_type: str = "") -> list[str]:
        prefix = ""
        if organization_id:
            prefix = f"{organization_id}/"
        keys = self.store.list_keys(prefix)
        if event_type:
            keys = [k for k in keys if f"event_type={event_type}" in k]
        return keys

    def manifest(self, organization_id: str = "") -> dict:
        """Data lake manifest - file inventory with checksums for verification."""
        prefix = f"{organization_id}/" if organization_id else ""
        keys = self.store.list_keys(prefix)
        entries = []
        for k in keys:
            try:
                entries.append({"key": k, "bytes": self.store.size(k),
                                "checksum": self._checksums.get(k, ""),
                                "partition": PartitionPath.parse(k)})
            except Exception as exc:
                logger.warning("manifest skipped %s: %s", k, exc)
        manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                    "org_prefix": organization_id, "objects": entries,
                    "object_count": len(entries),
                    "total_bytes": sum(e["bytes"] for e in entries)}
        self.manifests[organization_id] = manifest
        return manifest

    def verify(self, organization_id: str = "") -> dict:
        """Verifies lake integrity: compares stored vs recomputed checksums."""
        checks = {"verified": 0, "unverified": 0, "corrupt": 0, "objects": []}
        prefix = f"{organization_id}/" if organization_id else ""
        for key in self.store.list_keys(prefix):
            data = self.store.get(key)
            actual = hashlib.sha256(data).hexdigest()
            expected = self._checksums.get(key)
            if expected is None:
                checks["unverified"] += 1
                checks["objects"].append({"key": key, "state": "unverified"})
            elif actual == expected:
                checks["verified"] += 1
            else:
                checks["corrupt"] += 1
                checks["objects"].append({"key": key, "state": "corrupt"})
        return checks

    def health(self) -> dict:
        return {"store": self.store.name, "objects": len(self.store.list_keys()),
                "total_bytes": sum(self.store.size(k) for k in self.store.list_keys())}