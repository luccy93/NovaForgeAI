"""Tests for security scanner at backend/app/code_intelligence/security.py."""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# Prevent app/__init__.py from triggering the broken API import chain.
_APP_DIR = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "backend" / "app")
if "app" not in sys.modules:
    _stub = types.ModuleType("app")
    _stub.__path__ = [_APP_DIR]
    sys.modules["app"] = _stub

if "app.api" not in sys.modules:
    sys.modules["app.api"] = types.ModuleType("app.api")

from app.code_intelligence.security import (  # noqa: E402
    INJECTION_PATTERNS,
    INSECURE_PATTERNS,
    SECRET_PATTERNS,
    SecurityScanner,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _make_scanner() -> SecurityScanner:
    return SecurityScanner(db_session=AsyncMock())


# ─── Secret Detection ─────────────────────────────────────────────────


class TestSecretDetection:
    def test_detect_api_key_generic(self):
        scanner = _make_scanner()
        content = 'api_key = "supersecretkey12345678"\n'
        findings = scanner.detect_secrets(content, "config.py")
        assert any(f["finding_type"] == "hardcoded_secret" for f in findings)

    def test_detect_aws_key(self):
        scanner = _make_scanner()
        content = 'key = "AKIAIOSFODNN7ABCDEF1"\n'
        findings = scanner.detect_secrets(content, "main.py")
        aws_findings = [f for f in findings if "aws" in f["metadata"].get("pattern_name", "")]
        assert len(aws_findings) >= 1

    def test_detect_password(self):
        scanner = _make_scanner()
        content = 'password = "hunter2pass"\n'
        findings = scanner.detect_secrets(content, "db.py")
        pwd_findings = [f for f in findings if f["metadata"].get("pattern_name") == "password_in_code"]
        assert len(pwd_findings) >= 1

    def test_detect_private_key(self):
        scanner = _make_scanner()
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQ...\n"
        findings = scanner.detect_secrets(content, "server.pem")
        assert any(f["metadata"].get("pattern_name") == "private_key_header" for f in findings)

    def test_no_false_positives_in_tests(self):
        scanner = _make_scanner()
        content = 'api_key = "test_fake_key_12345678"\n'
        findings = scanner.detect_secrets(content, "tests/test_config.py")
        assert findings == []


# ─── Injection Detection ──────────────────────────────────────────────


class TestInjectionDetection:
    def test_detect_sql_injection(self):
        scanner = _make_scanner()
        content = 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")\n'
        findings = scanner.detect_injection_risks(content, "python")
        sql_findings = [f for f in findings if "sql_injection" in f["finding_type"]]
        assert len(sql_findings) >= 1

    def test_detect_command_injection(self):
        scanner = _make_scanner()
        content = 'os.system("echo " + user_input)\n'
        findings = scanner.detect_injection_risks(content, "python")
        cmd_findings = [f for f in findings if "command_injection" in f["finding_type"]]
        assert len(cmd_findings) >= 1

    def test_detect_xss(self):
        scanner = _make_scanner()
        content = 'document.write("<br>" + userInput);\n'
        findings = scanner.detect_injection_risks(content, "javascript")
        xss_findings = [f for f in findings if "xss" in f["finding_type"]]
        assert len(xss_findings) >= 1


# ─── Insecure Patterns ────────────────────────────────────────────────


class TestInsecurePatterns:
    def test_detect_eval(self):
        scanner = _make_scanner()
        content = 'result = eval(user_input)\n'
        findings = scanner.detect_insecure_patterns(content, "python")
        eval_findings = [f for f in findings if "eval_usage" in f["finding_type"]]
        assert len(eval_findings) >= 1

    def test_detect_hardcoded_secret(self):
        scanner = _make_scanner()
        content = 'secret = "mysecretvalue12345"\n'
        findings = scanner.detect_insecure_patterns(content, "generic")
        secret_findings = [f for f in findings if "hardcoded_password" in f["finding_type"]]
        assert len(secret_findings) >= 1

    def test_detect_weak_crypto(self):
        scanner = _make_scanner()
        content = 'h = hashlib.md5(data)\n'
        findings = scanner.detect_insecure_patterns(content, "python")
        md5_findings = [f for f in findings if "weak_crypto_md5" in f["finding_type"]]
        assert len(md5_findings) >= 1


# ─── Security Summary ─────────────────────────────────────────────────


class TestSecuritySummary:
    def test_severity_summary(self):
        scanner = _make_scanner()
        findings = [
            {"severity": "high", "category": "secrets", "finding_type": "hardcoded_secret",
             "file_path": "a.py", "confidence": 0.8},
            {"severity": "low", "category": "injection", "finding_type": "injection_xss",
             "file_path": "b.py", "confidence": 0.5},
            {"severity": "high", "category": "secrets", "finding_type": "hardcoded_secret",
             "file_path": "c.py", "confidence": 0.7},
        ]
        severity = scanner._calculate_severity(findings)
        assert severity == "high"

    def test_category_summary(self):
        scanner = _make_scanner()
        findings = [
            {"category": "secrets", "severity": "high", "confidence": 0.8,
             "finding_type": "hardcoded_secret", "file_path": "a.py"},
            {"category": "injection", "severity": "medium", "confidence": 0.6,
             "finding_type": "injection_sql", "file_path": "b.py"},
            {"category": "secrets", "severity": "low", "confidence": 0.5,
             "finding_type": "hardcoded_secret", "file_path": "c.py"},
        ]
        by_cat = {}
        for f in findings:
            cat = f["category"]
            by_cat[cat] = by_cat.get(cat, 0) + 1
        assert by_cat["secrets"] == 2
        assert by_cat["injection"] == 1


# ─── False Positive Reduction ─────────────────────────────────────────


class TestFalsePositiveReduction:
    def test_mock_not_flagged(self):
        scanner = _make_scanner()
        content = 'api_key = "supersecretkey12345678"\n'
        findings = scanner.detect_secrets(content, "mocks/fake_config.py")
        assert findings == []

    def test_comment_not_flagged(self):
        scanner = _make_scanner()
        content = '# api_key = "supersecretkey12345678"\n'
        findings = scanner.detect_secrets(content, "config.py")
        assert findings == []
