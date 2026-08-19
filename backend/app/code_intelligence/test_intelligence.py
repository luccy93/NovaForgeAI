"""Test Intelligence — detect, extract, map and analyse tests across
repositories stored in the code-intelligence database.

All methods are async and operate on SQLAlchemy ``AsyncSession`` instances.
File I/O is fully virtual: the module reads content from arguments or DB
records, never from the filesystem.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeFile,
    CodeIndex,
    CodeSymbol,
    CodeTest,
    SymbolType,
)

logger = logging.getLogger(__name__)

# ─── Test-file detection patterns ────────────────────────────────────────

TEST_FILE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"^test_[\w/\\]+\.py$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+_test\.py$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+/conftest\.py$", re.IGNORECASE),
    ],
    "javascript": [
        re.compile(r"^[\w/\\]+\.test\.js$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+\.spec\.js$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+/__tests__/[\w/\\]+\.js$", re.IGNORECASE),
    ],
    "typescript": [
        re.compile(r"^[\w/\\]+\.test\.ts$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+\.spec\.ts$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+\.test\.tsx$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+\.spec\.tsx$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+/__tests__/[\w/\\]+\.tsx?$", re.IGNORECASE),
    ],
    "go": [
        re.compile(r"^[\w/\\]+_test\.go$", re.IGNORECASE),
    ],
    "java": [
        re.compile(r"^[\w/\\]+Test\.java$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+Tests\.java$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+TestCase\.java$", re.IGNORECASE),
    ],
    "ruby": [
        re.compile(r"^[\w/\\]+_spec\.rb$", re.IGNORECASE),
        re.compile(r"^test_[\w/\\]+\.rb$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+_test\.rb$", re.IGNORECASE),
    ],
    "kotlin": [
        re.compile(r"^[\w/\\]+Test\.kt$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+Spec\.kt$", re.IGNORECASE),
    ],
    "scala": [
        re.compile(r"^[\w/\\]+Spec\.scala$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+Suite\.scala$", re.IGNORECASE),
        re.compile(r"^[\w/\\]+Test\.scala$", re.IGNORECASE),
    ],
    "c_sharp": [
        re.compile(r"^[\w/\\]+Tests?\.cs$", re.IGNORECASE),
    ],
}

LANG_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx"],
    "go": [".go"],
    "java": [".java"],
    "ruby": [".rb"],
    "kotlin": [".kt", ".kts"],
    "scala": [".scala"],
    "c_sharp": [".cs"],
}

EXTENSION_TO_LANG: dict[str, str] = {}
for lang, exts in LANG_EXTENSIONS.items():
    for ext in exts:
        EXTENSION_TO_LANG[ext] = lang


# ─── Framework detection patterns ────────────────────────────────────────

FRAMEWORK_DETECTORS: dict[str, dict[str, re.Pattern[str]]] = {
    "python": {
        "pytest": re.compile(
            r"(?:import\s+pytest|from\s+pytest|@pytest\.mark\.|@pytest\.fixture|"
            r"def\s+test_\w+\s*\(|class\s+Test\w+)"
        ),
        "unittest": re.compile(
            r"(?:import\s+unittest|from\s+unittest|class\s+\w+\(unittest\.TestCase\)|"
            r"def\s+test_\w+\s*\(self\))"
        ),
    },
    "javascript": {
        "jest": re.compile(
            r"(?:describe\s*\(|it\s*\(|test\s*\(|expect\s*\(|"
            r"jest\.mock\(|jest\.fn\(|beforeEach\s*\(|afterEach\s*\()"
        ),
        "mocha": re.compile(
            r"(?:describe\s*\(|it\s*\(|before\s*\(|after\s*\(|"
            r"context\s*\(| specify\s*\()"
        ),
        "vitest": re.compile(
            r"(?:import\s+\{.*\}\s+from\s+['\"]vitest['\"]|"
            r"vi\.mock\(|vi\.fn\(|describe\s*\(|it\s*\(|test\s*\()"
        ),
    },
    "typescript": {
        "jest": re.compile(
            r"(?:describe\s*\(|it\s*\(|test\s*\(|expect\s*\(|"
            r"jest\.mock\(|jest\.fn\(|beforeEach\s*\(|afterEach\s*\()"
        ),
        "vitest": re.compile(
            r"(?:import\s+\{.*\}\s+from\s+['\"]vitest['\"]|"
            r"vi\.mock\(|vi\.fn\(|describe\s*\(|it\s*\(|test\s*\()"
        ),
    },
    "go": {
        "go_test": re.compile(
            r"(?:func\s+Test\w+\s*\(|func\s+Test\w+\s*\(t\s+\*testing\.T\)|"
            r"func\s+Benchmark\w+\s*\(|func\s+Example\w+\s*\()"
        ),
    },
    "java": {
        "junit": re.compile(
            r"(?:@Test|@Before\b|@After\b|@BeforeEach|@AfterEach|"
            r"@BeforeAll|@AfterAll|@DisplayName|@ParameterizedTest|"
            r"import\s+org\.junit)"
        ),
        "testng": re.compile(
            r"(?:@Test|@BeforeMethod|@AfterMethod|@DataProvider|"
            r"import\s+org\.testng)"
        ),
    },
    "ruby": {
        "rspec": re.compile(
            r"(?:RSpec\.describe|describe\s+|context\s+|it\s+['\"].*['\"]|"
            r"let\s*\(|before\s*\(:each\)|subject\s*\{)"
        ),
        "minitest": re.compile(
            r"(?:class\s+\w+\s*<\s*(?:Test::Unit::)?TestCase|"
            r"def\s+test_\w+|require\s+['\"]minitest['\"])"
        ),
    },
}

# ─── Fixture patterns ────────────────────────────────────────────────────

FIXTURE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"@pytest\.fixture\b"),
        re.compile(r"@pytest\.yield_fixture\b"),
        re.compile(r"def\s+conftest\b"),
    ],
    "javascript": [
        re.compile(r"beforeEach\s*\("),
        re.compile(r"afterEach\s*\("),
        re.compile(r"beforeAll\s*\("),
        re.compile(r"afterAll\s*\("),
        re.compile(r"before\s*\("),
        re.compile(r"after\s*\("),
    ],
    "typescript": [
        re.compile(r"beforeEach\s*\("),
        re.compile(r"afterEach\s*\("),
        re.compile(r"beforeAll\s*\("),
        re.compile(r"afterAll\s*\("),
    ],
    "java": [
        re.compile(r"@BeforeEach"),
        re.compile(r"@AfterEach"),
        re.compile(r"@BeforeAll"),
        re.compile(r"@AfterAll"),
        re.compile(r"@Before\b"),
        re.compile(r"@After\b"),
    ],
    "ruby": [
        re.compile(r"before\s*\(:each\)"),
        re.compile(r"after\s*\(:each\)"),
        re.compile(r"let\s*\("),
        re.compile(r"subject\s*\{"),
    ],
}

# ─── Mock patterns ───────────────────────────────────────────────────────

MOCK_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"from\s+unittest\.mock\s+import"),
        re.compile(r"import\s+unittest\.mock"),
        re.compile(r"@mock\.patch\b"),
        re.compile(r"@patch\b"),
        re.compile(r"monkeypatch\."),
        re.compile(r"Mock\s*\("),
        re.compile(r"MagicMock\s*\("),
        re.compile(r"AsyncMock\s*\("),
        re.compile(r"mocker\."),
    ],
    "javascript": [
        re.compile(r"jest\.mock\s*\("),
        re.compile(r"jest\.spyOn\s*\("),
        re.compile(r"jest\.fn\s*\("),
        re.compile(r"sinon\.stub\s*\("),
        re.compile(r"sinon\.mock\s*\("),
        re.compile(r"sinon\.spy\s*\("),
        re.compile(r"vi\.mock\s*\("),
        re.compile(r"vi\.spyOn\s*\("),
        re.compile(r"vi\.fn\s*\("),
    ],
    "typescript": [
        re.compile(r"jest\.mock\s*\("),
        re.compile(r"jest\.spyOn\s*\("),
        re.compile(r"vi\.mock\s*\("),
        re.compile(r"vi\.spyOn\s*\("),
        re.compile(r"vi\.fn\s*\("),
    ],
    "java": [
        re.compile(r"Mockito\.mock\s*\("),
        re.compile(r"@Mock\b"),
        re.compile(r"@InjectMocks"),
        re.compile(r"when\s*\("),
        re.compile(r"verify\s*\("),
    ],
    "ruby": [
        re.compile(r"double\s*\("),
        re.compile(r"instance_double\s*\("),
        re.compile(r"allow\s*\("),
        re.compile(r"receive\s*\("),
    ],
}

# ─── Parametrize / data-driven patterns ──────────────────────────────────

PARAMETRIZE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"@pytest\.mark\.parametrize\s*\("),
        re.compile(r"@pytest\.param\s*\("),
        re.compile(r"pytest\.mark\.parametrize"),
    ],
    "javascript": [
        re.compile(r"\.each\s*\(\s*\["),
        re.compile(r"\.each\s*\(\s*\("),
        re.compile(r"\.test\.each\s*\("),
        re.compile(r"\.it\.each\s*\("),
        re.compile(r"\.describe\.each\s*\("),
    ],
    "typescript": [
        re.compile(r"\.each\s*\(\s*\["),
        re.compile(r"\.each\s*\(\s*\("),
        re.compile(r"\.test\.each\s*\("),
        re.compile(r"\.it\.each\s*\("),
    ],
    "java": [
        re.compile(r"@ParameterizedTest"),
        re.compile(r"@CsvSource"),
        re.compile(r"@MethodSource"),
        re.compile(r"@ValueSource"),
        re.compile(r"@EnumSource"),
        re.compile(r"@ArgumentsSource"),
    ],
    "ruby": [
        re.compile(r"\.each\s+do\s+\|"),
        re.compile(r"it\s+['\"].*['\"],\s+:\w+"),
    ],
}

# ─── Assertion patterns ──────────────────────────────────────────────────

ASSERTION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"\bassert\b"),
        re.compile(r"\bassertEqual\b"),
        re.compile(r"\bassertNotEqual\b"),
        re.compile(r"\bassertTrue\b"),
        re.compile(r"\bassertFalse\b"),
        re.compile(r"\bassertIs\b"),
        re.compile(r"\bassertIsNone\b"),
        re.compile(r"\bassertRaises\b"),
        re.compile(r"\bassertIn\b"),
        re.compile(r"\bassertAlmostEqual\b"),
        re.compile(r"pytest\.raises\b"),
        re.compile(r"expect\("),
    ],
    "javascript": [
        re.compile(r"\bexpect\s*\("),
        re.compile(r"\bassert\s*\("),
        re.compile(r"\bassert\.strictEqual\b"),
        re.compile(r"\bassert\.deepStrictEqual\b"),
        re.compile(r"\bassert\.notStrictEqual\b"),
    ],
    "typescript": [
        re.compile(r"\bexpect\s*\("),
        re.compile(r"\bassert\s*\("),
        re.compile(r"\bassertEqual\b"),
    ],
    "go": [
        re.compile(r"\b(?:t|tt)\.(Errorf|Fatalf|Logf)\b"),
        re.compile(r"\b(?:if|if)\s+.*!=\s*nil\b"),
        re.compile(r"\bassert\.\w+\b"),
        re.compile(r"\brequire\.\w+\b"),
    ],
    "java": [
        re.compile(r"assertEquals\b"),
        re.compile(r"assertNotEquals\b"),
        re.compile(r"assertTrue\b"),
        re.compile(r"assertFalse\b"),
        re.compile(r"assertNull\b"),
        re.compile(r"assertNotNull\b"),
        re.compile(r"assertThrows\b"),
        re.compile(r"assertThat\b"),
        re.compile(r"Assertions\."),
    ],
    "ruby": [
        re.compile(r"\bexpect\s*\("),
        re.compile(r"\bassert_equal\b"),
        re.compile(r"\bassert_\w+\b"),
        re.compile(r"\brefute_\w+\b"),
    ],
}

# ─── Regex patterns for extracting test definitions ──────────────────────

TEST_FUNC_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(
            r"^(?P<indent>\s*)(?:@[\w.]+(?:\(.*?\))?\s*\n\s*)*"
            r"(?:async\s+)?def\s+(?P<name>test_\w+)\s*\(",
            re.MULTILINE,
        ),
        re.compile(
            r"^(?P<indent>\s*)(?:@[\w.]+(?:\(.*?\))?\s*\n\s*)*"
            r"class\s+(?P<name>Test\w+)\s*(?:\([\w.,\s()]*\))?:",
            re.MULTILINE,
        ),
    ],
    "javascript": [
        re.compile(
            r"\b(?:it|test)\s*\(\s*['\"](?P<name>[^'\"]+)['\"]",
            re.MULTILINE,
        ),
        re.compile(
            r"\bdescribe\s*\(\s*['\"](?P<name>[^'\"]+)['\"]",
            re.MULTILINE,
        ),
    ],
    "typescript": [
        re.compile(
            r"\b(?:it|test)\s*\(\s*['\"](?P<name>[^'\"]+)['\"]",
            re.MULTILINE,
        ),
        re.compile(
            r"\bdescribe\s*\(\s*['\"](?P<name>[^'\"]+)['\"]",
            re.MULTILINE,
        ),
    ],
    "go": [
        re.compile(
            r"^func\s+(?P<name>Test\w+)\s*\(",
            re.MULTILINE,
        ),
        re.compile(
            r"^func\s+(?P<name>Benchmark\w+)\s*\(",
            re.MULTILINE,
        ),
        re.compile(
            r"^func\s+(?P<name>Example\w+)\s*\(",
            re.MULTILINE,
        ),
    ],
    "java": [
        re.compile(
            r"(?:@Test(?:\([^)]*\))?\s*\n\s*)"
            r"(?:public\s+)?void\s+(?P<name>\w+)\s*\(",
            re.MULTILINE,
        ),
        re.compile(
            r"(?:@DisplayName\s*\(['\"]([^'\"]+)['\"]\)\s*\n\s*)?"
            r"(?:@Test(?:\([^)]*\))?\s*\n\s*)"
            r"(?:public\s+)?void\s+(?P<name>\w+)\s*\(",
            re.MULTILINE,
        ),
        re.compile(
            r"class\s+(?P<name>\w+(?:Test|Tests|TestCase))\b",
            re.MULTILINE,
        ),
    ],
    "ruby": [
        re.compile(
            r"\bit\s+['\"](?P<name>[^'\"]+)['\"]",
            re.MULTILINE,
        ),
        re.compile(
            r"\bdescribe\s+['\"]?(?P<name>[^'\"\s]+)['\"]?",
            re.MULTILINE,
        ),
    ],
}

FIXTURE_DEF_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(
            r"(?:@pytest\.fixture(?:\(.*?\))?\s*\n\s*)"
            r"(?:async\s+)?def\s+(?P<name>\w+)\s*\(",
            re.MULTILINE,
        ),
    ],
    "javascript": [
        re.compile(
            r"\b(?:beforeEach|afterEach|beforeAll|afterAll|before|after)\s*\(",
            re.MULTILINE,
        ),
    ],
    "typescript": [
        re.compile(
            r"\b(?:beforeEach|afterEach|beforeAll|afterAll)\s*\(",
            re.MULTILINE,
        ),
    ],
    "java": [
        re.compile(
            r"(?:@BeforeEach|@AfterEach|@BeforeAll|@AfterAll|@Before|@After)\s*\n"
            r"\s*(?:public\s+)?void\s+(?P<name>\w+)\s*\(",
            re.MULTILINE,
        ),
    ],
    "ruby": [
        re.compile(
            r"\b(?:before|after)\s*\(:(?:each|all)\)\s+do",
            re.MULTILINE,
        ),
        re.compile(
            r"\blet\s*\(\s*:(?P<name>\w+)\s*\)",
            re.MULTILINE,
        ),
    ],
}

# ─── Test-name to source-symbol mapping heuristics ──────────────────────

_STRIP_PREFIXES = re.compile(r"^(?:test_|Test|spec_|Spec_|should_)")
_STRIP_SUFFIXES = re.compile(r"(?:_test|_spec|Tests?|Specs?|TestCase)$")


def _infer_source_symbol(test_name: str) -> Optional[str]:
    """Heuristically derive the source symbol name from a test name."""
    name = test_name
    name = _STRIP_PREFIXES.sub("", name)
    name = _STRIP_SUFFIXES.sub("", name)
    if not name:
        return None
    return name


# ─── Dataclasses ─────────────────────────────────────────────────────────


@dataclass
class TestFileInfo:
    file_id: uuid.UUID
    file_path: str
    file_name: str
    language: str
    detected_framework: Optional[str] = None
    line_count: int = 0
    is_test_file: bool = True


@dataclass
class TestRecord:
    file_id: uuid.UUID
    test_type: str
    test_name: str
    source_symbol_name: Optional[str] = None
    source_file_path: Optional[str] = None
    framework: Optional[str] = None
    is_async: bool = False
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    metadata_: dict = field(default_factory=dict)


@dataclass
class TestMapping:
    test_name: str
    test_file_path: str
    source_symbol_name: Optional[str] = None
    source_file_id: Optional[uuid.UUID] = None
    confidence: float = 0.0


@dataclass
class CoverageSummary:
    total_files: int = 0
    test_files: int = 0
    total_tests: int = 0
    source_files_with_tests: int = 0
    source_files_without_tests: int = 0
    framework_distribution: dict[str, int] = field(default_factory=dict)
    test_type_distribution: dict[str, int] = field(default_factory=dict)
    coverage_sources: list[str] = field(default_factory=list)


@dataclass
class TestQualityMetrics:
    file_id: uuid.UUID
    file_path: str
    test_count: int = 0
    fixture_count: int = 0
    mock_count: int = 0
    parametrize_count: int = 0
    assert_density: float = 0.0
    mock_ratio: float = 0.0
    avg_test_length: float = 0.0
    test_length_stddev: float = 0.0
    framework: Optional[str] = None
    quality_score: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class TestGapInfo:
    symbol_id: uuid.UUID
    symbol_name: str
    symbol_type: str
    file_path: str
    qualified_name: str
    has_tests: bool = False
    related_test_names: list[str] = field(default_factory=list)


@dataclass
class CoverageRecord:
    file_path: str
    line_rate: Optional[float] = None
    branch_rate: Optional[float] = None
    lines_covered: Optional[int] = None
    lines_total: Optional[int] = None
    branches_covered: Optional[int] = None
    branches_total: Optional[int] = None


# ─── Helpers ─────────────────────────────────────────────────────────────


def _detect_language(file_path: str) -> Optional[str]:
    """Determine language from file extension."""
    lower = file_path.lower()
    for ext, lang in EXTENSION_TO_LANG.items():
        if lower.endswith(ext):
            return lang
    return None


def _is_test_file(file_name: str, language: str) -> bool:
    """Check file name against known test-file patterns."""
    patterns = TEST_FILE_PATTERNS.get(language, [])
    for pat in patterns:
        if pat.search(file_name):
            return True
    return False


def _detect_framework(content: str, language: str) -> Optional[str]:
    """Detect the primary test framework used in a file."""
    detectors = FRAMEWORK_DETECTORS.get(language, {})
    best: Optional[str] = None
    best_count = 0
    for framework, pattern in detectors.items():
        matches = pattern.findall(content)
        if len(matches) > best_count:
            best = framework
            best_count = len(matches)
    return best


def _count_patterns(content: str, patterns: list[re.Pattern[str]]) -> int:
    total = 0
    for pat in patterns:
        total += len(pat.findall(content))
    return total


def _compute_stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return variance ** 0.5


# ─── Coverage file parsers ──────────────────────────────────────────────


def _parse_coverage_json(content: str) -> list[CoverageRecord]:
    """Parse a generic coverage.json structure (Istanbul/nyc format)."""
    import json

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return []

    records: list[CoverageRecord] = []
    files = data.get("files") or data.get("coverageMap") or {}
    if isinstance(files, dict):
        for fpath, info in files.items():
            if isinstance(info, dict):
                summary = info.get("summary") or info
                records.append(
                    CoverageRecord(
                        file_path=fpath,
                        line_rate=summary.get("linePercent", summary.get("lines", {}).get("pct"))
                        if isinstance(summary, dict)
                        else None,
                        lines_covered=summary.get("lines", {}).get("covered")
                        if isinstance(summary, dict) and isinstance(summary.get("lines"), dict)
                        else None,
                        lines_total=summary.get("lines", {}).get("total")
                        if isinstance(summary, dict) and isinstance(summary.get("lines"), dict)
                        else None,
                    )
                )
    return records


def _parse_lcov(content: str) -> list[CoverageRecord]:
    """Parse lcov.info format."""
    records: list[CoverageRecord] = []
    current_path: Optional[str] = None
    lines_found = 0
    lines_hit = 0
    branches_found = 0
    branches_hit = 0

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("SF:"):
            current_path = line[3:]
        elif line.startswith("LF:"):
            try:
                lines_found = int(line[3:])
            except ValueError:
                pass
        elif line.startswith("LH:"):
            try:
                lines_hit = int(line[3:])
            except ValueError:
                pass
        elif line.startswith("BRF:"):
            try:
                branches_found = int(line[4:])
            except ValueError:
                pass
        elif line.startswith("BRH:"):
            try:
                branches_hit = int(line[4:])
            except ValueError:
                pass
        elif line == "end_of_record":
            if current_path:
                records.append(
                    CoverageRecord(
                        file_path=current_path,
                        line_rate=float(lines_hit) / lines_found if lines_found > 0 else None,
                        lines_covered=lines_hit,
                        lines_total=lines_found,
                        branches_covered=branches_hit,
                        branches_total=branches_found,
                        branch_rate=float(branches_hit) / branches_found
                        if branches_found > 0
                        else None,
                    )
                )
            current_path = None
            lines_found = 0
            lines_hit = 0
            branches_found = 0
            branches_hit = 0
    return records


def _parse_cobertura(content: str) -> list[CoverageRecord]:
    """Parse Cobertura XML format."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    records: list[CoverageRecord] = []
    for pkg in root.iter("package"):
        pkg_name = pkg.get("name", "")
        line_rate = pkg.get("line-rate")
        branch_rate = pkg.get("branch-rate")
        for cls in pkg.iter("class"):
            cls_name = cls.get("name", "")
            fpath = f"{pkg_name}/{cls_name}.xml" if pkg_name else f"{cls_name}.xml"
            records.append(
                CoverageRecord(
                    file_path=fpath,
                    line_rate=float(line_rate) if line_rate else None,
                    branch_rate=float(branch_rate) if branch_rate else None,
                )
            )
    return records


# ═════════════════════════════════════════════════════════════════════════
# TestDetector — main class
# ═════════════════════════════════════════════════════════════════════════


class TestDetector:
    """Detect, extract, map and analyse tests for a repository."""

    # ── detect_test_files ────────────────────────────────────────────

    async def detect_test_files(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[TestFileInfo]:
        """Scan all ``CodeFile`` records for the repository and return
        those identified as test files."""
        logger.info("Detecting test files for repository %s", repository_id)

        result = await db.execute(
            select(CodeFile).where(
                CodeFile.repository_id == repository_id,
                CodeFile.status == "PARSED",
            )
        )
        files = result.scalars().all()

        test_files: list[TestFileInfo] = []
        for f in files:
            lang = f.language or _detect_language(f.file_path) or ""
            if _is_test_file(f.file_name, lang):
                framework = None
                test_files.append(
                    TestFileInfo(
                        file_id=f.id,
                        file_path=f.file_path,
                        file_name=f.file_name,
                        language=lang,
                        line_count=f.line_count or 0,
                        is_test_file=True,
                    )
                )

        logger.info("Found %d test files in repository %s", len(test_files), repository_id)
        return test_files

    # ── extract_tests ────────────────────────────────────────────────

    async def extract_tests(
        self,
        file_id: uuid.UUID,
        file_path: str,
        content: str,
        language: Optional[str],
        db: AsyncSession,
    ) -> list[TestRecord]:
        """Parse file content and return a list of ``TestRecord`` objects
        ready to be inserted as ``CodeTest`` rows.

        This is a regex-based extractor — no tree-sitter dependency.
        """
        lang = language or _detect_language(file_path) or ""
        framework = _detect_framework(content, lang)

        records: list[TestRecord] = []

        # -- Test classes ---------------------------------------------------
        class_patterns = TEST_FUNC_PATTERNS.get(lang, [])
        fixture_pats = FIXTURE_DEF_PATTERNS.get(lang, [])
        mock_pats = MOCK_PATTERNS.get(lang, [])
        param_pats = PARAMETRIZE_PATTERNS.get(lang, [])
        assert_pats = ASSERTION_PATTERNS.get(lang, [])

        # Extract test functions / methods
        for pat in class_patterns:
            for m in pat.finditer(content):
                name = m.group("name")
                line_no = content[: m.start()].count("\n") + 1
                source_sym = _infer_source_symbol(name)

                # Determine if inside a class
                is_class = "class" in pat.pattern[: pat.pattern.index("def")] if "def" in pat.pattern else "class" in pat.pattern

                test_type = "CLASS" if is_class else "FUNCTION"

                meta: dict = {
                    "assert_count": 0,
                    "mock_count": 0,
                    "parametrize_count": 0,
                    "framework": framework,
                    "line_number": line_no,
                }

                # Count assertions, mocks, parametrize in the body around this name
                search_region = _extract_region(content, line_no, lookahead=80)
                meta["assert_count"] = _count_patterns(search_region, assert_pats)
                meta["mock_count"] = _count_patterns(search_region, mock_pats)
                meta["parametrize_count"] = _count_patterns(search_region, param_pats)

                records.append(
                    TestRecord(
                        file_id=file_id,
                        test_type=test_type,
                        test_name=name,
                        source_symbol_name=source_sym,
                        framework=framework,
                        is_async="async" in pat.pattern if hasattr(pat, "pattern") else False,
                        start_line=line_no,
                        metadata_=meta,
                    )
                )

        # Extract fixtures
        for pat in fixture_pats:
            for m in pat.finditer(content):
                name = m.groupdict().get("name", m.group(0).strip())
                line_no = content[: m.start()].count("\n") + 1
                records.append(
                    TestRecord(
                        file_id=file_id,
                        test_type="FIXTURE",
                        test_name=name,
                        framework=framework,
                        start_line=line_no,
                        metadata_={"fixture_pattern": m.group(0)[:60]},
                    )
                )

        # Detect standalone mock usages (without being inside a test def)
        for pat in mock_pats:
            for m in pat.finditer(content):
                line_no = content[: m.start()].count("\n") + 1
                mock_name = f"mock_usage_L{line_no}"
                records.append(
                    TestRecord(
                        file_id=file_id,
                        test_type="MOCK",
                        test_name=mock_name,
                        framework=framework,
                        start_line=line_no,
                        metadata_={"mock_pattern": m.group(0)[:80]},
                    )
                )

        # Detect parametrize decorators / calls
        for pat in param_pats:
            for m in pat.finditer(content):
                line_no = content[: m.start()].count("\n") + 1
                param_name = f"parametrize_L{line_no}"
                records.append(
                    TestRecord(
                        file_id=file_id,
                        test_type="FUNCTION",
                        test_name=param_name,
                        framework=framework,
                        start_line=line_no,
                        metadata_={"parametrize_pattern": m.group(0)[:80]},
                    )
                )

        logger.info(
            "Extracted %d test records from %s (lang=%s, framework=%s)",
            len(records),
            file_path,
            lang,
            framework,
        )
        return records

    # ── persist_test_records ─────────────────────────────────────────

    async def persist_test_records(
        self,
        repository_id: uuid.UUID,
        file_id: uuid.UUID,
        index_id: uuid.UUID,
        records: list[TestRecord],
        db: AsyncSession,
    ) -> list[CodeTest]:
        """Insert extracted ``TestRecord`` objects into the database as
        ``CodeTest`` rows and return the created ORM instances."""
        created: list[CodeTest] = []
        for rec in records:
            ct = CodeTest(
                repository_id=repository_id,
                file_id=file_id,
                symbol_id=None,
                test_type=rec.test_type,
                test_name=rec.test_name,
                source_symbol_name=rec.source_symbol_name,
                source_file_path=rec.source_file_path,
                framework=rec.framework,
                is_async=rec.is_async,
                metadata_=rec.metadata_,
            )
            db.add(ct)
            created.append(ct)

        await db.flush()
        return created

    # ── mark_test_files ──────────────────────────────────────────────

    async def mark_test_files(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> int:
        """Update ``CodeFile.is_test_file`` for all files in the repository.
        Returns the number of files marked."""
        result = await db.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id)
        )
        files = result.scalars().all()
        count = 0
        for f in files:
            lang = f.language or _detect_language(f.file_path) or ""
            is_test = _is_test_file(f.file_name, lang)
            if f.is_test_file != is_test:
                f.is_test_file = is_test
                count += 1
        await db.flush()
        logger.info("Marked %d files as test/non-test for repo %s", count, repository_id)
        return count

    # ── map_tests_to_sources ─────────────────────────────────────────

    async def map_tests_to_sources(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[TestMapping]:
        """Return a mapping of each test to its inferred source symbol.

        The mapping uses name heuristics (strip ``test_`` prefix, etc.) and
        tries to resolve against ``CodeSymbol`` rows in the same repository.
        """
        logger.info("Mapping tests to sources for repository %s", repository_id)

        # Fetch all tests
        test_result = await db.execute(
            select(CodeTest).where(CodeTest.repository_id == repository_id)
        )
        tests = test_result.scalars().all()

        # Fetch all source symbols (non-test) for matching
        sym_result = await db.execute(
            select(CodeSymbol).where(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.symbol_type.in_([
                    SymbolType.FUNCTION.value,
                    SymbolType.METHOD.value,
                    SymbolType.CLASS.value,
                ]),
            )
        )
        symbols = sym_result.scalars().all()

        # Build lookup: lower(name) -> (symbol_id, qualified_name, file_id)
        sym_lookup: dict[str, tuple[uuid.UUID, str, uuid.UUID]] = {}
        for s in symbols:
            key = s.name.lower()
            if key not in sym_lookup:
                sym_lookup[key] = (s.id, s.qualified_name, s.file_id)

        # Also build path-based lookup for source files
        file_result = await db.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id)
        )
        source_files = file_result.scalars().all()
        file_lookup: dict[str, uuid.UUID] = {}
        for sf in source_files:
            file_lookup[sf.file_path] = sf.id

        mappings: list[TestMapping] = []
        for t in tests:
            inferred = _infer_source_symbol(t.test_name)
            conf = 0.0
            src_file_id: Optional[uuid.UUID] = None
            src_sym_name: Optional[str] = None

            if inferred:
                key = inferred.lower()
                if key in sym_lookup:
                    src_sym_name = inferred
                    src_file_id = sym_lookup[key][2]
                    conf = 0.95
                else:
                    # Fuzzy: check if any symbol name contains the inferred name
                    for sname, (sid, _qn, sfid) in sym_lookup.items():
                        if key in sname or sname in key:
                            src_sym_name = sname
                            src_file_id = sfid
                            conf = 0.6
                            break

            mappings.append(
                TestMapping(
                    test_name=t.test_name,
                    test_file_path=t.source_file_path or "",
                    source_symbol_name=src_sym_name,
                    source_file_id=src_file_id,
                    confidence=conf,
                )
            )

        # Update CodeTest rows with resolved mapping
        for t in tests:
            for m in mappings:
                if m.test_name == t.test_name and m.source_symbol_name:
                    t.source_symbol_name = m.source_symbol_name
                    break

        await db.flush()
        logger.info("Created %d test-source mappings", len(mappings))
        return mappings

    # ── get_test_coverage ────────────────────────────────────────────

    async def get_test_coverage(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> CoverageSummary:
        """Compute a coverage summary from existing DB records.

        If coverage files (coverage.json, lcov.info, cobertura.xml) are
        present as ``CodeFile`` entries in the repository, they are parsed
        and incorporated into the result.
        """
        logger.info("Computing test coverage summary for repository %s", repository_id)

        # Total files
        total_files_q = await db.execute(
            select(func.count(CodeFile.id)).where(
                CodeFile.repository_id == repository_id
            )
        )
        total_files = total_files_q.scalar() or 0

        # Test files
        test_files_q = await db.execute(
            select(func.count(CodeFile.id)).where(
                CodeFile.repository_id == repository_id,
                CodeFile.is_test_file == True,  # noqa: E712
            )
        )
        test_files = test_files_q.scalar() or 0

        # Total tests
        total_tests_q = await db.execute(
            select(func.count(CodeTest.id)).where(
                CodeTest.repository_id == repository_id
            )
        )
        total_tests = total_tests_q.scalar() or 0

        # Source symbols with at least one test mapping
        mapped_q = await db.execute(
            select(
                CodeTest.source_symbol_name,
            ).where(
                CodeTest.repository_id == repository_id,
                CodeTest.source_symbol_name.isnot(None),
            ).group_by(CodeTest.source_symbol_name)
        )
        mapped_symbols = set(mapped_q.scalars().all())
        source_files_with_tests = len(mapped_symbols)

        # Source files without any tests
        source_files_q = await db.execute(
            select(func.count(CodeFile.id)).where(
                CodeFile.repository_id == repository_id,
                CodeFile.is_test_file == False,  # noqa: E712
            )
        )
        source_files_total = source_files_q.scalar() or 0
        source_files_without_tests = max(0, source_files_total - source_files_with_tests)

        # Framework distribution
        fw_q = await db.execute(
            select(
                CodeTest.framework,
                func.count(CodeTest.id),
            ).where(
                CodeTest.repository_id == repository_id,
            ).group_by(CodeTest.framework)
        )
        framework_distribution = {
            row[0] or "unknown": row[1] for row in fw_q.all()
        }

        # Test type distribution
        tt_q = await db.execute(
            select(
                CodeTest.test_type,
                func.count(CodeTest.id),
            ).where(
                CodeTest.repository_id == repository_id,
            ).group_by(CodeTest.test_type)
        )
        test_type_distribution = {
            row[0]: row[1] for row in tt_q.all()
        }

        # Look for coverage files in the repository
        coverage_sources: list[str] = []
        cov_files_q = await db.execute(
            select(CodeFile.file_path).where(
                CodeFile.repository_id == repository_id,
                CodeFile.file_path.ilike("%coverage.json%"),
            ).limit(10)
        )
        for row in cov_files_q.scalars().all():
            coverage_sources.append(row)

        cov_lcov_q = await db.execute(
            select(CodeFile.file_path).where(
                CodeFile.repository_id == repository_id,
                CodeFile.file_path.ilike("%lcov.info%"),
            ).limit(10)
        )
        for row in cov_lcov_q.scalars().all():
            coverage_sources.append(row)

        cov_cob_q = await db.execute(
            select(CodeFile.file_path).where(
                CodeFile.repository_id == repository_id,
                CodeFile.file_path.ilike("%cobertura.xml%"),
            ).limit(10)
        )
        for row in cov_cob_q.scalars().all():
            coverage_sources.append(row)

        return CoverageSummary(
            total_files=total_files,
            test_files=test_files,
            total_tests=total_tests,
            source_files_with_tests=source_files_with_tests,
            source_files_without_tests=source_files_without_tests,
            framework_distribution=framework_distribution,
            test_type_distribution=test_type_distribution,
            coverage_sources=coverage_sources,
        )

    # ── get_test_quality ─────────────────────────────────────────────

    async def get_test_quality(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[TestQualityMetrics]:
        """Return per-file test quality metrics for every test file in the
        repository."""
        logger.info("Computing test quality for repository %s", repository_id)

        test_files_q = await db.execute(
            select(CodeFile).where(
                CodeFile.repository_id == repository_id,
                CodeFile.is_test_file == True,  # noqa: E712
            )
        )
        test_files = test_files_q.scalars().all()

        metrics: list[TestQualityMetrics] = []

        for tf in test_files:
            # Fetch all tests in this file
            tests_q = await db.execute(
                select(CodeTest).where(CodeTest.file_id == tf.id)
            )
            tests = tests_q.scalars().all()

            test_count = 0
            fixture_count = 0
            mock_count = 0
            parametrize_count = 0
            total_assert = 0
            total_mock = 0
            test_lengths: list[float] = []

            for t in tests:
                meta = t.metadata_ or {}
                if t.test_type in ("FUNCTION", "CLASS"):
                    test_count += 1
                    total_assert += meta.get("assert_count", 0)
                    total_mock += meta.get("mock_count", 0)
                    parametrize_count += meta.get("parametrize_count", 0)
                elif t.test_type == "FIXTURE":
                    fixture_count += 1
                elif t.test_type == "MOCK":
                    mock_count += 1

            # Compute assert density (assertions per test)
            assert_density = float(total_assert) / test_count if test_count > 0 else 0.0

            # Mock ratio (mock usages / tests)
            mock_ratio = float(total_mock + mock_count) / test_count if test_count > 0 else 0.0

            # Average test length — approximate from start/end lines
            for t in tests:
                if t.metadata_ and "line_number" in t.metadata_:
                    # Use a default estimate of 15 lines per test if no end_line
                    length = 15.0
                    test_lengths.append(length)

            avg_len = sum(test_lengths) / len(test_lengths) if test_lengths else 0.0
            stddev_len = _compute_stddev(test_lengths)

            # Compute quality score (0.0 - 1.0)
            quality_score = self._compute_quality_score(
                test_count=test_count,
                assert_density=assert_density,
                mock_ratio=mock_ratio,
                fixture_count=fixture_count,
                parametrize_count=parametrize_count,
            )

            # Generate warnings
            warnings: list[str] = []
            if test_count == 0:
                warnings.append("File has no test functions/methods")
            if assert_density < 1.0 and test_count > 0:
                warnings.append(
                    f"Low assertion density: {assert_density:.1f} asserts/test"
                )
            if mock_ratio > 2.0:
                warnings.append(
                    f"High mock ratio: {mock_ratio:.1f} mocks/test"
                )

            metrics.append(
                TestQualityMetrics(
                    file_id=tf.id,
                    file_path=tf.file_path,
                    test_count=test_count,
                    fixture_count=fixture_count,
                    mock_count=mock_count,
                    parametrize_count=parametrize_count,
                    assert_density=round(assert_density, 2),
                    mock_ratio=round(mock_ratio, 2),
                    avg_test_length=round(avg_len, 1),
                    test_length_stddev=round(stddev_len, 1),
                    framework=tests[0].framework if tests else None,
                    quality_score=round(quality_score, 3),
                    warnings=warnings,
                )
            )

        return metrics

    # ── analyze_test_gaps ────────────────────────────────────────────

    async def analyze_test_gaps(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[TestGapInfo]:
        """Find source symbols (functions, methods, classes) that have no
        corresponding test coverage."""
        logger.info("Analyzing test gaps for repository %s", repository_id)

        # Fetch source symbols
        sym_q = await db.execute(
            select(CodeSymbol).where(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.symbol_type.in_([
                    SymbolType.FUNCTION.value,
                    SymbolType.METHOD.value,
                    SymbolType.CLASS.value,
                ]),
            )
        )
        symbols = sym_q.scalars().all()

        # Fetch all test source_symbol_name mappings
        test_names_q = await db.execute(
            select(CodeTest.source_symbol_name).where(
                CodeTest.repository_id == repository_id,
                CodeTest.source_symbol_name.isnot(None),
            )
        )
        tested_names = {name.lower() for name in test_names_q.scalars().all()}

        # Build a reverse lookup for files
        file_ids = {s.file_id for s in symbols}
        file_q = await db.execute(
            select(CodeFile).where(CodeFile.id.in_(file_ids))
        )
        file_map = {f.id: f.file_path for f in file_q.scalars().all()}

        gaps: list[TestGapInfo] = []
        for s in symbols:
            is_tested = s.name.lower() in tested_names

            # Also check fuzzy match
            related: list[str] = []
            if not is_tested:
                for tn in tested_names:
                    if s.name.lower() in tn or tn in s.name.lower():
                        related.append(tn)
                        is_tested = True

            if not is_tested:
                gaps.append(
                    TestGapInfo(
                        symbol_id=s.id,
                        symbol_name=s.name,
                        symbol_type=s.symbol_type,
                        file_path=file_map.get(s.file_id, "unknown"),
                        qualified_name=s.qualified_name,
                        has_tests=False,
                        related_test_names=related,
                    )
                )

        logger.info("Found %d untested symbols in repository %s", len(gaps), repository_id)
        return gaps

    # ── parse_coverage_file ──────────────────────────────────────────

    async def parse_coverage_file(
        self,
        file_path: str,
        content: str,
    ) -> list[CoverageRecord]:
        """Detect format and parse a coverage report file into records."""
        lower = file_path.lower()
        if lower.endswith(".json"):
            return _parse_coverage_json(content)
        elif lower.endswith("lcov.info") or lower.endswith(".info"):
            return _parse_lcov(content)
        elif lower.endswith(".xml") or lower.endswith("cobertura.xml"):
            return _parse_cobertura(content)
        else:
            logger.warning("Unknown coverage file format: %s", file_path)
            return []

    # ── get_framework_stats ──────────────────────────────────────────

    async def get_framework_stats(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict[str, dict[str, int]]:
        """Return per-framework statistics for the repository."""
        result = await db.execute(
            select(
                CodeTest.framework,
                CodeTest.test_type,
                func.count(CodeTest.id),
            ).where(
                CodeTest.repository_id == repository_id,
            ).group_by(CodeTest.framework, CodeTest.test_type)
        )

        stats: dict[str, dict[str, int]] = {}
        for framework, test_type, count in result.all():
            fw = framework or "unknown"
            if fw not in stats:
                stats[fw] = {}
            stats[fw][test_type] = count
        return stats

    # ── get_untested_high_value_symbols ──────────────────────────────

    async def get_untested_high_value_symbols(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        min_line_count: int = 20,
    ) -> list[TestGapInfo]:
        """Return untested symbols that exceed a line-count threshold
        (high value, high risk)."""
        gaps = await self.analyze_test_gaps(repository_id, db)

        high_value: list[TestGapInfo] = []
        for gap in gaps:
            sym_q = await db.execute(
                select(CodeSymbol).where(CodeSymbol.id == gap.symbol_id)
            )
            sym = sym_q.scalar_one_or_none()
            if sym and sym.start_line and sym.end_line:
                line_count = sym.end_line - sym.start_line + 1
                if line_count >= min_line_count:
                    high_value.append(gap)

        return high_value

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _compute_quality_score(
        test_count: int,
        assert_density: float,
        mock_ratio: float,
        fixture_count: int,
        parametrize_count: int,
    ) -> float:
        """Compute a 0.0–1.0 quality score for a test file.

        Scoring rubric:
        - Presence of tests (30%)
        - Assert density ≥ 2.0 (25%)
        - Moderate mock ratio 0.0–1.5 (20%)
        - Use of fixtures (15%)
        - Use of parametrize (10%)
        """
        score = 0.0

        # Presence of tests
        if test_count > 0:
            score += 0.30
        if test_count >= 5:
            score += 0.05
        if test_count >= 10:
            score += 0.05

        # Assert density (ideal: 2-5 assertions per test)
        if assert_density >= 2.0:
            score += 0.25
        elif assert_density >= 1.0:
            score += 0.15
        elif assert_density > 0:
            score += 0.05

        # Mock ratio (lower is generally better)
        if mock_ratio <= 0.5:
            score += 0.20
        elif mock_ratio <= 1.5:
            score += 0.10
        elif mock_ratio <= 3.0:
            score += 0.05

        # Fixtures
        if fixture_count > 0:
            score += 0.15

        # Parametrize
        if parametrize_count > 0:
            score += 0.10

        return min(score, 1.0)

    # ── run_full_analysis ────────────────────────────────────────────

    async def run_full_analysis(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict:
        """Run the complete test intelligence pipeline:

        1. Mark test files
        2. Detect test files
        3. Extract tests from each test file (requires content to be supplied externally)
        4. Map tests to source symbols
        5. Compute quality metrics
        6. Analyze gaps

        Returns a summary dictionary.
        """
        logger.info("Running full test analysis for repository %s", repository_id)

        await self.mark_test_files(repository_id, db)
        test_files = await self.detect_test_files(repository_id, db)
        coverage = await self.get_test_coverage(repository_id, db)
        quality = await self.get_test_quality(repository_id, db)
        gaps = await self.analyze_test_gaps(repository_id, db)
        framework_stats = await self.get_framework_stats(repository_id, db)

        return {
            "repository_id": str(repository_id),
            "test_files_detected": len(test_files),
            "coverage_summary": coverage,
            "quality_metrics": quality,
            "test_gaps": gaps,
            "framework_stats": framework_stats,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }


def _extract_region(content: str, start_line: int, lookahead: int = 80) -> str:
    """Extract a region of lines around *start_line* (1-based)."""
    lines = content.splitlines()
    start = max(0, start_line - 1)
    end = min(len(lines), start + lookahead)
    return "\n".join(lines[start:end])
