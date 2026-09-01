"""Volume 67 Commit 1 — AI Developer Experience (workspace, search, patch,
review, test, fix) tests.
"""

from datetime import datetime, timezone
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.ai_dev.common import (
    NotFoundError as AiDevNotFound,
    PatchAlreadyAppliedError,
    StalePatchError,
)
from app.ai_dev import chat as chat_svc
from app.ai_dev import deps as deps_svc
from app.ai_dev import explain as explain_svc
from app.ai_dev import fix as fix_svc
from app.ai_dev import indexing as indexing_svc
from app.ai_dev import patch as patch_svc
from app.ai_dev import repo_assist as repo_assist_svc
from app.ai_dev import review as review_svc
from app.ai_dev import search as search_svc
from app.ai_dev import tests as tests_svc
from app.ai_dev import usage as usage_svc
from app.ai_dev import workspaces as workspaces_svc
from app.ai_dev.models import (
    CodeAIUsage,
    CodePatch,
    CodeReview,
    CodeReviewFinding,
    CodeTestRun,
    CodeWorkspace,
)
from app.code_intelligence.models import CodeImport, CodeOwnership, CodeSymbol, CodeIndexVersion
from sqlalchemy import select

pytestmark = pytest.mark.asyncio

EVAL_FILE = "app/views.py"
EVIL_CONTENT = (
    "import pickle\n"
    "AKIAIOSFODNN7EXAMPLE\n"
    "eval(user_input)\n"
    "def vulnerable_thing():\n"
    "    return pickle.loads(blob)\n"
    + "x = 'y' * 3\n"
)


async def _new_ws(db, org_id, rid, name="ws"):
    return await workspaces_svc.create_workspace(
        db, org_id, "u1", name=name, repository_id=rid
    )


# ── workspaces ──────────────────────────────────────────────────────────────


async def test_workspace_create_and_scope(db, org_id, make_repo):
    data = await make_repo(org_id)
    ws = await _new_ws(db, org_id, data["repo_id"])
    assert ws.tenant == org_id
    assert ws.status == "ACTIVE"
    row = await workspaces_svc.get_workspace(db, org_id, ws.id)
    assert row is not None
    assert row.id == ws.id


async def test_workspace_tenant_isolation(db, org_id, other_org_id, make_repo):
    data = await make_repo(org_id)
    ws = await _new_ws(db, org_id, data["repo_id"])
    # other tenant cannot see the workspace
    assert await workspaces_svc.get_workspace(db, other_org_id, ws.id) is None
    # other tenant cannot create a workspace on org's repo
    with pytest.raises(AiDevNotFound):
        await workspaces_svc.create_workspace(db, other_org_id, "u2", name="ws2", repository_id=data["repo_id"])


async def test_workspace_pin(db, org_id, make_repo):
    data = await make_repo(org_id)
    ws = await _new_ws(db, org_id, data["repo_id"])
    ws = await workspaces_svc.pin_workspace(db, org_id, ws.id, pinned=True)
    assert ws.pinned is True


# ── index contract ──────────────────────────────────────────────────────────


async def test_index_contract_records_provenance_and_versions(db, org_id, make_repo):
    data = await make_repo(org_id)
    v1 = await indexing_svc.record_index_contract(db, org_id, data["repo_id"], commit_sha="abc")
    assert v1.version_number == 1
    assert v1.is_active is True
    v2 = await indexing_svc.record_index_contract(db, org_id, data["repo_id"], commit_sha="def")
    assert v2.version_number == 2
    assert v2.is_active is False
    assert v2.index_id == v1.index_id
    rows = (await db.execute(select(CodeIndexVersion))).scalars().all()
    assert len(rows) == 2


async def test_index_contract_pipelines_unavailable_is_honest(db, org_id, make_repo):
    data = await make_repo(org_id)
    result = await indexing_svc.trigger_full_pipeline(db, org_id, data["repo_id"])
    assert result["ok"] is False
    assert "unavailable" in result.get("error", "")  # no fabricated ready state


# ── search / context ────────────────────────────────────────────────────────


async def test_symbol_search_scoped_to_repo(db, org_id, other_org_id, make_repo, seed_index):
    r1 = await make_repo(org_id)
    r2 = await make_repo(other_org_id)
    await seed_index(r1["repo_id"], symbols=[("main", "FUNCTION", 1, 10)])
    await seed_index(r2["repo_id"], symbols=[("main", "FUNCTION", 1, 10)])
    hits = await search_svc.symbol_search(db, org_id, r1["repo_id"], "main")
    assert len(hits) == 1
    assert hits[0]["name"] == "main"
    # plain token in other repo must not leak into this search
    with pytest.raises(AiDevNotFound):
        await search_svc.symbol_search(db, org_id, r2["repo_id"], "main")


async def test_hybrid_search_honest_semantic_flag(db, org_id, make_repo, seed_index):
    r1 = await make_repo(org_id)
    await seed_index(r1["repo_id"], symbols=[("main", "FUNCTION", 1, 10)],
                     chunks=[("def main(x): return x + 1", 1, 10)])
    result = await search_svc.hybrid_search(db, org_id, r1["repo_id"], "main")
    assert result["semantic"] is False
    assert len(result["results"]) >= 2


async def test_build_context_truncates_at_budget(db, org_id, make_repo, seed_index):
    r1 = await make_repo(org_id)
    await seed_index(r1["repo_id"], symbols=[("main", "FUNCTION", 1, 10)],
                     chunks=[("def main(x):\n    return x + " + "1" * 200, 1, 30)])
    from app.ai_dev.context import build_context

    ctx = await build_context(db, org_id, r1["repo_id"], "main", token_budget=4)
    assert ctx["token_budget"] == 4
    assert ctx["tokens_used"] <= 4


# ── chat / explain ──────────────────────────────────────────────────────────


async def test_chat_falls_back_honestly_without_model(db, org_id, make_repo, seed_index):
    r1 = await make_repo(org_id)
    await seed_index(r1["repo_id"], symbols=[("main", "FUNCTION", 1, 10)])
    with patch.object(chat_svc, "_gateway_route", return_value=(None, {})), \
         patch.object(chat_svc, "_gateway_invoke", new=AsyncMock(return_value=None)):
        result = await chat_svc.code_chat(db, org_id, "u1", repository_id=r1["repo_id"], question="main")
    assert result["uncertainty"] is True
    assert result["model"] is None
    assert result["citations"]


async def test_explain_file_and_function(db, org_id, make_repo, seed_index):
    r1 = await make_repo(org_id)
    await seed_index(r1["repo_id"], symbols=[("main", "FUNCTION", 1, 10)])
    out = await explain_svc.explain(db, org_id, r1["repo_id"], "file", "src/main.py")
    assert out["kind"] == "file"
    assert out["file_path"] == "src/main.py"
    fn = await explain_svc.explain(db, org_id, r1["repo_id"], "function", "main")
    assert fn["kind"] == "function"
    assert fn["matches"][0]["name"] == "main"


# ── patches ─────────────────────────────────────────────────────────────────


async def test_patch_create_builds_diffs_and_hashes(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    patch = await patch_svc.create_patch(
        db, org_id, "u1",
        repository_id=r1["repo_id"],
        title="fix bug",
        files=[{"path": "app/main.py", "old_content": "def a():\n    pass\n", "new_content": "def a():\n    return 1\n"}],
    )
    entry = patch.files[0]
    assert entry["old_hash"] != entry["new_hash"]
    assert "def a()" in patch.diffs["app/main.py"]
    assert patch.status == "CREATED"


async def test_patch_stale_rejected_on_apply(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    patch = await patch_svc.create_patch(
        db, org_id, "u1",
        repository_id=r1["repo_id"],
        title="stale",
        files=[{"path": "app/main.py", "old_content": "OLD", "new_content": "NEW"}],
    )
    with pytest.raises(StalePatchError):
        await patch_svc.apply_patch(db, org_id, "u1", patch.id, current_files={"app/main.py": "DIFFERENT"})
    patch2 = await patch_svc.apply_patch(db, org_id, "u1", patch.id, current_files={"app/main.py": "OLD"})
    assert patch2.status == "APPLIED"
    with pytest.raises(PatchAlreadyAppliedError):
        await patch_svc.apply_patch(db, org_id, "u1", patch.id, current_files={"app/main.py": "OLD"})


async def test_patch_rollback_lifecycle(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    patch = await patch_svc.create_patch(
        db, org_id, "u1",
        repository_id=r1["repo_id"],
        title="rb",
        files=[{"path": "a.py", "old_content": "old", "new_content": "new"}],
    )
    await patch_svc.apply_patch(db, org_id, "u1", patch.id, current_files={"a.py": "old"})
    patch = await patch_svc.rollback_patch(db, org_id, "u1", patch.id)
    assert patch.status == "ROLLED_BACK"
    assert patch.rollback_diffs["a.py"].startswith("---")


async def test_patch_fanout_enforced(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    files = [{"path": f"f{i}.py", "old_content": "", "new_content": f"# {i}"} for i in range(12)]
    with pytest.raises(ValueError, match="max files"):
        await patch_svc.create_patch(db, org_id, "u1", repository_id=r1["repo_id"], title="too many", files=files)


# ── reviews ─────────────────────────────────────────────────────────────────


async def test_review_detects_secret_sast_and_static_findings(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    review = await review_svc.generate_review(
        db, org_id, "u1",
        repository_id=r1["repo_id"],
        files=[{"path": EVAL_FILE, "content": EVIL_CONTENT}],
    )
    assert review.status == "OPEN"
    rows = (
        (await db.execute(select(CodeReviewFinding).where(CodeReviewFinding.review_id == review.id)))
        .scalars().all()
    )
    cats = {f.category for f in rows}
    assert "SECURITY" in cats
    assert any("eval" in (f.reason or "") or "code_execution" in (f.reason or "") for f in rows)
    secrets = [f for f in rows if "scanner:secret" in (f.reason or "")]
    assert secrets  # real scanner produced at least one secret finding


async def test_review_dismiss_finding(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    review = await review_svc.generate_review(
        db, org_id, "u1", repository_id=r1["repo_id"],
        files=[{"path": "x.py", "content": EVIL_CONTENT}],
    )
    fid = (
        (await db.execute(select(CodeReviewFinding).where(CodeReviewFinding.review_id == review.id)))
        .scalars().first()
    ).id
    finding = await review_svc.dismiss_finding(db, org_id, "u1", review.id, fid, reason="FP")
    assert finding.status == "DISMISSED"
    assert finding.dismissed_reason == "FP"


# ── tests ───────────────────────────────────────────────────────────────────


async def test_test_plan_extracts_real_definitions(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    patch = await patch_svc.create_patch(
        db, org_id, "u1",
        repository_id=r1["repo_id"],
        title="add service",
        files=[{"path": "app/service.py", "old_content": "", "new_content": "def ping():\n    return 'pong'\n\nclass Repo:\n    def get(self):\n        pass\n"}],
    )
    run = await tests_svc.generate_test_plan(db, org_id, "u1", repository_id=r1["repo_id"], patch_id=patch.id)
    assert run.status == "GENERATED"
    plan = run.test_plan[0]
    assert plan["proposed_test_file"] == "tests/test_service.py"
    assert "ping" in plan["functions"]
    assert "Repo" in plan["functions"]


async def test_test_execute_creates_real_ci_run(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    run = await tests_svc.generate_test_plan(db, org_id, "u1", repository_id=r1["repo_id"])
    run2 = await tests_svc.execute_tests(db, org_id, "u1", run.id)
    assert run2.status == "QUEUED"
    assert run2.ci_pipeline_run_id
    from app.delivery.models import DeliveryPipelineRun
    drow = await db.get(DeliveryPipelineRun, uuid.UUID(run2.ci_pipeline_run_id))
    assert drow is not None
    assert drow.status == "queued"


async def test_test_result_ingested_from_ci(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    run = await tests_svc.generate_test_plan(db, org_id, "u1", repository_id=r1["repo_id"])
    run = await tests_svc.record_test_result(
        db, org_id, run.id, "failed",
        results=[{"name": "test_ping", "passed": False}],
        logs="1 failed",
        failures_analysis="assertion error",
    )
    assert run.status == "FAILED"
    assert len(run.test_results) == 1
    with pytest.raises(ValueError):
        await tests_svc.record_test_result(db, org_id, run.id, "BOGUS")


# ── fix loop ────────────────────────────────────────────────────────────────


async def test_fix_loop_bounded_and_creates_patch_proposals(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    result = await fix_svc.run_fix_loop(
        db, org_id, "u1",
        repository_id=r1["repo_id"],
        files=[{"path": EVAL_FILE, "content": EVIL_CONTENT}],
        goal="remove dangerous calls",
        patch_title="hardening",
        max_iterations=3,
    )
    assert result["iterations"] <= 3
    assert result["max_iterations"] == 3
    patches = (await db.execute(select(CodePatch))).scalars().all()
    assert patches  # deterministic remediation proposals were persisted
    assert result["cycles"][0]["findings"] >= 1


async def test_fix_loop_rejects_over_budget(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    with pytest.raises(ValueError):
        await fix_svc.run_fix_loop(
            db, org_id, "u1", repository_id=r1["repo_id"],
            files=[{"path": "a.py", "content": "x = 1\n"}],
            goal="g", patch_title="p", max_iterations=9,
        )


# ── dependencies ────────────────────────────────────────────────────────────


async def test_dependency_graph_from_imports(db, org_id, make_repo, seed_index):
    r1 = await make_repo(org_id)
    seed = await seed_index(r1["repo_id"])
    for name, external in (("os", True), ("flask", True), ("app.mod", False)):
        imp = CodeImport(
            repository_id=uuid.UUID(r1["repo_id"]),
            index_id=uuid.UUID(seed["index_id"]),
            source_file_id=uuid.UUID(seed["file_id"]),
            imported_name=name,
            import_type="MODULE",
            is_external=external,
        )
        db.add(imp)
    await db.flush()
    out = await deps_svc.dependency_graph(db, org_id, r1["repo_id"])
    assert out["total_edges"] == 3
    assert out["external_imports"]["os"] == 1


async def test_dependency_scan_reports_real_vulns(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    out = await deps_svc.analyze_dependencies(
        db, org_id, r1["repo_id"],
        files=[{"name": "requirements.txt", "content": "requests==2.28.0\nflask==2.0.0\n"}],
    )
    assert out["packages_analyzed"] == 2
    assert out["vulnerable"] is True
    assert any(v["cve_id"] == "CVE-2023-32681" for v in out["vulnerabilities"])


# ── repo assist ─────────────────────────────────────────────────────────────


async def test_change_summary_and_pr_assist(db, org_id, make_repo, seed_index):
    r1 = await make_repo(org_id)
    seed = await seed_index(r1["repo_id"])
    owner = CodeOwnership(
        repository_id=uuid.UUID(r1["repo_id"]),
        file_path="src/main.py",
        owner_email="lead@acme.io",
        ownership_score=0.9,
    )
    db.add(owner)
    await db.flush()
    files = [
        {"path": "src/main.py", "old_content": "a\n", "new_content": "b\n"},
    ]
    summary = await repo_assist_svc.change_summary(db, org_id, r1["repo_id"], files=files)
    assert summary["stats"]["files"] == 1
    assert summary["stats"]["deletions"] >= 1
    draft = await repo_assist_svc.pr_assistant(
        db, org_id, r1["repo_id"], title="chore: unify", files=files,
        test_summary={"status": "passed", "passed": 3},
    )
    assert "chore: unify" in draft["draft"]
    assert draft["suggested_reviewers"][0]["email"] == "lead@acme.io"


# ── usage ───────────────────────────────────────────────────────────────────


async def test_usage_records_and_totals(db, org_id, make_repo):
    r1 = await make_repo(org_id)
    await usage_svc.record_usage(
        db, org_id, "u1", action="chat", total_tokens=100,
        cost_cents=0.01, repository_id=r1["repo_id"],
    )
    totals = await usage_svc.usage_totals(db, org_id)
    assert totals["requests"] == 1
    assert totals["total_tokens"] == 100


# ── API surface ─────────────────────────────────────────────────────────────


async def test_api_workspace_and_index(api_client, org_id, make_repo):
    data = await make_repo(org_id)
    api_client._user_holder["user"].organization_id = org_id
    resp = await api_client.post("/api/v1/ai-dev/workspaces", json={
        "name": "api-ws", "repository_id": data["repo_id"],
    })
    assert resp.status_code == 201
    wid = resp.json()["id"]
    resp = await api_client.get(f"/api/v1/ai-dev/workspaces/{wid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "api-ws"


async def test_api_patch_stale_returns_409(api_client, org_id, make_repo):
    data = await make_repo(org_id)
    api_client._user_holder["user"].organization_id = org_id
    resp = await api_client.post("/api/v1/ai-dev/patch", json={
        "repository_id": data["repo_id"],
        "title": "api patch",
        "files": [{"path": "a.py", "old_content": "OLD", "new_content": "NEW"}],
    })
    assert resp.status_code == 201
    pid = resp.json()["id"]
    resp = await api_client.post(f"/api/v1/ai-dev/patches/{pid}/apply", json={
        "current_files": {"a.py": "STALE"},
    })
    assert resp.status_code == 409


async def test_api_search_and_usage(api_client, org_id, make_repo, seed_index):
    data = await make_repo(org_id)
    api_client._user_holder["user"].organization_id = org_id
    await seed_index(data["repo_id"], symbols=[("main", "FUNCTION", 1, 10)])
    resp = await api_client.get(
        f"/api/v1/ai-dev/repositories/{data['repo_id']}/search", params={"q": "main"}
    )
    assert resp.status_code == 200
    assert resp.json()["results"]
    resp = await api_client.get("/api/v1/ai-dev/usage")
    assert resp.status_code == 200
    assert isinstance(resp.json()["items"], list)