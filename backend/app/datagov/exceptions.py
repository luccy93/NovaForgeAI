"""Volume 57 — Exceptions alias (re-export from controls + retention holds).

Provides async create_exception, list_exceptions, get_exception, expire_exceptions
and legal-hold alias create_hold/release_hold/is_under_hold.

This module exists to satisfy the spec's "in same file or separate exceptions.py"
clause — the canonical implementation lives in controls.py (ExceptionService) and
retention.py (legal holds). This file re-exports those services so imports from
either path work.
"""

from __future__ import annotations

from app.datagov.controls import ExceptionService, exception_service, control_service  # noqa: F401

# Re-export alias functions for ergonomic import
create_exception = exception_service.create_exception
list_exceptions = exception_service.list_exceptions
get_exception = exception_service.get_exception
is_exception_active = exception_service.is_exception_active
expire_exceptions = exception_service.expire_exceptions
create_hold = exception_service.create_hold
release_hold = exception_service.release_hold
is_under_hold = exception_service.is_under_hold

# Also re-export retention hold alias for direct use
try:
    from app.datagov.retention import RetentionService  # noqa: F401

    retention_service = RetentionService()
except Exception:  # noqa: BLE001
    retention_service = None  # type: ignore

__all__ = [
    "ExceptionService",
    "exception_service",
    "create_exception",
    "list_exceptions",
    "get_exception",
    "is_exception_active",
    "expire_exceptions",
    "create_hold",
    "release_hold",
    "is_under_hold",
    "retention_service",
]
