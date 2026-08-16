"""Service Mesh — Istio, Linkerd, traffic policies, circuit breaker, mTLS, observability."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MeshConfig:
    id: str; org_id: str; name: str; mesh_type: str = "istio"
    mtls_enabled: bool = True; circuit_breaker: dict = field(default_factory=dict)
    retry_policy: dict = field(default_factory=dict); traffic_policies: dict = field(default_factory=dict)
    is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ServiceMesh:
    def __init__(self, storage_dir: str = "infra_data/mesh"):
        self.storage_dir = storage_dir; self._configs: dict[str, MeshConfig] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "configs.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._configs[k] = MeshConfig(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._configs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def configure(self, org_id: str, name: str, mesh_type: str = "istio") -> MeshConfig:
        c = MeshConfig(id=str(uuid.uuid4()), org_id=org_id, name=name, mesh_type=mesh_type)
        self._configs[c.id] = c; self._save(); return c

    def get_telemetry(self) -> dict: return {"configs": len(self._configs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ContainerImage:
    id: str; org_id: str; name: str; tag: str = "latest"; registry: str = ""
    digest: str = ""; signed: bool = False; scanned: bool = False; size_bytes: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ContainerPlatform:
    def __init__(self, storage_dir: str = "infra_data/containers"):
        self.storage_dir = storage_dir; self._images: dict[str, ContainerImage] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "images.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._images[k] = ContainerImage(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._images.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, tag: str = "latest", registry: str = "") -> ContainerImage:
        i = ContainerImage(id=str(uuid.uuid4()), org_id=org_id, name=name, tag=tag, registry=registry)
        self._images[i.id] = i; self._save(); return i

    def get_telemetry(self) -> dict: return {"images": len(self._images)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class StorageBucket:
    id: str; org_id: str; name: str; storage_type: str  # object, repo, artifact, knowledge, vector, archive, cold
    region: str = ""; size_bytes: int = 0; versioning: bool = True
    replication: bool = False; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GlobalStorage:
    def __init__(self, storage_dir: str = "infra_data/storage"):
        self.storage_dir = storage_dir; self._buckets: dict[str, StorageBucket] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "buckets.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._buckets[k] = StorageBucket(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._buckets.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, storage_type: str, region: str = "") -> StorageBucket:
        b = StorageBucket(id=str(uuid.uuid4()), org_id=org_id, name=name, storage_type=storage_type, region=region)
        self._buckets[b.id] = b; self._save(); return b

    def get_telemetry(self) -> dict: return {"buckets": len(self._buckets)}
