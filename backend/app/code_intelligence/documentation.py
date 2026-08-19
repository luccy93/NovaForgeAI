"""Documentation Extraction Engine — discover, parse, link, and score
documentation artifacts across a repository.

Extracts READMEs, docstrings, inline comments, API specs, and architecture
documents. Links documentation to symbols and files, calculates coverage and
quality metrics, and extracts code examples for RAG context bundles.
"""

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import CodeFile, CodeSymbol, CodeChunk

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

README_FILENAMES: frozenset[str] = frozenset({
    "README.md", "README.rst", "README.txt", "README.markdown", "README",
    "readme.md", "readme.rst", "readme.txt", "readme.markdown", "readme",
    "Readme.md", "Readme.rst",
})

_TRIVIAL_COMMENT_RE = re.compile(
    r"^\s*(?:#|//|/\*|\*|;|--)\s*$"
    r"|^\s*(?:#|//|/\*|\*|;|--)\s*(?:end\s+(?:if|for|while|function|class))\s*$",
    re.IGNORECASE,
)

_CODE_EXAMPLE_RE = re.compile(
    r"(?:```(?:python|javascript|typescript|java|go|rust|csharp|ruby|bash|yaml|json|sql)?\s*\n)"
    r"([\s\S]*?)(?:```)", re.MULTILINE,
)

_DOCSTRING_STYLE_MARKERS: dict[str, list[str]] = {
    "google": [":param ", ":returns:", ":return:", ":raises "],
    "numpy": ["Parameters\n    ----------", "Returns\n    ----------"],
    "sphinx": ["param ", "rtype:"],
    "jsdoc": ["@param", "@returns", "@throws"],
    "javadoc": ["@param", "@return", "@throws"],
    "godoc": ["Args:", "Returns:", "Raises:"],
    "rustdoc": ["# Arguments", "# Returns", "# Panics", "# Examples"],
    "csharp": ["<param", "<returns>", "<summary>"],
}

ADR_FILENAME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[-_]?.*\.md$|^ADR[-_]?\d+.*\.md$", re.IGNORECASE,
)

ARCHITECTURE_DOC_PATTERNS: list[str] = [
    r"ARCHITECTURE", r"DESIGN", r"RFC[-_]?\d+", r"ADR[-_]?\d+",
    r"SPECIFICATION", r"architecture\.md", r"design\.md", r"design-doc\.md",
]

API_SPEC_PATTERNS: list[str] = [
    r"openapi\.(yaml|json|yml)$", r"swagger\.(yaml|json|yml)$",
    r"\.swagger\.(yaml|json|yml)$", r"api-docs?\.(yaml|json|yml)$",
    r"graphql\.schema$", r"\.graphql$", r"schema\.graphql$", r"gql\.schema$",
]

_LANG_COMMENT_PREFIX: dict[str, str] = {
    "python": "#", "ruby": "#", "shell": "#", "bash": "#", "yaml": "#",
    "javascript": "//", "typescript": "//", "jsx": "//", "tsx": "//",
    "java": "//", "csharp": "//", "c_sharp": "//", "kotlin": "//",
    "scala": "//", "swift": "//", "go": "//", "c": "//", "cpp": "//",
    "c++": "//", "objective-c": "//", "rust": "///",
}

_BLOCK_COMMENT_LANGS: frozenset[str] = frozenset({
    "javascript", "typescript", "jsx", "tsx", "java",
    "csharp", "c_sharp", "kotlin", "scala", "swift", "c", "cpp", "c++",
})

_PARAM_RE = re.compile(r"(?:@param\s|:param\s|Parameters\s*\n\s*[-]+|Args:\s*$)")
_RETURN_RE = re.compile(r"(?:@return[s]?\b|:return[s]?:|Returns\s*\n\s*[-]+|<returns>)")
_EXAMPLE_RE = re.compile(r"(?:>>>|```|Example[s]?:|Usage:|\.\.\.\s*>>>)")
_TYPE_RE = re.compile(r"(?::type\s+\w+:|@type\s+|:rtype:|<param\s+\w+\s+type=)")

TodoIndicator = re.compile(r"(?:TODO|FIXME|HACK|XXX|BUG)", re.IGNORECASE)

_EXPLANATION_KEYWORDS = frozenset({
    "because", "since", "note:", "important:", "warning:", "this is",
    "we need", "we use", "the reason", "workaround", "see ", "reference",
    "algorithm", "complexity", "performance",
})

_SIGNIFICANCE_KEYWORDS = frozenset({
    "because", "since", "note:", "important:", "warning:", "todo:",
    "fixme:", "hack:", "workaround:", "issue:", "bug:", "see ",
    "reference:", "example:", "returns ", "algorithm", "complexity",
    "performance", "deprecated",
})


# ── Utility functions ──────────────────────────────────────────────────


def _is_significant_comment(text: str) -> bool:
    clean = re.sub(r"^(?:#|//|/\*|\*|;|--)\s*", "", text.strip()).strip()
    if not clean or len(clean) < 10:
        return False
    if _TRIVIAL_COMMENT_RE.match(text.strip()):
        return False
    lower = clean.lower()
    if any(kw in lower for kw in _SIGNIFICANCE_KEYWORDS):
        return True
    if len(clean) > 60 or len(re.split(r"[.!?]+", clean)) >= 2:
        return True
    return "?" in clean or ":" in clean


def _parse_readme_sections(content: str) -> list[dict]:
    sections: list[dict] = []
    current: Optional[dict] = None
    for line in content.split("\n"):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            if current:
                sections.append(current)
            current = {"level": len(m.group(1)), "title": m.group(2).strip(), "content": ""}
        elif current:
            current["content"] += line + "\n"
    if current:
        sections.append(current)
    return sections


def _parse_openapi_spec(raw: str) -> dict:
    try:
        if raw.strip().startswith("{"):
            return json.loads(raw)
        try:
            import yaml
            return yaml.safe_load(raw) or {}
        except ImportError:
            return {}
    except (json.JSONDecodeError, ValueError):
        return {}


# ── Dataclasses ────────────────────────────────────────────────────────


@dataclass
class DocstringInfo:
    symbol_id: str
    symbol_name: str
    symbol_type: str
    qualified_name: str
    docstring: str
    style: str
    has_parameters: bool = False
    has_return_description: bool = False
    has_examples: bool = False
    has_type_annotations: bool = False
    line_start: int = 0
    line_end: int = 0
    quality_score: float = 0.0


@dataclass
class CommentInfo:
    file_id: str
    line_number: int
    text: str
    language: str
    comment_type: str = "inline"
    referenced_symbol: Optional[str] = None
    is_todo: bool = False
    is_explanation: bool = False


@dataclass
class READMEContent:
    file_id: str
    file_path: str
    language: str
    raw_content: str
    sections: list[dict] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    badges: list[str] = field(default_factory=list)
    has_installation: bool = False
    has_usage: bool = False
    has_contributing: bool = False
    has_license: bool = False
    word_count: int = 0


@dataclass
class APIDocumentation:
    file_id: str
    file_path: str
    spec_type: str
    title: str = ""
    version: str = ""
    description: str = ""
    endpoints: list[dict] = field(default_factory=list)
    schemas: list[dict] = field(default_factory=list)
    security: list[dict] = field(default_factory=list)
    total_endpoints: int = 0
    documented_endpoints: int = 0


@dataclass
class ArchitectureDoc:
    file_id: str
    file_path: str
    doc_type: str
    title: str = ""
    sections: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    diagrams_mentioned: list[str] = field(default_factory=list)
    word_count: int = 0


@dataclass
class DocumentationCoverage:
    total_symbols: int = 0
    documented_symbols: int = 0
    coverage_percent: float = 0.0
    by_symbol_type: dict[str, dict] = field(default_factory=dict)
    by_language: dict[str, dict] = field(default_factory=dict)
    undocumented_symbols: list[dict] = field(default_factory=list)


@dataclass
class DocumentationQuality:
    average_docstring_length: float = 0.0
    median_docstring_length: float = 0.0
    symbols_with_parameters_documented: int = 0
    symbols_with_return_documented: int = 0
    symbols_with_examples: int = 0
    docstring_style_distribution: dict[str, int] = field(default_factory=dict)
    files_with_readme: int = 0
    files_with_api_docs: int = 0
    files_with_architecture_docs: int = 0
    quality_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DocSymbolLink:
    doc_type: str
    doc_identifier: str
    symbol_id: Optional[str] = None
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None
    confidence: float = 0.0
    context: str = ""


@dataclass
class CodeExample:
    source_file: str
    language: str
    code: str
    description: str = ""
    context_section: str = ""


@dataclass
class DocumentationSummary:
    readme_files: int = 0
    total_docstring_symbols: int = 0
    total_significant_comments: int = 0
    api_spec_files: int = 0
    architecture_doc_files: int = 0
    total_code_examples: int = 0
    overall_coverage_percent: float = 0.0
    overall_quality_score: float = 0.0
    top_documented_modules: list[dict] = field(default_factory=list)
    least_documented_modules: list[dict] = field(default_factory=list)
    documentation_languages: dict[str, int] = field(default_factory=dict)


@dataclass
class DocumentationAnalysis:
    repository_id: str
    summary: DocumentationSummary = field(default_factory=DocumentationSummary)
    coverage: DocumentationCoverage = field(default_factory=DocumentationCoverage)
    quality: DocumentationQuality = field(default_factory=DocumentationQuality)
    readme_contents: list[READMEContent] = field(default_factory=list)
    docstrings: list[DocstringInfo] = field(default_factory=list)
    comments: list[CommentInfo] = field(default_factory=list)
    api_docs: list[APIDocumentation] = field(default_factory=list)
    architecture_docs: list[ArchitectureDoc] = field(default_factory=list)
    code_examples: list[CodeExample] = field(default_factory=list)
    symbol_links: list[DocSymbolLink] = field(default_factory=list)
    analyzed_at: Optional[datetime] = None


# ── Main class ─────────────────────────────────────────────────────────


class DocumentationExtractor:
    """Extract, parse, link, and score documentation across a repository."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    # ── 1. README extraction ───────────────────────────────────────────

    async def extract_readme(
        self, repository_id: UUID, db: AsyncSession,
    ) -> list[READMEContent]:
        """Locate and parse README files in the repository."""
        logger.info("Extracting README files for repository %s", repository_id)

        result = await db.execute(
            select(CodeFile)
            .where(CodeFile.repository_id == repository_id,
                   CodeFile.file_name.in_(list(README_FILENAMES)))
            .order_by(CodeFile.file_path)
        )
        files = list(result.scalars().all())
        if not files:
            fb = await db.execute(
                select(CodeFile).where(
                    CodeFile.repository_id == repository_id,
                    CodeFile.file_name.ilike("readme%")).order_by(CodeFile.file_path))
            files = list(fb.scalars().all())

        contents: list[READMEContent] = []
        for rf in files:
            text = await self._load_file_content(rf)
            if not text:
                continue
            sections = _parse_readme_sections(text)
            code_blocks = self._extract_readme_code_blocks(text, sections)
            links = [{"text": m.group(1), "url": m.group(2)}
                     for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", text)]
            badges = [m.group(0) for m in re.finditer(
                r"!\[[^\]]*\]\([^)]*(?:badge|shields\.io)[^)]*\)", text)]
            contents.append(READMEContent(
                file_id=str(rf.id), file_path=rf.file_path,
                language=rf.language or "markdown", raw_content=text,
                sections=sections, code_blocks=code_blocks, links=links,
                badges=badges, word_count=len(text.split()),
                has_installation=self._has_section(sections, ["install", "setup", "getting started"]),
                has_usage=self._has_section(sections, ["usage", "how to use", "examples"]),
                has_contributing=self._has_section(sections, ["contributing", "development"]),
                has_license=(any("license" in l.get("url", "").lower() for l in links)
                             or "license" in text.lower()),
            ))
        logger.info("Extracted %d README file(s)", len(contents))
        return contents

    # ── 2. Docstring extraction ────────────────────────────────────────

    async def extract_docstrings(
        self, file_id: UUID, content: str, language: str, db: AsyncSession,
    ) -> list[DocstringInfo]:
        """Extract docstrings from source code and link them to symbols."""
        logger.debug("Extracting docstrings from file %s (%s)", file_id, language)
        result = await db.execute(
            select(CodeSymbol).where(CodeSymbol.file_id == file_id).order_by(CodeSymbol.start_line))
        symbols = list(result.scalars().all())
        lines = content.split("\n")
        lang = (language or "").lower()
        docstrings: list[DocstringInfo] = []

        for sym in symbols:
            ds = sym.docstring
            if not ds or not ds.strip():
                ds = self._extract_docstring_from_source(lines, sym, lang)
            if not ds or not ds.strip():
                continue
            ds = ds.strip()
            q = _calculate_docstring_quality(ds)
            docstrings.append(DocstringInfo(
                symbol_id=sym.symbol_id, symbol_name=sym.name,
                symbol_type=sym.symbol_type, qualified_name=sym.qualified_name,
                docstring=ds, style=_detect_docstring_style(ds),
                has_parameters=bool(_PARAM_RE.search(ds)),
                has_return_description=bool(_RETURN_RE.search(ds)),
                has_examples=bool(_EXAMPLE_RE.search(ds)),
                has_type_annotations=bool(_TYPE_RE.search(ds)),
                line_start=sym.start_line or 0, line_end=sym.end_line or 0,
                quality_score=round(q, 4),
            ))
        logger.debug("Extracted %d docstrings from file %s", len(docstrings), file_id)
        return docstrings

    # ── 3. Comment extraction ──────────────────────────────────────────

    async def extract_comments(
        self, file_id: UUID, content: str, language: str, db: AsyncSession,
    ) -> list[CommentInfo]:
        """Extract significant inline comments, filtering trivial ones."""
        logger.debug("Extracting comments from file %s (%s)", file_id, language)
        result = await db.execute(select(CodeFile).where(CodeFile.id == file_id))
        if not result.scalar_one_or_none():
            return []

        lang = (language or "").lower()
        lines = content.split("\n")
        comments: list[CommentInfo] = []
        in_block = False
        block_buf: list[str] = []

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Block-comment languages (JS/TS/Java/C#/C/C++/Swift/Kotlin/Scala)
            if lang in _BLOCK_COMMENT_LANGS:
                if in_block:
                    end = stripped.find("*/")
                    if end >= 0:
                        block_buf.append(stripped[:end].strip())
                        text = "\n".join(block_buf)
                        if _is_significant_comment(text):
                            comments.append(self._mk_comment(file_id, line_num, text, lang, "block"))
                        in_block = False
                        block_buf.clear()
                    else:
                        block_buf.append(stripped.lstrip("*").strip())
                    continue
                start = stripped.find("/*")
                if start >= 0:
                    after = stripped[start + 2:]
                    end = after.find("*/")
                    if end >= 0:
                        single = after[:end].strip()
                        if _is_significant_comment(single):
                            comments.append(self._mk_comment(file_id, line_num, single, lang, "block"))
                    else:
                        in_block = True
                        block_buf.append(after.lstrip("*").strip())
                    continue

            # Line-comment languages
            prefix = _LANG_COMMENT_PREFIX.get(lang, "#")
            m = re.match(rf"^\s*{re.escape(prefix)}\s?(.*)", stripped)
            text = m.group(1).strip() if m else None
            if text and _is_significant_comment(text):
                ref = self._find_referenced_symbol(lines, line_num, lang)
                c = self._mk_comment(file_id, line_num, text, lang, "inline")
                c.referenced_symbol = ref
                comments.append(c)

        logger.debug("Extracted %d significant comments from file %s", len(comments), file_id)
        return comments

    # ── 4. Documentation coverage ──────────────────────────────────────

    async def get_documentation_coverage(
        self, repository_id: UUID, db: AsyncSession,
    ) -> DocumentationCoverage:
        """Calculate what percentage of symbols have docstrings."""
        logger.info("Calculating documentation coverage for repo %s", repository_id)
        result = await db.execute(
            select(CodeSymbol).where(CodeSymbol.repository_id == repository_id))
        all_sym = list(result.scalars().all())
        if not all_sym:
            return DocumentationCoverage()

        total = len(all_sym)
        doc_sym = [s for s in all_sym if s.docstring and s.docstring.strip()]
        pct = len(doc_sym) / total * 100.0

        by_type: dict[str, dict] = defaultdict(lambda: {"total": 0, "documented": 0})
        by_lang: dict[str, dict] = defaultdict(lambda: {"total": 0, "documented": 0})
        for s in all_sym:
            st, lg = s.symbol_type or "UNKNOWN", s.language or "unknown"
            by_type[st]["total"] += 1
            by_lang[lg]["total"] += 1
            if s.docstring and s.docstring.strip():
                by_type[st]["documented"] += 1
                by_lang[lg]["documented"] += 1

        def _mk_cov(d: dict) -> dict[str, dict]:
            return {k: {"total": v["total"], "documented": v["documented"],
                        "coverage_percent": round(v["documented"] / v["total"] * 100, 2) if v["total"] else 0}
                    for k, v in d.items()}

        undocumented = [
            {"symbol_id": s.symbol_id, "name": s.name, "symbol_type": s.symbol_type,
             "qualified_name": s.qualified_name, "language": s.language, "file_id": str(s.file_id)}
            for s in all_sym if not s.docstring or not s.docstring.strip()
        ][:200]

        cov = DocumentationCoverage(
            total_symbols=total, documented_symbols=len(doc_sym),
            coverage_percent=round(pct, 2), by_symbol_type=_mk_cov(by_type),
            by_language=_mk_cov(by_lang), undocumented_symbols=undocumented,
        )
        logger.info("Documentation coverage: %.1f%% (%d/%d)", pct, len(doc_sym), total)
        return cov

    # ── 5. Documentation quality ───────────────────────────────────────

    async def get_documentation_quality(
        self, repository_id: UUID, db: AsyncSession,
    ) -> DocumentationQuality:
        """Assess documentation quality signals and generate recommendations."""
        logger.info("Assessing documentation quality for repo %s", repository_id)
        result = await db.execute(
            select(CodeSymbol).where(CodeSymbol.repository_id == repository_id))
        all_sym = list(result.scalars().all())
        docstrings = [s for s in all_sym if s.docstring and s.docstring.strip()]
        lengths = [len(s.docstring.strip()) for s in docstrings]

        avg_len = sum(lengths) / len(lengths) if lengths else 0.0
        med_len = 0.0
        if lengths:
            sl = sorted(lengths)
            mid = len(sl) // 2
            med_len = (sl[mid - 1] + sl[mid]) / 2.0 if len(sl) % 2 == 0 else float(sl[mid])

        params_doc = sum(1 for s in docstrings if _PARAM_RE.search(s.docstring.strip()))
        ret_doc = sum(1 for s in docstrings if _RETURN_RE.search(s.docstring.strip()))
        ex_count = sum(1 for s in docstrings if _EXAMPLE_RE.search(s.docstring.strip()))
        style_dist: dict[str, int] = defaultdict(int)
        for s in docstrings:
            style_dist[_detect_docstring_style(s.docstring.strip())] += 1

        readme_n = await self._count_files(repository_id, list(README_FILENAMES), db, exact=True)
        api_n = await self._count_files(repository_id, API_SPEC_PATTERNS, db)
        arch_n = await self._count_files(repository_id, ARCHITECTURE_DOC_PATTERNS, db)

        total, doc_count = len(all_sym), len(docstrings)
        q = _quality_score(total, doc_count, avg_len, params_doc, ret_doc, ex_count, readme_n, api_n)
        recs = _recommendations(total, doc_count, avg_len, params_doc, ret_doc, ex_count, readme_n, api_n)

        return DocumentationQuality(
            average_docstring_length=round(avg_len, 1), median_docstring_length=round(med_len, 1),
            symbols_with_parameters_documented=params_doc, symbols_with_return_documented=ret_doc,
            symbols_with_examples=ex_count, docstring_style_distribution=dict(style_dist),
            files_with_readme=readme_n, files_with_api_docs=api_n,
            files_with_architecture_docs=arch_n, quality_score=round(q, 4), recommendations=recs,
        )

    # ── 6. Link docs to symbols ────────────────────────────────────────

    async def link_docs_to_symbols(
        self, repository_id: UUID, db: AsyncSession,
    ) -> list[DocSymbolLink]:
        """Build links between documentation artifacts and code symbols."""
        logger.info("Linking documentation to symbols for repo %s", repository_id)
        links: list[DocSymbolLink] = []

        result = await db.execute(
            select(CodeSymbol).where(CodeSymbol.repository_id == repository_id))
        symbols = list(result.scalars().all())
        for sym in symbols:
            if sym.docstring and sym.docstring.strip():
                links.append(DocSymbolLink(
                    doc_type="docstring", doc_identifier=sym.symbol_id,
                    symbol_id=sym.symbol_id, symbol_name=sym.name,
                    symbol_type=sym.symbol_type, confidence=1.0,
                    context=sym.docstring.strip()[:200],
                ))

        file_result = await db.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id))
        for rf in [f for f in file_result.scalars().all()
                    if f.file_name in README_FILENAMES]:
            directory = rf.file_path.replace("\\", "/").rsplit("/", 1)[0] if "/" in rf.file_path else ""
            links.append(DocSymbolLink(
                doc_type="readme", doc_identifier=str(rf.id),
                symbol_name=directory, symbol_type="directory",
                confidence=0.9, context=rf.file_path,
            ))

        chunk_result = await db.execute(
            select(CodeChunk).where(
                CodeChunk.repository_id == repository_id, CodeChunk.chunk_type == "comment"))
        sym_by_id = {s.symbol_id: s for s in symbols} | {str(s.id): s for s in symbols}
        for chunk in list(chunk_result.scalars().all()):
            if chunk.symbol_id and str(chunk.symbol_id) in sym_by_id:
                sym = sym_by_id[str(chunk.symbol_id)]
                links.append(DocSymbolLink(
                    doc_type="inline_comment", doc_identifier=str(chunk.id),
                    symbol_id=sym.symbol_id, symbol_name=sym.name,
                    symbol_type=sym.symbol_type, confidence=0.85,
                    context=(chunk.content or "")[:200],
                ))

        logger.info("Created %d doc-to-symbol links", len(links))
        return links

    # ── 7. API documentation extraction ────────────────────────────────

    async def extract_api_docs(
        self, repository_id: UUID, db: AsyncSession,
    ) -> list[APIDocumentation]:
        """Extract and parse OpenAPI/Swagger/GraphQL specifications."""
        logger.info("Extracting API documentation for repo %s", repository_id)
        file_result = await db.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id))
        api_files = [f for f in file_result.scalars().all() if _is_api_spec(f.file_name)]

        docs: list[APIDocumentation] = []
        for af in api_files:
            text = await self._load_file_content(af)
            if not text:
                continue
            if "graphql" in af.file_name.lower():
                d = self._parse_graphql(af, text)
            else:
                d = self._parse_openapi(af, text)
            if d:
                docs.append(d)
        logger.info("Extracted %d API documentation file(s)", len(docs))
        return docs

    # ── 8. Architecture documentation ──────────────────────────────────

    async def extract_architecture_docs(
        self, repository_id: UUID, db: AsyncSession,
    ) -> list[ArchitectureDoc]:
        """Extract architecture decision records and design documents."""
        logger.info("Extracting architecture docs for repo %s", repository_id)
        file_result = await db.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id))
        arch_files = [f for f in file_result.scalars().all() if _is_arch_doc(f.file_name)]

        docs: list[ArchitectureDoc] = []
        for af in arch_files:
            text = await self._load_file_content(af)
            if not text:
                continue
            doc_type = "adr" if ADR_FILENAME_RE.search(af.file_name) else "design"
            sections = _parse_readme_sections(text)
            decisions = [
                {"section": s["title"], "content": s.get("content", "")[:500]}
                for s in sections
                if any(kw in s.get("title", "").lower()
                       for kw in ["decision", "status", "context", "consequences"])
            ] if doc_type == "adr" else []
            diagrams = [m.group(1).strip()[:200]
                        for m in re.finditer(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)]
            diagrams += [f"{m.group(1)}: {m.group(2)}"
                         for m in re.finditer(r"!\[([^\]]*)\]\(([^)]*\.(?:png|jpg|svg|drawio))\)", text)]
            docs.append(ArchitectureDoc(
                file_id=str(af.id), file_path=af.file_path, doc_type=doc_type,
                title=sections[0]["title"] if sections else af.file_name,
                sections=sections, decisions=decisions, diagrams_mentioned=diagrams,
                word_count=len(text.split()),
            ))
        logger.info("Extracted %d architecture documentation file(s)", len(docs))
        return docs

    # ── 9. Documentation summary ───────────────────────────────────────

    async def get_documentation_summary(
        self, repository_id: UUID, db: AsyncSession,
    ) -> DocumentationSummary:
        """Produce a high-level overview of all documentation in the repository."""
        logger.info("Generating documentation summary for repo %s", repository_id)
        coverage = await self.get_documentation_coverage(repository_id, db)
        quality = await self.get_documentation_quality(repository_id, db)
        readme_contents = await self.extract_readme(repository_id, db)
        api_docs = await self.extract_api_docs(repository_id, db)
        arch_docs = await self.extract_architecture_docs(repository_id, db)

        result = await db.execute(
            select(CodeSymbol).where(CodeSymbol.repository_id == repository_id))
        all_sym = list(result.scalars().all())
        by_lang: dict[str, int] = defaultdict(int)
        module_docs: dict[str, int] = defaultdict(int)
        module_total: dict[str, int] = defaultdict(int)
        for s in all_sym:
            by_lang[s.language or "unknown"] += 1
            parts = s.qualified_name.split(".")
            mod = ".".join(parts[:-1]) if len(parts) >= 2 else s.qualified_name
            module_total[mod] += 1
            if s.docstring and s.docstring.strip():
                module_docs[mod] += 1

        top_mods = sorted(
            [{"module": m, "coverage": round(module_docs.get(m, 0) / t * 100, 1) if t else 0,
              "total": t, "documented": module_docs.get(m, 0)}
             for m, t in module_total.items()],
            key=lambda x: x["coverage"], reverse=True)[:10]
        least_mods = sorted(
            [{"module": m, "coverage": round(module_docs.get(m, 0) / t * 100, 1) if t else 0,
              "total": t, "documented": module_docs.get(m, 0)}
             for m, t in module_total.items() if t >= 2],
            key=lambda x: x["coverage"])[:10]

        cr = await db.execute(
            select(func.count(CodeChunk.id)).where(
                CodeChunk.repository_id == repository_id, CodeChunk.chunk_type == "comment"))
        return DocumentationSummary(
            readme_files=len(readme_contents),
            total_docstring_symbols=sum(1 for s in all_sym if s.docstring and s.docstring.strip()),
            total_significant_comments=cr.scalar() or 0,
            api_spec_files=len(api_docs), architecture_doc_files=len(arch_docs),
            total_code_examples=sum(len(r.code_blocks) for r in readme_contents),
            overall_coverage_percent=coverage.coverage_percent,
            overall_quality_score=quality.quality_score,
            top_documented_modules=top_mods, least_documented_modules=least_mods,
            documentation_languages=dict(by_lang),
        )

    # ── 10. Comprehensive analysis ─────────────────────────────────────

    async def analyze_documentation(
        self, repository_id: UUID, db: AsyncSession,
    ) -> DocumentationAnalysis:
        """Run full documentation analysis across all dimensions."""
        logger.info("Running comprehensive documentation analysis for repo %s", repository_id)
        readme_contents = await self.extract_readme(repository_id, db)
        coverage = await self.get_documentation_coverage(repository_id, db)
        quality = await self.get_documentation_quality(repository_id, db)
        api_docs = await self.extract_api_docs(repository_id, db)
        arch_docs = await self.extract_architecture_docs(repository_id, db)
        symbol_links = await self.link_docs_to_symbols(repository_id, db)

        file_result = await db.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id))
        all_files = list(file_result.scalars().all())

        docstrings: list[DocstringInfo] = []
        comments: list[CommentInfo] = []
        for cf in all_files:
            text = await self._load_file_content(cf)
            if not text:
                continue
            docstrings.extend(await self.extract_docstrings(cf.id, text, cf.language or "", db))
            comments.extend(await self.extract_comments(cf.id, text, cf.language or "", db))

        code_examples: list[CodeExample] = []
        for rm in readme_contents:
            for b in rm.code_blocks:
                code_examples.append(CodeExample(
                    source_file=rm.file_path, language=b.get("language", "unknown"),
                    code=b.get("code", ""), description=b.get("description", ""),
                    context_section=b.get("section", ""),
                ))
        for ds in docstrings:
            for ex in _extract_examples_from_docstring(ds.docstring):
                code_examples.append(CodeExample(
                    source_file=ds.qualified_name, language=ex["language"],
                    code=ex["code"], description=ex["description"],
                    context_section="docstring",
                ))

        summary = await self.get_documentation_summary(repository_id, db)
        return DocumentationAnalysis(
            repository_id=str(repository_id), summary=summary, coverage=coverage,
            quality=quality, readme_contents=readme_contents, docstrings=docstrings,
            comments=comments, api_docs=api_docs, architecture_docs=arch_docs,
            code_examples=code_examples, symbol_links=symbol_links,
            analyzed_at=datetime.now(timezone.utc),
        )

    # ── Private: file I/O ──────────────────────────────────────────────

    async def _load_file_content(self, code_file: CodeFile) -> Optional[str]:
        for chunk_type in ("file_content", None):
            stmt = select(CodeChunk).where(CodeChunk.file_id == code_file.id)
            if chunk_type:
                stmt = stmt.where(CodeChunk.chunk_type == chunk_type)
            result = await self._db.execute(stmt.order_by(CodeChunk.start_line).limit(1))
            chunk = result.scalar_one_or_none()
            if chunk and chunk.content:
                return chunk.content
        return None

    # ── Private: docstring source extraction ────────────────────────────

    def _extract_docstring_from_source(
        self, lines: list[str], sym: CodeSymbol, lang: str,
    ) -> Optional[str]:
        start = (sym.start_line or 1) - 1
        end = min((sym.end_line or len(lines)), len(lines))

        if lang == "python":
            for i in range(start, min(start + 5, end)):
                if i >= len(lines): break
                s = lines[i].strip()
                if not (s.startswith('"""') or s.startswith("'''")): continue
                q = s[:3]
                if s.count(q) >= 2 and len(s) > 6: return s[3:-3].strip()
                parts: list[str] = []
                first = s[3:].strip()
                if first: parts.append(first)
                for j in range(i + 1, min(i + 100, end)):
                    if j >= len(lines): break
                    if q in lines[j]:
                        trail = lines[j].split(q)[0].strip()
                        if trail: parts.append(trail)
                        break
                    parts.append(lines[j].rstrip())
                return "\n".join(parts).strip()

        elif lang in ("javascript", "typescript", "jsx", "tsx", "java"):
            for i in range(start, min(start + 8, end)):
                if i >= len(lines): break
                s = lines[i].strip()
                if not s.startswith("/**"): continue
                parts: list[str] = []
                first = s[3:].strip()
                if first and not first.endswith("*/"): parts.append(first)
                elif first.endswith("*/"): return first[:-2].strip()
                for j in range(i + 1, min(i + 80, end)):
                    if j >= len(lines): break
                    ln = lines[j].strip()
                    if ln.endswith("*/"):
                        before = ln[:-2].strip().lstrip("*").strip()
                        if before: parts.append(before)
                        break
                    parts.append(ln.lstrip("*").strip())
                return "\n".join(parts).strip()

        elif lang == "go":
            parts = []
            for i in range(max(0, start - 1), start):
                if i >= len(lines): break
                s = lines[i].strip()
                if s.startswith("//"): parts.append(s[2:].strip())
                elif s == "" and parts: break
                elif s and not s.startswith("//"): break
            return "\n".join(parts).strip() if parts else None

        elif lang == "rust":
            parts = []
            for i in range(max(0, start - 1), start):
                if i >= len(lines): break
                s = lines[i].strip()
                if s.startswith(("///", "//!")): parts.append(s[3:].strip())
                elif s == "" and parts: break
                elif s and not s.startswith(("///", "//!")): break
            return "\n".join(parts).strip() if parts else None

        elif lang in ("csharp", "c_sharp"):
            for i in range(max(0, start - 3), min(start + 5, end)):
                if i >= len(lines) or not lines[i].strip().startswith("///"): continue
                parts = []
                for j in range(i, min(i + 30, end)):
                    if j >= len(lines): break
                    ln = lines[j].strip()
                    if ln.startswith("///"): parts.append(ln[3:].strip())
                    elif ln == "" or ln.startswith("["): continue
                    else: break
                full = "\n".join(parts).strip()
                m = re.search(r"<summary>(.*?)</summary>", full, re.DOTALL)
                return m.group(1).strip() if m else full

        return None

    # ── Private: comment helpers ────────────────────────────────────────

    def _find_referenced_symbol(self, lines: list[str], line_num: int, lang: str) -> Optional[str]:
        for i in range(line_num - 1, min(line_num + 2, len(lines))):
            ln = lines[i].strip()
            if lang == "python":
                m = re.match(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", ln)
            elif lang in ("javascript", "typescript", "jsx", "tsx"):
                m = re.match(r"^\s*(?:function|const|let|var|class|async\s+function)\s+(\w+)", ln)
            elif lang == "go":
                m = re.match(r"^\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", ln)
            else:
                continue
            if m:
                return m.group(1)
        return None

    def _mk_comment(self, file_id: UUID, line: int, text: str, lang: str, ctype: str) -> CommentInfo:
        return CommentInfo(
            file_id=str(file_id), line_number=line, text=text,
            language=lang, comment_type=ctype,
            is_todo=bool(TodoIndicator.search(text)),
            is_explanation=bool(_EXPLANATION_KEYWORDS & set(text.lower().split())),
        )

    # ── Private: README helpers ─────────────────────────────────────────

    def _extract_readme_code_blocks(self, content: str, sections: list[dict]) -> list[dict]:
        blocks: list[dict] = []
        for m in re.finditer(r"```(\w*)\s*\n(.*?)```", content, re.DOTALL):
            lang, code = m.group(1) or "unknown", m.group(2).strip()
            if not code:
                continue
            pos = m.start()
            sec = ""
            for s in reversed(sections):
                sp = content.find(s["title"])
                if sp >= 0 and sp < pos:
                    sec = s["title"]
                    break
            before = content[:pos].rstrip().split("\n")
            desc = ""
            for ln in reversed(before[-5:]):
                c = ln.strip().lstrip("#-*>").strip()
                if c and len(c) > 3:
                    desc = c
                    break
            blocks.append({"language": lang, "code": code, "description": desc, "section": sec})
        return blocks

    @staticmethod
    def _has_section(sections: list[dict], keywords: list[str]) -> bool:
        return any(any(kw in s.get("title", "").lower() for kw in keywords) for s in sections)

    # ── Private: API doc helpers ────────────────────────────────────────

    def _parse_openapi(self, code_file: CodeFile, content: str) -> Optional[APIDocumentation]:
        spec = _parse_openapi_spec(content)
        if not spec:
            return None
        info = spec.get("info", {})
        endpoints: list[dict] = []
        for path, methods in spec.get("paths", {}).items():
            if not isinstance(methods, dict):
                continue
            for method, det in methods.items():
                if method.startswith("x-") or not isinstance(det, dict):
                    continue
                endpoints.append({
                    "method": method.upper(), "path": path,
                    "summary": det.get("summary", ""), "description": det.get("description", ""),
                    "operation_id": det.get("operationId", ""),
                    "parameter_count": len(det.get("parameters", [])),
                    "response_count": len(det.get("responses", {})),
                    "documented": bool(det.get("summary") or det.get("description")),
                })
        schemas = [
            {"name": n, "description": sd.get("description", ""), "type": sd.get("type", "object"),
             "properties_count": len(sd.get("properties", {}))}
            for n, sd in spec.get("components", {}).get("schemas", {}).items()
            if isinstance(sd, dict)
        ]
        doc_count = sum(1 for e in endpoints if e.get("documented"))
        return APIDocumentation(
            file_id=str(code_file.id), file_path=code_file.file_path, spec_type="openapi",
            title=info.get("title", ""), version=info.get("version", ""),
            description=info.get("description", ""), endpoints=endpoints, schemas=schemas,
            security=spec.get("security", []),
            total_endpoints=len(endpoints), documented_endpoints=doc_count,
        )

    def _parse_graphql(self, code_file: CodeFile, content: str) -> Optional[APIDocumentation]:
        types: list[dict] = []
        for m in re.finditer(r"(?:type|interface|input|enum)\s+(\w+)(?:\s+implements\s+\w+)?\s*\{([^}]*)\}", content, re.DOTALL):
            fields = []
            for fl in m.group(2).strip().split("\n"):
                fm = re.match(r"(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+)", fl.strip())
                if fm:
                    fields.append({"name": fm.group(1), "type": fm.group(2).strip()})
            types.append({"name": m.group(1), "fields": fields, "field_count": len(fields)})

        endpoints: list[dict] = []
        for sec in ("Query", "Mutation"):
            sm = re.search(rf"type\s+{sec}\s*\{{([^}}]*)\}}", content, re.DOTALL)
            if sm:
                for ln in sm.group(1).split("\n"):
                    fm = re.match(r"(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+)", ln.strip())
                    if fm:
                        endpoints.append({"method": sec.upper(), "path": fm.group(1),
                                          "type": fm.group(2).strip(), "documented": False})

        descs: dict[str, str] = {}
        for dm in re.finditer(r'"""(.*?)"""', content, re.DOTALL):
            nm = re.search(r"(?:type|input|enum)\s+(\w+)", content[dm.end():dm.end() + 200])
            if nm:
                descs[nm.group(1)] = dm.group(1).strip()
        for ep in endpoints:
            if ep["path"] in descs:
                ep["summary"] = descs[ep["path"]]
                ep["documented"] = True

        return APIDocumentation(
            file_id=str(code_file.id), file_path=code_file.file_path, spec_type="graphql",
            title="GraphQL Schema", endpoints=endpoints, schemas=types,
            total_endpoints=len(endpoints), documented_endpoints=sum(1 for e in endpoints if e.get("documented")),
        )

    # ── Private: file counting ──────────────────────────────────────────

    async def _count_files(
        self, repository_id: UUID, patterns: list[str], db: AsyncSession, exact: bool = False,
    ) -> int:
        result = await db.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id))
        count = 0
        for f in result.scalars().all():
            if exact:
                if f.file_name in patterns:
                    count += 1
            elif any(re.search(p, f.file_name, re.IGNORECASE) for p in patterns):
                count += 1
        return count


# ── Module-level helpers ───────────────────────────────────────────────


def _detect_docstring_style(docstring: str) -> str:
    for style, markers in _DOCSTRING_STYLE_MARKERS.items():
        if any(m in docstring for m in markers):
            return style
    return "plain"


def _calculate_docstring_quality(docstring: str) -> float:
    if not docstring or not docstring.strip():
        return 0.0
    score = 0.0
    length = len(docstring.strip())
    if length > 20:  score += 0.15
    if length > 80:  score += 0.10
    if length > 200: score += 0.10
    if _PARAM_RE.search(docstring):    score += 0.20
    if _RETURN_RE.search(docstring):   score += 0.15
    if re.search(r"(?:raise|throws|exception|:raises|@throws)", docstring, re.IGNORECASE):
        score += 0.10
    if _EXAMPLE_RE.search(docstring):  score += 0.10
    if "```" in docstring:             score += 0.05
    if len(re.split(r"[.!?]+", docstring.strip())) >= 2:
        score += 0.05
    return min(score, 1.0)


def _extract_examples_from_docstring(docstring: str) -> list[dict]:
    if not docstring:
        return []
    examples: list[dict] = []
    for m in re.finditer(r">>>\s*(.*?)(?=\n>>>|\n\S|\Z)", docstring, re.DOTALL):
        code = m.group(0).strip()
        if code:
            examples.append({"code": code, "language": "python", "description": ""})
    for m in re.finditer(r"```(\w*)\s*\n(.*?)```", docstring, re.DOTALL):
        code = m.group(2).strip()
        if code:
            examples.append({"code": code, "language": m.group(1) or "unknown", "description": ""})
    return examples


def _quality_score(
    total: int, doc_count: int, avg_len: float, params: int, rets: int,
    examples: int, readme: int, api: int,
) -> float:
    if total == 0:
        return 0.0
    cov = doc_count / total
    return min(
        cov * 0.25 + min(avg_len / 200.0, 1.0) * 0.15
        + (params / doc_count if doc_count else 0) * 0.15
        + (rets / doc_count if doc_count else 0) * 0.10
        + min(examples / max(total * 0.1, 1), 1.0) * 0.10
        + min(readme, 1) * 0.10 + min(api, 1) * 0.08,
        1.0,
    )


def _recommendations(
    total: int, doc_count: int, avg_len: float, params: int, rets: int,
    examples: int, readme: int, api: int,
) -> list[str]:
    recs: list[str] = []
    if total == 0:
        return ["No symbols found. Ensure the repository is indexed."]
    cov = doc_count / total
    if cov < 0.3:
        recs.append(f"Documentation coverage is low ({cov:.0%}). Focus on public classes and functions.")
    elif cov < 0.6:
        recs.append(f"Documentation coverage is moderate ({cov:.0%}). Document remaining public APIs.")
    elif cov < 0.8:
        recs.append(f"Documentation coverage is good ({cov:.0%}). Aim for complete public interface coverage.")
    else:
        recs.append(f"Documentation coverage is excellent ({cov:.0%}).")
    if doc_count > 0 and params / doc_count < 0.5:
        recs.append(f"Only {params / doc_count:.0%} of documented symbols have parameter docs.")
    if doc_count > 0 and rets / doc_count < 0.4:
        recs.append(f"Only {rets / doc_count:.0%} of documented symbols document return values.")
    if avg_len < 50 and doc_count > 0:
        recs.append("Average docstring is short. Add more context, examples, or parameter details.")
    if examples < total * 0.05 and total > 0:
        recs.append("Very few code examples found. Add usage examples to key functions.")
    if readme == 0:
        recs.append("No README found. Every repository needs a README.md.")
    if api == 0:
        recs.append("No API specification found. Consider adding OpenAPI/Swagger/GraphQL specs.")
    return recs


def _is_api_spec(filename: str) -> bool:
    return any(re.search(p, filename, re.IGNORECASE) for p in API_SPEC_PATTERNS)


def _is_arch_doc(filename: str) -> bool:
    return (ADR_FILENAME_RE.search(filename) or
            any(re.search(p, filename.upper(), re.IGNORECASE) for p in ARCHITECTURE_DOC_PATTERNS))
