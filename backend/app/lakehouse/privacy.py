"""Privacy Engine - PII detection, masking, redaction and GDPR-style erasure workflows."""
import re, hashlib, uuid
from dataclasses import dataclass
from typing import Optional


PII_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+(\.[\w-]+)+",
    "phone": r"(?:\+?\d[\d\s().-]{8,}\d)",
    "ssn": r"\d{3}-\d{2}-\d{4}",
    "credit_card": r"(?:\d[ -]?){13,19}",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "iban": r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}",
    "date_of_birth": r"\b\d{4}-\d{2}-\d{2}\b",
}


@dataclass
class PrivacyEvent:
    subject: str  # data subject id
    event_type: str  # access | rectification | erasure | portability
    requested_at: str = ""
    fulfilled_at: str = ""
    payload: Optional[dict] = None
    status: str = "pending"


class PIIInspector:
    """Detects PII inside string values using compiled patterns."""

    def __init__(self, patterns: Optional[dict] = None):
        self.patterns = {**PII_PATTERNS, **(patterns or {})}
        self._compiled = {name: re.compile(pat) for name, pat in self.patterns.items()}

    def inspect_value(self, value: str) -> dict[str, int]:
        out = {}
        if not isinstance(value, str):
            return out
        for name, rx in self._compiled.items():
            count = len(rx.findall(value))
            if count:
                out[name] = count
        return out

    def classify(self, records: list[dict]) -> list[dict]:
        out = []
        for idx, record in enumerate(records):
            found = {}
            for field_name, value in record.items():
                if not isinstance(value, str):
                    continue
                detected = self.inspect_value(value)
                if detected:
                    found[field_name] = {"types": detected,
                                         "matches": sum(detected.values())}
            out.append({"index": idx, "pii_fields": found, "flagged": bool(found)})
        return out

    def has_pii(self, record: dict) -> bool:
        return bool(self.classify([record])[0]["flagged"])


class PrivacyEngine:
    """Applies masking, tokenization, hashing and right-to-be-forgotten operations."""

    def __init__(self, inspector: Optional[PIIInspector] = None):
        self.inspector = inspector or PIIInspector()
        self.operations: list[dict] = []

    def mask(self, records: list[dict], sensitive_types: Optional[list[str]] = None,
             policy: str = "mask") -> list[dict]:
        sensitive_types = list(sensitive_types or
                               ["email", "phone", "ssn", "credit_card", "iban"])
        masked = []
        for record in records:
            copy = dict(record)
            for field_name, value in record.items():
                if not isinstance(value, str):
                    continue
                detected = self.inspector.inspect_value(value)
                if detected and any(t in sensitive_types for t in detected):
                    copy[field_name] = self._transform(value, policy)
            masked.append(copy)
        self.operations.append({"op": "mask", "policy": policy, "records": len(records)})
        return masked

    def _transform(self, value: str, policy: str) -> str:
        if policy == "hash":
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
            return f"h-{digest[:16]}"
        if policy == "token":
            return f"tok-{uuid.uuid4().hex[:12]}"
        if policy == "nullify":
            return ""
        if len(value) > 6:
            return re.sub(r"(?<=.{3}).(?=.{2})", "*", value)
        return "****"

    def right_to_be_forgotten(self, subject: str, tables: dict[str, list[dict]],
                              id_field: str = "id") -> dict:
        """Removes every reference to a subject from the given in-memory tables."""
        removed = {}
        for dataset, rows in tables.items():
            before = len(rows)
            kept = [r for r in rows if str(r.get(id_field)) != subject]
            removed[dataset] = before - len(kept)
            tables[dataset] = kept
        self.operations.append({"op": "rtbf", "subject": subject, "removed": removed})
        return removed

    def report(self) -> dict:
        return {"operation_count": len(self.operations),
                "latest": self.operations[-5:]}