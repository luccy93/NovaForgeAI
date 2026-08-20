"""Analyzer tests (Volume 48)."""

import pytest

from app.quality.analyzers.base import ReviewContext
from app.quality.analyzers.correctness import CorrectnessAnalyzer
from app.quality.analyzers.performance import PerformanceAnalyzer
from app.quality.analyzers.reliability import ReliabilityAnalyzer
from app.quality.analyzers.architecture import ArchitectureAnalyzer
from app.quality.analyzers.api_compat import APICompatAnalyzer
from app.quality.analyzers.database import DatabaseAnalyzer
from app.quality.analyzers.dependency import DependencyAnalyzer
from app.quality.analyzers.documentation import DocumentationAnalyzer
from app.quality.analyzers.dead_code import DeadCodeAnalyzer
from app.quality.analyzers.code_smells import CodeSmellAnalyzer
from app.quality.analyzers.test_quality import TestQualityAnalyzer


@pytest.mark.asyncio
async def test_correctness_bare_except():
    analyzer = CorrectnessAnalyzer()
    ctx = ReviewContext(file_contents={"app.py": "try:\n    pass\nexcept:\n    pass"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("bare" in f.description.lower() or "except" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_correctness_clean_code():
    analyzer = CorrectnessAnalyzer()
    ctx = ReviewContext(file_contents={"app.py": "x = 1\ny = 2\nprint(x + y)"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) == 0


@pytest.mark.asyncio
async def test_performance_n_plus_one():
    analyzer = PerformanceAnalyzer()
    code = "for item in items:\n    result = db.query.filter(item.id).first()\n    print(result)"
    ctx = ReviewContext(file_contents={"models.py": code})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("n+1" in f.description.lower() or "query inside loop" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_performance_blocking_sleep():
    analyzer = PerformanceAnalyzer()
    ctx = ReviewContext(file_contents={"app.py": "import time\ntime.sleep(10)"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("sleep" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_reliability_no_timeout():
    analyzer = ReliabilityAnalyzer()
    ctx = ReviewContext(file_contents={"api.py": "response = requests.get(url)\nprint(response)"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("timeout" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_reliability_empty_handler():
    analyzer = ReliabilityAnalyzer()
    ctx = ReviewContext(file_contents={"app.py": "try:\n    x = 1\nexcept ValueError:\n    pass"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("error" in f.description.lower() or "handler" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_architecture_layer_violation():
    analyzer = ArchitectureAnalyzer()
    ctx = ReviewContext(file_contents={"api/routes.py": "from app.repository import UserRepository\nprint(UserRepository)"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("layer" in f.description.lower() or "violation" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_api_compat_deprecated():
    analyzer = APICompatAnalyzer()
    ctx = ReviewContext(file_contents={"api/routes.py": '@router.get("/old")\ndef old_endpoint():\n    """Deprecated."""\n    pass'})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("deprecated" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_database_destructive_migration():
    analyzer = DatabaseAnalyzer()
    ctx = ReviewContext(file_contents={"migration.py": "op.drop_table('users')"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("drop" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_dependency_dep_file_changed():
    analyzer = DependencyAnalyzer()
    ctx = ReviewContext(
        file_contents={"requirements.txt": "flask==2.0\nrequests==2.28"},
        changed_files=["requirements.txt"],
    )
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1


@pytest.mark.asyncio
async def test_documentation_missing_docstring():
    analyzer = DocumentationAnalyzer()
    ctx = ReviewContext(file_contents={"app.py": "def public_function():\n    return 42"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("docstring" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_dead_code_unused_import():
    analyzer = DeadCodeAnalyzer()
    ctx = ReviewContext(file_contents={"app.py": "import os\nimport sys\nprint('hello')"})
    result = await analyzer.analyze(ctx)
    unused = [f for f in result.findings if "unused import" in f.description.lower()]
    assert len(unused) >= 1


@pytest.mark.asyncio
async def test_code_smells_long_function():
    analyzer = CodeSmellAnalyzer()
    lines = ["def long_func():"] + ["    x = i" for i in range(60)]
    ctx = ReviewContext(file_contents={"app.py": "\n".join(lines)})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("long" in f.description.lower() or "lines" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_test_quality_skipped():
    analyzer = TestQualityAnalyzer()
    ctx = ReviewContext(file_contents={"test_app.py": "@pytest.mark.skip\ndef test_something():\n    pass"})
    result = await analyzer.analyze(ctx)
    assert len(result.findings) >= 1
    assert any("skip" in f.description.lower() for f in result.findings)


@pytest.mark.asyncio
async def test_analyzer_result_shape():
    analyzer = CorrectnessAnalyzer()
    ctx = ReviewContext(file_contents={"a.py": "x = 1"})
    result = await analyzer.analyze(ctx)
    assert result.analyzer_name == "correctness"
    assert isinstance(result.findings, list)
    assert result.tokens_used >= 0
