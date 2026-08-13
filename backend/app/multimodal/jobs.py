"""Job Management - queued/processing/completed/failed/cancelled/retrying/dead_letter lifecycle."""
import asyncio, logging, time, uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class JobStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


@dataclass
class Job:
    job_id: str = ""
    kind: str = ""                # ocr | pdf_extraction | video_processing | ...
    organization_id: str = ""
    asset_id: str = ""
    source: str = ""
    worker: str = ""
    status: str = JobStatus.QUEUED
    attempt: int = 0
    max_attempts: int = 3
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    result: Optional[dict] = None
    created_at: str = ""
    payload: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.job_id:
            self.job_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class JobManager:
    """Async background job execution with retries, DLQ and status transitions."""

    MAX_QUEUE = 10_000
    RETRY_BACKOFF_S = 0.5

    def __init__(self, max_concurrency: int = 4, max_retries: int = 3):
        self.jobs: dict[str, Job] = {}
        self.dead_letter: list[dict] = []
        self.handlers: dict[str, Callable[[Job], Awaitable[dict]]] = {}
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._started = False
        self.completed_count = 0
        self.failed_count = 0

    def register_handler(self, kind: str, fn: Callable[[Job], Awaitable[dict]]) -> None:
        self.handlers[kind] = fn

    def enqueue(self, kind: str, organization_id: str, asset_id: str = "",
                payload: Optional[dict] = None, source: str = "") -> Job:
        if len(self.jobs) >= self.MAX_QUEUE:
            raise RuntimeError("job queue full")
        job = Job(kind=kind, organization_id=organization_id, asset_id=asset_id,
                  payload=payload or {}, source=source, max_attempts=self.max_retries + 1)
        self.jobs[job.job_id] = job
        self._queue.put_nowait(job)
        self._ensure_workers()
        return job

    def start(self) -> None:
        self._ensure_workers()

    def _ensure_workers(self) -> None:
        if self._started:
            return
        self._started = True
        for _ in range(self.max_concurrency):
            task = asyncio.get_event_loop().create_task(self._worker_loop())
            self._workers.append(task)

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            except Exception as exc:  # worker-level safety net
                logger.error("worker crashed on job %s: %s", job.job_id, exc)
            finally:
                self._queue.task_done()

    async def _process(self, job: Job) -> None:
        handler = self.handlers.get(job.kind)
        if not handler:
            job.status = JobStatus.FAILED
            job.error = f"no handler registered for kind '{job.kind}'"
            self.failed_count += 1
            return
        while job.attempt < job.max_attempts:
            job.attempt += 1
            job.status = JobStatus.PROCESSING
            job.worker = job.kind
            job.started_at = datetime.now(timezone.utc).isoformat()
            try:
                job.result = await handler(job)
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc).isoformat()
                self.completed_count += 1
                return
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                raise
            except Exception as exc:
                job.error = str(exc)
                if job.attempt >= job.max_attempts:
                    job.status = JobStatus.DEAD_LETTER
                    self.dead_letter.append(job.to_dict())
                    self.failed_count += 1
                else:
                    job.status = JobStatus.RETRYING
                    await asyncio.sleep(self.RETRY_BACKOFF_S * job.attempt)

    def get(self, job_id: str, organization_id: str = "") -> Optional[Job]:
        job = self.jobs.get(job_id)
        if job and organization_id and job.organization_id != organization_id:
            return None
        return job

    def cancel(self, job_id: str, organization_id: str = "") -> bool:
        job = self.get(job_id, organization_id)
        if not job or job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED,
                                     JobStatus.DEAD_LETTER):
            return False
        job.status = JobStatus.CANCELLED
        return True

    def retry(self, job_id: str, organization_id: str = "") -> Optional[Job]:
        job = self.get(job_id, organization_id)
        if not job:
            return None
        job.attempt = 0
        job.error = ""
        job.status = JobStatus.QUEUED
        self._queue.put_nowait(job)
        self._ensure_workers()
        return job

    def list(self, organization_id: str = "", status: str = "", limit: int = 100) -> list[dict]:
        rows = [j for j in self.jobs.values()
                if (not organization_id or j.organization_id == organization_id)
                and (not status or j.status == status)]
        rows.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in rows[:limit]]

    def counts(self) -> dict:
        out = {s: 0 for s in (JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.COMPLETED,
                              JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.RETRYING,
                              JobStatus.DEAD_LETTER)}
        for job in self.jobs.values():
            out[job.status] = out.get(job.status, 0) + 1
        return out

    def health(self) -> dict:
        return {"jobs_total": len(self.jobs),
                "queued": self._queue.qsize(),
                "completed": self.completed_count,
                "failed": self.failed_count,
                "dead_letter": len(self.dead_letter),
                "workers": len(self._workers),
                **self.counts()}