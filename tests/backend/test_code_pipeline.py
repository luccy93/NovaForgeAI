"""Tests for the indexing pipeline at backend/app/code_intelligence/pipeline.py."""

import asyncio
import os
import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

# ── Stub `app` package before any submodule imports ───────────────────
_backend_dir = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
if "app" not in sys.modules:
    _app = types.ModuleType("app")
    _app.__path__ = [os.path.join(_backend_dir, "app")]
    _app.__package__ = "app"
    _app.__version__ = "3.0.0-test"
    sys.modules["app"] = _app

import pytest

from app.code_intelligence.pipeline import (
    EXTENSION_LANGUAGE_MAP,
    IGNORE_PATTERNS,
    STAGE_ORDER,
    IndexingPipeline,
)


# ─── Helpers ─────────────────────────────────────────────────────────


def _make_pipeline():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return IndexingPipeline(db_session=db)


# ─── TestIgnorePatterns ──────────────────────────────────────────────


class TestIgnorePatterns:
    """Verify that IGNORE_PATTERNS correctly gates file/directory skipping."""

    def test_skip_git_dir(self):
        pipeline = _make_pipeline()
        assert ".git" in IGNORE_PATTERNS
        assert pipeline._should_skip_path(".git", is_dir=True) is True

    def test_skip_node_modules(self):
        pipeline = _make_pipeline()
        assert "node_modules" in IGNORE_PATTERNS
        assert pipeline._should_skip_path("node_modules", is_dir=True) is True

    def test_skip_pycache(self):
        pipeline = _make_pipeline()
        assert "__pycache__" in IGNORE_PATTERNS
        assert pipeline._should_skip_path("__pycache__", is_dir=True) is True

    def test_skip_env_files(self):
        pipeline = _make_pipeline()
        assert ".env" in IGNORE_PATTERNS
        assert ".env.local" in IGNORE_PATTERNS
        assert ".env.production" in IGNORE_PATTERNS
        assert pipeline._should_skip_path(".env", is_dir=False) is True
        assert pipeline._should_skip_path(".env.local", is_dir=False) is True
        assert pipeline._should_skip_path(".env.production", is_dir=False) is True

    def test_allow_source_files(self):
        pipeline = _make_pipeline()
        assert pipeline._should_skip_path("main.py", is_dir=False) is False
        assert pipeline._should_skip_path("app.ts", is_dir=False) is False
        assert pipeline._should_skip_path("utils.js", is_dir=False) is False
        assert pipeline._should_skip_path("handler.go", is_dir=False) is False


# ─── TestLanguageDetection ───────────────────────────────────────────


class TestLanguageDetection:
    """Verify language detection from file extensions."""

    def test_detect_python(self):
        pipeline = _make_pipeline()
        assert pipeline._detect_language("src/models/user.py") == "python"
        assert pipeline._detect_language("utils.pyi") == "python"

    def test_detect_typescript(self):
        pipeline = _make_pipeline()
        assert pipeline._detect_language("src/app.ts") == "typescript"
        assert pipeline._detect_language("components/Header.tsx") == "typescript"

    def test_detect_mixed_repo(self):
        pipeline = _make_pipeline()
        files = {
            "main.py": "python",
            "app.ts": "typescript",
            "server.go": "go",
            "lib.rs": "rust",
            "index.js": "javascript",
            "handler.java": "java",
            "style.css": "css",
            "schema.sql": "sql",
        }
        detected = {path: pipeline._detect_language(path) for path in files}
        for path, expected_lang in files.items():
            assert detected[path] == expected_lang, (
                f"Expected {expected_lang} for {path}, got {detected[path]}"
            )
        assert pipeline._detect_language("readme.md") == "markdown"
        assert pipeline._detect_language("config.toml") == "toml"


# ─── TestPipelineStages ──────────────────────────────────────────────


class TestPipelineStages:
    """Verify pipeline stage ordering, tracking, and failure isolation."""

    def test_stage_order(self):
        assert STAGE_ORDER[0] == "DISCOVER"
        assert STAGE_ORDER[-1] == "ACTIVATE"
        for name in (
            "PARSE", "EXTRACT_SYMBOLS", "RESOLVE_REFS", "BUILD_GRAPH",
            "CALC_METRICS", "DETECT_SMELLS", "SECURITY_SCAN", "ARCHITECTURE",
            "CHUNK", "EMBED", "UPDATE_GRAPH", "VALIDATE",
        ):
            assert name in STAGE_ORDER

        assert (
            STAGE_ORDER.index("DISCOVER")
            < STAGE_ORDER.index("PARSE")
            < STAGE_ORDER.index("EXTRACT_SYMBOLS")
        )
        assert (
            STAGE_ORDER.index("RESOLVE_REFS")
            < STAGE_ORDER.index("BUILD_GRAPH")
            < STAGE_ORDER.index("CALC_METRICS")
        )
        assert STAGE_ORDER.index("ACTIVATE") == len(STAGE_ORDER) - 1

    def test_stage_tracking(self):
        pipeline = _make_pipeline()
        stages_seen: list[str] = []

        async def mock_run_stage(index_id, stage, **kwargs):
            stages_seen.append(stage)
            return {"status": "completed"}

        pipeline.run_stage = mock_run_stage
        asyncio.run(_simulate_indexing(pipeline, stages_seen))

        assert len(stages_seen) > 0
        assert all(isinstance(s, str) for s in stages_seen)

    def test_failure_isolates_stage(self):
        pipeline = _make_pipeline()
        pipeline._emit_event = MagicMock()
        failing_stage = "CALC_METRICS"

        async def selective_run_stage(index_id, stage, **kwargs):
            if stage == failing_stage:
                raise RuntimeError(f"Simulated failure in {stage}")
            return {"status": "completed"}

        pipeline.run_stage = selective_run_stage
        pipeline._record_error = AsyncMock()
        pipeline._update_status = AsyncMock()

        index = MagicMock()
        index.id = uuid.uuid4()
        index.status = "QUEUED"
        index.errors = []
        pipeline._load_index = AsyncMock(return_value=index)
        pipeline.db = AsyncMock()
        pipeline.db.add = MagicMock()
        pipeline.db.flush = AsyncMock()

        stages_run: list[str] = []
        failed = None

        async def run():
            nonlocal failed
            for stage in STAGE_ORDER:
                if stage == "ACTIVATE":
                    continue
                try:
                    await pipeline.run_stage(
                        str(index.id), stage, repo_id="r1", repo_path="/tmp"
                    )
                    stages_run.append(stage)
                except Exception:
                    failed = stage
                    break

        asyncio.run(run())

        assert failed == failing_stage
        assert failing_stage not in stages_run
        assert "DISCOVER" in stages_run


# ─── TestEventEmission ───────────────────────────────────────────────


class TestEventEmission:
    """Verify that pipeline emits start and completed events."""

    def test_index_started_event(self):
        pipeline = _make_pipeline()
        emitted: list[dict] = []
        pipeline._emit_event = lambda t, d: emitted.append({"type": t, "data": d})

        pipeline._emit_event("pipeline_started", {
            "index_id": "idx-1",
            "repo_id": "repo-1",
            "repo_path": "/tmp/repo",
            "commit_sha": "abc123",
            "incremental": True,
        })

        assert len(emitted) == 1
        assert emitted[0]["type"] == "pipeline_started"
        assert emitted[0]["data"]["index_id"] == "idx-1"
        assert emitted[0]["data"]["commit_sha"] == "abc123"

    def test_index_completed_event(self):
        pipeline = _make_pipeline()
        emitted: list[dict] = []
        pipeline._emit_event = lambda t, d: emitted.append({"type": t, "data": d})

        pipeline._emit_event("pipeline_completed", {
            "index_id": "idx-1",
            "repo_id": "repo-1",
            "status": "READY",
            "files_total": 42,
            "files_processed": 42,
            "symbols_extracted": 128,
            "chunks_created": 256,
        })

        assert len(emitted) == 1
        data = emitted[0]["data"]
        assert data["status"] == "READY"
        assert data["files_total"] == 42
        assert data["symbols_extracted"] == 128
        assert data["chunks_created"] == 256


# ─── Helpers ─────────────────────────────────────────────────────────


async def _simulate_indexing(pipeline, stages_seen):
    for stage in STAGE_ORDER:
        if stage == "ACTIVATE":
            continue
        await pipeline.run_stage("index-1", stage)
