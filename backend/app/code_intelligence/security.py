"""Security Signal Detection Engine — evidence-based, integrates with existing scanning.

Every finding requires an actual code snippet and confidence score. The scanner
never labels arbitrary code as vulnerable without evidence.
"""

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeFile,
    CodeImport,
    CodeSymbol,
)

logger = logging.getLogger(__name__)


# ── Compiled Secret Patterns ───────────────────────────────────────────

SECRET_PATTERNS: dict[str, re.Pattern] = {
    "generic_api_key": re.compile(
        r"""(?i)(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*['"]([A-Za-z0-9_\-]{16,})['"]""",
    ),
    "aws_access_key": re.compile(
        r"""(?<![A-Za-z0-9/+=])(?:AKIA|ABIA|ACCA|AROA)[A-Za-z0-9]{16}(?![A-Za-z0-9/+=])""",
    ),
    "aws_secret_key": re.compile(
        r"""(?i)(?:aws[_-]?secret[_-]?access[_-]?key|secret[_-]?key)\s*[:=]\s*['"]([A-Za-z0-9/+=]{40})['"]""",
    ),
    "aws_connection_string": re.compile(
        r"""(?i)aws[_-]?(?:secret|key|token|credential)[^'\n]{0,80}['"][A-Za-z0-9/+=]{20,}['"]""",
    ),
    "gcp_api_key": re.compile(
        r"""(?i)(?:google[_-]?api[_-]?key|gcp[_-]?api[_-]?key)\s*[:=]\s*['"]([A-Za-z0-9_\-]{30,})['"]""",
    ),
    "gcp_service_account": re.compile(
        r"""(?i)["']type["']\s*:\s*["']service_account["']""",
    ),
    "azure_connection_string": re.compile(
        r"""(?i)DefaultEndpointsProtocol=https?;AccountName=[^;]+;AccountKey=[A-Za-z0-9/+=]{40,}""",
    ),
    "azure_storage_key": re.compile(
        r"""(?i)(?:azure[_-]?storage[_-]?key|account[_-]?key)\s*[:=]\s*['"]([A-Za-z0-9/+=]{40,})['"]""",
    ),
    "generic_token": re.compile(
        r"""(?i)(?:auth[_-]?token|bearer[_-]?token|access[_-]?token|id[_-]?token)\s*[:=]\s*['"]([A-Za-z0-9_\-\.]{20,})['"]""",
    ),
    "password_in_code": re.compile(
        r"""(?i)(?:password|passwd|pwd)\s*[:=]\s*['"]([^'"]{4,})['"]""",
    ),
    "private_key_header": re.compile(
        r"""-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----""",
    ),
    "connection_string": re.compile(
        r"""(?i)(?:jdbc|mysql|postgres|postgresql|mongodb|redis|amqp|rabbitmq)://[^\s'"]{10,}""",
    ),
    "jwt_token": re.compile(
        r"""eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}""",
    ),
    "github_token": re.compile(
        r"""(?i)(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}""",
    ),
    "slack_token": re.compile(
        r"""(?i)xox[baprs]-[A-Za-z0-9\-]{10,}""",
    ),
    "stripe_key": re.compile(
        r"""(?i)(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{16,}""",
    ),
    "heroku_api_key": re.compile(
        r"""(?i)(?:heroku[_-]?api[_-]?key)\s*[:=]\s*['"]([A-Za-z0-9\-]{40,})['"]""",
    ),
}


# ── Injection Patterns (per-language) ──────────────────────────────────

INJECTION_PATTERNS: dict[str, dict[str, re.Pattern]] = {
    "sql_injection": {
        "generic": re.compile(
            r"""(?i)(?:execute|executemany|raw|cursor\.execute|query)\s*\(\s*(?:f['"]|['"].*%s|['"].*\.format|['"].*\+\s*)""",
        ),
        "python": re.compile(
            r"""(?i)(?:execute|executemany|raw)\s*\(\s*(?:f['"]|['"].*%s|['"].*\.format|['"].*\+\s*|['"].*\{)""",
        ),
        "javascript": re.compile(
            r"""(?i)(?:query|execute|run)\s*\(\s*(?:`|['"].*\+\s*|\$\{)""",
        ),
        "php": re.compile(
            r"""(?i)(?:mysql_query|mysqli_query|->query|->prepare)\s*\(\s*(?:['"].*\.\s*\$|\$_GET|\$_POST|\$_REQUEST)""",
        ),
        "java": re.compile(
            r"""(?i)(?:Statement|executeQuery|executeUpdate)\s*\(.*(?:\+\s*["']|String\.format)""",
        ),
    },
    "command_injection": {
        "python": re.compile(
            r"""(?i)(?:os\.system|os\.popen|subprocess\.(?:call|run|Popen|check_output)|commands\.(?:getoutput|getstatusoutput))\s*\(\s*(?:f['"]|['"].*\+\s*|['"].*\.format|['"].*%\s)""",
        ),
        "javascript": re.compile(
            r"""(?i)(?:exec|execSync|spawnSync|execFile)\s*\(\s*(?:['"].*\+\s*|\$\{)""",
        ),
        "php": re.compile(
            r"""(?i)(?:exec|system|passthru|shell_exec|popen|proc_open)\s*\(\s*(?:['"].*\.\s*\$|\$_GET|\$_POST)""",
        ),
        "ruby": re.compile(
            r"""(?i)(?:system|exec|`[^`]*#\{|%x\{|IO\.popen)\s*\(?['"].*\#\{""",
        ),
        "go": re.compile(
            r"""(?i)(?:exec\.Command|os\.exec)\s*\(\s*[^,)]*\+\s*""",
        ),
    },
    "xss": {
        "javascript": re.compile(
            r"""(?i)(?:document\.write|\.innerHTML\s*=|\.outerHTML\s*=|\.insertAdjacentHTML)\s*\(\s*(?:['"].*\+\s*|\$\{|\beval\b)""",
        ),
        "html": re.compile(
            r"""(?i)<(?:script|iframe|object|embed|form|input|img)[^>]*(?:on\w+\s*=\s*['"][^'"]*\{[^}]*\}|src\s*=\s*['"]https?://[^'"]*\+)""",
        ),
        "php": re.compile(
            r"""(?i)(?:echo|print)\s+\$_(?:GET|POST|REQUEST|COOKIE|SERVER)\["?(\w+)"?\]""",
        ),
        "python": re.compile(
            r"""(?i)(?:mark_safe|SafeString|\.format)\s*\(\s*(?:request\.(?:GET|POST|GET\.get|POST\.get)|f['"].*\{.*request)""",
        ),
        "java": re.compile(
            r"""(?i)(?:response\.getWriter\(\)\.print|out\.print)\s*\(\s*(?:request\.getParameter|request\.getHeader)""",
        ),
    },
    "path_traversal": {
        "generic": re.compile(
            r"""(?i)(?:open|read_file|readFileSync|FileInputStream|fopen)\s*\(\s*(?:['"].*\.\.\/|['"].*\.\.\\|\$_GET|\$_POST|request\.params)""",
        ),
    },
    "deserialization": {
        "python": re.compile(
            r"""(?i)(?:pickle\.loads?|yaml\.load\s*\(|marshal\.loads?|shelve\.open)\s*\("""
        ),
        "java": re.compile(
            r"""(?i)(?:ObjectInputStream|readObject|XMLDecoder|readValue|fromJson)\s*\("""
        ),
        "php": re.compile(
            r"""(?i)(?:unserialize)\s*\(\s*(?:['"].*\.\s*\$|\$_GET|\$_POST|\$_REQUEST)""",
        ),
    },
}


# ── Insecure Patterns ─────────────────────────────────────────────────

INSECURE_PATTERNS: dict[str, dict[str, re.Pattern]] = {
    "eval_usage": {
        "python": re.compile(r"""\beval\s*\("""),
        "javascript": re.compile(r"""\beval\s*\("""),
    },
    "exec_usage": {
        "python": re.compile(r"""\bexec\s*\("""),
        "javascript": re.compile(
            r"""(?i)\b(?:Function)\s*\(\s*['"]return"""
        ),
    },
    "hardcoded_password": {
        "generic": re.compile(
            r"""(?i)(?:password|passwd|pwd|secret|token|api_?key)\s*[:=]\s*['"]([^'"]{4,60})['"]""",
        ),
    },
    "weak_crypto_md5": {
        "generic": re.compile(
            r"""(?i)(?:hashlib\.md5|MD5Digest|MessageDigest\.getInstance\s*\(\s*['"]MD5['"]|createHash\s*\(\s*['"]md5['"])""",
        ),
    },
    "weak_crypto_sha1": {
        "generic": re.compile(
            r"""(?i)(?:hashlib\.sha1(?:\b)|SHA1Digest|MessageDigest\.getInstance\s*\(\s*['"]SHA-?1['"]|createHash\s*\(\s*['"]sha1['"])""",
        ),
    },
    "weak_crypto_des": {
        "generic": re.compile(
            r"""(?i)(?:DES\/ECB|DESede|DES\.getInstance|cipher\.init.*DES)""",
        ),
    },
    "disabled_tls_verify": {
        "python": re.compile(
            r"""(?i)(?:verify\s*=\s*False|SSLContext.*check_hostname\s*=\s*False|CERT_NONE|ssl\._create_unverified_context)""",
        ),
        "javascript": re.compile(
            r"""(?i)(?:rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['"]0['"]|process\.env\.NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['"]0['"])""",
        ),
        "go": re.compile(
            r"""(?i)InsecureSkipVerify\s*:\s*true""",
        ),
        "java": re.compile(
            r"""(?i)(?:SSLContext.*null|null\s*\(\)\s*\(\s*\)\s*->\s*checkServerTrusted|TRUST_ALL)""",
        ),
    },
    "debug_mode_production": {
        "python": re.compile(
            r"""(?i)(?:DEBUG\s*=\s*True|app\.run\(\s*debug\s*=\s*True)""",
        ),
        "javascript": re.compile(
            r"""(?i)(?:DEBUG\s*=\s*true|debug\s*:\s*true)""",
        ),
    },
    "cors_wildcard": {
        "generic": re.compile(
            r"""(?i)(?:Access-Control-Allow-Origin|cors[_-]?origin|allowed_origins?)[\s:'"]*\*""",
        ),
    },
    "insecure_random": {
        "python": re.compile(
            r"""(?i)\brandom\.(?:random|randint|choice|randrange|sample)\b"""
        ),
        "javascript": re.compile(
            r"""(?i)\bMath\.random\b"""
        ),
    },
    "template_injection": {
        "python": re.compile(
            r"""(?i)(?:render_template_string|Markup|jinja2\.Template)\s*\(\s*(?:f['"]|['"].*\.format|['"].*%\s)""",
        ),
    },
    "open_redirect": {
        "generic": re.compile(
            r"""(?i)(?:redirect|location\s*=)\s*(?:f['"]|['"].*\+\s*(?:request\.|params\.|query\.))""",
        ),
    },
    "ssrf": {
        "generic": re.compile(
            r"""(?i)(?:requests\.(?:get|post|put|delete|patch|head|options)|urllib\.request\.urlopen|http\.get|fetch)\s*\(\s*(?:f['"]|['"].*\+\s*(?:request\.|params\.|user))""",
        ),
    },
    "open_redirect_html": {
        "generic": re.compile(
            r"""(?i)<meta[^>]+http-equiv\s*=\s*['"]refresh['"][^>]+url\s*=\s*['"]*\{""",
        ),
    },
}


# ── Known Vulnerable Dependency Patterns ──────────────────────────────

VULNERABLE_DEPENDENCIES: dict[str, dict[str, str]] = {
    "python": {
        "requests": {"below": "2.31.0", "cve": "CVE-2023-32681"},
        "flask": {"below": "2.3.2", "cve": "CVE-2023-30861"},
        "django": {"below": "4.2.1", "cve": "CVE-2023-31047"},
        "jinja2": {"below": "3.1.2", "cve": "CVE-2023-30277"},
        "pillow": {"below": "10.0.0", "cve": "CVE-2023-44271"},
        "cryptography": {"below": "41.0.0", "cve": "CVE-2023-38325"},
        "pyjwt": {"below": "2.8.0", "cve": "CVE-2022-29217"},
        "aiohttp": {"below": "3.8.5", "cve": "CVE-2023-37276"},
        "urllib3": {"below": "2.0.4", "cve": "CVE-2023-43804"},
        "certifi": {"below": "2023.7.22", "cve": "CVE-2023-37920"},
    },
    "javascript": {
        "express": {"below": "4.18.2", "cve": "CVE-2022-24999"},
        "lodash": {"below": "4.17.21", "cve": "CVE-2021-23337"},
        "minimist": {"below": "1.2.6", "cve": "CVE-2021-44906"},
        "node-fetch": {"below": "2.6.7", "cve": "CVE-2022-0235"},
        "qs": {"below": "6.5.3", "cve": "CVE-2022-24999"},
        "axios": {"below": "0.21.2", "cve": "CVE-2021-3749"},
        "jsonwebtoken": {"below": "9.0.0", "cve": "CVE-2022-23529"},
    },
    "java": {
        "log4j": {"below": "2.17.1", "cve": "CVE-2021-44228"},
        "spring-core": {"below": "5.3.18", "cve": "CVE-2022-22965"},
        "jackson-databind": {"below": "2.13.4", "cve": "CVE-2022-42003"},
        "httpclient": {"below": "4.5.14", "cve": "CVE-2020-13956"},
    },
    "go": {
        "golang.org/x/crypto": {"below": "0.0.0-20220214200702-86341886e292", "cve": "CVE-2022-27191"},
        "github.com/gin-gonic/gin": {"below": "1.7.7", "cve": "CVE-2022-28948"},
    },
}


# ── Insecure Configuration Patterns ───────────────────────────────────

MISCONFIGURATION_PATTERNS: dict[str, re.Pattern] = {
    "debug_enabled": re.compile(
        r"""(?i)(?:DEBUG\s*=\s*True|debug\s*:\s*true|debug\s*=\s*1)""",
    ),
    "cors_wildcard": re.compile(
        r"""(?i)(?:ALLOWED_ORIGINS?\s*[=:]\s*\[?\s*['"]\*['"]|cors[_-]?origin\s*[=:]\s*['"]\*['"]|Access-Control-Allow-Origin\s*[=:]\s*['"]\*['"])""",
    ),
    "exposed_secret_in_config": re.compile(
        r"""(?i)(?:SECRET_KEY|API_KEY|PRIVATE_KEY|TOKEN|PASSWORD|CREDENTIAL)\s*[=:]\s*['"]([^'"]{8,})['"]""",
    ),
    "host_binding_wildcard": re.compile(
        r"""(?i)(?:host\s*[=:]\s*['"]0\.0\.0\.0['"]|HOST\s*[=:]\s*['"]0\.0\.0\.0['"]|listen\s+0\.0\.0\.0)""",
    ),
    "disabled_csrf": re.compile(
        r"""(?i)(?:csrf[_-]protection\s*[=:]\s*(?:false|off|0)|CSRF_ENABLED\s*=\s*(?:False|0)|disableCsrf\s*:\s*true)""",
    ),
    "verbose_error_pages": re.compile(
        r"""(?i)(?:DEBUG\s*=\s*True|showErrors\s*:\s*true|displayErrorPages\s*:\s*true)""",
    ),
    "weak_session_config": re.compile(
        r"""(?i)(?:session[_-]?cookie[_-]?secure\s*[=:]\s*(?:false|0)|SESSION_COOKIE_SECURE\s*=\s*(?:False|0))""",
    ),
    "http_only_cookies_disabled": re.compile(
        r"""(?i)(?:httponly\s*[=:]\s*(?:false|0)|HTTPONLY\s*=\s*(?:False|0))""",
    ),
}


# ── Language aliases ──────────────────────────────────────────────────

_LANG_ALIASES: dict[str, str] = {
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "ts": "javascript",
    "tsx": "javascript",
    "jsx": "javascript",
    "rb": "ruby",
    "java8": "java",
    "java11": "java",
    "java17": "java",
    "kt": "kotlin",
    "cs": "csharp",
    "cpp": "cpp",
    "c": "c",
    "go": "go",
    "rs": "rust",
    "php": "php",
    "swift": "swift",
}


def _normalize_lang(lang: str | None) -> str:
    if not lang:
        return "generic"
    return _LANG_ALIASES.get(lang.lower(), lang.lower())


# ── SecurityScanner ───────────────────────────────────────────────────


class SecurityScanner:
    """Detect security signals in indexed code. Integrates with existing
    scanning infrastructure rather than duplicating SAST systems.

    Every finding includes the actual code snippet (evidence) and a
    confidence score. The scanner never labels code as vulnerable
    without verifiable evidence.
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ── orchestration ────────────────────────────────────────────────

    async def scan_repository(
        self, repo_id: str, index_id: str
    ) -> list[dict]:
        """Full security scan across all files in an indexed repository."""
        all_findings: list[dict] = []

        files = await self._load_indexed_files(repo_id, index_id)
        logger.info("Security scanning %d files for repo %s", len(files), repo_id)

        for file_row in files:
            content = await self._read_file_content(file_row)
            if not content:
                continue

            language = _normalize_lang(file_row.language)
            file_path = file_row.file_path
            file_id = str(file_row.id)

            try:
                secret_findings = self.detect_secrets(content, file_path)
                for f in secret_findings:
                    f["file_id"] = file_id
                all_findings.extend(secret_findings)

                injection_findings = self.detect_injection_risks(content, language)
                for f in injection_findings:
                    f["file_id"] = file_id
                all_findings.extend(injection_findings)

                insecure_findings = self.detect_insecure_patterns(content, language)
                for f in insecure_findings:
                    f["file_id"] = file_id
                all_findings.extend(insecure_findings)
            except Exception:
                logger.exception(
                    "Security scan failed for file %s", file_path
                )

        dependency_findings = await self.detect_dependency_risks(repo_id)
        all_findings.extend(dependency_findings)

        misconfig_findings = await self.detect_misconfigurations(repo_id)
        all_findings.extend(misconfig_findings)

        return all_findings

    async def scan_file(
        self, file_id: str, content: str, language: str
    ) -> list[dict]:
        """Scan a single file for security issues."""
        norm_lang = _normalize_lang(language)
        file_path = await self._get_file_path(file_id)

        findings: list[dict] = []

        secret_findings = self.detect_secrets(content, file_path)
        for f in secret_findings:
            f["file_id"] = file_id
        findings.extend(secret_findings)

        injection_findings = self.detect_injection_risks(content, norm_lang)
        for f in injection_findings:
            f["file_id"] = file_id
        findings.extend(injection_findings)

        insecure_findings = self.detect_insecure_patterns(content, norm_lang)
        for f in insecure_findings:
            f["file_id"] = file_id
        findings.extend(insecure_findings)

        return findings

    # ── secret detection ─────────────────────────────────────────────

    def detect_secrets(self, content: str, file_path: str) -> list[dict]:
        """Detect hardcoded secrets: API keys, tokens, passwords, private
        keys, AWS/GCP/Azure keys, connection strings, JWT tokens.

        Only flags patterns that match a concrete regex against actual
        code content. False positive filtering is applied.
        """
        findings: list[dict] = []
        lines = content.split("\n")

        for pattern_name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(content):
                matched_text = match.group(0) if match.lastindex is None else match.group(1)
                if not matched_text:
                    continue

                line_num = self._line_of_match(content, match.start())
                line_text = lines[line_num - 1] if 0 < line_num <= len(lines) else ""

                if self._is_false_positive_secret(
                    matched_text, line_text, file_path, pattern_name
                ):
                    continue

                snippet = self._extract_snippet(lines, line_num, context=2)

                severity = self._secret_severity(pattern_name)
                confidence = self._secret_confidence(
                    pattern_name, matched_text, line_text, file_path
                )

                findings.append(self._create_finding(
                    finding_type="hardcoded_secret",
                    severity=severity,
                    message=f"Potential hardcoded secret detected ({pattern_name.replace('_', ' ')})",
                    evidence=snippet,
                    file_path=file_path,
                    line=line_num,
                    confidence=confidence,
                    category="secrets",
                    metadata={"pattern_name": pattern_name},
                ))

        return findings

    # ── injection risk detection ─────────────────────────────────────

    def detect_injection_risks(
        self, content: str, language: str
    ) -> list[dict]:
        """Detect SQL injection, command injection, XSS, path traversal,
        and insecure deserialization patterns.

        Patterns are language-aware. Each finding requires the actual
        vulnerable code pattern to be present.
        """
        findings: list[dict] = []
        lines = content.split("\n")

        for vuln_category, lang_patterns in INJECTION_PATTERNS.items():
            patterns_to_check = {}

            if language in lang_patterns:
                patterns_to_check["specific"] = lang_patterns[language]
            if "generic" in lang_patterns:
                patterns_to_check["generic"] = lang_patterns["generic"]

            for qualifier, pattern in patterns_to_check.items():
                for match in pattern.finditer(content):
                    line_num = self._line_of_match(content, match.start())
                    line_text = lines[line_num - 1] if 0 < line_num <= len(lines) else ""

                    if self._is_false_positive_injection(
                        line_text, vuln_category, language
                    ):
                        continue

                    snippet = self._extract_snippet(lines, line_num, context=2)

                    severity = self._injection_severity(vuln_category)
                    confidence = self._injection_confidence(
                        vuln_category, line_text, language, qualifier
                    )

                    findings.append(self._create_finding(
                        finding_type=f"injection_{vuln_category}",
                        severity=severity,
                        message=f"Potential {vuln_category.replace('_', ' ')} vulnerability",
                        evidence=snippet,
                        file_path="",
                        line=line_num,
                        confidence=confidence,
                        category="injection",
                        metadata={
                            "language": language,
                            "pattern_qualifier": qualifier,
                        },
                    ))

        return findings

    # ── insecure pattern detection ───────────────────────────────────

    def detect_insecure_patterns(
        self, content: str, language: str
    ) -> list[dict]:
        """Detect eval/exec, hardcoded credentials, weak cryptography,
        disabled TLS verification, debug mode, and other insecure patterns.
        """
        findings: list[dict] = []
        lines = content.split("\n")

        for pattern_group, lang_patterns in INSECURE_PATTERNS.items():
            patterns_to_check = {}

            if language in lang_patterns:
                patterns_to_check["specific"] = lang_patterns[language]
            if "generic" in lang_patterns:
                patterns_to_check["generic"] = lang_patterns["generic"]

            for qualifier, pattern in patterns_to_check.items():
                for match in pattern.finditer(content):
                    line_num = self._line_of_match(content, match.start())
                    line_text = lines[line_num - 1] if 0 < line_num <= len(lines) else ""

                    if self._is_false_positive_insecure(
                        line_text, pattern_group, file_path=""
                    ):
                        continue

                    snippet = self._extract_snippet(lines, line_num, context=2)

                    severity = self._insecure_severity(pattern_group)
                    confidence = self._insecure_confidence(
                        pattern_group, line_text, language
                    )

                    findings.append(self._create_finding(
                        finding_type=f"insecure_{pattern_group}",
                        severity=severity,
                        message=self._insecure_message(pattern_group),
                        evidence=snippet,
                        file_path="",
                        line=line_num,
                        confidence=confidence,
                        category="insecure_pattern",
                        metadata={"language": language},
                    ))

        return findings

    # ── dependency risk detection ────────────────────────────────────

    async def detect_dependency_risks(
        self, repo_id: str
    ) -> list[dict]:
        """Check external imports against known vulnerable dependency
        patterns. Cross-references extracted imports with a catalog of
        known CVEs for common packages.
        """
        findings: list[dict] = []

        stmt = (
            select(CodeImport, CodeFile)
            .join(CodeFile, CodeImport.source_file_id == CodeFile.id)
            .where(
                CodeImport.repository_id == UUID(repo_id),
                CodeImport.is_external.is_(True),
                CodeImport.is_stdlib.is_(False),
            )
        )
        result = await self.db.execute(stmt)
        imports = result.all()

        if not imports:
            return findings

        detected_languages: set[str] = set()
        for imp, file_ in imports:
            if file_.language:
                detected_languages.add(_normalize_lang(file_.language))

        for imp, file_ in imports:
            imported_name = imp.imported_name
            root_package = imported_name.split(".")[0]
            language = _normalize_lang(file_.language)

            vuln_db = VULNERABLE_DEPENDENCIES.get(language, {})
            for vuln_pkg, vuln_info in vuln_db.items():
                if root_package.lower() == vuln_pkg.lower():
                    findings.append(self._create_finding(
                        finding_type="vulnerable_dependency",
                        severity="high",
                        message=(
                            f"Dependency '{root_package}' may be affected by "
                            f"{vuln_info['cve']}"
                        ),
                        evidence=(
                            f"import {imported_name} in {file_.file_path}"
                        ),
                        file_path=file_.file_path,
                        line=None,
                        confidence=0.6,
                        category="dependency",
                        metadata={
                            "package": root_package,
                            "cve": vuln_info["cve"],
                            "fixed_in": vuln_info["below"],
                            "imported_name": imported_name,
                        },
                    ))
                    break

        return findings

    # ── misconfiguration detection ───────────────────────────────────

    async def detect_misconfigurations(
        self, repo_id: str
    ) -> list[dict]:
        """Detect insecure configuration patterns: CORS wildcard,
        debug=True, exposed secrets in config, etc.
        """
        findings: list[dict] = []

        config_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".yaml", ".yml",
            ".toml", ".json", ".env", ".cfg", ".ini", ".conf",
            ".properties", ".xml", ".rb", ".go",
        }

        config_name_patterns = {
            "settings", "config", "configuration", "appsettings",
            "database", "docker", "docker-compose", ".env",
            "webpack", "vite", "nginx", "gunicorn", "uwsgi",
            "celery", "redis", "rabbitmq", "kafka", "prometheus",
            "grafana", "terraform", "ansible",
        }

        stmt = (
            select(CodeFile)
            .where(
                CodeFile.repository_id == UUID(repo_id),
            )
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        for file_row in files:
            file_path = file_row.file_path
            file_name = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            _, ext = file_path.rsplit(".", 1) if "." in file_path else ("", "")

            is_config = (
                ext.lower() in config_extensions
                or any(cp in file_name for cp in config_name_patterns)
                or file_row.is_config_file
            )
            if not is_config:
                continue

            content = await self._read_file_content(file_row)
            if not content:
                continue

            for misconfig_name, pattern in MISCONFIGURATION_PATTERNS.items():
                for match in pattern.finditer(content):
                    line_num = self._line_of_match(content, match.start())
                    lines = content.split("\n")
                    line_text = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
                    snippet = self._extract_snippet(lines, line_num, context=1)

                    if self._is_false_positive_misconfig(
                        line_text, misconfig_name, file_path
                    ):
                        continue

                    confidence = self._misconfig_confidence(
                        misconfig_name, line_text, file_path
                    )

                    findings.append(self._create_finding(
                        finding_type=f"misconfiguration_{misconfig_name}",
                        severity=self._misconfig_severity(misconfig_name),
                        message=self._misconfig_message(misconfig_name),
                        evidence=snippet,
                        file_path=file_path,
                        line=line_num,
                        confidence=confidence,
                        category="misconfiguration",
                        metadata={"config_pattern": misconfig_name},
                    ))

        return findings

    # ── severity calculation ─────────────────────────────────────────

    def _calculate_severity(self, findings: list) -> str:
        """Aggregate severity across a set of findings."""
        if not findings:
            return "info"

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        best = "info"

        for finding in findings:
            sev = finding.get("severity", "info")
            if severity_order.get(sev, 4) < severity_order.get(best, 4):
                best = sev

        return best

    # ── finding factory ──────────────────────────────────────────────

    def _create_finding(
        self,
        finding_type: str,
        severity: str,
        message: str,
        evidence: str,
        file_path: str,
        line: Optional[int],
        confidence: float,
        category: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Build a security finding dict with required evidence and confidence."""
        return {
            "finding_type": finding_type,
            "severity": severity,
            "message": message,
            "evidence": evidence,
            "file_path": file_path,
            "line": line,
            "confidence": round(confidence, 2),
            "category": category,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

    # ── security summary ─────────────────────────────────────────────

    async def get_security_summary(self, repo_id: str) -> dict:
        """Aggregate summary of all security findings for a repository."""
        all_findings = await self._collect_all_repo_findings(repo_id)

        by_category: dict[str, int] = Counter()
        by_severity: dict[str, int] = Counter()
        by_type: dict[str, int] = Counter()
        files_with_findings: set[str] = set()
        total = 0

        for finding in all_findings:
            by_category[finding.get("category", "unknown")] += 1
            by_severity[finding.get("severity", "info")] += 1
            by_type[finding.get("finding_type", "unknown")] += 1
            fp = finding.get("file_path", "")
            if fp:
                files_with_findings.add(fp)
            total += 1

        avg_confidence = 0.0
        if total > 0:
            avg_confidence = round(
                sum(f.get("confidence", 0) for f in all_findings) / total, 2
            )

        top_risks = sorted(
            all_findings,
            key=lambda f: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(
                    f.get("severity", "info"), 4
                ),
                -f.get("confidence", 0),
            ),
        )[:20]

        file_count_stmt = select(func.count()).where(
            CodeFile.repository_id == UUID(repo_id)
        )
        file_count_result = await self.db.execute(file_count_stmt)
        total_files = file_count_result.scalar() or 0

        coverage_pct = (
            round(len(files_with_findings) / total_files * 100, 1)
            if total_files > 0
            else 0.0
        )

        return {
            "repository_id": repo_id,
            "total_findings": total,
            "by_category": dict(by_category),
            "by_severity": dict(by_severity),
            "by_type": dict(by_type),
            "files_scanned": total_files,
            "files_with_findings": len(files_with_findings),
            "scan_coverage_pct": coverage_pct,
            "avg_confidence": avg_confidence,
            "overall_severity": self._calculate_severity(all_findings),
            "top_risks": top_risks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── false positive filtering ─────────────────────────────────────

    def _is_false_positive_secret(
        self,
        matched_text: str,
        line_text: str,
        file_path: str,
        pattern_name: str,
    ) -> bool:
        lower_line = line_text.lower().strip()

        if lower_line.startswith("//") or lower_line.startswith("#"):
            return True
        if lower_line.startswith("*"):
            return True
        if "example" in lower_line or "placeholder" in lower_line:
            return True
        if "test" in file_path.lower() or "spec" in file_path.lower():
            if pattern_name == "generic_api_key":
                return True
        if "mock" in file_path.lower():
            return True
        if "fake" in file_path.lower():
            return True
        if matched_text in (
            "your-api-key-here", "xxx", "changeme", "todo",
            "REPLACE_ME", "insert_key_here", "sk-xxx",
            "password", "secret",
        ):
            return True
        if len(matched_text) < 8:
            return True

        return False

    def _is_false_positive_injection(
        self, line_text: str, category: str, language: str
    ) -> bool:
        lower = line_text.strip().lower()

        if lower.startswith("//") or lower.startswith("#") or lower.startswith("*"):
            return True
        if "example" in lower or "placeholder" in lower:
            return True
        if "test" in lower and ("assert" in lower or "expect" in lower):
            return True
        if "logging" in lower or "logger" in lower or "log." in lower:
            if category in ("sql_injection",):
                return True
        if '"""' in line_text or "'''" in line_text:
            return True

        return False

    def _is_false_positive_insecure(
        self, line_text: str, pattern_group: str, file_path: str
    ) -> bool:
        lower = line_text.strip().lower()

        if lower.startswith("//") or lower.startswith("#") or lower.startswith("*"):
            return True
        if "example" in lower or "placeholder" in lower:
            return True
        if "test" in file_path.lower() and pattern_group in (
            "insecure_random",
        ):
            return True
        if "migrations" in file_path.lower() and pattern_group == "weak_crypto_md5":
            return True

        return False

    def _is_false_positive_misconfig(
        self, line_text: str, pattern_name: str, file_path: str
    ) -> bool:
        lower = line_text.strip().lower()

        if lower.startswith("#") or lower.startswith("//"):
            return True
        if "example" in lower or "template" in file_path.lower():
            return True
        if "test" in file_path.lower() or "spec" in file_path.lower():
            return True
        if pattern_name == "debug_enabled":
            if "env" in file_path.lower() and "prod" not in file_path.lower():
                return True
        if pattern_name == "cors_wildcard":
            if "test" in file_path.lower() or "dev" in file_path.lower():
                return True
        if pattern_name == "host_binding_wildcard":
            if "docker" in file_path.lower() or "k8s" in file_path.lower():
                return True
            if "compose" in file_path.lower():
                return True

        return False

    # ── severity/confidence helpers ───────────────────────────────────

    def _secret_severity(self, pattern_name: str) -> str:
        high_severity = {
            "private_key_header", "aws_secret_key", "aws_access_key",
            "gcp_service_account", "azure_connection_string", "azure_storage_key",
            "github_token", "stripe_key",
        }
        medium_severity = {
            "generic_api_key", "generic_token", "password_in_code",
            "connection_string", "jwt_token", "slack_token", "heroku_api_key",
            "gcp_api_key", "aws_connection_string",
        }
        if pattern_name in high_severity:
            return "high"
        if pattern_name in medium_severity:
            return "medium"
        return "low"

    def _secret_confidence(
        self,
        pattern_name: str,
        matched_text: str,
        line_text: str,
        file_path: str,
    ) -> float:
        base = 0.6

        high_confidence_patterns = {
            "private_key_header", "github_token", "slack_token", "stripe_key",
            "aws_access_key",
        }
        if pattern_name in high_confidence_patterns:
            base = 0.85

        if "test" in file_path.lower() or "spec" in file_path.lower():
            base -= 0.15
        if "example" in file_path.lower() or "sample" in file_path.lower():
            base -= 0.25
        if "README" in file_path:
            base -= 0.3

        if len(matched_text) > 40:
            base += 0.05

        if "=" in line_text and '""' not in line_text:
            base += 0.05

        return round(max(0.1, min(base, 0.99)), 2)

    def _injection_severity(self, category: str) -> str:
        severity_map = {
            "sql_injection": "critical",
            "command_injection": "critical",
            "path_traversal": "high",
            "deserialization": "high",
            "xss": "medium",
        }
        return severity_map.get(category, "medium")

    def _injection_confidence(
        self,
        category: str,
        line_text: str,
        language: str,
        qualifier: str,
    ) -> float:
        base = 0.55

        if qualifier == "specific":
            base += 0.15

        if "logging" in line_text.lower() or "log." in line_text.lower():
            base -= 0.2
        if "comment" in line_text.lower() or "todo" in line_text.lower():
            base -= 0.3

        if category in ("sql_injection", "command_injection"):
            base += 0.1

        return round(max(0.1, min(base, 0.95)), 2)

    def _insecure_severity(self, pattern_group: str) -> str:
        critical = {"eval_usage", "exec_usage"}
        high = {"disabled_tls_verify", "template_injection", "ssrf"}
        medium = {
            "hardcoded_password", "weak_crypto_md5", "weak_crypto_sha1",
            "weak_crypto_des", "debug_mode_production", "cors_wildcard",
            "open_redirect",
        }
        if pattern_group in critical:
            return "critical"
        if pattern_group in high:
            return "high"
        if pattern_group in medium:
            return "medium"
        return "low"

    def _insecure_confidence(
        self, pattern_group: str, line_text: str, language: str
    ) -> float:
        base = 0.5

        if pattern_group in ("eval_usage", "exec_usage"):
            base = 0.8
        elif pattern_group == "disabled_tls_verify":
            base = 0.75
        elif pattern_group in ("weak_crypto_md5", "weak_crypto_sha1"):
            base = 0.7
        elif pattern_group == "hardcoded_password":
            base = 0.55

        if "test" in line_text.lower():
            base -= 0.15
        if "example" in line_text.lower():
            base -= 0.2

        return round(max(0.1, min(base, 0.95)), 2)

    def _insecure_message(self, pattern_group: str) -> str:
        messages = {
            "eval_usage": "Use of eval() — potential code injection risk",
            "exec_usage": "Use of exec() / Function() — potential code injection risk",
            "hardcoded_password": "Hardcoded credential detected in source code",
            "weak_crypto_md5": "Use of MD5 — cryptographically weak hash algorithm",
            "weak_crypto_sha1": "Use of SHA-1 — cryptographically weak hash algorithm",
            "weak_crypto_des": "Use of DES — weak encryption algorithm",
            "disabled_tls_verify": "TLS certificate verification disabled",
            "debug_mode_production": "Debug mode enabled — may expose sensitive information",
            "cors_wildcard": "CORS configured with wildcard origin",
            "insecure_random": "Use of non-cryptographic random number generator",
            "template_injection": "Potential server-side template injection",
            "open_redirect": "Potential open redirect vulnerability",
            "ssrf": "Potential server-side request forgery (SSRF)",
            "open_redirect_html": "Meta-refresh redirect with user-controlled URL",
        }
        return messages.get(pattern_group, f"Insecure pattern detected: {pattern_group}")

    def _misconfig_severity(self, pattern_name: str) -> str:
        high = {"exposed_secret_in_config", "debug_enabled"}
        medium = {"cors_wildcard", "disabled_csrf", "verbose_error_pages"}
        low = {"host_binding_wildcard", "weak_session_config", "http_only_cookies_disabled"}
        if pattern_name in high:
            return "high"
        if pattern_name in medium:
            return "medium"
        if pattern_name in low:
            return "low"
        return "info"

    def _misconfig_confidence(
        self, pattern_name: str, line_text: str, file_path: str
    ) -> float:
        base = 0.65

        if pattern_name == "debug_enabled":
            base = 0.75
            if ".env.example" in file_path or "template" in file_path.lower():
                base = 0.3
        elif pattern_name == "cors_wildcard":
            base = 0.7
        elif pattern_name == "exposed_secret_in_config":
            base = 0.7
        elif pattern_name == "disabled_csrf":
            base = 0.6

        if "test" in file_path.lower():
            base -= 0.2
        if "example" in file_path.lower() or "template" in file_path.lower():
            base -= 0.3

        return round(max(0.1, min(base, 0.95)), 2)

    def _misconfig_message(self, pattern_name: str) -> str:
        messages = {
            "debug_enabled": "Debug mode is enabled — may expose stack traces and sensitive info",
            "cors_wildcard": "CORS allows all origins (*) — may permit unauthorized cross-origin requests",
            "exposed_secret_in_config": "Secret or API key found in configuration file",
            "host_binding_wildcard": "Service binds to 0.0.0.0 — accessible on all network interfaces",
            "disabled_csrf": "CSRF protection is disabled",
            "verbose_error_pages": "Verbose error pages may expose internal details",
            "weak_session_config": "Session cookie security flag not set",
            "http_only_cookies_disabled": "HTTP-only flag not set on cookies",
        }
        return messages.get(pattern_name, f"Misconfiguration detected: {pattern_name}")

    # ── content extraction helpers ────────────────────────────────────

    @staticmethod
    def _line_of_match(content: str, offset: int) -> int:
        """Return 1-indexed line number for a character offset."""
        return content[:offset].count("\n") + 1

    @staticmethod
    def _extract_snippet(
        lines: list[str], line_num: int, context: int = 2
    ) -> str:
        """Extract a code snippet around the given line number."""
        start = max(0, line_num - 1 - context)
        end = min(len(lines), line_num + context)
        snippet_lines = []
        for i in range(start, end):
            prefix = ">>> " if i == line_num - 1 else "    "
            snippet_lines.append(f"{prefix}{i + 1}: {lines[i]}")
        return "\n".join(snippet_lines)

    # ── database helpers ─────────────────────────────────────────────

    async def _load_indexed_files(
        self, repo_id: str, index_id: str
    ) -> list[CodeFile]:
        stmt = (
            select(CodeFile)
            .where(
                CodeFile.repository_id == UUID(repo_id),
                CodeFile.index_id == UUID(index_id),
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _read_file_content(self, file_row: CodeFile) -> str | None:
        """Read file content from disk given a CodeFile row."""
        try:
            with open(
                file_row.file_path, "r", encoding="utf-8", errors="replace"
            ) as f:
                return f.read()
        except (OSError, IOError, ValueError):
            logger.debug("Cannot read file: %s", file_row.file_path)
            return None

    async def _get_file_path(self, file_id: str) -> str:
        try:
            stmt = select(CodeFile.file_path).where(
                CodeFile.id == UUID(file_id)
            )
            result = await self.db.execute(stmt)
            return result.scalar() or ""
        except (ValueError, TypeError):
            return ""

    async def _collect_all_repo_findings(self, repo_id: str) -> list[dict]:
        """Collect all security findings for a repo by re-scanning indexed files."""
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        all_findings: list[dict] = []
        for file_row in files:
            content = await self._read_file_content(file_row)
            if not content:
                continue

            language = _normalize_lang(file_row.language)
            file_path = file_row.file_path

            try:
                all_findings.extend(self.detect_secrets(content, file_path))
                all_findings.extend(self.detect_injection_risks(content, language))
                all_findings.extend(self.detect_insecure_patterns(content, language))
            except Exception:
                logger.exception(
                    "Security scan failed for file %s during summary", file_path
                )

        dep_findings = await self.detect_dependency_risks(repo_id)
        all_findings.extend(dep_findings)

        misconfig_findings = await self.detect_misconfigurations(repo_id)
        all_findings.extend(misconfig_findings)

        return all_findings
