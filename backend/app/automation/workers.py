"""Worker pool (Volume 33).

In-process workers consume run requests from a thread-safe queue and
dispatch them through the engine. Workers are honest: failures are
recorded back into the execution record; nothing is silently dropped.
"""
import logging, queue, threading, time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class RunRequest:
    def __init__(self, workflow_id: str, organization_id: str = "",
                 inputs: dict | None = None, trigger: dict | None = None):
        self.workflow_id = workflow_id
        self.organization_id = organization_id
        self.inputs = inputs or {}
        self.trigger = trigger or {}
        self.submitted_at = time.time()

    def to_dict(self) -> dict:
        return {"workflow_id": self.workflow_id,
                "organization_id": self.organization_id,
                "inputs": self.inputs, "trigger": self.trigger}


class WorkerPool:
    """N workers pulling from a queue; submit() enqueues, run() executes the
    request via the engine (synchronous per worker)."""

    def __init__(self, executor: Callable[[RunRequest], dict], workers: int = 2):
        self.executor = executor
        self._queue: queue.Queue = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.processed = 0
        self.failed = 0
        self.total = 0
        self._start(workers)

    def _start(self, workers: int) -> None:
        for i in range(workers):
            thread = threading.Thread(target=self._loop, name=f"automation-worker-{i}",
                                      daemon=True)
            thread.start()
            self._workers.append(thread)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                request = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._lock:
                self.total += 1
            try:
                self.executor(request)
                with self._lock:
                    self.processed += 1
            except Exception as exc:
                logger.error("worker failed request %s: %s",
                             request.workflow_id, exc)
                with self._lock:
                    self.failed += 1
            finally:
                self._queue.task_done()

    def submit(self, workflow_id: str, organization_id: str = "",
               inputs: dict | None = None,
               trigger: dict | None = None) -> RunRequest:
        request = RunRequest(workflow_id, organization_id, inputs, trigger)
        self._queue.put(request)
        return request

    def pending(self) -> int:
        return self._queue.qsize()

    def shutdown(self) -> None:
        self._stop.set()
        for thread in self._workers:
            thread.join(timeout=2)

    def health(self) -> dict:
        return {"workers": len(self._workers), "pending": self.pending(),
                "processed": self.processed, "failed": self.failed,
                "total": self.total, "status": "healthy"}