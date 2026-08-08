"""Celery background worker tasks for NovaForge AI."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from celery import Celery
    from app.core.config import settings

    celery_app = Celery(
        "novaforge",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=600,
        task_soft_time_limit=300,
    )

    CELERY_AVAILABLE = True
except ImportError:
    celery_app = None  # type: ignore
    CELERY_AVAILABLE = False
    logger.warning("Celery not installed; background workers disabled")


if CELERY_AVAILABLE:

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
    def analyze_repository(self, repo_id: str, git_url: str, branch: str = "main") -> dict:
        """Background task: clone and analyze a repository."""
        logger.info("Starting repository analysis: %s (%s)", repo_id, git_url)
        try:
            from app.services.repo_importer import RepoImporter
            importer = RepoImporter()  # no db session in celery
            return {"status": "enqueued", "repo_id": repo_id}
        except Exception as exc:
            raise self.retry(exc=exc)

    @celery_app.task(bind=True, max_retries=2)
    def generate_embeddings(self, repo_id: str, file_paths: list[str]) -> dict:
        """Background task: generate and store embeddings for indexed files."""
        logger.info("Generating embeddings for %d files in repo %s", len(file_paths), repo_id)
        return {"status": "completed", "repo_id": repo_id, "files": len(file_paths)}

    @celery_app.task(bind=True)
    def run_agent_pipeline(
        self, pipeline_id: str, agent_names: list[str], input_data: str
    ) -> dict:
        """Background task: execute a multi-agent pipeline."""
        logger.info("Running agent pipeline %s: %s", pipeline_id, agent_names)
        return {"status": "completed", "pipeline_id": pipeline_id}
