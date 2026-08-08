"""Worker Orchestration — search, embedding, AI, parser, analytics, security, testing, documentation, deployment, background."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Worker:
    id: str; org_id: str; name: str; worker_type: str; status: str = "idle"
    queue: list = field(default_factory=list); concurrency: int = 1
    current_jobs: int = 0; total_jobs: int = 0; failed_jobs: int = 0
    last_heartbeat: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Worker": return cls(**data)

class WorkerOrchestration:
    def __init__(self, storage_dir: str = "aiops_data/workers"):
        self.storage_dir = storage_dir; self._workers: dict[str, Worker] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "workers.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._workers[k] = Worker.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._workers.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, worker_type: str, concurrency: int = 1) -> Worker:
        w = Worker(id=str(uuid.uuid4()), org_id=org_id, name=name, worker_type=worker_type, concurrency=concurrency)
        self._workers[w.id] = w; self._save(); return w

    def heartbeat(self, worker_id: str) -> bool:
        w = self._workers.get(worker_id)
        if not w: return False
        import time; w.last_heartbeat = time.time(); self._save(); return True

    def assign_job(self, worker_id: str, job: dict) -> Optional[Worker]:
        w = self._workers.get(worker_id)
        if not w: return None
        w.queue.append(job); w.total_jobs += 1; w.current_jobs += 1; self._save(); return w

    def get_workers_by_type(self, org_id: str, worker_type: str) -> list[Worker]:
        return [w for w in self._workers.values() if w.org_id == org_id and w.worker_type == worker_type]

    def get_telemetry(self) -> dict: return {"workers": len(self._workers)}
