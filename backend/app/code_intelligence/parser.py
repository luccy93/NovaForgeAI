"""Tree-sitter parsing engine for NovaForge code intelligence.

Supports 20 languages via tree-sitter grammars with automatic regex fallback
when tree-sitter is not installed.
"""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

HAS_TREE_SITTER = False
tree_sitter = None
ts_language = None

try:
    import tree_sitter as _tree_sitter
    import tree_sitter_languages as _tree_sitter_languages

    tree_sitter = _tree_sitter
    HAS_TREE_SITTER = True
except ImportError:
    try:
        import tree_sitter as _tree_sitter

        tree_sitter = _tree_sitter
        HAS_TREE_SITTER = True
    except ImportError:
        HAS_TREE_SITTER = False
        tree_sitter = None


class SymbolType(Enum):
    FILE = "file"
    MODULE = "module"
    PACKAGE = "package"
    NAMESPACE = "namespace"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    PROPERTY = "property"
    TYPE = "type"
    IMPORT = "import"


@dataclass
class SymbolInfo:
    name: str
    qualified_name: str
    symbol_type: SymbolType
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"
    is_async: bool = False
    is_abstract: bool = False
    is_static: bool = False
    decorators: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    return_type: str = ""
    parent_name: str = ""
    language: str = ""
    file_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportInfo:
    name: str
    import_type: str
    alias: str = ""
    module_path: str = ""
    is_external: bool = False
    is_stdlib: bool = False
    line: int = 0


@dataclass
class CallInfo:
    caller_name: str
    callee_name: str
    call_line: int
    call_type: str = "DIRECT"
    resolved: bool = False
    confidence: float = 0.0


@dataclass
class ParseResult:
    file_path: str
    language: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    line_count: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    parse_time_ms: float = 0.0
    error: str = ""
    tree_hash: str = ""


STDLIB_MODULES_PYTHON = frozenset({
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii", "binhex",
    "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk",
    "cmath", "cmd", "code", "codecs", "codeop", "collections", "colorsys",
    "compileall", "concurrent", "configparser", "contextlib", "contextvars",
    "copy", "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
    "distutils", "doctest", "email", "encodings", "enum", "errno",
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch", "fractions",
    "ftplib", "functools", "gc", "getopt", "getpass", "gettext", "glob",
    "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http", "idlelib",
    "imaplib", "imghdr", "imp", "importlib", "inspect", "io", "ipaddress",
    "itertools", "json", "keyword", "lib2to3", "linecache", "locale",
    "logging", "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
    "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue",
    "quopri", "random", "re", "readline", "reprlib", "resource", "rlcompleter",
    "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr", "socket",
    "socketserver", "spwd", "sqlite3", "sre_compile", "sre_constants",
    "sre_parse", "ssl", "stat", "statistics", "string", "stringprep",
    "struct", "subprocess", "sunau", "symtable", "sys", "sysconfig",
    "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile", "termios",
    "test", "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
    "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
    "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
    "typing_extensions", "dataclasses_json", "pydantic",
})

STDLIB_MODULES_JAVASCRIPT = frozenset({
    "assert", "buffer", "child_process", "cluster", "console", "constants",
    "crypto", "dgram", "dns", "domain", "events", "fs", "http", "http2",
    "https", "inspector", "module", "net", "os", "path", "process",
    "punycode", "querystring", "readline", "repl", "stream", "string_decoder",
    "sys", "timers", "tls", "trace_events", "tty", "url", "util", "v8",
    "vm", "wasi", "worker_threads", "zlib",
})

STDLIB_MODULES_GO = frozenset({
    "bufio", "bytes", "compress", "container", "context", "crypto", "database",
    "debug", "embed", "encoding", "errors", "expvar", "flag", "fmt", "go",
    "hash", "html", "image", "index", "internal", "io", "log", "maps",
    "math", "mime", "net", "os", "path", "plugin", "reflect", "regexp",
    "runtime", "runtime/cgo", "runtime/debug", "runtime/metrics",
    "runtime/pprof", "runtime/trace", "slices", "sort", "strconv", "strings",
    "sync", "syscall", "testing", "testing/fstest", "testing/iotest",
    "testing/quick", "testing/slogtest", "testing/synctest", "text",
    "time", "unicode", "unsafe", "unique", "weak",
})

STDLIB_MODULES_RUST = frozenset({
    "std", "core", "alloc", "proc_macro", "proc_macro2", "any", "arch",
    "array", "ascii", "assert_matches", "borrow", "boxed", "cell", "char",
    "clone", "cmp", "collections", "convert", "default", "env", "error",
    "f32", "f64", "ffi", "fmt", "fs", "future", "hash", "hashbrown",
    "hint", "i128", "i16", "i32", "i64", "i8", "io", "iter", "lazy_static",
    "marker", "mem", "net", "num", "ops", "option", "os", "panic", "path",
    "pin", "process", "ptr", "rc", "regex", "result", "slice", "str",
    "string", "sync", "task", "thread", "time", "u128", "u16", "u32",
    "u64", "u8", "vec",
})

STDLIB_MODULES_CPP = frozenset({
    "algorithm", "any", "array", "atomic", "barrier", "bit", "bitset",
    "cassert", "cctype", "cerrno", "cfenv", "cfloat", "charconv",
    "chrono", "climits", "clocale", "cmath", "compare", "concepts",
    "condition_variable", "coroutine", "csetjmp", "csignal", "cstdarg",
    "cstddef", "cstdint", "cstdio", "cstdlib", "cstring", "ctime",
    "cwchar", "cwctype", "deque", "exception", "execution", "expected",
    "filesystem", "format", "forward_list", "fstream", "functional",
    "future", "initializer_list", "iomanip", "ios", "iosfwd", "iostream",
    "istream", "iterator", "latch", "limits", "list", "locale", "map",
    "memory", "memory_resource", "mutex", "new", "numbers", "numeric",
    "optional", "ostream", "print", "queue", "random", "ranges", "ratio",
    "regex", "scoped_allocator", "semaphore", "set", "shared_mutex",
    "source_location", "span", "spanstream", "sstream", "stack",
    "stacktrace", "stdexcept", "stop_token", "streambuf", "string",
    "string_view", "syncstream", "system_error", "thread", "tuple",
    "type_traits", "typeindex", "typeinfo", "unordered_map",
    "unordered_set", "utility", "valarray", "variant", "vector", "version",
})

STDLIB_MODULES_CSHARP = frozenset({
    "System", "Microsoft", "System.Collections", "System.Collections.Generic",
    "System.IO", "System.Linq", "System.Net", "System.Net.Http",
    "System.Threading", "System.Threading.Tasks", "System.Text",
    "System.Text.Json", "System.Text.RegularExpressions", "System.Diagnostics",
    "System.ComponentModel", "System.Runtime", "System.Security",
    "System.Reflection", "System.Data", "System.Xml", "System.Web",
    "System.Configuration", "System.Transactions", "System.ServiceProcess",
    "System.Drawing", "System.Windows", "Newtonsoft.Json", "AutoMapper",
})

STDLIB_MODULES_KOTLIN = frozenset({
    "kotlin", "kotlinx", "kotlin.reflect", "kotlin.collections",
    "kotlin.comparisons", "kotlin.io", "kotlin.math", "kotlin.random",
    "kotlin.streams", "kotlin.text", "kotlinx.coroutines",
    "kotlinx.serialization", "kotlinx.datetime", "kotlinx.io",
})

STDLIB_MODULES_SWIFT = frozenset({
    "Swift", "Foundation", "UIKit", "AppKit", "Combine", "CoreData",
    "CoreGraphics", "CoreLocation", "Dispatch", "Metal", "PlaygroundSupport",
    "SwiftUI", "XCTest",
})

STDLIB_MODULES_PHP = frozenset({
    "Core", "date", "ereg", "libxml", "openssl", "pcre", "sqlite3",
    "standard", "bcmath", "bz2", "calendar", "ctype", "curl", "dba",
    "dom", "enchant", "exif", "fileinfo", "filter", "ftp", "gd",
    "gettext", "gmp", "hash", "iconv", "imap", "interbase", "intl",
    "json", "ldap", "mbstring", "mcrypt", "mysqli", "mysqlnd", "odbc",
    "opcache", "pgsql", "posix", "pspell", "readline", "recode",
    "session", "shmop", "simplexml", "snmp", "soap", "sockets",
    "sodium", "solr", "spl", "sysvmsg", "sysvsem", "sysvshm",
    "tidy", "tokenizer", "wddx", "xml", "xmlreader", "xmlrpc",
    "xmlwriter", "xsl", "yaml", "zip",
})

STDLIB_MODULES_RUBY = frozenset({
    "abbrev", "base64", "benchmark", "bigdecimal", "cgi", "cmath",
    "csv", "date", "delegate", "did_you_mean", "drb", "english",
    "erb", "error_highlight", "etc", "fcntl", "fiddle", "fileutils",
    "find", "forwardable", "getoptlong", "io-console", "irb",
    "json", "logger", "mutex_m", "net-http", "net-pop", "net-smtp",
    "observer", "open-uri", "open3", "optparse", "ostruct", "pathname",
    "pp", "pstore", "psych", "racc", "rdoc", "readline", "reline",
    "resolv", "resolv-replace", "rinda", "ruby2_keywords", "securerandom",
    "set", "shellwords", "singleton", "stringio", "strscan", "syntax_suggest",
    "syslog", "tempfile", "time", "timeout", "tmpdir", "tsort", "un",
    "uri", "weakref", "webrick", "win32ole", "yaml", "zlib",
})

STDLIB_MODULES_BASH = frozenset({
    "awk", "basename", "cat", "chmod", "chown", "cp", "cron", "cut",
    "date", "dd", "df", "diff", "dirname", "echo", "env", "expr",
    "find", "grep", "gzip", "head", "hostname", "id", "ifconfig",
    "kill", "ln", "ls", "make", "mkdir", "mktemp", "mount", "mv",
    "nice", "nohup", "passwd", "paste", "patch", "printf", "ps",
    "pwd", "read", "rm", "rmdir", "sed", "seq", "set", "sh",
    "shutdown", "sleep", "sort", "ssh", "stat", "stty", "su",
    "sudo", "tail", "tar", "tee", "test", "time", "touch",
    "tr", "ulimit", "umask", "uname", "uniq", "unset", "uptime",
    "useradd", "userdel", "wc", "which", "xargs", "yes",
})

STDLIB_MODULES = {
    "python": STDLIB_MODULES_PYTHON,
    "javascript": STDLIB_MODULES_JAVASCRIPT,
    "typescript": STDLIB_MODULES_JAVASCRIPT,
    "go": STDLIB_MODULES_GO,
    "rust": STDLIB_MODULES_RUST,
    "c": frozenset(),
    "cpp": STDLIB_MODULES_CPP,
    "c_sharp": STDLIB_MODULES_CSHARP,
    "java": frozenset({
        "java.lang", "java.util", "java.io", "java.net", "java.nio",
        "java.math", "java.text", "java.time", "java.sql", "java.security",
        "javax.swing", "javax.servlet", "org.xml.sax", "org.w3c.dom",
    }),
    "kotlin": STDLIB_MODULES_KOTLIN,
    "swift": STDLIB_MODULES_SWIFT,
    "php": STDLIB_MODULES_PHP,
    "ruby": STDLIB_MODULES_RUBY,
    "bash": STDLIB_MODULES_BASH,
    "html": frozenset(),
    "css": frozenset(),
    "json": frozenset(),
    "yaml": frozenset(),
    "sql": frozenset({
        "information_schema", "pg_catalog", "pg_toast", "sys",
    }),
    "markdown": frozenset(),
}

SECRET_PATTERNS: dict[str, re.Pattern] = {
    "api_key": re.compile(
        r"""(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*['"]([^'"]{16,})['"]""",
        re.IGNORECASE,
    ),
    "token": re.compile(
        r"""(?:token|access[_-]?token|auth[_-]?token|bearer)\s*[:=]\s*['"]([^'"]{16,})['"]""",
        re.IGNORECASE,
    ),
    "password": re.compile(
        r"""(?:password|passwd|pwd|secret)\s*[:=]\s*['"]([^'"]{6,})['"]""",
        re.IGNORECASE,
    ),
    "private_key": re.compile(
        r"""-----BEGIN\s(?:RSA|DSA|EC|OPENSSH)?\s*PRIVATE KEY-----""",
        re.IGNORECASE,
    ),
    "aws_access_key": re.compile(r"""(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"""),
    "aws_secret_key": re.compile(
        r"""aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*['"]([^'"]{40})['"]""",
        re.IGNORECASE,
    ),
    "connection_string": re.compile(
        r"""(?:mongodb|postgres|mysql|redis|amqp|smtp|ftp|http|https):\/\/[^'"\s]{10,}""",
        re.IGNORECASE,
    ),
    "jwt_token": re.compile(
        r"""eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+""",
    ),
    "slack_token": re.compile(r"""xox[bpsar]-[0-9]{10,}-[0-9a-zA-Z-]+"""),
    "github_token": re.compile(r"""gh[ps]_[A-Za-z0-9_]{36,}"""),
    "generic_secret": re.compile(
        r"""(?:secret|credential|key)\s*[:=]\s*['"]([^'"]{8,})['"]""",
        re.IGNORECASE,
    ),
}


class ParserEngine:
    _GRAMMARS: dict[str, str] = {
        "python": "tree_sitter_python",
        "typescript": "tree_sitter_typescript",
        "javascript": "tree_sitter_javascript",
        "java": "tree_sitter_java",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "c_sharp": "tree_sitter_c_sharp",
        "go": "tree_sitter_go",
        "rust": "tree_sitter_rust",
        "php": "tree_sitter_php",
        "ruby": "tree_sitter_ruby",
        "kotlin": "tree_sitter_kotlin",
        "swift": "tree_sitter_swift",
        "html": "tree_sitter_html",
        "css": "tree_sitter_css",
        "json": "tree_sitter_json",
        "yaml": "tree_sitter_yaml",
        "bash": "tree_sitter_bash",
    }

    _EXTENSION_MAP: dict[str, str] = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cs": "c_sharp",
        ".go": "go",
        ".rs": "rust",
        ".php": "php",
        ".rb": "ruby",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".swift": "swift",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".sh": "bash",
        ".zsh": "bash",
        ".sql": "sql",
        ".md": "markdown",
    }

    def __init__(self) -> None:
        self._parser_cache: dict[str, Any] = {}
        self._grammar_cache: dict[str, Any] = {}
        self._ts_available = HAS_TREE_SITTER

        if self._ts_available:
            try:
                if hasattr(tree_sitter, "Language"):
                    pass
                logger.info("Tree-sitter parser engine initialized (tree-sitter available)")
            except Exception as exc:
                logger.warning("Tree-sitter detected but initialization issue: %s", exc)
                self._ts_available = False
        else:
            logger.info("Tree-sitter not available, using regex fallback engine")

    def detect_language(self, file_path: str) -> str:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        return self._EXTENSION_MAP.get(ext, "")

    def is_supported(self, file_path: str) -> bool:
        lang = self.detect_language(file_path)
        if not lang:
            return False
        if lang in self._GRAMMARS:
            return True
        return lang != ""

    def get_supported_extensions(self) -> list[str]:
        return sorted(self._EXTENSION_MAP.keys())

    def _get_parser(self, language: str) -> Any:
        if language in self._parser_cache:
            return self._parser_cache[language]

        if not self._ts_available:
            return None

        grammar_module_name = self._GRAMMARS.get(language)
        if not grammar_module_name:
            return None

        try:
            if hasattr(tree_sitter, "Language") and hasattr(tree_sitter, "Parser"):
                grammar_module = __import__(grammar_module_name)
                lang_class_name = grammar_module_name.replace("tree_sitter_", "")
                lang_function_name = lang_class_name + "()"
                if hasattr(grammar_module, lang_class_name):
                    lang_obj = getattr(grammar_module, lang_class_name)()
                elif hasattr(grammar_module, lang_function_name):
                    lang_obj = getattr(grammar_module, lang_function_name)()
                else:
                    attrs = [a for a in dir(grammar_module) if not a.startswith("_")]
                    if attrs:
                        lang_obj = getattr(grammar_module, attrs[0])()
                    else:
                        return None

                if isinstance(lang_obj, str):
                    lang_obj = tree_sitter.Language(lang_obj)

                parser = tree_sitter.Parser(lang_obj)
                self._parser_cache[language] = parser
                self._grammar_cache[language] = lang_obj
                return parser

            elif hasattr(tree_sitter_languages, "get_parser"):
                parser = tree_sitter_languages.get_parser(language)
                self._parser_cache[language] = parser
                return parser

        except Exception as exc:
            logger.debug("Failed to create tree-sitter parser for %s: %s", language, exc)
            self._parser_cache[language] = None
            return None

        return None

    def parse_file(
        self,
        file_path: str,
        content: str,
        language: str | None = None,
    ) -> ParseResult:
        start_time = time.perf_counter()

        if language is None:
            language = self.detect_language(file_path)

        if not language:
            return ParseResult(
                file_path=file_path,
                language="unknown",
                error=f"Unsupported file type: {file_path}",
                parse_time_ms=(time.perf_counter() - start_time) * 1000,
            )

        if language not in self._GRAMMARS and language not in (
            "sql", "markdown",
        ):
            return ParseResult(
                file_path=file_path,
                language=language,
                error=f"Unsupported language: {language}",
                parse_time_ms=(time.perf_counter() - start_time) * 1000,
            )

        tree_hash = self._compute_tree_hash(content)
        total_lines, comment_lines, blank_lines = self._count_lines(content)

        secrets = self._detect_secrets(content)
        cleaned_content = self._redact_secrets(content) if secrets else content

        parser = self._get_parser(language)

        if parser is not None and self._ts_available:
            try:
                result = self._parse_with_tree_sitter(cleaned_content, language, file_path)
                result.tree_hash = tree_hash
                result.line_count = total_lines
                result.comment_lines = comment_lines
                result.blank_lines = blank_lines
                result.parse_time_ms = (time.perf_counter() - start_time) * 1000
                return result
            except Exception as exc:
                logger.warning(
                    "Tree-sitter parse failed for %s (%s), falling back to regex: %s",
                    file_path,
                    language,
                    exc,
                )

        result = self._regex_fallback(cleaned_content, language, file_path)
        result.tree_hash = tree_hash
        result.line_count = total_lines
        result.comment_lines = comment_lines
        result.blank_lines = blank_lines
        result.parse_time_ms = (time.perf_counter() - start_time) * 1000
        return result

    def _parse_with_tree_sitter(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> ParseResult:
        parser = self._get_parser(language)
        if parser is None:
            return ParseResult(
                file_path=file_path,
                language=language,
                error="No parser available",
            )

        content_bytes = content.encode("utf-8", errors="replace")
        tree = parser.parse(content_bytes)

        ast = self._walk_tree(tree.root_node)
        symbols = self.extract_symbols(content, language, file_path)
        imports = self.extract_imports(content, language)
        calls = self.extract_calls(content, language, symbols)

        return ParseResult(
            file_path=file_path,
            language=language,
            symbols=symbols,
            imports=imports,
            calls=calls,
        )

    def _walk_tree(self, node: Any, depth: int = 0, max_depth: int = 50) -> dict:
        if depth > max_depth:
            return {"type": "max_depth_reached", "children": []}

        result: dict[str, Any] = {
            "type": getattr(node, "type", "unknown"),
            "start_point": {
                "row": getattr(node, "start_point", (0, 0))[0],
                "column": getattr(node, "start_point", (0, 0))[1],
            },
            "end_point": {
                "row": getattr(node, "end_point", (0, 0))[0],
                "column": getattr(node, "end_point", (0, 0))[1],
            },
            "text": "",
            "children": [],
        }

        try:
            if hasattr(node, "text") and node.text is not None:
                text_bytes = node.text
                if isinstance(text_bytes, bytes):
                    result["text"] = text_bytes.decode("utf-8", errors="replace")[:500]
                else:
                    result["text"] = str(text_bytes)[:500]
        except Exception:
            pass

        if hasattr(node, "children") and node.children:
            for child in node.children:
                result["children"].append(self._walk_tree(child, depth + 1, max_depth))

        return result

    def extract_symbols(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> list[SymbolInfo]:
        if not self._ts_available:
            return self._extract_symbols_regex(content, language, file_path)

        parser = self._get_parser(language)
        if parser is None:
            return self._extract_symbols_regex(content, language, file_path)

        try:
            content_bytes = content.encode("utf-8", errors="replace")
            tree = parser.parse(content_bytes)
            return self._extract_symbols_from_tree(tree, language, file_path)
        except Exception as exc:
            logger.debug("Tree-sitter symbol extraction failed for %s: %s", language, exc)
            return self._extract_symbols_regex(content, language, file_path)

    def _extract_symbols_from_tree(
        self,
        tree: Any,
        language: str,
        file_path: str,
    ) -> list[SymbolInfo]:
        symbols: list[SymbolInfo] = []
        root = tree.root_node

        type_map = self._get_node_type_map(language)
        method_types = {
            "function_definition",
            "function_item",
            "method_definition",
            "method_declaration",
            "constructor_definition",
        }
        class_types = {
            "class_definition",
            "class_declaration",
            "class_specifier",
            "struct_declaration",
            "struct_item",
            "interface_declaration",
            "interface_item",
            "enum_declaration",
            "enum_item",
        }

        def _walk(node: Any, parent_name: str = "", parent_type: str = "") -> None:
            node_type = getattr(node, "type", "")

            if node_type in class_types:
                symbol_type = type_map.get(node_type, SymbolType.CLASS)
                name = self._extract_node_name(node)
                qualified = f"{parent_name}.{name}" if parent_name else name
                visibility = self._extract_visibility(node, language)
                docstring = self._extract_docstring(node, language)
                decorators = self._extract_decorators(node, language)
                is_abstract = self._is_abstract(node, language)

                sig_lines: list[str] = []
                if decorators:
                    sig_lines.extend(decorators)
                if is_abstract:
                    sig_lines.append("abstract")
                if visibility and visibility != "public":
                    sig_lines.append(visibility)
                if node_type in {"class_definition", "class_declaration", "class_specifier"}:
                    sig_lines.append("class")
                elif node_type in {"struct_declaration", "struct_item"}:
                    sig_lines.append("struct")
                elif node_type in {"interface_declaration", "interface_item"}:
                    sig_lines.append("interface")
                elif node_type in {"enum_declaration", "enum_item"}:
                    sig_lines.append("enum")
                sig_lines.append(name)
                signature = " ".join(sig_lines)

                sym = SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    symbol_type=symbol_type,
                    start_line=getattr(node, "start_point", (0, 0))[0] + 1,
                    end_line=getattr(node, "end_point", (0, 0))[0] + 1,
                    signature=signature,
                    docstring=docstring,
                    visibility=visibility,
                    is_abstract=is_abstract,
                    decorators=decorators,
                    parent_name=parent_name,
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)

                for child in (node.children if hasattr(node, "children") and node.children else []):
                    _walk(child, name, node_type)
                return

            if node_type in method_types:
                symbol_type = type_map.get(node_type, SymbolType.FUNCTION)
                name = self._extract_node_name(node)
                qualified = f"{parent_name}.{name}" if parent_name else name
                visibility = self._extract_visibility(node, language)
                docstring = self._extract_docstring(node, language)
                decorators = self._extract_decorators(node, language)
                params = self._extract_parameters(node, language)
                ret_type = self._extract_return_type(node, language)
                is_async = self._is_async(node, language)
                is_static = self._is_static(node, language)

                sig_parts: list[str] = []
                if decorators:
                    sig_parts.extend(decorators)
                if is_async:
                    sig_parts.append("async")
                if visibility and visibility != "public":
                    sig_parts.append(visibility)
                if is_static:
                    sig_parts.append("static")
                sig_parts.append(name)
                if params:
                    sig_parts.append(f"({', '.join(params)})")
                if ret_type:
                    sig_parts.append(f"-> {ret_type}")
                signature = " ".join(sig_parts)

                final_type = symbol_type
                if symbol_type == SymbolType.FUNCTION and parent_type in class_types:
                    final_type = SymbolType.METHOD

                sym = SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    symbol_type=final_type,
                    start_line=getattr(node, "start_point", (0, 0))[0] + 1,
                    end_line=getattr(node, "end_point", (0, 0))[0] + 1,
                    signature=signature,
                    docstring=docstring,
                    visibility=visibility,
                    is_async=is_async,
                    is_static=is_static,
                    decorators=decorators,
                    parameters=params,
                    return_type=ret_type,
                    parent_name=parent_name,
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)

                for child in (node.children if hasattr(node, "children") and node.children else []):
                    _walk(child, name if final_type == SymbolType.METHOD else parent_name, node_type)
                return

            for child in (node.children if hasattr(node, "children") and node.children else []):
                _walk(child, parent_name, node_type)

        _walk(root)

        file_sym = SymbolInfo(
            name=os.path.basename(file_path),
            qualified_name=file_path,
            symbol_type=SymbolType.FILE,
            start_line=1,
            end_line=getattr(root, "end_point", (0,))[0] + 1,
            language=language,
            file_path=file_path,
        )
        symbols.insert(0, file_sym)

        return symbols

    def _get_node_type_map(self, language: str) -> dict[str, SymbolType]:
        common = {
            "function_definition": SymbolType.FUNCTION,
            "function_item": SymbolType.FUNCTION,
            "function_declaration": SymbolType.FUNCTION,
            "method_definition": SymbolType.METHOD,
            "method_declaration": SymbolType.METHOD,
            "constructor_definition": SymbolType.METHOD,
            "class_definition": SymbolType.CLASS,
            "class_declaration": SymbolType.CLASS,
            "class_specifier": SymbolType.CLASS,
            "struct_declaration": SymbolType.STRUCT,
            "struct_item": SymbolType.STRUCT,
            "interface_declaration": SymbolType.INTERFACE,
            "interface_item": SymbolType.INTERFACE,
            "enum_declaration": SymbolType.ENUM,
            "enum_item": SymbolType.ENUM,
            "type_alias_declaration": SymbolType.TYPE,
            "type_item": SymbolType.TYPE,
            "type_specifier": SymbolType.TYPE,
            "arrow_function": SymbolType.FUNCTION,
            "function_expression": SymbolType.FUNCTION,
            "function": SymbolType.FUNCTION,
            "method": SymbolType.METHOD,
            "class": SymbolType.CLASS,
            "interface": SymbolType.INTERFACE,
            "struct": SymbolType.STRUCT,
            "enum": SymbolType.ENUM,
            "property_definition": SymbolType.PROPERTY,
            "field_definition": SymbolType.PROPERTY,
            "field_declaration": SymbolType.PROPERTY,
            "variable_declaration": SymbolType.VARIABLE,
            "let_declaration": SymbolType.VARIABLE,
            "const_declaration": SymbolType.VARIABLE,
            "lexical_declaration": SymbolType.VARIABLE,
            "var_declaration": SymbolType.VARIABLE,
            "import_statement": SymbolType.IMPORT,
            "import_declaration": SymbolType.IMPORT,
            "import_from_statement": SymbolType.IMPORT,
            "module": SymbolType.MODULE,
            "namespace_declaration": SymbolType.NAMESPACE,
        }
        return common

    def _extract_node_name(self, node: Any) -> str:
        if hasattr(node, "child_by_field_name"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                try:
                    text = name_node.text
                    if isinstance(text, bytes):
                        return text.decode("utf-8", errors="replace")
                    return str(text)
                except Exception:
                    pass

        for child in (node.children if hasattr(node, "children") and node.children else []):
            child_type = getattr(child, "type", "")
            if child_type in ("identifier", "name", "type_identifier", "field_name",
                              "property_identifier", "type_identifier"):
                try:
                    text = child.text
                    if isinstance(text, bytes):
                        return text.decode("utf-8", errors="replace")
                    return str(text)
                except Exception:
                    pass

        return "<anonymous>"

    def _extract_visibility(self, node: Any, language: str) -> str:
        for child in (node.children if hasattr(node, "children") and node.children else []):
            child_type = getattr(child, "type", "")
            if child_type in ("public", "private", "protected", "internal"):
                return child_type

            if child_type == "modifiers":
                for mod in (child.children if hasattr(child, "children") and child.children else []):
                    mod_type = getattr(mod, "type", "")
                    if mod_type in ("public", "private", "protected", "internal"):
                        return mod_type

            if child_type == "visibility_modifier" or child_type == "access_modifier":
                try:
                    text = child.text
                    if isinstance(text, bytes):
                        return text.decode("utf-8", errors="replace")
                    return str(text)
                except Exception:
                    pass

        if language in ("python",):
            return "public"
        return "public"

    def _extract_docstring(self, node: Any, language: str) -> str:
        for child in (node.children if hasattr(node, "children") and node.children else []):
            child_type = getattr(child, "type", "")
            if child_type in ("string", "expression_statement", "comment",
                              "docstring", "block_comment", "documentation_comment",
                              "line_comment"):
                try:
                    text = child.text
                    if isinstance(text, bytes):
                        text = text.decode("utf-8", errors="replace")
                    text = str(text).strip()
                    if text.startswith('"""') or text.startswith("'''"):
                        return text[3:-3].strip()
                    if text.startswith('r"""') or text.startswith("r'''"):
                        return text[4:-3].strip()
                    if text.startswith("//"):
                        return text[2:].strip()
                    if text.startswith("/*"):
                        inner = text[2:]
                        if inner.endswith("*/"):
                            inner = inner[:-2]
                        return inner.strip()
                    if text.startswith("#"):
                        return text[1:].strip()
                    if text.startswith("///") or text.startswith("//!"):
                        return text[3:].strip()
                    return text
                except Exception:
                    pass
            if child_type == "block":
                for subchild in (child.children if hasattr(child, "children") and child.children else []):
                    sub_type = getattr(subchild, "type", "")
                    if sub_type in ("string", "comment", "docstring"):
                        try:
                            text = subchild.text
                            if isinstance(text, bytes):
                                text = text.decode("utf-8", errors="replace")
                            return str(text).strip()
                        except Exception:
                            pass
        return ""

    def _extract_decorators(self, node: Any, language: str) -> list[str]:
        decorators: list[str] = []
        for child in (node.children if hasattr(node, "children") and node.children else []):
            child_type = getattr(child, "type", "")
            if child_type in ("decorator", "decorated_definition", "attribute",
                              "annotation", "marker_annotation"):
                try:
                    text = child.text
                    if isinstance(text, bytes):
                        text = text.decode("utf-8", errors="replace")
                    decorators.append(str(text).strip())
                except Exception:
                    pass
        return decorators

    def _extract_parameters(self, node: Any, language: str) -> list[str]:
        params: list[str] = []
        param_list = node.child_by_field_name("parameters") if hasattr(node, "child_by_field_name") else None

        if param_list is None:
            for child in (node.children if hasattr(node, "children") and node.children else []):
                child_type = getattr(child, "type", "")
                if child_type in ("parameters", "formal_parameters", "parameter_list",
                                  "argument_list"):
                    param_list = child
                    break

        if param_list is None:
            return params

        if hasattr(param_list, "children") and param_list.children:
            for param_child in param_list.children:
                child_type = getattr(param_child, "type", "")
                if child_type in ("parameter", "formal_parameter", "identifier",
                                  "default_parameter", "typed_parameter",
                                  "keyword_argument", "optional_parameter",
                                  "splat_parameter", "double_splat_parameter",
                                  "variadic_parameter", "rest_parameter",
                                  "required_parameter"):
                    try:
                        text = param_child.text
                        if isinstance(text, bytes):
                            text = text.decode("utf-8", errors="replace")
                        params.append(str(text).strip())
                    except Exception:
                        pass

        return params

    def _extract_return_type(self, node: Any, language: str) -> str:
        for child in (node.children if hasattr(node, "children") and node.children else []):
            child_type = getattr(child, "type", "")
            if child_type in ("return_type", "type_annotation", "type",
                              "function_return_type"):
                try:
                    text = child.text
                    if isinstance(text, bytes):
                        text = text.decode("utf-8", errors="replace")
                    return str(text).strip().lstrip("->").lstrip(":").strip()
                except Exception:
                    pass

        if hasattr(node, "child_by_field_name"):
            ret_node = node.child_by_field_name("return_type")
            if ret_node is not None:
                try:
                    text = ret_node.text
                    if isinstance(text, bytes):
                        text = text.decode("utf-8", errors="replace")
                    return str(text).strip()
                except Exception:
                    pass

        return ""

    def _is_async(self, node: Any, language: str) -> bool:
        for child in (node.children if hasattr(node, "children") and node.children else []):
            if getattr(child, "type", "") == "async":
                return True
            if getattr(child, "type", "") == "async_function_signature":
                return True
            if getattr(child, "type", "") == "modifiers":
                for mod in (child.children if hasattr(child, "children") and child.children else []):
                    if getattr(mod, "type", "") == "async":
                        return True
        return False

    def _is_static(self, node: Any, language: str) -> bool:
        for child in (node.children if hasattr(node, "children") and node.children else []):
            child_type = getattr(child, "type", "")
            if child_type == "static":
                return True
            if child_type == "modifiers":
                for mod in (child.children if hasattr(child, "children") and child.children else []):
                    if getattr(mod, "type", "") == "static":
                        return True
        return False

    def _is_abstract(self, node: Any, language: str) -> bool:
        for child in (node.children if hasattr(node, "children") and node.children else []):
            child_type = getattr(child, "type", "")
            if child_type == "abstract":
                return True
            if child_type == "modifiers":
                for mod in (child.children if hasattr(child, "children") and child.children else []):
                    if getattr(mod, "type", "") == "abstract":
                        return True
        return False

    def extract_imports(self, content: str, language: str) -> list[ImportInfo]:
        if language == "python":
            return self._extract_imports_python(content)
        elif language in ("javascript", "typescript"):
            return self._extract_imports_javascript(content)
        elif language == "go":
            return self._extract_imports_go(content)
        elif language == "java":
            return self._extract_imports_java(content)
        elif language == "rust":
            return self._extract_imports_rust(content)
        elif language == "cpp":
            return self._extract_imports_cpp(content)
        elif language == "c":
            return self._extract_imports_c(content)
        elif language == "c_sharp":
            return self._extract_imports_csharp(content)
        elif language == "kotlin":
            return self._extract_imports_kotlin(content)
        elif language == "swift":
            return self._extract_imports_swift(content)
        elif language == "php":
            return self._extract_imports_php(content)
        elif language == "ruby":
            return self._extract_imports_ruby(content)
        else:
            return self._extract_imports_generic(content, language)

    def _extract_imports_python(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()

            abs_match = re.match(r"^import\s+(.+)$", stripped)
            if abs_match:
                names = abs_match.group(1).split(",")
                for name in names:
                    name = name.strip().rstrip(";")
                    is_ext = self._is_external_import(name.split(".")[0], "python")
                    is_std = name.split(".")[0] in STDLIB_MODULES_PYTHON
                    imports.append(ImportInfo(
                        name=name,
                        import_type="ABSOLUTE",
                        module_path=name,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                continue

            from_match = re.match(
                r"^from\s+([\w.]+)\s+import\s+(.+)$", stripped
            )
            if from_match:
                module = from_match.group(1).strip()
                raw_names = from_match.group(2).strip().rstrip(";")
                is_ext = self._is_external_import(module.split(".")[0], "python")
                is_std = module.split(".")[0] in STDLIB_MODULES_PYTHON

                if raw_names == "*":
                    imports.append(ImportInfo(
                        name=module,
                        import_type="WILDCARD",
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                else:
                    for alias_part in raw_names.split(","):
                        alias_part = alias_part.strip()
                        if " as " in alias_part:
                            parts = alias_part.split(" as ")
                            imported_name = parts[0].strip()
                            alias = parts[1].strip()
                        else:
                            imported_name = alias_part
                            alias = ""
                        imports.append(ImportInfo(
                            name=imported_name,
                            import_type="FROM",
                            alias=alias,
                            module_path=module,
                            is_external=is_ext,
                            is_stdlib=is_std,
                            line=i,
                        ))
                continue

            dyn_match = re.match(
                r"""^\w+\s*=\s*__import__\s*\(\s*['"]([^'"]+)['"]""", stripped
            )
            if dyn_match:
                module = dyn_match.group(1)
                is_ext = self._is_external_import(module.split(".")[0], "python")
                is_std = module.split(".")[0] in STDLIB_MODULES_PYTHON
                imports.append(ImportInfo(
                    name=module,
                    import_type="DYNAMIC",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))

        return imports

    def _extract_imports_javascript(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()

            es_match = re.match(
                r"""^import\s+(?:([\w*\s{},]+)\s+from\s+)?['"]([^'"]+)['"]""", stripped
            )
            if es_match:
                names = es_match.group(1)
                module = es_match.group(2)
                is_ext = self._is_external_import(module, "javascript")
                is_std = module in STDLIB_MODULES_JAVASCRIPT

                if names is None:
                    imports.append(ImportInfo(
                        name=module,
                        import_type="ABSOLUTE",
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                else:
                    names = names.strip()
                    if names == "*":
                        imports.append(ImportInfo(
                            name=module,
                            import_type="WILDCARD",
                            module_path=module,
                            is_external=is_ext,
                            is_stdlib=is_std,
                            line=i,
                        ))
                    else:
                        for alias_part in re.split(r",\s*", names):
                            alias_part = alias_part.strip()
                            if " as " in alias_part:
                                parts = alias_part.split(" as ")
                                imported_name = parts[0].strip()
                                alias = parts[1].strip()
                            else:
                                imported_name = alias_part
                                alias = ""
                            imports.append(ImportInfo(
                                name=imported_name,
                                import_type="FROM",
                                alias=alias,
                                module_path=module,
                                is_external=is_ext,
                                is_stdlib=is_std,
                                line=i,
                            ))
                continue

            req_match = re.match(
                r"""(?:const|let|var)\s+(\w+)\s*=\s*require\s*\(\s*['"]([^'"]+)['"]""",
                stripped,
            )
            if req_match:
                alias = req_match.group(1)
                module = req_match.group(2)
                is_ext = self._is_external_import(module, "javascript")
                is_std = module in STDLIB_MODULES_JAVASCRIPT
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    alias=alias,
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
                continue

            req_match2 = re.match(
                r"""require\s*\(\s*['"]([^'"]+)['"]""", stripped
            )
            if req_match2:
                module = req_match2.group(1)
                is_ext = self._is_external_import(module, "javascript")
                is_std = module in STDLIB_MODULES_JAVASCRIPT
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))

        return imports

    def _extract_imports_go(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        single_re = re.compile(r'^import\s+"([^"]+)"')
        group_re = re.compile(r'^import\s*\($')
        in_group = False

        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()

            if in_group:
                if stripped == ")":
                    in_group = False
                    continue
                imp_match = re.match(r'(?:(\w+)\s+)?\"([^\"]+)\"', stripped)
                if imp_match:
                    alias = imp_match.group(1) or ""
                    module = imp_match.group(2)
                    is_ext = self._is_external_import(module, "go")
                    is_std = module in STDLIB_MODULES_GO
                    imports.append(ImportInfo(
                        name=module,
                        import_type="ABSOLUTE",
                        alias=alias,
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                continue

            m = single_re.match(stripped)
            if m:
                module = m.group(1)
                is_ext = self._is_external_import(module, "go")
                is_std = module in STDLIB_MODULES_GO
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
                continue

            if group_re.match(stripped):
                in_group = True

        return imports

    def _extract_imports_java(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            m = re.match(r"^import\s+(static\s+)?([\w.]+\*?)\s*;", stripped)
            if m:
                is_static = bool(m.group(1))
                module = m.group(2)
                is_ext = self._is_external_import(module.split(".")[0], "java")
                is_std = any(module.startswith(s) for s in STDLIB_MODULES_JAVASCRIPT) or module.split(".")[0] in ("java", "javax", "org", "com")
                imp_type = "ABSOLUTE"
                if module.endswith(".*"):
                    imp_type = "WILDCARD"
                    module = module[:-2]
                imports.append(ImportInfo(
                    name=module,
                    import_type=imp_type,
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                    metadata={"is_static": is_static},
                ))
        return imports

    def _extract_imports_rust(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            m = re.match(r"^use\s+(.+)\s*;", stripped)
            if m:
                module = m.group(1).strip()
                parts = module.split("::")
                top = parts[0]
                is_ext = self._is_external_import(top, "rust")
                is_std = top in STDLIB_MODULES_RUST
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
        return imports

    def _extract_imports_cpp(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            inc_match = re.match(r"""^#\s*include\s+[<"]([^>"]+)[>"]""", stripped)
            if inc_match:
                module = inc_match.group(1)
                is_system = stripped.endswith(">")
                is_ext = not is_system
                is_std = module.split("/")[0].split(".")[0] in STDLIB_MODULES_CPP
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
        return imports

    def _extract_imports_c(self, content: str) -> list[ImportInfo]:
        return self._extract_imports_cpp(content)

    def _extract_imports_csharp(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            m = re.match(r"^using\s+(?:static\s+)?([\w.]+)\s*;", stripped)
            if m:
                module = m.group(1)
                is_ext = self._is_external_import(module.split(".")[0], "c_sharp")
                is_std = any(module.startswith(s) for s in STDLIB_MODULES_CSHARP)
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
        return imports

    def _extract_imports_kotlin(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            m = re.match(r"^import\s+([\w.]+)", stripped)
            if m:
                module = m.group(1)
                is_ext = self._is_external_import(module.split(".")[0], "kotlin")
                is_std = any(module.startswith(s) for s in STDLIB_MODULES_KOTLIN)
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
        return imports

    def _extract_imports_swift(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            m = re.match(r"^import\s+([\w]+)", stripped)
            if m:
                module = m.group(1)
                is_ext = self._is_external_import(module, "swift")
                is_std = module in STDLIB_MODULES_SWIFT
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
        return imports

    def _extract_imports_php(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            ns_match = re.match(r"^namespace\s+([\w\\]+)\s*;", stripped)
            if ns_match:
                imports.append(ImportInfo(
                    name=ns_match.group(1),
                    import_type="ABSOLUTE",
                    module_path=ns_match.group(1),
                    is_external=False,
                    is_stdlib=False,
                    line=i,
                ))
                continue

            use_match = re.match(r"^use\s+([\w\\]+(?:\s+as\s+\w+)?)\s*;", stripped)
            if use_match:
                parts = use_match.group(1).split(" as ")
                module = parts[0].strip()
                alias = parts[1].strip() if len(parts) > 1 else ""
                top = module.split("\\")[0]
                is_ext = self._is_external_import(top, "php")
                is_std = top in STDLIB_MODULES_PHP
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    alias=alias,
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))
        return imports

    def _extract_imports_ruby(self, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            for pattern, imp_type in [
                (r"""^require\s+['"]([^'"]+)['"]""", "ABSOLUTE"),
                (r"""^require_relative\s+['"]([^'"]+)['"]""", "RELATIVE"),
                (r"""^load\s+['"]([^'"]+)['"]""", "ABSOLUTE"),
                (r"""^autoload\s+(\w+)\s*,\s*['"]([^'"]+)['"]""", "ABSOLUTE"),
            ]:
                m = re.match(pattern, stripped)
                if m:
                    if pattern == r"""^autoload\s+(\w+)\s*,\s*['"]([^'"]+)['"]""":
                        alias_name = m.group(1)
                        module = m.group(2)
                    else:
                        alias_name = ""
                        module = m.group(1)
                    top = module.split("/")[0]
                    is_ext = self._is_external_import(top, "ruby")
                    is_std = top in STDLIB_MODULES_RUBY
                    imports.append(ImportInfo(
                        name=module,
                        import_type=imp_type,
                        alias=alias_name,
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                    break
        return imports

    def _extract_imports_generic(self, content: str, language: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        patterns = [
            (r"""^import\s+(?:[\w*\s{},]+\s+from\s+)?['"]([^'"]+)['"]""", "ABSOLUTE"),
            (r"""^from\s+([\w.]+)\s+import""", "ABSOLUTE"),
            (r"""^require\s*\(\s*['"]([^'"]+)['"]""", "ABSOLUTE"),
            (r"""^require\s+['"]([^'"]+)['"]""", "ABSOLUTE"),
            (r"""^use\s+([\w.]+)""", "ABSOLUTE"),
            (r"""^include\s+[<"]([^>"]+)[>"]""", "ABSOLUTE"),
            (r"""^#include\s+[<"]([^>"]+)[>"]""", "ABSOLUTE"),
        ]

        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            for pattern, imp_type in patterns:
                m = re.match(pattern, stripped)
                if m:
                    module = m.group(1)
                    top = module.split(".")[0].split("/")[0].split("\\")[0]
                    is_ext = self._is_external_import(top, language)
                    is_std = top in STDLIB_MODULES.get(language, frozenset())
                    imports.append(ImportInfo(
                        name=module,
                        import_type=imp_type,
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                    break

        return imports

    def _is_external_import(self, top_module: str, language: str) -> bool:
        if not top_module:
            return False
        std = STDLIB_MODULES.get(language, frozenset())
        if top_module in std:
            return False
        if language == "python" and top_module.startswith("_"):
            return False
        if language in ("javascript", "typescript") and top_module.startswith("."):
            return False
        if language == "go" and not "." in top_module:
            return False
        return True

    def extract_calls(
        self,
        content: str,
        language: str,
        symbols: list[SymbolInfo] | None = None,
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        symbol_names: set[str] = set()
        if symbols:
            symbol_names = {s.name for s in symbols if s.symbol_type in (
                SymbolType.FUNCTION, SymbolType.METHOD, SymbolType.CLASS,
            )}

        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()

            if language == "python":
                calls.extend(self._extract_calls_python_line(stripped, i, symbol_names))
            elif language in ("javascript", "typescript"):
                calls.extend(self._extract_calls_js_line(stripped, i, symbol_names))
            elif language == "go":
                calls.extend(self._extract_calls_go_line(stripped, i, symbol_names))
            elif language in ("java", "c_sharp", "kotlin"):
                calls.extend(self._extract_calls_java_like_line(stripped, i, symbol_names))
            elif language in ("c", "cpp"):
                calls.extend(self._extract_calls_c_line(stripped, i, symbol_names))
            elif language == "rust":
                calls.extend(self._extract_calls_rust_line(stripped, i, symbol_names))
            elif language == "ruby":
                calls.extend(self._extract_calls_ruby_line(stripped, i, symbol_names))
            elif language == "php":
                calls.extend(self._extract_calls_php_line(stripped, i, symbol_names))
            else:
                calls.extend(self._extract_calls_generic_line(stripped, i, symbol_names))

        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if language == "python" and stripped.startswith("@"):
                dec_match = re.match(r"^@(\w+[\w.]*)", stripped)
                if dec_match:
                    callee = dec_match.group(1)
                    resolved = callee in symbol_names
                    calls.append(CallInfo(
                        caller_name="<module>",
                        callee_name=callee,
                        call_line=i,
                        call_type="DECORATOR",
                        resolved=resolved,
                        confidence=0.9 if resolved else 0.3,
                    ))

        return calls

    def _extract_calls_python_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:\.\w+)*)\s*\(")
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            if callee in ("if", "for", "while", "with", "as", "in", "is", "not",
                          "and", "or", "def", "class", "return", "yield", "import",
                          "from", "print", "self", "cls", "super", "type", "len",
                          "range", "enumerate", "zip", "map", "filter", "set",
                          "list", "dict", "tuple", "int", "float", "str", "bool",
                          "isinstance", "issubclass", "hasattr", "getattr", "setattr",
                          "delattr", "vars", "dir", "globals", "locals", "exec",
                          "eval", "compile", "open", "input", "repr", "id", "hash",
                          "callable", "chr", "ord", "hex", "oct", "bin", "abs",
                          "all", "any", "pow", "round", "sum", "min", "max",
                          "sorted", "reversed", "next", "iter", "super", "object",
                          "Exception", "ValueError", "TypeError", "KeyError",
                          "IndexError", "AttributeError", "RuntimeError",
                          "StopIteration", "OSError", "IOError", "FileNotFoundError",
                          "json", "os", "sys", "re", "logging", "time", "datetime",
                          "collections", "itertools", "functools", "pathlib",
                          "typing", "dataclasses", "enum", "abc", "copy", "pprint",
                          "textwrap"):
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "." in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_js_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:\.\w+)*)\s*\(")
        skip_words = {
            "if", "for", "while", "switch", "catch", "function", "class",
            "return", "new", "typeof", "instanceof", "throw", "async",
            "await", "yield", "import", "export", "from", "require",
            "console", "window", "document", "Math", "JSON", "Object",
            "Array", "String", "Number", "Boolean", "RegExp", "Date",
            "Promise", "Map", "Set", "WeakMap", "WeakSet", "Symbol",
            "Error", "TypeError", "RangeError", "SyntaxError",
            "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURI",
            "decodeURI", "setTimeout", "setInterval", "clearTimeout",
            "clearInterval", "fetch", "alert", "confirm", "prompt",
            "process", "Buffer", "global", "module", "exports",
        }
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            base = callee.split(".")[0]
            if base in skip_words:
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "." in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_go_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:\.\w+)*)\s*\(")
        skip_words = {
            "if", "for", "switch", "select", "case", "func", "return",
            "defer", "go", "chan", "make", "new", "len", "cap", "append",
            "copy", "delete", "close", "complex", "real", "imag",
            "panic", "recover", "print", "println", "error",
        }
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            base = callee.split(".")[0]
            if base in skip_words:
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "." in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_java_like_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:\.\w+)*)\s*\(")
        skip_words = {
            "if", "for", "while", "switch", "catch", "return", "new",
            "throw", "super", "this", "class", "interface", "enum",
            "public", "private", "protected", "static", "final",
            "abstract", "synchronized", "volatile", "transient",
            "System", "String", "Integer", "Boolean", "Object", "Math",
            "Collections", "Arrays", "List", "Map", "Set", "ArrayList",
            "HashMap", "HashSet", "println", "printf", "print",
        }
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            base = callee.split(".")[0]
            if base in skip_words:
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "." in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_c_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:\.\w+)*(?:->\w+)*)\s*\(")
        skip_words = {
            "if", "for", "while", "switch", "return", "sizeof", "typeof",
            "define", "include", "ifdef", "ifndef", "endif", "pragma",
            "printf", "fprintf", "sprintf", "snprintf", "scanf",
            "malloc", "calloc", "realloc", "free", "memcpy", "memset",
            "strlen", "strcpy", "strncpy", "strcmp", "strncmp", "strcat",
            "strncat", "atoi", "atof", "atol", "strtol", "strtod",
            "fopen", "fclose", "fread", "fwrite", "fgets", "fputs",
            "cout", "cin", "cerr", "endl", "std",
        }
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            base = callee.split(".")[0].split("->")[0]
            if base in skip_words:
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "." in callee or "->" in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_rust_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:::\w+)*(?:\.\w+)*)\s*\(")
        skip_words = {
            "if", "for", "while", "loop", "match", "return", "fn", "let",
            "mut", "pub", "use", "mod", "struct", "enum", "trait", "impl",
            "type", "where", "self", "Self", "super", "crate", "as",
            "println", "print", "eprintln", "eprint", "format", "vec",
            "assert", "assert_eq", "assert_ne", "panic", "todo", "unimplemented",
            "unreachable", "dbg", "mem", "ptr", "rc", "Arc", "Box",
            "Option", "Result", "Ok", "Err", "Some", "None",
            "String", "Vec", "HashMap", "HashSet", "BTreeMap", "BTreeSet",
        }
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            base = callee.split("::")[0].split(".")[0]
            if base in skip_words:
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "::" in callee or "." in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_ruby_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:\.\w+)*)\s*[\(?]")
        skip_words = {
            "if", "unless", "while", "until", "case", "when", "def",
            "class", "module", "begin", "rescue", "ensure", "end",
            "return", "yield", "raise", "puts", "print", "p", "pp",
            "require", "require_relative", "load", "attr_reader",
            "attr_writer", "attr_accessor", "include", "extend",
            "private", "protected", "public", "self", "super",
            "nil", "true", "false", "and", "or", "not", "then",
            "do", "block_given?", "respond_to?", "is_a?", "kind_of?",
            "instance_of?", "method", "send", "public_send",
        }
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            base = callee.split(".")[0]
            if base in skip_words:
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "." in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_php_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\$?\w+(?:->\w+)*(?:::\w+)*)\s*\(")
        skip_words = {
            "if", "elseif", "while", "for", "foreach", "switch", "case",
            "return", "echo", "print", "die", "exit", "include", "require",
            "include_once", "require_once", "define", "new", "clone",
            "class", "interface", "trait", "extends", "implements",
            "function", "abstract", "final", "static", "public",
            "private", "protected", "var", "const", "self", "parent",
            "null", "true", "false", "array", "list", "compact",
            "extract", "isset", "unset", "empty", "var_dump", "print_r",
        }
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            base = callee.lstrip("$").split("->")[0].split("::")[0]
            if base in skip_words:
                continue
            resolved = callee in symbol_names
            call_type = "METHOD" if "->" in callee or "::" in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.9 if resolved else 0.3,
            ))
        return calls

    def _extract_calls_generic_line(
        self, line: str, line_num: int, symbol_names: set[str],
    ) -> list[CallInfo]:
        calls: list[CallInfo] = []
        func_call_re = re.compile(r"(\w+(?:\.\w+)*)\s*\(")
        for m in func_call_re.finditer(line):
            callee = m.group(1)
            resolved = callee in symbol_names
            call_type = "METHOD" if "." in callee else "DIRECT"
            calls.append(CallInfo(
                caller_name="<scope>",
                callee_name=callee,
                call_line=line_num,
                call_type=call_type,
                resolved=resolved,
                confidence=0.8 if resolved else 0.2,
            ))
        return calls

    def _detect_secrets(self, content: str) -> list[dict]:
        findings: list[dict] = []
        for i, line in enumerate(content.split("\n"), 1):
            for pattern_name, pattern in SECRET_PATTERNS.items():
                matches = pattern.finditer(line)
                for match in matches:
                    findings.append({
                        "pattern": pattern_name,
                        "line": i,
                        "match_start": match.start(),
                        "match_end": match.end(),
                        "matched_text": match.group()[:80],
                    })
        return findings

    def _redact_secrets(self, content: str) -> str:
        result = content
        for pattern_name, pattern in SECRET_PATTERNS.items():
            if pattern_name == "private_key":
                result = pattern.sub("[REDACTED_PRIVATE_KEY]", result)
            elif pattern_name in ("aws_access_key", "jwt_token", "slack_token", "github_token"):
                result = pattern.sub("[REDACTED]", result)
            else:
                def _make_replacer(pname: str):
                    def _replacer(m: Any) -> str:
                        full = m.group()
                        if m.lastindex and m.lastindex >= 1:
                            captured = m.group(1)
                            return full.replace(captured, "[REDACTED]")
                        return "[REDACTED]"
                    return _replacer
                result = pattern.sub(_make_replacer(pattern_name), result)
        return result

    def _regex_fallback(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> ParseResult:
        if language == "python":
            return self._regex_extract_python(content, file_path)
        elif language in ("javascript", "typescript"):
            return self._regex_extract_javascript(content, file_path)
        else:
            return self._regex_extract_generic(content, language, file_path)

    def _regex_extract_python(self, content: str, file_path: str) -> ParseResult:
        symbols: list[SymbolInfo] = []
        imports: list[ImportInfo] = []
        calls: list[CallInfo] = []
        lines = content.split("\n")

        current_indent = 0
        parent_stack: list[tuple[str, int, SymbolType]] = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())

            while parent_stack and indent <= parent_stack[-1][1] and parent_stack[-1][2] in (
                SymbolType.CLASS, SymbolType.FUNCTION, SymbolType.METHOD,
            ):
                parent_stack.pop()

            parent_name = parent_stack[-1][0] if parent_stack else ""

            func_match = re.match(
                r"^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*(\S+))?\s*:", stripped
            )
            if func_match:
                name = func_match.group(1)
                params_str = func_match.group(2)
                ret_type = func_match.group(3) or ""
                params = [p.strip().split(":")[0].split("=")[0].strip()
                          for p in params_str.split(",") if p.strip()]
                qualified = f"{parent_name}.{name}" if parent_name else name
                is_async = stripped.startswith("async")
                visibility = "private" if name.startswith("_") and not name.startswith("__") else "public"
                if name.startswith("__") and name.endswith("__"):
                    visibility = "dunder"

                sym_type = SymbolType.METHOD if parent_stack else SymbolType.FUNCTION
                sym = SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    symbol_type=sym_type,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip(":"),
                    docstring="",
                    visibility=visibility,
                    is_async=is_async,
                    parameters=params,
                    return_type=ret_type,
                    parent_name=parent_name,
                    language="python",
                    file_path=file_path,
                )
                symbols.append(sym)
                parent_stack.append((name, indent, sym_type))

                for param_name in params:
                    param_name_clean = param_name.strip().lstrip("*")
                    if param_name_clean:
                        calls.append(CallInfo(
                            caller_name=name,
                            callee_name=param_name_clean,
                            call_line=i,
                            call_type="DIRECT",
                            resolved=False,
                            confidence=0.1,
                        ))
                continue

            class_match = re.match(
                r"^(?:class)\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", stripped
            )
            if class_match:
                name = class_match.group(1)
                bases = class_match.group(2) or ""
                qualified = f"{parent_name}.{name}" if parent_name else name
                sym = SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    symbol_type=SymbolType.CLASS,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip(":"),
                    docstring="",
                    parent_name=parent_name,
                    language="python",
                    file_path=file_path,
                )
                symbols.append(sym)
                parent_stack.append((name, indent, SymbolType.CLASS))

                for base in bases.split(","):
                    base = base.strip()
                    if base and base not in ("object",):
                        calls.append(CallInfo(
                            caller_name=name,
                            callee_name=base,
                            call_line=i,
                            call_type="DIRECT",
                            resolved=False,
                            confidence=0.5,
                        ))
                continue

            var_match = re.match(
                r"^(\w+)\s*(?::\s*\S+)?\s*=\s*(.+)", stripped
            )
            if var_match and not stripped.startswith(("if", "for", "while", "with",
                                                      "return", "yield", "import",
                                                      "from", "class", "def")):
                name = var_match.group(1)
                value = var_match.group(2).strip()
                if value.startswith(("lambda", "def ", "class ", "(")):
                    sym_type = SymbolType.FUNCTION
                elif name.isupper():
                    sym_type = SymbolType.CONSTANT
                else:
                    sym_type = SymbolType.VARIABLE
                qualified = f"{parent_name}.{name}" if parent_name else name
                sym = SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    symbol_type=sym_type,
                    start_line=i,
                    end_line=i,
                    signature=stripped,
                    parent_name=parent_name,
                    language="python",
                    file_path=file_path,
                )
                symbols.append(sym)
                continue

            call_match = re.findall(r"(\w+(?:\.\w+)*)\s*\(", stripped)
            for callee in call_match:
                if callee not in ("if", "for", "while", "with", "as", "def", "class",
                                  "return", "yield", "import", "from", "print"):
                    calls.append(CallInfo(
                        caller_name=parent_name or "<module>",
                        callee_name=callee,
                        call_line=i,
                        call_type="DIRECT",
                        resolved=False,
                        confidence=0.2,
                    ))

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            abs_match = re.match(r"^import\s+(.+)$", stripped)
            if abs_match:
                for name in abs_match.group(1).split(","):
                    name = name.strip().rstrip(";")
                    imports.append(ImportInfo(
                        name=name,
                        import_type="ABSOLUTE",
                        module_path=name,
                        is_external=self._is_external_import(name.split(".")[0], "python"),
                        is_stdlib=name.split(".")[0] in STDLIB_MODULES_PYTHON,
                        line=i,
                    ))
                continue

            from_match = re.match(r"^from\s+([\w.]+)\s+import\s+(.+)$", stripped)
            if from_match:
                module = from_match.group(1)
                raw_names = from_match.group(2).strip()
                is_ext = self._is_external_import(module.split(".")[0], "python")
                is_std = module.split(".")[0] in STDLIB_MODULES_PYTHON
                if raw_names == "*":
                    imports.append(ImportInfo(
                        name=module,
                        import_type="WILDCARD",
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                else:
                    for alias_part in raw_names.split(","):
                        alias_part = alias_part.strip()
                        if " as " in alias_part:
                            parts = alias_part.split(" as ")
                            imported_name = parts[0].strip()
                            alias = parts[1].strip()
                        else:
                            imported_name = alias_part
                            alias = ""
                        imports.append(ImportInfo(
                            name=imported_name,
                            import_type="FROM",
                            alias=alias,
                            module_path=module,
                            is_external=is_ext,
                            is_stdlib=is_std,
                            line=i,
                        ))

        file_sym = SymbolInfo(
            name=os.path.basename(file_path),
            qualified_name=file_path,
            symbol_type=SymbolType.FILE,
            start_line=1,
            end_line=len(lines),
            language="python",
            file_path=file_path,
        )
        symbols.insert(0, file_sym)

        return ParseResult(
            file_path=file_path,
            language="python",
            symbols=symbols,
            imports=imports,
            calls=calls,
        )

    def _regex_extract_javascript(self, content: str, file_path: str) -> ParseResult:
        language = "typescript" if file_path.endswith((".ts", ".tsx")) else "javascript"
        symbols: list[SymbolInfo] = []
        imports: list[ImportInfo] = []
        calls: list[CallInfo] = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            func_match = re.match(
                r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*(\S+))?",
                stripped,
            )
            if func_match:
                name = func_match.group(1)
                params_str = func_match.group(2)
                ret_type = func_match.group(3) or ""
                params = [p.strip().split(":")[0].strip().split("=")[0].strip()
                          for p in params_str.split(",") if p.strip()]
                is_async = "async" in stripped.split("function")[0]
                visibility = "public" if "export" in stripped else "private"
                sym = SymbolInfo(
                    name=name,
                    qualified_name=name,
                    symbol_type=SymbolType.FUNCTION,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip("{").strip(),
                    visibility=visibility,
                    is_async=is_async,
                    parameters=params,
                    return_type=ret_type,
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)
                continue

            class_match = re.match(
                r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?",
                stripped,
            )
            if class_match:
                name = class_match.group(1)
                extends = class_match.group(2)
                implements = class_match.group(3)
                visibility = "public" if "export" in stripped else "private"
                is_abstract = "abstract" in stripped
                sym = SymbolInfo(
                    name=name,
                    qualified_name=name,
                    symbol_type=SymbolType.CLASS,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip("{").strip(),
                    visibility=visibility,
                    is_abstract=is_abstract,
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)

                if extends:
                    calls.append(CallInfo(
                        caller_name=name,
                        callee_name=extends,
                        call_line=i,
                        call_type="DIRECT",
                        resolved=False,
                        confidence=0.5,
                    ))
                if implements:
                    for impl in implements.split(","):
                        impl = impl.strip()
                        if impl:
                            calls.append(CallInfo(
                                caller_name=name,
                                callee_name=impl,
                                call_line=i,
                                call_type="DIRECT",
                                resolved=False,
                                confidence=0.5,
                            ))
                continue

            arrow_match = re.match(
                r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*\S+)?\s*=\s*(?:async\s*)?\(([^)]*)\)\s*(?::\s*(\S+))?\s*=>",
                stripped,
            )
            if arrow_match:
                name = arrow_match.group(1)
                params_str = arrow_match.group(2)
                ret_type = arrow_match.group(3) or ""
                params = [p.strip().split(":")[0].strip()
                          for p in params_str.split(",") if p.strip()]
                is_async = "async" in stripped
                sym = SymbolInfo(
                    name=name,
                    qualified_name=name,
                    symbol_type=SymbolType.FUNCTION,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip("{").strip(),
                    is_async=is_async,
                    parameters=params,
                    return_type=ret_type,
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)
                continue

            var_match = re.match(
                r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*\S+)?\s*=\s*(.+)",
                stripped,
            )
            if var_match:
                name = var_match.group(1)
                value = var_match.group(2).strip()
                if value.startswith(("class ", "function", "async ")):
                    continue
                if name.isupper():
                    sym_type = SymbolType.CONSTANT
                else:
                    sym_type = SymbolType.VARIABLE
                sym = SymbolInfo(
                    name=name,
                    qualified_name=name,
                    symbol_type=sym_type,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip(";").strip(),
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)
                continue

            interface_match = re.match(
                r"^(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([\w,\s]+))?",
                stripped,
            )
            if interface_match:
                name = interface_match.group(1)
                sym = SymbolInfo(
                    name=name,
                    qualified_name=name,
                    symbol_type=SymbolType.INTERFACE,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip("{").strip(),
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)
                continue

            enum_match = re.match(
                r"^(?:export\s+)?(?:const\s+)?enum\s+(\w+)",
                stripped,
            )
            if enum_match:
                name = enum_match.group(1)
                sym = SymbolInfo(
                    name=name,
                    qualified_name=name,
                    symbol_type=SymbolType.ENUM,
                    start_line=i,
                    end_line=i,
                    signature=stripped.rstrip("{").strip(),
                    language=language,
                    file_path=file_path,
                )
                symbols.append(sym)
                continue

            call_match = re.findall(r"(\w+(?:\.\w+)*)\s*\(", stripped)
            for callee in call_match:
                if callee not in ("if", "for", "while", "switch", "catch",
                                  "function", "class", "return", "new",
                                  "typeof", "instanceof", "throw", "async",
                                  "await", "import", "export", "from",
                                  "require", "console", "document", "window"):
                    calls.append(CallInfo(
                        caller_name="<scope>",
                        callee_name=callee,
                        call_line=i,
                        call_type="METHOD" if "." in callee else "DIRECT",
                        resolved=False,
                        confidence=0.2,
                    ))

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            es_match = re.match(
                r"""^import\s+(?:([\w*\s{},]+)\s+from\s+)?['"]([^'"]+)['"]""", stripped
            )
            if es_match:
                names = es_match.group(1)
                module = es_match.group(2)
                is_ext = self._is_external_import(module, language)
                is_std = module in STDLIB_MODULES_JAVASCRIPT
                if names is None:
                    imports.append(ImportInfo(
                        name=module,
                        import_type="ABSOLUTE",
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                else:
                    for alias_part in re.split(r",\s*", names.strip()):
                        alias_part = alias_part.strip()
                        if " as " in alias_part:
                            parts = alias_part.split(" as ")
                            imported_name = parts[0].strip()
                            alias = parts[1].strip()
                        else:
                            imported_name = alias_part
                            alias = ""
                        imports.append(ImportInfo(
                            name=imported_name,
                            import_type="FROM",
                            alias=alias,
                            module_path=module,
                            is_external=is_ext,
                            is_stdlib=is_std,
                            line=i,
                        ))
                continue

            req_match = re.match(
                r"""(?:const|let|var)\s+(\w+)\s*=\s*require\s*\(\s*['"]([^'"]+)['"]""",
                stripped,
            )
            if req_match:
                alias = req_match.group(1)
                module = req_match.group(2)
                is_ext = self._is_external_import(module, language)
                is_std = module in STDLIB_MODULES_JAVASCRIPT
                imports.append(ImportInfo(
                    name=module,
                    import_type="ABSOLUTE",
                    alias=alias,
                    module_path=module,
                    is_external=is_ext,
                    is_stdlib=is_std,
                    line=i,
                ))

        file_sym = SymbolInfo(
            name=os.path.basename(file_path),
            qualified_name=file_path,
            symbol_type=SymbolType.FILE,
            start_line=1,
            end_line=len(lines),
            language=language,
            file_path=file_path,
        )
        symbols.insert(0, file_sym)

        return ParseResult(
            file_path=file_path,
            language=language,
            symbols=symbols,
            imports=imports,
            calls=calls,
        )

    def _regex_extract_generic(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> ParseResult:
        symbols: list[SymbolInfo] = []
        imports: list[ImportInfo] = []
        calls: list[CallInfo] = []
        lines = content.split("\n")

        func_patterns = [
            (r"^(?:public|private|protected|static|final|abstract|sealed|virtual|override|async|inline|constexpr|const)?\s*(?:function)\s+(\w+)\s*\(([^)]*)\)", SymbolType.FUNCTION),
            (r"^(?:pub\s+)?(?:fn)\s+(\w+)\s*\(([^)]*)\)", SymbolType.FUNCTION),
            (r"^(?:func)\s+(?:\([^)]*\)\s+)?(\w+)\s*\(([^)]*)\)", SymbolType.FUNCTION),
            (r"^(\w+(?:::\w+)*)\s*\(([^)]*)\)\s*(?:->|=>|\{|where)", SymbolType.FUNCTION),
            (r"^(?:func|function|fun|def|sub|proc)\s+(\w+)\s*\(([^)]*)\)", SymbolType.FUNCTION),
        ]

        class_patterns = [
            (r"^(?:public|private|protected)?\s*(?:abstract\s+)?class\s+(\w+)", SymbolType.CLASS),
            (r"^(?:pub\s+)?(?:struct)\s+(\w+)", SymbolType.STRUCT),
            (r"^(?:pub\s+)?(?:enum)\s+(\w+)", SymbolType.ENUM),
            (r"^(?:pub\s+)?(?:trait)\s+(\w+)", SymbolType.INTERFACE),
            (r"^(?:data\s+)?type\s+(\w+)", SymbolType.TYPE),
            (r"^(?:interface)\s+(\w+)", SymbolType.INTERFACE),
        ]

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            for pattern, sym_type in func_patterns:
                m = re.match(pattern, stripped)
                if m:
                    name = m.group(1)
                    params_str = m.group(2) if m.lastindex >= 2 else ""
                    params = [p.strip().split(":")[0].split("=")[0].strip()
                              for p in params_str.split(",") if p.strip()]
                    sym = SymbolInfo(
                        name=name,
                        qualified_name=name,
                        symbol_type=sym_type,
                        start_line=i,
                        end_line=i,
                        signature=stripped.rstrip("{").rstrip(":").strip(),
                        language=language,
                        file_path=file_path,
                    )
                    symbols.append(sym)
                    break

            for pattern, sym_type in class_patterns:
                m = re.match(pattern, stripped)
                if m:
                    name = m.group(1)
                    sym = SymbolInfo(
                        name=name,
                        qualified_name=name,
                        symbol_type=sym_type,
                        start_line=i,
                        end_line=i,
                        signature=stripped.rstrip("{").rstrip(":").strip(),
                        language=language,
                        file_path=file_path,
                    )
                    symbols.append(sym)
                    break

            call_matches = re.findall(r"(\w+(?:\.\w+)*)\s*\(", stripped)
            for callee in call_matches:
                if callee not in ("if", "for", "while", "switch", "return",
                                  "function", "class", "def", "fn", "func",
                                  "struct", "enum", "trait", "interface",
                                  "type", "import", "from", "require",
                                  "pub", "private", "protected", "static",
                                  "final", "abstract", "new", "throw",
                                  "catch", "case", "when", "do", "begin",
                                  "end", "unless", "until", "loop",
                                  "match", "where", "let", "var", "const"):
                    calls.append(CallInfo(
                        caller_name="<scope>",
                        callee_name=callee,
                        call_line=i,
                        call_type="METHOD" if "." in callee else "DIRECT",
                        resolved=False,
                        confidence=0.2,
                    ))

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for pattern, imp_type in [
                (r"""^import\s+(?:[\w*\s{},]+\s+from\s+)?['"]([^'"]+)['"]""", "ABSOLUTE"),
                (r"^from\s+([\w.]+)\s+import", "ABSOLUTE"),
                (r"""^require\s*\(\s*['"]([^'"]+)['"]""", "ABSOLUTE"),
                (r"""^require\s+['"]([^'"]+)['"]""", "ABSOLUTE"),
                (r"^use\s+([\w.]+)", "ABSOLUTE"),
                (r"^#include\s+[<\"]([^>\"]+)[>\"]", "ABSOLUTE"),
                (r"^include\s+[<\"]([^>\"]+)[>\"]", "ABSOLUTE"),
                (r"^using\s+([\w.]+)\s*;", "ABSOLUTE"),
            ]:
                m = re.match(pattern, stripped)
                if m:
                    module = m.group(1)
                    top = module.split(".")[0].split("/")[0].split("\\")[0]
                    is_ext = self._is_external_import(top, language)
                    is_std = top in STDLIB_MODULES.get(language, frozenset())
                    imports.append(ImportInfo(
                        name=module,
                        import_type=imp_type,
                        module_path=module,
                        is_external=is_ext,
                        is_stdlib=is_std,
                        line=i,
                    ))
                    break

        file_sym = SymbolInfo(
            name=os.path.basename(file_path),
            qualified_name=file_path,
            symbol_type=SymbolType.FILE,
            start_line=1,
            end_line=len(lines),
            language=language,
            file_path=file_path,
        )
        symbols.insert(0, file_sym)

        return ParseResult(
            file_path=file_path,
            language=language,
            symbols=symbols,
            imports=imports,
            calls=calls,
        )

    def _extract_symbols_regex(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> list[SymbolInfo]:
        if language == "python":
            result = self._regex_extract_python(content, file_path)
        elif language in ("javascript", "typescript"):
            result = self._regex_extract_javascript(content, file_path)
        else:
            result = self._regex_extract_generic(content, language, file_path)
        return result.symbols

    def _count_lines(self, content: str) -> tuple[int, int, int]:
        total = 0
        comment = 0
        blank = 0
        in_block_comment = False

        single_line_comment_patterns = {
            "python": "#",
            "javascript": "//",
            "typescript": "//",
            "java": "//",
            "c": "//",
            "cpp": "//",
            "c_sharp": "//",
            "go": "//",
            "rust": "//",
            "php": "//",
            "ruby": "#",
            "kotlin": "//",
            "swift": "//",
            "bash": "#",
            "yaml": "#",
            "sql": "--",
        }

        block_comment_start = {
            "python": ('"""', "'''"),
            "javascript": ("/*",),
            "typescript": ("/*",),
            "java": ("/*",),
            "c": ("/*",),
            "cpp": ("/*",),
            "c_sharp": ("/*",),
            "go": ("/*",),
            "rust": ("/*",),
            "php": ("/*",),
            "ruby": ("=begin",),
            "kotlin": ("/*",),
            "swift": ("/*",),
            "bash": (":'",),
        }

        block_comment_end = {
            "python": ('"""', "'''"),
            "javascript": ("*/",),
            "typescript": ("*/",),
            "java": ("*/",),
            "c": ("*/",),
            "cpp": ("*/",),
            "c_sharp": ("*/",),
            "go": ("*/",),
            "rust": ("*/",),
            "php": ("*/",),
            "ruby": ("=end",),
            "kotlin": ("*/",),
            "swift": ("*/",),
            "bash": ("'",),
        }

        for line in content.split("\n"):
            total += 1
            stripped = line.strip()

            if not stripped:
                blank += 1
                continue

            if in_block_comment:
                comment += 1
                ends = block_comment_end.get("", block_comment_end.get("javascript", ("*/",)))
                for end in ends:
                    if end in stripped:
                        in_block_comment = False
                        break
                continue

            starts = block_comment_start.get("", block_comment_start.get("javascript", ("/*",)))
            for start in starts:
                if start in stripped:
                    comment += 1
                    ends = block_comment_end.get("", block_comment_end.get("javascript", ("*/",)))
                    for end in ends:
                        if end in stripped and stripped.index(start) < stripped.index(end):
                            break
                    else:
                        in_block_comment = True
                    break

            for lang, pattern in single_line_comment_patterns.items():
                if stripped.startswith(pattern):
                    comment += 1
                    break

        return total, comment, blank

    def get_language_adapters(self) -> dict[str, dict]:
        adapters: dict[str, dict] = {}
        for lang in sorted(set(self._GRAMMARS.keys()) | set(self._EXTENSION_MAP.values())):
            extensions = [ext for ext, l in self._EXTENSION_MAP.items() if l == lang]
            has_tree_sitter_parser = lang in self._GRAMMARS and self._ts_available
            adapters[lang] = {
                "language": lang,
                "extensions": sorted(extensions),
                "tree_sitter_available": has_tree_sitter_parser,
                "regex_fallback": True,
                "stdlib_modules": len(STDLIB_MODULES.get(lang, frozenset())),
                "supports_symbols": True,
                "supports_imports": True,
                "supports_calls": True,
                "supports_secrets_detection": True,
            }
        return adapters

    def _compute_tree_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
