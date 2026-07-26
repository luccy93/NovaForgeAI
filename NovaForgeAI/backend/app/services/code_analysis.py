import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_LANGUAGE_GRAMMARS: dict[str, str] = {
    "python": "tree_sitter_python",
    "typescript": "tree_sitter_typescript",
    "javascript": "tree_sitter_javascript",
    "go": "tree_sitter_go",
    "rust": "tree_sitter_rust",
    "java": "tree_sitter_java",
}

_FUNC_NODE_TYPES = {"function_definition", "function_declaration", "function_item", "method_declaration"}
_CLASS_NODE_TYPES = {"class_definition", "class_declaration"}


class CodeAnalysisService:
    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}

    def _get_parser(self, language: str) -> Any:
        lang_lower = language.lower()
        if lang_lower in self._parsers:
            return self._parsers[lang_lower]

        if lang_lower not in _LANGUAGE_GRAMMARS:
            raise ValueError(f"Unsupported language: {language}. Supported: {list(_LANGUAGE_GRAMMARS.keys())}")

        try:
            import tree_sitter as ts
        except ImportError:
            logger.warning("tree_sitter not installed; falling back to regex analysis")
            return None

        try:
            grammar_module = __import__(_LANGUAGE_GRAMMARS[lang_lower], fromlist=["language"])
            lang = grammar_module.language()
            parser = ts.Parser(lang)
            self._parsers[lang_lower] = parser
            return parser
        except Exception as e:
            logger.warning("Failed to load tree-sitter grammar for %s: %s", language, e)
            return None

    def _parse(self, content: str, language: str) -> Optional[Any]:
        parser = self._get_parser(language)
        if parser is None:
            return None
        tree = parser.parse(bytes(content, "utf-8"))
        return tree

    def analyze_file(self, content: str, language: str) -> dict[str, Any]:
        tree = self._parse(content, language)
        return {
            "language": language,
            "size_bytes": len(content.encode("utf-8")),
            "line_count": len(content.splitlines()),
            "functions": self.extract_functions(content, language),
            "classes": self.extract_classes(content, language),
            "complexity": self.compute_complexity(content, language),
            "dependencies": self.detect_dependencies(content, language),
            "has_syntax_tree": tree is not None,
        }

    def extract_functions(self, content: str, language: str) -> list[dict[str, Any]]:
        functions: list[dict[str, Any]] = []
        tree = self._parse(content, language)
        if tree is not None:
            self._walk_tree(tree.root_node, content, functions, _FUNC_NODE_TYPES, "name")
        if not functions:
            functions = self._extract_func_regex(content, language)
        return functions

    def extract_classes(self, content: str, language: str) -> list[dict[str, Any]]:
        classes: list[dict[str, Any]] = []
        tree = self._parse(content, language)
        if tree is not None:
            self._walk_tree(tree.root_node, content, classes, _CLASS_NODE_TYPES, "name")
        if not classes:
            classes = self._extract_class_regex(content, language)
        return classes

    def _walk_tree(
        self, node: Any, content: str, results: list[dict[str, Any]],
        node_types: set[str], name_field: str
    ) -> None:
        if node.type in node_types:
            name_node = node.child_by_field_name(name_field)
            if name_node:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                results.append({
                    "name": content[name_node.start_byte:name_node.end_byte],
                    "start_line": start_line,
                    "end_line": end_line,
                })
        for child in node.children:
            self._walk_tree(child, content, results, node_types, name_field)

    def _extract_func_regex(self, content: str, language: str) -> list[dict[str, Any]]:
        patterns = {
            "python": r"^\s*def\s+(\w+)\s*\(",
            "javascript": r"(?:function\s+(\w+)\s*\(|(\w+)\s*=\s*(?:async\s+)?function\s*\()",
            "typescript": r"(?:function\s+(\w+)\s*\(|(\w+)\s*=\s*(?:async\s+)?function\s*\(|^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?::|{))",
            "go": r"^\s*func\s+(\w+)\s*\(",
            "rust": r"^\s*fn\s+(\w+)\s*\(",
            "java": r"(?:public|private|protected)\s+\S+\s+(\w+)\s*\(",
        }
        pattern = patterns.get(language)
        if not pattern:
            return []
        functions = []
        for i, line in enumerate(content.splitlines(), 1):
            m = re.search(pattern, line)
            if m:
                name = m.group(1) or m.group(2) or m.group(3) or ""
                if name:
                    functions.append({"name": name, "start_line": i, "end_line": i})
        return functions

    def _extract_class_regex(self, content: str, language: str) -> list[dict[str, Any]]:
        patterns = {
            "python": r"^\s*class\s+(\w+)",
            "typescript": r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)",
            "javascript": r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)",
            "java": r"^\s*(?:public|private|protected)?\s*(?:abstract\s+)?class\s+(\w+)",
        }
        pattern = patterns.get(language)
        if not pattern:
            return []
        classes = []
        for i, line in enumerate(content.splitlines(), 1):
            m = re.search(pattern, line)
            if m:
                classes.append({"name": m.group(1), "start_line": i, "end_line": i})
        return classes

    def compute_complexity(self, content: str, language: str) -> int:
        complexity = 1
        decision_keywords = {
            "python": [r"\bif\b", r"\belif\b", r"\bfor\b", r"\bwhile\b", r"\band\b", r"\bor\b", r"\bexcept\b", r"\bcase\b"],
            "javascript": [r"\bif\b", r"\belse if\b", r"\bfor\b", r"\bwhile\b", r"\bcatch\b", r"\bcase\b", r"&&", r"\|\|"],
            "typescript": [r"\bif\b", r"\belse if\b", r"\bfor\b", r"\bwhile\b", r"\bcatch\b", r"\bcase\b", r"&&", r"\|\|"],
            "go": [r"\bif\b", r"\bfor\b", r"\brange\b", r"\bswitch\b", r"\bcase\b", r"&&", r"\|\|"],
            "rust": [r"\bif\b", r"\bfor\b", r"\bwhile\b", r"\bmatch\b", r"\bcase\b", r"&&", r"\|\|"],
            "java": [r"\bif\b", r"\belse if\b", r"\bfor\b", r"\bwhile\b", r"\bcatch\b", r"\bcase\b", r"&&", r"\|\|"],
        }
        patterns = decision_keywords.get(language)
        if not patterns:
            return complexity
        for pattern in patterns:
            complexity += len(re.findall(pattern, content))
        return complexity

    def detect_dependencies(self, content: str, language: str) -> list[str]:
        patterns = {
            "python": (r"^\s*(?:import\s+(\S+)|from\s+(\S+)\s+import)", 1),
            "javascript": (r"(?:require\(['\"]([^'\"]+)['\"]\)|from\s+['\"]([^'\"]+)['\"])", 1),
            "typescript": (r"(?:require\(['\"]([^'\"]+)['\"]\)|from\s+['\"]([^'\"]+)['\"])", 1),
            "go": (r'^\s*import\s+(?:"([^"]+)"|\([^)]*\))', 1),
            "rust": (r'^\s*use\s+(\S+);', 1),
            "java": (r'^\s*import\s+(\S+);', 1),
        }
        lang_data = patterns.get(language)
        if not lang_data:
            return []
        pattern, group_idx = lang_data
        deps: list[str] = []
        for line in content.splitlines():
            m = re.search(pattern, line)
            if m:
                dep = m.group(1) or m.group(2) or ""
                if dep and dep not in deps:
                    deps.append(dep)
        return deps
