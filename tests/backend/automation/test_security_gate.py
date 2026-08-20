"""Tests for security gate: secret scanning, SAST, policy checks."""

import pytest
from app.automation.security_gate import SecurityGate


def test_clean_diff():
    gate = SecurityGate()
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new"
    result = gate.validate_patch(diff)
    assert result["clean"] is True
    assert result["blocks_delivery"] is False


def test_detects_hardcoded_password():
    gate = SecurityGate()
    diff = 'password = "super_secret_123"'
    result = gate.validate_patch(diff)
    assert result["clean"] is False
    assert result["blocks_delivery"] is True
    assert any(f["type"] == "hardcoded_password" for f in result["findings"])


def test_detects_eval():
    gate = SecurityGate()
    diff = 'result = eval(user_input)'
    result = gate.validate_patch(diff)
    assert any(f["type"] == "eval_usage" for f in result["findings"])


def test_detects_aws_key():
    gate = SecurityGate()
    diff = "key = AKIAIOSFODNN7EXAMPLE"
    result = gate.validate_patch(diff)
    assert any(f["severity"] == "critical" for f in result["findings"])


def test_detects_github_token():
    gate = SecurityGate()
    diff = "token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop"
    result = gate.validate_patch(diff)
    assert any(f["type"] == "secret_exposure" for f in result["findings"])


def test_detects_openai_key():
    gate = SecurityGate()
    diff = "api_key = sk-proj1234567890abcdefghijklmnopqrstuvwx"
    result = gate.validate_patch(diff)
    assert any(f["type"] == "secret_exposure" for f in result["findings"])


def test_detects_ssl_disable():
    gate = SecurityGate()
    diff = "requests.get(url, verify=False)"
    result = gate.validate_patch(diff)
    assert any(f["type"] == "disable_ssl" for f in result["findings"])


def test_detects_debug_mode():
    gate = SecurityGate()
    diff = "DEBUG = True"
    result = gate.validate_patch(diff)
    assert any(f["type"] == "debug_mode" for f in result["findings"])


def test_detects_sql_injection():
    gate = SecurityGate()
    diff = 'cursor.execute("SELECT * FROM users WHERE id = %s", user_id)'
    result = gate.validate_patch(diff)
    assert any(f["type"] == "sql_injection" for f in result["findings"])


def test_file_changes_scan():
    gate = SecurityGate()
    changes = [
        {"path": "config.py", "content": 'password = "abc123"'},
        {"path": "main.py", "content": "print('hello')"},
    ]
    result = gate.scan_file_changes(changes)
    assert result["clean"] is False
    assert any(f["file"] == "config.py" for f in result["findings"])


def test_multiple_findings():
    gate = SecurityGate()
    diff = 'password = "test"\nresult = eval(x)\nrequests.get(url, verify=False)'
    result = gate.validate_patch(diff)
    assert len(result["findings"]) >= 3
    assert result["critical_count"] >= 2


def test_custom_blocked_patterns():
    gate = SecurityGate(blocked_patterns={"disable_ssl"})
    diff = "requests.get(url, verify=False)"
    result = gate.validate_patch(diff)
    assert result["blocks_delivery"] is True


def test_safe_code():
    gate = SecurityGate()
    diff = """
def add(a, b):
    return a + b

def greet(name: str) -> str:
    return f"Hello, {name}"
"""
    result = gate.validate_patch(diff)
    assert result["clean"] is True
    assert len(result["findings"]) == 0
