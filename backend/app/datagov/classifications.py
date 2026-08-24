"""Volume 57 — ClassificationService.

Levels PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED/SECRET (configurable, seeded
with these 5). Persists to governance_classifications. detect_sensitive is
a sync helper that combines lakehouse.privacy PII_PATTERNS and
security.secret_scanner SECRET_PATTERNS but returns only categories and
sha256[:16] fingerprints — never raw secret/PII values. auto_classify is an
advisory AI path that stores with advisory=True.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceClassification

logger = logging.getLogger(__name__)


# ── Configurable classification levels (seeded with 5) ──────────────────

CLASSIFICATION_LEVELS: list[str] = [
    "PUBLIC",
    "INTERNAL",
    "CONFIDENTIAL",
    "RESTRICTED",
    "SECRET",
]

# ordering for severity — higher index = more sensitive
_LEVEL_RANK: dict[str, int] = {lvl: idx for idx, lvl in enumerate(CLASSIFICATION_LEVELS)}

ALLOWED_SOURCES: set[str] = {"schema", "user", "scanner", "policy", "provider", "ai"}

# advisory-aware: AI classifications stored advisory unless policy promotes
ADVISORY_SOURCES: set[str] = {"ai"}


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "governance_classification",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_classification", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _fingerprint(value: str) -> str:
    """sha256[:16] fingerprint — never persist raw value."""
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _load_pii_patterns() -> dict[str, str]:
    try:
        from app.lakehouse.privacy import PII_PATTERNS as _PII  # type: ignore

        return dict(_PII)
    except Exception as exc:  # noqa: BLE001
        logger.debug("PII_PATTERNS unavailable: %s", exc)
        return {
            "email": r"[\w.+-]+@[\w-]+(\.[\w-]+)+",
            "phone": r"(?:\+?\d[\d\s().-]{8,}\d)",
            "ssn": r"\d{3}-\d{2}-\d{4}",
            "credit_card": r"(?:\d[ -]?){13,19}",
            "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "iban": r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}",
            "date_of_birth": r"\b\d{4}-\d{2}-\d{2}\b",
        }


def _load_secret_patterns() -> list[dict]:
    try:
        from app.security.secret_scanner import SECRET_PATTERNS as _SP  # type: ignore

        return list(_SP)
    except Exception as exc:  # noqa: BLE001
        logger.debug("SECRET_PATTERNS unavailable: %s", exc)
        return []


_PII_PATTERNS: dict[str, str] = _load_pii_patterns()
_SECRET_PATTERNS: list[dict] = _load_secret_patterns()

# pre-compile PII
_PII_COMPILED: dict[str, re.Pattern] = {}
for _k, _pat in _PII_PATTERNS.items():
    try:
        _PII_COMPILED[_k] = re.compile(_pat)
    except re.error as exc:
        logger.warning("invalid PII pattern %s: %s", _k, exc)


class ClassificationService:
    """Governance classification — levels configurable, no raw secrets persisted."""

    def __init__(self, levels: list[str] | None = None):
        if levels:
            self.levels = [lvl.upper() for lvl in levels]
            # rebuild rank
            self._rank = {lvl: idx for idx, lvl in enumerate(self.levels)}
        else:
            self.levels = list(CLASSIFICATION_LEVELS)
            self._rank = dict(_LEVEL_RANK)

    # ── core classify ───────────────────────────────────────────────────

    async def classify(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        level: str,
        source: str,
        confidence: float = 0.95,
        evidence: dict | None = None,
        classified_by: str | None = None,
        advisory: bool = False,
    ) -> GovernanceClassification:
        """Persist a classification decision.

        Args:
            tenant, asset_id: identity.
            level: one of CLASSIFICATION_LEVELS (case-insensitive).
            source: schema|user|scanner|policy|provider|ai
            confidence: 0.0-1.0
            evidence: metadata only — must not contain raw secrets/PII values.
            classified_by: actor id.
            advisory: True for AI advisory classifications (stored but not enforced
                      unless policy promotes).

        Returns: persisted GovernanceClassification row.
        """
        if not tenant or not asset_id:
            raise ValueError("tenant and asset_id are required")
        lvl = level.upper().strip()
        if lvl not in self.levels:
            raise ValueError(f"unknown classification level '{level}'; allowed: {self.levels}")
        src = source.lower().strip()
        if src not in ALLOWED_SOURCES:
            raise ValueError(f"unknown source '{source}'; allowed: {sorted(ALLOWED_SOURCES)}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

        # AI source should be advisory by default unless caller explicitly says False via policy
        if src == "ai" and not advisory:
            # allow explicit non-advisory only when caller is policy promotion path;
            # default to advisory if evidence came from auto_classify — caller passes advisory=True
            # Here we do not force; we respect caller value but log when non-advisory AI used
            logger.debug("AI classification stored non-advisory for %s/%s", tenant, asset_id)

        # sanitize evidence: ensure no raw secret values leak — only keep fingerprints/categories
        safe_evidence: dict = {}
        if evidence:
            # shallow copy; caller responsible for not passing raw values, but we strip known leak keys
            for k, v in evidence.items():
                if k in ("raw_value", "secret", "match", "value"):
                    continue
                safe_evidence[k] = v
            # if raw_value sneaks in nested dicts, remove at one depth
            for kk in list(safe_evidence.keys()):
                if isinstance(safe_evidence[kk], dict) and "raw_value" in safe_evidence[kk]:
                    safe_evidence[kk] = {ik: iv for ik, iv in safe_evidence[kk].items() if ik != "raw_value"}

        row = GovernanceClassification(
            asset_id=asset_id,
            tenant=tenant,
            level=lvl,
            source=src,
            confidence=float(confidence),
            advisory=bool(advisory),
            evidence=safe_evidence,
            classified_by=classified_by,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(
            tenant,
            classified_by or "system",
            "governance.data.classified",
            asset_id,
            {"level": lvl, "source": src, "confidence": confidence, "advisory": bool(advisory)},
        )
        return row

    # ── detect_sensitive (sync helper) ──────────────────────────────────

    def detect_sensitive(self, text: str) -> dict[str, Any]:
        """Combine lakehouse PII_PATTERNS + secret_scanner patterns.

        Returns categories + fingerprints only — never raw values.

        Output shape:
        {
            "categories": ["email","ssn","aws_access_key",...],
            "fingerprints": ["abc123...","def456...", ...],  # sha256[:16] per match
            "counts": {"email": 2, "aws_access_key": 1},
            "has_sensitive": True,
            "pii": {"email": 2, ...},
            "secrets": {"aws_access_key": 1, ...}
        }
        """
        if not text or not isinstance(text, str):
            return {"categories": [], "fingerprints": [], "counts": {}, "has_sensitive": False, "pii": {}, "secrets": {}}

        # cap text length to avoid regex DoS on huge inputs
        sample = text[:200_000]

        counts: dict[str, int] = {}
        pii_counts: dict[str, int] = {}
        secret_counts: dict[str, int] = {}
        fps: list[str] = []
        categories: list[str] = []

        # PII detection
        for name, rx in _PII_COMPILED.items():
            try:
                matches = rx.findall(sample)
                # findall may return tuples for groups; normalize to list of strings
                n = len(matches)
                if n:
                    # extract raw strings for fingerprinting via finditer (more accurate than findall)
                    fp_for_type = 0
                    for m in rx.finditer(sample):
                        raw = m.group(0)
                        fps.append(_fingerprint(raw))
                        fp_for_type += 1
                        if fp_for_type >= 20:
                            break  # cap fingerprints per type to avoid explosion
                    pii_counts[name] = n
                    counts[name] = counts.get(name, 0) + n
            except re.error:
                continue

        # Secret detection — SECRET_PATTERNS have dict with name/pattern
        for pat in _SECRET_PATTERNS:
            name = pat.get("name", "secret")
            pattern = pat.get("pattern", "")
            if not pattern:
                continue
            try:
                rx = re.compile(pattern, re.IGNORECASE)
            except re.error:
                continue
            try:
                found = list(rx.finditer(sample))
                if found:
                    secret_counts[name] = len(found)
                    counts[name] = counts.get(name, 0) + len(found)
                    for m in found[:20]:
                        raw = m.group(0)
                        fps.append(_fingerprint(raw))
            except re.error:
                continue

        categories = sorted(counts.keys())
        # fingerprints are already hashes — no raw value stored
        # de-duplicate fingerprints while preserving order
        seen: set[str] = set()
        uniq_fps: list[str] = []
        for h in fps:
            if h not in seen:
                seen.add(h)
                uniq_fps.append(h)

        return {
            "categories": categories,
            "fingerprints": uniq_fps,
            "counts": counts,
            "has_sensitive": bool(categories),
            "pii": pii_counts,
            "secrets": secret_counts,
        }

    # ── auto_classify (advisory) ────────────────────────────────────────

    async def auto_classify(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        content_sample: str,
    ) -> GovernanceClassification:
        """Auto-classify asset from sample text (advisory).

        Uses detect_sensitive + PII; never persists raw values. Returns an
        advisory classification row (source=ai, advisory=True) so policy
        can promote if needed.
        """
        result = self.detect_sensitive(content_sample or "")
        cats: list[str] = result.get("categories", [])
        pii: dict = result.get("pii", {})
        secrets: dict = result.get("secrets", {})

        # decide level by sensitivity hierarchy
        # secrets or highly sensitive PII => SECRET/RESTRICTED
        # financial/credentials => RESTRICTED
        # email/phone/ip => CONFIDENTIAL
        # otherwise => INTERNAL (never auto PUBLIC from content alone without policy)
        level = "INTERNAL"
        confidence = 0.75

        # secret patterns present -> most sensitive
        if secrets:
            # any critical secret -> SECRET, else RESTRICTED
            # SECRET_PATTERNS severity critical vs high — approximate by count
            level = "SECRET"
            confidence = 0.92
        elif any(k in pii for k in ("ssn", "credit_card", "iban")):
            # financial/identity PII
            level = "RESTRICTED"
            confidence = 0.90
        elif any(k in pii for k in ("email", "phone", "ip_address", "date_of_birth")):
            level = "CONFIDENTIAL"
            # confidence scales with number of distinct PII types
            distinct = len([k for k in pii if pii[k] > 0])
            confidence = 0.80 if distinct == 1 else 0.86
        elif cats:
            level = "CONFIDENTIAL"
            confidence = 0.78
        else:
            level = "INTERNAL"
            confidence = 0.70

        # evidence: categories, counts, fingerprints (hashes), no raw
        evidence = {
            "detector": "auto_classify",
            "categories": cats,
            "counts": result.get("counts", {}),
            "pii": pii,
            "secrets": secrets,
            "fingerprints": result.get("fingerprints", [])[:20],  # cap stored fingerprints
            "sample_length": len(content_sample or ""),
        }

        return await self.classify(
            db,
            tenant=tenant,
            asset_id=asset_id,
            level=level,
            source="ai",
            confidence=confidence,
            evidence=evidence,
            classified_by="auto",
            advisory=True,
        )


classification_service = ClassificationService()
