from unittest.mock import MagicMock, patch
import pytest
import sys


@pytest.fixture(autouse=True)
def reset_module():
    yield
    keys = [k for k in sys.modules if "workers" in k]
    for k in keys:
        del sys.modules[k]


class TestWorkersCeleryAvailable:
    @pytest.fixture(autouse=True)
    def mock_celery(self):
        with patch("celery.Celery") as mock_cls, patch(
            "app.services.repo_importer.RepoImporter"
        ):
            mock_app = MagicMock()
            mock_app.conf = MagicMock()

            def _task_decorator(*args, **kwargs):
                bind = kwargs.get("bind", False)

                def decorator(fn):
                    if bind:
                        def wrapper(*a, **kw):
                            return fn(MagicMock(), *a, **kw)
                        return wrapper
                    return fn
                return decorator

            mock_app.task = _task_decorator
            mock_cls.return_value = mock_app
            yield

    def test_celery_app_configured(self):
        import app.workers
        assert app.workers.celery_app is not None

    def test_celery_available_flag(self):
        import app.workers
        assert app.workers.CELERY_AVAILABLE is True

    def test_task_functions_exist(self):
        import app.workers
        assert hasattr(app.workers, "analyze_repository")
        assert hasattr(app.workers, "generate_embeddings")
        assert hasattr(app.workers, "run_agent_pipeline")

    def test_analyze_repository_returns_enqueued(self):
        import app.workers
        result = app.workers.analyze_repository("repo-1", "https://github.com/example/repo.git")
        assert result == {"status": "enqueued", "repo_id": "repo-1"}

    def test_analyze_repository_uses_default_branch(self):
        import app.workers
        result = app.workers.analyze_repository("r-1", "https://example.com/repo.git")
        assert result["status"] == "enqueued"

    def test_generate_embeddings_returns_completed(self):
        import app.workers
        result = app.workers.generate_embeddings("repo-1", ["main.py", "utils.py"])
        assert result == {"status": "completed", "repo_id": "repo-1", "files": 2}

    def test_generate_embeddings_zero_files(self):
        import app.workers
        result = app.workers.generate_embeddings("repo-1", [])
        assert result["files"] == 0

    def test_run_agent_pipeline_returns_completed(self):
        import app.workers
        result = app.workers.run_agent_pipeline("pipe-1", ["planner"], "build")
        assert result == {"status": "completed", "pipeline_id": "pipe-1"}

    def test_run_agent_pipeline_empty_agents(self):
        import app.workers
        result = app.workers.run_agent_pipeline("pipe-2", [], "")
        assert result["status"] == "completed"


class TestWorkersCeleryNotAvailable:
    @pytest.fixture(autouse=True)
    def mock_celery_unavailable(self):
        keys = [k for k in sys.modules if "workers" in k]
        for k in keys:
            del sys.modules[k]
        with patch.dict(
            "sys.modules",
            {"celery": None},
        ):
            yield

    def test_celery_app_none_without_celery(self):
        import app.workers
        assert app.workers.CELERY_AVAILABLE is False
        assert app.workers.celery_app is None

    def test_celery_not_available_no_tasks_defined(self):
        import app.workers
        assert not hasattr(app.workers, "analyze_repository")

    def test_celery_not_available_warning(self):
        import app.workers
        assert app.workers.CELERY_AVAILABLE is False
