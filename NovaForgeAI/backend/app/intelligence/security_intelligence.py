"""Security Intelligence — continuous security analysis: secrets, CVEs, injection risk, auth issues, compliance gaps."""

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class SecretFinding:
    file: str
    line: int
    type: str  # api_key, password, private_key, token, connection_string, jwt
    severity: str  # critical, high, medium, low
    value_preview: str
    recommendation: str


@dataclass
class VulnerabilityFinding:
    package: str
    version: str
    cve: str
    severity: str
    description: str
    fixed_in: str
    cvss_score: Optional[float] = None


@dataclass
class PromptInjectionRisk:
    file: str
    line: int
    pattern: str
    risk_level: str
    description: str
    recommendation: str


@dataclass
class AuthFinding:
    file: str
    line: int
    issue: str
    severity: str
    recommendation: str


@dataclass
class SecurityReport:
    repo_id: str
    repo_name: str
    timestamp: str
    secrets: list[SecretFinding] = field(default_factory=list)
    vulnerabilities: list[VulnerabilityFinding] = field(default_factory=list)
    injection_risks: list[PromptInjectionRisk] = field(default_factory=list)
    auth_issues: list[AuthFinding] = field(default_factory=list)
    compliance_gaps: list[dict] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    overall_security_score: float = 100.0


class SecurityIntelligence:
    """Continuous security analysis — secrets, CVE scanning, injection risks, auth issues, compliance."""

    SECRET_PATTERNS = {
        "api_key": (r'(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*["\']?([\w-]{16,})["\']?', "high"),
        "password": (r'(?:password|passwd|pwd)\s*[:=]\s*["\']([^"\']{6,})["\']', "high"),
        "private_key": (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', "critical"),
        "aws_key": (r'(AKIA[0-9A-Z]{16})', "high"),
        "github_token": (r'(gh[pousr]_[A-Za-z0-9]{36})', "high"),
        "npm_token": (r'(npm_[A-Za-z0-9]{36})', "high"),
        "jwt_token": (r'(eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+)', "high"),
        "connection_string": (r'(mongodb(?:\+srv)?://[^\s"\']+|postgresql?://[^\s"\']+|mysql://[^\s"\']+|redis://[^\s"\']+)', "medium"),
        "slack_token": (r'(xox[baprs]-[0-9a-zA-Z-]{10,})', "high"),
        "google_api": (r'(AIza[0-9A-Za-z_-]{35})', "high"),
    }

    INSECURE_CODE_PATTERNS = {
        "eval_usage": (r'\beval\s*\(', 10.0),
        "exec_usage": (r'\bexec\s*\(', 10.0),
        "pickle_load": (r'pickle\.loads?\s*\(', 8.0),
        "shell_injection": (r'(?:os\.system|subprocess\.(?:call|Popen|run)\(.*shell\s*=\s*True)', 9.0),
        "sql_injection": (r'(?:execute|executemany)\(.*[fF]["\'].*\{', 9.0),
        "path_traversal": (r'(?:open|read_text)\(.*\+.*["\']', 7.0),
        "unsafe_yaml": (r'yaml\.load\s*\(', 7.0),
        "insecure_crypto": (r'(?:DES|MD5|SHA1|RC4|ECB)[^_]', 5.0),
        "assert_perimeter": (r'assert\s+\w+\s*[=!]=', 3.0),
    }

    PROMPT_INJECTION_PATTERNS = {
        "direct_user_input": (r'user_message|user_input|user_prompt|user_query', "medium"),
        "unvalidated_prompt": (r'f["\'].*\{.*prompt.*\}["\']', "high"),
        "template_injection": (r'system_template.*\{.*\}.*user_template', "high"),
        "raw_llm_call": (r'(?:openai|anthropic|ollama)\.\w+\.\w+\(.*prompt', "medium"),
        "unchecked_output": (r'response\.choices\[0\]\.message\.content', "low"),
    }

    AUTH_PATTERNS = {
        "missing_auth": (r'@app\.(?:get|post|put|delete|patch)\s*\(.*\)\s*\n\s*async?\s+def\s+\w+\(', "high"),
        "hardcoded_jwt_secret": (r'jwt.*secret.*=.*["\'][a-zA-Z0-9]{1,15}["\']', "critical"),
        "weak_password_policy": (r'password.*len\(.*\)\s*<\s*[0-7]', "medium"),
        "missing_rate_limit": (r'@app\.(?:get|post|put|delete|patch)\s*\(.*\)\s*\n\s*async?\s+def\s+\w+\(', "medium"),
        "insecure_session": (r'session\[["\'](?:user|admin|role)["\']\]\s*=', "medium"),
        "cors_wildcard": (r'allow_origins\s*=\s*\["\*"\]|Access-Control-Allow-Origin:\s*\*', "high"),
    }

    KNOWN_CVES: dict[str, list[dict]] = {
        "lodash": [{"cve": "CVE-2024-23346", "cvss": 7.5, "fixed_in": "4.17.21"}],
        "axios": [{"cve": "CVE-2024-39338", "cvss": 8.1, "fixed_in": "1.7.4"}],
        "requests": [{"cve": "CVE-2024-35195", "cvss": 5.5, "fixed_in": "2.32.0"}],
        "cryptography": [{"cve": "CVE-2024-26130", "cvss": 7.4, "fixed_in": "42.0.4"}],
        "jinja2": [{"cve": "CVE-2024-34064", "cvss": 6.1, "fixed_in": "3.1.4"}],
        "werkzeug": [{"cve": "CVE-2024-34069", "cvss": 5.3, "fixed_in": "3.0.3"}],
        "urllib3": [{"cve": "CVE-2024-37891", "cvss": 6.5, "fixed_in": "2.2.2"}],
        "starlette": [{"cve": "CVE-2024-47874", "cvss": 7.5, "fixed_in": "0.37.2"}],
        "httpx": [{"cve": "CVE-2024-3651", "cvss": 5.3, "fixed_in": "0.27.2"}],
    }

    COMPLIANCE_CHECKS = [
        ("no_encryption_at_rest", r"encrypt|AES|Fernet|bcrypt|argon2", "medium"),
        ("no_tls", r"ssl|tls|https|certificate", "medium"),
        ("no_audit_logging", r"audit|log.*access|logging\.getLogger", "medium"),
        ("no_input_sanitization", r"sanitize|validate|escape|clean_input", "low"),
    ]

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> SecurityReport:
        report = SecurityReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        for file_path in sorted(self.repo_path.rglob("*")):
            if not file_path.is_file() or file_path.suffix not in (
                ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php",
                ".yaml", ".yml", ".env", ".env.example", ".env.sample", ".json", ".tf", ".vue"
            ):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel_path = str(file_path.relative_to(self.repo_path))

            self._scan_secrets(content, rel_path, report)
            self._scan_injection_risks(content, rel_path, report)
            self._scan_auth_issues(content, rel_path, report)
            self._scan_insecure_code(content, rel_path, report)
            self._scan_prompt_injection(content, rel_path, report)

        self._scan_vulnerabilities(report)
        self._scan_compliance_gaps(report)

        report.critical_count = sum(1 for s in report.secrets if s.severity == "critical") + \
                                sum(1 for v in report.vulnerabilities if v.severity == "critical") + \
                                sum(1 for a in report.auth_issues if a.severity == "critical")
        report.high_count = sum(1 for s in report.secrets if s.severity == "high") + \
                            sum(1 for v in report.vulnerabilities if v.severity == "high")
        report.medium_count = sum(1 for s in report.secrets if s.severity == "medium")

        total_issues = (len(report.secrets) * 5 + len(report.vulnerabilities) * 3 +
                        len(report.injection_risks) * 4 + len(report.auth_issues) * 3 +
                        len(report.compliance_gaps) * 2)
        report.overall_security_score = max(0, 100 - min(100, total_issues))

        return report

    def _scan_secrets(self, content: str, rel_path: str, report: SecurityReport):
        for secret_type, (pattern, severity) in self.SECRET_PATTERNS.items():
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                value = match.group(1) if match.lastindex else match.group(0)
                report.secrets.append(SecretFinding(
                    file=rel_path,
                    line=line_num,
                    type=secret_type,
                    severity=severity,
                    value_preview=value[:20] + "..." if len(value) > 20 else value,
                    recommendation=self._secret_recommendation(secret_type),
                ))

    def _scan_injection_risks(self, content: str, rel_path: str, report: SecurityReport):
        for name, (pattern, penalty) in self.INSECURE_CODE_PATTERNS.items():
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                severity = "critical" if penalty > 8 else ("high" if penalty > 5 else "medium")
                report.secrets.append(SecretFinding(
                    file=rel_path,
                    line=line_num,
                    type=f"insecure_code_{name}",
                    severity=severity,
                    value_preview=match.group(0)[:50],
                    recommendation=self._insecure_code_recommendation(name),
                ))

    def _scan_prompt_injection(self, content: str, rel_path: str, report: SecurityReport):
        for risk_type, (pattern, risk_level) in self.PROMPT_INJECTION_PATTERNS.items():
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                report.injection_risks.append(PromptInjectionRisk(
                    file=rel_path,
                    line=line_num,
                    pattern=risk_type,
                    risk_level=risk_level,
                    description=f"Prompt injection risk: {risk_type.replace('_', ' ')}",
                    recommendation=self._prompt_injection_recommendation(risk_type),
                ))

    def _scan_auth_issues(self, content: str, rel_path: str, report: SecurityReport):
        for issue_type, (pattern, severity) in self.AUTH_PATTERNS.items():
            if issue_type == "missing_auth":
                for match in re.finditer(r'@app\.(get|post|put|delete|patch)\s*\(', content):
                    line = content[: match.start()].count("\n") + 1
                    snippet = content[match.end():match.end() + 200]
                    if "login" not in snippet.lower() and "auth" not in snippet.lower() and "public" not in snippet.lower():
                        report.auth_issues.append(AuthFinding(
                            file=rel_path,
                            line=line,
                            issue=f"Endpoint may be missing authentication: @app.{match.group(1)}",
                            severity="high",
                            recommendation="Add authentication decorator or middleware to protect this endpoint",
                        ))
            elif issue_type == "cors_wildcard":
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    line_num = content[: match.start()].count("\n") + 1
                    report.auth_issues.append(AuthFinding(
                        file=rel_path,
                        line=line_num,
                        issue="CORS configured with wildcard origin",
                        severity=severity,
                        recommendation="Restrict CORS to specific trusted origins instead of '*'",
                    ))
            else:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    line_num = content[: match.start()].count("\n") + 1
                    report.auth_issues.append(AuthFinding(
                        file=rel_path,
                        line=line_num,
                        issue=issue_type.replace("_", " ").title(),
                        severity=severity,
                        recommendation=self._auth_recommendation(issue_type),
                    ))

    def _scan_vulnerabilities(self, report: SecurityReport):
        req_files = list(self.repo_path.glob("requirements.txt")) + list(self.repo_path.glob("pyproject.toml"))
        for rf in req_files:
            try:
                content = rf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pkg, cves in self.KNOWN_CVES.items():
                for cve_info in cves:
                    if pkg in content.lower() and cve_info["fixed_in"] not in content:
                        report.vulnerabilities.append(VulnerabilityFinding(
                            package=pkg,
                            version="(check)",
                            cve=cve_info["cve"],
                            severity="high" if cve_info.get("cvss", 0) >= 7 else "medium",
                            description=f"{cve_info['cve']}: Known vulnerability in {pkg}",
                            fixed_in=cve_info["fixed_in"],
                            cvss_score=cve_info.get("cvss"),
                        ))

    def _scan_insecure_code(self, content: str, rel_path: str, report: SecurityReport):
        pass  # handled in _scan_injection_risks via the patterns

    def _scan_compliance_gaps(self, report: SecurityReport):
        all_content = ""
        for f in list(self.repo_path.rglob("*.py"))[:50]:
            try:
                all_content += f.read_text(encoding="utf-8", errors="ignore") + "\n"
            except Exception:
                continue

        for check_name, pattern, severity in self.COMPLIANCE_CHECKS:
            if not re.search(pattern, all_content, re.IGNORECASE):
                report.compliance_gaps.append({
                    "check": check_name.replace("_", " ").title(),
                    "severity": severity,
                    "finding": f"No evidence of {check_name.replace('_', ' ')} implementation",
                    "recommendation": f"Implement {check_name.replace('_', ' ')} measures",
                })

    def _secret_recommendation(self, secret_type: str) -> str:
        recs = {
            "api_key": "Use environment variables or a secrets manager. Rotate the exposed key immediately.",
            "password": "Remove hardcoded passwords. Use environment variables or vault services.",
            "private_key": "REVOKE THIS KEY IMMEDIATELY. Use a hardware security module or key management service.",
            "aws_key": "Revoke this AWS key in IAM. Use IAM roles or AWS Secrets Manager.",
            "github_token": "Revoke this token in GitHub settings. Use GitHub Actions secrets or OIDC.",
            "npm_token": "Revoke this npm token. Use npm token rotation.",
            "jwt_token": "This is a live JWT. Rotate the signing key immediately.",
            "connection_string": "Use environment variables. Restrict database access by IP.",
            "slack_token": "Revoke this Slack token immediately.",
            "google_api": "Revoke this API key in Google Cloud Console. Restrict by HTTP referrer and API.",
        }
        return recs.get(secret_type, "Remove the exposed secret and use a secure alternative.")

    def _insecure_code_recommendation(self, name: str) -> str:
        recs = {
            "eval_usage": "Replace eval() with ast.literal_eval() or a proper parser.",
            "exec_usage": "Replace exec() with function calls or method dispatch.",
            "pickle_load": "Use json or a safer serialization format. Never unpickle untrusted data.",
            "shell_injection": "Use subprocess with argument list (shell=False) instead of strings.",
            "sql_injection": "Use parameterized queries: cursor.execute('SELECT * FROM t WHERE id = %s', (val,))",
            "path_traversal": "Use os.path.realpath() and validate user-supplied path components.",
            "unsafe_yaml": "Use yaml.safe_load() instead of yaml.load().",
            "insecure_crypto": "Use modern algorithms: AES-256-GCM, ChaCha20-Poly1305, Argon2.",
            "assert_perimeter": "Use proper validation logic instead of assert statements.",
        }
        return recs.get(name, "Review and fix this security issue.")

    def _auth_recommendation(self, issue_type: str) -> str:
        recs = {
            "missing_auth": "Add @login_required decorator or authentication middleware to all endpoints",
            "hardcoded_jwt_secret": "Use a strong randomly generated secret via environment variable (min 32 chars)",
            "weak_password_policy": "Enforce minimum 8 characters, mixed case, numbers, and special characters",
            "missing_rate_limit": "Implement rate limiting (slowapi, express-rate-limit, etc.)",
            "insecure_session": "Use server-side sessions with secure cookies (httponly, samesite, secure)",
            "cors_wildcard": "Restrict CORS to specific origins instead of wildcard '*'",
        }
        return recs.get(issue_type, "Review and fix authentication/authorization issue.")

    def _prompt_injection_recommendation(self, risk_type: str) -> str:
        recs = {
            "direct_user_input": "Sanitize and validate user input before passing to LLM prompts",
            "unvalidated_prompt": "Use input validation and prompt templates with strict variable interpolation",
            "template_injection": "Use structured prompt templates with proper escaping",
            "raw_llm_call": "Add prompt validation layer before sending to LLM API",
            "unchecked_output": "Validate and sanitize LLM output before using in application logic",
        }
        return recs.get(risk_type, "Review prompt injection risk and implement mitigations.")

    def get_summary(self, report: SecurityReport) -> dict[str, Any]:
        return {
            "secrets_found": len(report.secrets),
            "vulnerabilities_found": len(report.vulnerabilities),
            "injection_risks": len(report.injection_risks),
            "auth_issues": len(report.auth_issues),
            "compliance_gaps": len(report.compliance_gaps),
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "security_score": report.overall_security_score,
            "top_secrets": [s.type for s in report.secrets[:5]],
            "top_cves": [v.cve for v in report.vulnerabilities[:5]],
        }
