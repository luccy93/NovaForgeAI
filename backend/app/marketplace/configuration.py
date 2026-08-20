"""Typed configuration validation and secret-reference handling.

Package configuration values are validated against the manifest's declared
``configuration`` schema. Secret values are never stored as plaintext: they
are converted to scoped ``${secret:<ref>}`` references.
"""

import re
from typing import Any, Optional

from app.marketplace.manifest import ManifestConfigField

_SECRET_REF_RE = re.compile(r"^\$\{secret:[^}]+\}$")


def validate_configuration(schema_fields: list, values: dict) -> tuple[bool, list, list]:
    """Validate ``values`` against ``schema_fields``.

    Returns ``(valid, errors, secret_refs)``. Secret-typed fields are emitted
    as references rather than stored values.
    """
    errors: list[str] = []
    secret_refs: list[str] = []
    field_map = {f.key: f for f in schema_fields}

    for f in schema_fields:
        present = f.key in values
        if f.required and not present:
            errors.append(f"missing required field: {f.key}")
            continue
        if not present:
            continue
        val = values[f.key]
        if f.type == "secret":
            if isinstance(val, str) and _SECRET_REF_RE.match(val):
                secret_refs.append(val)
            else:
                ref = f"${{secret:{f.key}}}"
                secret_refs.append(ref)
                values[f.key] = ref
            continue
        if f.type == "integer" and not isinstance(val, int):
            try:
                val = int(val)
                values[f.key] = val
            except (TypeError, ValueError):
                errors.append(f"field {f.key} must be an integer")
                continue
        if f.type == "number" and not isinstance(val, (int, float)):
            try:
                val = float(val)
                values[f.key] = val
            except (TypeError, ValueError):
                errors.append(f"field {f.key} must be a number")
                continue
        if f.type == "boolean" and not isinstance(val, bool):
            errors.append(f"field {f.key} must be a boolean")
            continue
        if f.type == "enum" and f.allowed_values and val not in f.allowed_values:
            errors.append(f"field {f.key} must be one of {f.allowed_values}")
            continue
        if f.allowed_values and f.type in ("string", "json") and val not in f.allowed_values:
            errors.append(f"field {f.key} value not allowed: {val}")
            continue

    for key in values:
        if key not in field_map:
            errors.append(f"unknown configuration field: {key}")

    return (len(errors) == 0, errors, secret_refs)


def extract_secret_refs(values: dict) -> list:
    refs = []
    for v in values.values():
        if isinstance(v, str) and _SECRET_REF_RE.match(v):
            refs.append(v)
    return refs
