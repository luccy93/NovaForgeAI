"""Autonomous Code Review — AI-driven code review detecting architecture, security, performance, naming, documentation, testing, API, and complexity issues."""

import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class ReviewComment:
    id: str
    file: str
    line: int
    severity: str  # critical, high, medium, low, info
    category: str  # architecture, security, performance, naming, documentation, testing, api, complexity
    message: str
    suggestion: str
    patch: str = ""
    confidence: float = 0.8


@dataclass
class ReviewReport:
    repo_id: str
    repo_name: str
    timestamp: str
    comments: list[ReviewComment] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    category_breakdown: dict[str, int] = field(default_factory=dict)
    overall_quality_score: float = 0.0
    suggested_patches: list[dict] = field(default_factory=list)


class AutonomousCodeReview:
    """AI-driven code review engine — detects issues and generates patches automatically."""

    NAMING_PATTERNS = {
        "single_char_name": (r'\bdef\s+([a-z])\s*\(', "low"),
        "unclear_abbrev": (r'\bdef\s+(?:do_sth|get_data|process|handle|run|exec|do_it)\b', "low"),
        "snake_case_class": (r'class\s+[a-z]+_[a-z]+', "medium"),
        "mixed_case_function": (r'def\s+[A-Z][a-zA-Z]*', "low"),
    }

    PERFORMANCE_PATTERNS = {
        "nested_loop": (r'for\s+\w+\s+in\s+.*:\s*\n\s+for\s+\w+\s+in\s+', "medium"),
        "inefficient_string_concat": (r'\w+\s*\+=\s*["\']', "low"),
        "missing_cache": (r'def\s+\w+\(.*\):\s*\n(?:.*\n)*\s+return\s+\w+\.(?:filter|get|first|all)\(\)', "medium"),
        "sync_in_async": (r'async\s+def.*:\s*\n\s+.*(?:requests\.get|time\.sleep|subprocess\.call)', "high"),
    }

    DOCUMENTATION_PATTERNS = {
        "missing_docstring": (r'^def\s+\w+\(', "medium"),
        "missing_class_docstring": (r'^class\s+\w+', "medium"),
        "todo_comment": (r'#\s*(TODO|FIXME|HACK|XXX)', "low"),
    }

    TESTING_PATTERNS = {
        "missing_assert": (r'def\s+test_\w+\(\):\s*\n(?:.*\n)*\s*(?!=.*assert)', "medium"),
        "no_edge_case": (r'def\s+test_\w+\(\):\s*\n\s+(?!.*(?:None|empty|zero|null|false|invalid|error|exception))', "low"),
    }

    API_PATTERNS = {
        "hardcoded_url": (r'https?://localhost:\d+|https?://[a-z]+\.com', "medium"),
        "missing_validation": (r'def\s+\w+\(.*request.*\):\s*\n(?!.*validation|.*validate|.*model_validator)', "medium"),
        "no_error_handler": (r'@app\.(?:get|post|put|delete|patch).*\n(?:.*\n)*def\s+\w+\(', "high"),
    }

    COMPLEXITY_PATTERNS = {
        "excessive_parameters": (r'def\s+\w+\([^)]{100,}\)', "medium"),
        "deep_conditionals": (r'if\s+.*:\s*\n\s+if\s+.*:\s*\n\s+if\s+.*:\s*\n\s+if\s+', "high"),
        "long_lambda": (r'lambda\s+\w+\s*:\s*[^,)]{80,}', "low"),
    }

    def _detect_naming(self, content: str, rel_path: str, report: ReviewReport):
        for name, (pattern, severity) in self.NAMING_PATTERNS.items():
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                cid = self._cid(rel_path, line_num, name)
                report.comments.append(ReviewComment(
                    id=cid, file=rel_path, line=line_num,
                    severity=severity, category="naming",
                    message=f"Naming issue: {name.replace('_', ' ')}",
                    suggestion=self._naming_suggestion(name, match),
                    confidence=0.7,
                ))

    def _generate_performance_patches(self, content: str, rel_path: str, report: ReviewReport):
        for name, (pattern, severity) in self.PERFORMANCE_PATTERNS.items():
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if re.search(pattern, line):
                    line_num = i + 1
                    cid = self._cid(rel_path, line_num, name)
                    comment = ReviewComment(
                        id=cid, file=rel_path, line=line_num,
                        severity=severity, category="performance",
                        message=f"Performance issue: {name.replace('_', ' ')}",
                        suggestion=self._perf_suggestion(name),
                        confidence=0.7,
                    )
                    patch = self._generate_perf_patch(name, lines, i)
                    if patch:
                        comment.patch = patch
                        report.suggested_patches.append({
                            "file": rel_path,
                            "line": line_num,
                            "category": f"performance.{name}",
                            "patch": patch,
                        })
                    report.comments.append(comment)

    def _generate_docstring_patches(self, content: str, rel_path: str, report: ReviewReport):
        for f in [f for f in [self._try_parse_ast(content)] if f]:
            tree = f
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not ast.get_docstring(node):
                        cid = self._cid(rel_path, node.lineno, "missing_docstring")
                        report.comments.append(ReviewComment(
                            id=cid, file=rel_path, line=node.lineno,
                            severity="medium", category="documentation",
                            message=f"Missing docstring for function `{node.name}`",
                            suggestion=f"Add docstring describing parameters, return value, and behavior",
                            patch=f'    """{node.name} — TODO: add description.\n\n    Returns:\n        TODO: add return type.\n    """\n',
                            confidence=0.6,
                        ))
                elif isinstance(node, ast.ClassDef):
                    if not ast.get_docstring(node):
                        cid = self._cid(rel_path, node.lineno, "missing_class_docstring")
                        report.comments.append(ReviewComment(
                            id=cid, file=rel_path, line=node.lineno,
                            severity="medium", category="documentation",
                            message=f"Missing docstring for class `{node.name}`",
                            suggestion=f"Add class docstring describing purpose and usage",
                            patch=f'    """{node.name} — TODO: add class description.\n    """\n',
                            confidence=0.6,
                        ))

    def _detect_security_issues(self, content: str, rel_path: str, report: ReviewComment):
        security_checks = [
            ("hardcoded_secret", r'(?:api[_-]?key|apikey|secret)\s*[:=]\s*["\'][\w-]{16,}', "high",
             "Hardcoded secret detected", "Use environment variables or a vault service"),
            ("sql_injection", r'execute\(.*f["\'].*\{.*["\']', "critical",
             "SQL injection risk", "Use parameterized queries: cursor.execute(query, params)"),
            ("command_injection", r'(?:os\.system|subprocess\.\w+\(.*["\'].*\+)', "critical",
             "Command injection risk", "Use subprocess with argument list, avoid shell interpolation"),
            ("path_traversal", r'open\(.*\+.*["\']', "high",
             "Path traversal risk", "Use os.path.join and validate path components"),
            ("insecure_crypto", r'(?:DES|MD5|SHA1|RC4|ECB)', "high",
             "Insecure cryptographic algorithm", "Use AES-256-GCM or ChaCha20-Poly1305"),
        ]

        for name, pattern, severity, message, suggestion in security_checks:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                cid = self._cid(rel_path, line_num, name)
                report.comments.append(ReviewComment(
                    id=cid, file=rel_path, line=line_num,
                    severity=severity, category="security",
                    message=message, suggestion=suggestion,
                    confidence=0.85,
                ))

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def review(self) -> ReviewReport:
        report = ReviewReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        for file_path in sorted(self.repo_path.rglob("*")):
            if not file_path.is_file() or file_path.suffix not in (".py", ".js", ".ts", ".jsx", ".tsx"):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel_path = str(file_path.relative_to(self.repo_path))

            self._detect_naming(content, rel_path, report)
            self._detect_performance(content, rel_path, report)
            self._detect_documentation_gaps(content, rel_path, report)
            self._detect_testing_gaps(content, rel_path, report)
            self._detect_api_inconsistencies(content, rel_path, report)
            self._detect_complexity(content, rel_path, report)
            self._detect_security_issues(content, rel_path, report)

        report.critical_count = sum(1 for c in report.comments if c.severity == "critical")
        report.high_count = sum(1 for c in report.comments if c.severity == "high")
        report.medium_count = sum(1 for c in report.comments if c.severity == "medium")
        report.low_count = sum(1 for c in report.comments if c.severity in ("low", "info"))

        cat_counts = defaultdict(int)
        for c in report.comments:
            cat_counts[c.category] += 1
        report.category_breakdown = dict(cat_counts)

        total = max(len(report.comments), 1)
        report.overall_quality_score = max(0, 100 - (report.critical_count * 10 + report.high_count * 5 +
                                                      report.medium_count * 2 + report.low_count * 0.5) / total * 10)

        return report

    def _detect_performance(self, content: str, rel_path: str, report: ReviewReport):
        for name, (pattern, severity) in self.PERFORMANCE_PATTERNS.items():
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                cid = self._cid(rel_path, line_num, name)
                report.comments.append(ReviewComment(
                    id=cid, file=rel_path, line=line_num,
                    severity=severity, category="performance",
                    message=f"Performance issue: {name.replace('_', ' ')}",
                    suggestion=self._perf_suggestion(name),
                    confidence=0.7,
                ))

    def _detect_documentation_gaps(self, content: str, rel_path: str, report: ReviewReport):
        for name, (pattern, severity) in self.DOCUMENTATION_PATTERNS.items():
            if name == "missing_docstring":
                for match in re.finditer(r'^def\s+\w+\(', content, re.MULTILINE):
                    pos = match.start()
                    line_start = content.rfind("\n", 0, pos) + 1 if pos > 0 else 0
                    preceding = content[max(0, line_start - 200):line_start]
                    if '"""' not in preceding and "'''" not in preceding:
                        line_num = content[:pos].count("\n") + 1
                        fn_name = match.group(0)[4:-1]
                        cid = self._cid(rel_path, line_num, name)
                        report.comments.append(ReviewComment(
                            id=cid, file=rel_path, line=line_num,
                            severity=severity, category="documentation",
                            message=f"Missing docstring for function `{fn_name}`",
                            suggestion=f"Add docstring describing parameters, return value, and behavior",
                            confidence=0.6,
                        ))
            elif name == "missing_class_docstring":
                for match in re.finditer(r'^class\s+\w+', content, re.MULTILINE):
                    pos = match.start()
                    line_start = content.rfind("\n", 0, pos) + 1 if pos > 0 else 0
                    preceding = content[max(0, line_start - 200):line_start]
                    if '"""' not in preceding and "'''" not in preceding:
                        line_num = content[:pos].count("\n") + 1
                        cls_name = match.group(0)[6:]
                        cid = self._cid(rel_path, line_num, name)
                        report.comments.append(ReviewComment(
                            id=cid, file=rel_path, line=line_num,
                            severity=severity, category="documentation",
                            message=f"Missing docstring for class `{cls_name}`",
                            suggestion="Add class docstring describing purpose and usage",
                            confidence=0.6,
                        ))
            else:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    line_num = content[: match.start()].count("\n") + 1
                    cid = self._cid(rel_path, line_num, name)
                    report.comments.append(ReviewComment(
                        id=cid, file=rel_path, line=line_num,
                        severity=severity, category="documentation",
                        message=f"Documentation: {match.group(0).strip()} found",
                        suggestion="Address TODO/FIXME items or add documentation",
                        confidence=0.8,
                    ))

    def _detect_testing_gaps(self, content: str, rel_path: str, report: ReviewReport):
        if "test" not in rel_path.lower():
            return

        for name, (pattern, severity) in self.TESTING_PATTERNS.items():
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                cid = self._cid(rel_path, line_num, name)
                report.comments.append(ReviewComment(
                    id=cid, file=rel_path, line=line_num,
                    severity=severity, category="testing",
                    message=f"Testing gap: {name.replace('_', ' ')}",
                    suggestion=self._testing_suggestion(name),
                    confidence=0.5,
                ))

    def _detect_api_inconsistencies(self, content: str, rel_path: str, report: ReviewReport):
        for name, (pattern, severity) in self.API_PATTERNS.items():
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                cid = self._cid(rel_path, line_num, name)
                report.comments.append(ReviewComment(
                    id=cid, file=rel_path, line=line_num,
                    severity=severity, category="api",
                    message=f"API issue: {name.replace('_', ' ')}",
                    suggestion=self._api_suggestion(name),
                    confidence=0.65,
                ))

    def _detect_complexity(self, content: str, rel_path: str, report: ReviewReport):
        for name, (pattern, severity) in self.COMPLEXITY_PATTERNS.items():
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                cid = self._cid(rel_path, line_num, name)
                report.comments.append(ReviewComment(
                    id=cid, file=rel_path, line=line_num,
                    severity=severity, category="complexity",
                    message=f"Complexity issue: {name.replace('_', ' ')}",
                    suggestion=self._complexity_suggestion(name),
                    confidence=0.7,
                ))

    def _detect_security_issues(self, content: str, rel_path: str, report: ReviewReport):
        checks = [
            ("hardcoded_secret", r'(?:api[_-]?key|apikey|secret)\s*[:=]\s*["\'][\w-]{16,}', "high"),
            ("sql_injection", r'execute\(.*f["\'].*\{', "critical"),
            ("command_injection", r'(?:os\.system|subprocess\.\w+\(.*["\'].*\+)', "critical"),
            ("path_traversal", r'open\(.*\+.*["\']', "high"),
            ("insecure_crypto", r'(?:DES|MD5|SHA1|RC4|ECB)', "high"),
        ]
        for name, pattern, severity in checks:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                cid = self._cid(rel_path, line_num, name)
                report.comments.append(ReviewComment(
                    id=cid, file=rel_path, line=line_num,
                    severity=severity, category="security",
                    message=f"Security issue: {name.replace('_', ' ')}",
                    suggestion=self._security_suggestion(name),
                    confidence=0.85,
                ))

    def _naming_suggestion(self, issue: str, match: re.Match) -> str:
        suggestions = {
            "single_char_name": "Use descriptive function names (e.g., `calculate_total()` instead of `t()`)",
            "unclear_abbrev": "Use descriptive function names that convey the operation clearly",
            "snake_case_class": "Use PascalCase for class names (e.g., `class UserProfile` instead of `class user_profile`)",
            "mixed_case_function": "Use snake_case for function names (e.g., `get_user()` instead of `getUser()`)",
        }
        return suggestions.get(issue, "Follow naming conventions for better readability")

    def _perf_suggestion(self, issue: str) -> str:
        suggestions = {
            "nested_loop": "Avoid nested loops over large datasets; use dictionary lookups or set operations",
            "inefficient_string_concat": "Use ''.join() or f-strings instead of += for string concatenation in loops",
            "missing_cache": "Consider caching expensive computations with functools.lru_cache or similar",
            "sync_in_async": "Use async-compatible libraries (aiohttp, asyncio.sleep) inside async functions",
        }
        return suggestions.get(issue, "Review for performance optimization")

    def _testing_suggestion(self, issue: str) -> str:
        suggestions = {
            "missing_assert": "Test function appears to have no assertions — verify expected behavior",
            "no_edge_case": "Consider adding test cases for edge cases (None, empty, invalid inputs)",
        }
        return suggestions.get(issue, "Improve test coverage")

    def _api_suggestion(self, issue: str) -> str:
        suggestions = {
            "hardcoded_url": "Use configuration variables or environment variables for URLs",
            "missing_validation": "Add request validation (Pydantic models, marshmallow schemas, etc.)",
            "no_error_handler": "Add try/except blocks with proper error responses",
        }
        return suggestions.get(issue, "Review API design consistency")

    def _complexity_suggestion(self, issue: str) -> str:
        suggestions = {
            "excessive_parameters": "Consider using a configuration object or dataclass for many parameters",
            "deep_conditionals": "Use early returns, guard clauses, or pattern matching to flatten nesting",
            "long_lambda": "Replace complex lambda with a named function for readability",
        }
        return suggestions.get(issue, "Simplify complex code")

    def _security_suggestion(self, issue: str) -> str:
        suggestions = {
            "hardcoded_secret": "Use environment variables or a secrets manager (e.g., HashiCorp Vault)",
            "sql_injection": "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
            "command_injection": "Use subprocess with argument list: subprocess.run(['ls', '-la'], shell=False)",
            "path_traversal": "Use os.path.realpath() and validate user-supplied path components",
            "insecure_crypto": "Use modern algorithms: AES-256-GCM, ChaCha20-Poly1305, Argon2",
        }
        return suggestions.get(issue, "Fix security vulnerability")

    def _generate_perf_patch(self, issue: str, lines: list[str], line_idx: int) -> str:
        if issue == "nested_loop":
            return "# TODO: Extract nested loop into vectorized operation using map() or comprehensions"
        elif issue == "inefficient_string_concat":
            return "# TODO: Replace string concatenation with ''.join([...])"
        return ""

    def _try_parse_ast(self, content: str) -> Optional[ast.AST]:
        try:
            return ast.parse(content)
        except SyntaxError:
            return None

    def _cid(self, file: str, line: int, issue: str) -> str:
        seed = f"{file}:{line}:{issue}:{datetime.now(timezone.utc).isoformat()}"
        return hashlib.sha256(seed.encode()).hexdigest()[:16]
