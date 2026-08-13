"""Artifact store (Volume 33).

Step outputs can be published as versioned artifacts (JSON snapshots).
Artifacts are tenant-scoped, content-addressed by sha256 and listed per
workflow/execution. Binary payloads are capped.
"""
import hashlib, json, logging, os, time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)


@dataclass
class Artifact:
    artifact_id: str
    workflow_id: str
    execution_id: str
    name: str
    content_type: str = "application/json"
    size_bytes: int = 0
    created_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    organization_id: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ArtifactStore:
    def __init__(self, base_dir: str = "data/automation/artifacts",
                 storage: Optional[JsonFileStorage] = None,
                 max_bytes: int = 2_000_000):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self._storage = storage or JsonFileStorage(
            "data/automation/artifacts_index.json")
        self.max_bytes = max_bytes

    def store(self, payload: Any, workflow_id: str, execution_id: str,
              name: str = "", organization_id: str = "") -> Artifact:
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
            content_type = "application/json"
        elif isinstance(payload, bytes):
            data = payload
            content_type = "application/octet-stream"
        else:
            data = str(payload).encode("utf-8")
            content_type = "text/plain"
        if len(data) > self.max_bytes:
            raise ValueError(f"artifact exceeds max_bytes ({len(data)})")
        digest = sha256_hex(data)
        artifact_id = f"{digest[:16]}"
        path = os.path.join(self.base_dir, f"{artifact_id}.bin")
        with open(path, "wb") as fh:
            fh.write(data)
        artifact = Artifact(artifact_id=artifact_id,
                            workflow_id=workflow_id,
                            execution_id=execution_id,
                            name=name or f"artifact_{digest[:8]}",
                            content_type=content_type,
                            size_bytes=len(data),
                            organization_id=organization_id)
        self._storage.set(f"{organization_id or 'default'}:{artifact_id}",
                          artifact.to_dict())
        return artifact

    def get_meta(self, artifact_id: str,
                 organization_id: str = "") -> Optional[Artifact]:
        raw = self._storage.get(f"{organization_id or 'default'}:{artifact_id}")
        return Artifact(**raw) if raw else None

    def read(self, artifact_id: str,
             organization_id: str = "") -> Optional[bytes]:
        meta = self.get_meta(artifact_id, organization_id)
        if meta is None:
            return None
        path = os.path.join(self.base_dir, f"{meta.artifact_id}.bin")
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as fh:
            return fh.read()

    def list(self, workflow_id: str = "",
             organization_id: str = "", limit: int = 50) -> list[dict]:
        prefix = f"{organization_id or 'default'}:"
        rows = [v for k, v in self._storage.get_all().items()
                if k.startswith(prefix)]
        if workflow_id:
            rows = [r for r in rows if r.get("workflow_id") == workflow_id]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def count(self) -> int:
        return len(self._storage.get_all())