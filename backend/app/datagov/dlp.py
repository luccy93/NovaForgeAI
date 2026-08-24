"""Volume 57 — DLPService.

Detects attempts to move restricted data to external destinations:
external APIs, public repos, marketplace packages, customer messages,
exports, logs.

Uses classifications.ClassificationService.detect_sensitive + patterns.
Actions: BLOCK / REDACT / WARN / REQUIRE_APPROVAL per policy and
classification. Emits GovernanceDLPEvent with
idempotency_key = sha256(tenant+actor+resource+content_hash).
Never silently allow violations.

Also exposes apply_redaction(text, classification) with masking.

Tenant-scoped, AsyncSession, audit best-effort, never log raw secrets.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.datagov.models import GovernanceDLPEvent

logger = logging.getLogger(__name__)

# ── constants ───────────────────────────────────────────────────────────

_RESTRICTED_LEVELS: set[str] = {"RESTRICTED", "SECRET"}
_HIGH_LEVELS: set[str] = {"CONFIDENTIAL", "RESTRICTED", "SECRET"}

# Destination categories — any match triggers DLP inspection
_EXTERNAL_DESTINATIONS: set[str] = {
    "external_api",
    "external_apis",
    "public_repo",
    "public_repos",
    "public_repository",
    "marketplace",
    "package",
    "packages",
    "package_registry",
    "customer_message",
    "customer_messages",
    "export",
    "exports",
    "log",
    "logs",
    "logging",
    "api",
    "webhook",
    "third_party",
    "third-party",
    "external",
}

# Normalize destination aliases
_DEST_ALIASES: dict[str, str] = {
    "external_api": "external_api",
    "external apis": "external_api",
    "public_repo": "public_repo",
    "public repos": "public_repo",
    "public_repository": "public_repo",
    "marketplace": "marketplace",
    "package": "marketplace",
    "packages": "marketplace",
    "package_registry": "marketplace",
    "customer_message": "customer_message",
    "customer_messages": "customer_message",
    "export": "export",
    "exports": "export",
    "log": "log",
    "logs": "log",
    "logging": "log",
    "api": "external_api",
    "webhook": "external_api",
    "third_party": "external_api",
    "third-party": "external_api",
    "external": "external_api",
}

_VALID_ACTIONS: set[str] = {"BLOCK", "REDACT", "WARN", "REQUIRE_APPROVAL"}
_VALID_LEVELS: set[str] = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "SECRET"}

# Redaction masks per classification
_REDACTION_MASKS: dict[str, str] = {
    "SECRET": "[REDACTED:SECRET]",
    "RESTRICTED": "[REDACTED:RESTRICTED]",
    "CONFIDENTIAL": "[REDACTED]",
    "INTERNAL": "[MASKED]",
    "PUBLIC": "[MASKED]",
}

# Compiled redaction patterns (same sources as ClassificationService)
# Built lazily to avoid import cycle at module load
_REDACTION_COMPILED: list[tuple[str, re.Pattern]] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe_details: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "content", "text", "value", "match", "content_sample"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe_details[k] = v
        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "governance_dlp",
                resource_id,
                "success",
                safe_details,
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_dlp", resource_id, "success", safe_details)
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _normalize_classification(level: str | None) -> str:
    if not level:
        return "INTERNAL"
    lvl = str(level).strip().upper()
    if lvl in _VALID_LEVELS:
        return lvl
    if lvl == "REGULATED":
        return "RESTRICTED"
    return "INTERNAL"


def _normalize_destination(dest: str | None) -> str:
    if not dest:
        return "external_api"
    d = str(dest).strip().lower().replace("-", "_").replace(" ", "_")
    if d in _DEST_ALIASES:
        return _DEST_ALIASES[d]
    # fallback: if contains known substring
    for key, alias in _DEST_ALIASES.items():
        if key in d:
            return alias
    # any string with external/public/marketplace etc triggers external
    for marker in ("external", "public", "marketplace", "package", "customer", "export", "log"):
        if marker in d:
            return _DEST_ALIASES.get(marker, "external_api")
    return d


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _idempotency_key(tenant: str, actor: str, resource: str, content_hash_hex: str) -> str:
    raw = f"{tenant}:{actor}:{resource}:{content_hash_hex}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_redaction_patterns() -> list[tuple[str, re.Pattern]]:
    global _REDACTION_COMPILED
    if _REDACTION_COMPILED is not None:
        return _REDACTION_COMPILED
    compiled: list[tuple[str, re.Pattern]] = []

    # PII patterns
    pii_patterns: dict[str, str] = {}
    try:
        from app.lakehouse.privacy import PII_PATTERNS as _PII  # type: ignore

        pii_patterns = dict(_PII)
    except Exception:
        pii_patterns = {
            "email": r"[\w.+-]+@[\w-]+(\.[\w-]+)+",
            "phone": r"(?:\+?\d[\d\s().-]{8,}\d)",
            "ssn": r"\d{3}-\d{2}-\d{4}",
            "credit_card": r"(?:\d[ -]?){13,19}",
            "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "iban": r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}",
            "date_of_birth": r"\b\d{4}-\d{2}-\d{2}\b",
        }
    for name, pat in pii_patterns.items():
        try:
            compiled.append((name, re.compile(pat)))
        except re.error as exc:
            logger.warning("invalid PII redaction pattern %s: %s", name, exc)

    # Secret patterns
    try:
        from app.security.secret_scanner import SECRET_PATTERNS as _SP  # type: ignore

        for pat in list(_SP):
            name = pat.get("name", "secret")
            pattern = pat.get("pattern", "")
            if not pattern:
                continue
            try:
                compiled.append((name, re.compile(pattern, re.IGNORECASE)))
            except re.error:
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("SECRET_PATTERNS unavailable for redaction: %s", exc)

    _REDACTION_COMPILED = compiled
    return compiled


def apply_redaction(text: str, classification: str | None = None) -> str:
    """Apply masking to text based on classification.

    Replaces every PII/secret match with a mask that includes the
    classification. Never returns raw matched values.

    Args:
        text: input text to redact (up to 200k chars scanned).
        classification: data classification driving mask severity.

    Returns:
        Redacted text with matches replaced by [REDACTED:*] tokens.
    """
    if not text or not isinstance(text, str):
        return text
    level = _normalize_classification(classification)
    mask = _REDACTION_MASKS.get(level, "[REDACTED]")
    # For SECRET/RESTRICTED, use stronger mask that also covers surrounding context lightly
    patterns = _load_redaction_patterns()
    # Work on capped sample
    sample = text[:200_000]
    redacted = sample
    # To avoid overlapping replacements corrupting offsets, collect all matches then replace
    # Simplest: sequential re.sub for each pattern (masks are same token, so idempotent)
    for _name, rx in patterns:
        try:
            redacted = rx.sub(mask, redacted)
        except re.error:
            continue
    # If original was longer than cap, append truncation notice (no raw spill)
    if len(text) > 200_000:
        redacted += f" {mask} [TRUNCATED]"
    # If still no replacement but classification is RESTRICTED/SECRET and text is non-empty,
    # we do not blanket-redact — only pattern-based. Caller decides BLOCK vs REDACT.
    return redacted


def _decide_action(
    classification: str,
    has_sensitive: bool,
    categories: list[str],
    destination: str,
    policy_override: str | None = None,
) -> tuple[str, str]:
    """Decide DLP action. Never silently allow restricted violations.

    Priority:
      SECRET/RESTRICTED + has_sensitive + external/public/marketplace/export/log -> BLOCK
      SECRET/RESTRICTED + has_sensitive + customer_message -> REQUIRE_APPROVAL or BLOCK
      CONFIDENTIAL + has_sensitive + external -> REDACT
      INTERNAL + has_sensitive -> WARN or REDACT
      PUBLIC + has_sensitive -> WARN
      No sensitive -> ALLOW is not a valid DLP action; return WARN or ALLOW-mapped-to-WARN

    Policy override can force BLOCK/REDACT/etc but never downgrade RESTRICTED violation to silent ALLOW.
    """
    if policy_override and policy_override.upper() in _VALID_ACTIONS:
        # Policy can elevate but never silently allow restricted leak
        if has_sensitive and classification in _RESTRICTED_LEVELS and policy_override.upper() == "WARN":
            # elevate WARN to BLOCK for restricted leak
            return "BLOCK", f"policy WARN elevated to BLOCK for {classification} leak to {destination}"
        return policy_override.upper(), f"policy-mandated {policy_override.upper()} for {classification} -> {destination}"

    dest_norm = _normalize_destination(destination)

    # Restricted/secret with sensitive -> BLOCK or REQUIRE_APPROVAL
    if has_sensitive and classification in _RESTRICTED_LEVELS:
        if dest_norm in ("external_api", "public_repo", "marketplace"):
            return "BLOCK", f"restricted data ({classification}) with sensitive categories {categories} blocked to {dest_norm}"
        if dest_norm in ("customer_message", "export", "log"):
            # Customer messages and exports need approval, logs need redaction/block
            if dest_norm == "log":
                return "BLOCK", f"restricted data leak to logs blocked ({classification}: {categories})"
            return "REQUIRE_APPROVAL", f"restricted data to {dest_norm} requires approval ({classification}: {categories})"
        # unknown external still blocked
        return "BLOCK", f"restricted data with sensitive categories {categories} blocked to {dest_norm}"

    if has_sensitive and classification == "CONFIDENTIAL":
        if dest_norm in ("external_api", "public_repo", "marketplace"):
            return "REDACT", f"confidential data with {categories} redacted to {dest_norm}"
        if dest_norm in ("export", "customer_message", "log"):
            return "REDACT", f"confidential data redacted to {dest_norm} ({categories})"
        return "WARN", f"confidential data with {categories} flagged to {dest_norm}"

    if has_sensitive and classification == "INTERNAL":
        # Internal with PII/secrets still needs warning
        if categories:
            return "WARN", f"internal data with {categories} flagged to {dest_norm}"
        return "WARN", f"internal data flagged to {dest_norm}"

    if has_sensitive and classification == "PUBLIC":
        return "WARN", f"public data with unexpected sensitive categories {categories} flagged to {dest_norm}"

    # No sensitive detected — allow would be implicit, but DLP actions do not include ALLOW
    # Map to WARN with low severity or REDACT if policy says so
    return "WARN", f"no sensitive categories detected for {classification} -> {dest_norm} (no violation)"


class DLPService:
    """Data Loss Prevention — scan, block, redact, warn."""

    async def scan(
        self,
        db: AsyncSession,
        tenant: str,
        actor: str,
        destination: str,
        content_sample: str,
        classification: str | None = None,
    ) -> dict[str, Any]:
        """Scan content for restricted-data exfiltration.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant scope (required).
            actor: actor attempting the move (required).
            destination: destination type — external_api, public_repo,
                marketplace, package, customer_message, export, log, etc.
            content_sample: text sample to inspect (required, up to 200k scanned).
            classification: data classification PUBLIC/INTERNAL/CONFIDENTIAL/
                RESTRICTED/SECRET. If None, inferred as INTERNAL but still
                checked via detect_sensitive.

        Returns:
            dict with action (BLOCK/REDACT/WARN/REQUIRE_APPROVAL), reason,
            categories, has_sensitive, redacted (if REDACT), persisted event id,
            idempotency_key, detection. Never contains raw secret values.

        Never silently allow violations: RESTRICTED/SECRET with sensitive data
        to external destinations always returns BLOCK or REQUIRE_APPROVAL even
        on detection failure (fail-closed).

        Emits GovernanceDLPEvent with idempotency_key = sha256(tenant+actor+
        resource+content_hash). Idempotent: duplicate key returns existing event
        with current decision.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not actor or not str(actor).strip():
            raise ValueError("actor is required")
        if not destination or not str(destination).strip():
            raise ValueError("destination is required")
        if content_sample is None or not isinstance(content_sample, str):
            raise ValueError("content_sample is required and must be a string")
        tenant_s = str(tenant).strip()
        actor_s = str(actor).strip()
        dest_s = str(destination).strip()
        dest_norm = _normalize_destination(dest_s)
        classification_s = _normalize_classification(classification)
        sample = content_sample  # keep original for hashing; capped inside detect

        # ── 1. Detect sensitive via ClassificationService ───────────────
        detection: dict[str, Any] = {}
        has_sensitive = False
        categories: list[str] = []
        counts: dict = {}
        fingerprints: list[str] = []
        pii: dict = {}
        secrets: dict = {}
        try:
            from app.datagov.classifications import classification_service  # type: ignore

            svc = classification_service
            # detect_sensitive is sync; try instance method then class
            if hasattr(svc, "detect_sensitive"):
                detection = svc.detect_sensitive(sample)  # type: ignore
            else:
                from app.datagov.classifications import ClassificationService as _CS  # type: ignore

                detection = _CS().detect_sensitive(sample)  # type: ignore
            has_sensitive = bool(detection.get("has_sensitive"))
            categories = list(detection.get("categories") or [])
            counts = dict(detection.get("counts") or {})
            fingerprints = list(detection.get("fingerprints") or [])
            pii = dict(detection.get("pii") or {})
            secrets = dict(detection.get("secrets") or {})
        except Exception as exc:  # noqa: BLE001
            logger.debug("detect_sensitive failed: %s", exc)
            # Fail-closed for restricted: assume sensitive if detection unavailable
            if classification_s in _RESTRICTED_LEVELS:
                has_sensitive = True
                categories = ["detection_unavailable"]
                detection = {"has_sensitive": True, "categories": categories, "counts": {}, "fingerprints": [], "pii": {}, "secrets": {}, "error": str(exc)[:200]}
            else:
                detection = {"has_sensitive": False, "categories": [], "counts": {}, "fingerprints": [], "pii": {}, "secrets": {}, "error": str(exc)[:200]}

        # ── 2. Policy lookup (optional) — governance PolicyEngine DLP rules ─
        policy_action: str | None = None
        try:
            from app.governance.policy_engine import PolicyEngine, PolicyType  # type: ignore

            stor = f"policy_engine_data_{tenant_s}"
            engine: Any | None = None
            for s in (stor, "policy_engine_data"):
                try:
                    eng = PolicyEngine(storage_dir=s)  # type: ignore
                    engine = eng
                    break
                except Exception:
                    continue
            if engine is not None:
                ctx: dict[str, Any] = {
                    "classification": classification_s,
                    "destination": dest_norm,
                    "resource": dest_s,
                    "actor": actor_s,
                    "tenant": tenant_s,
                    "has_sensitive": has_sensitive,
                    "categories": categories,
                    "action": "dlp.scan",
                }
                # Evaluate SECURITY and DATA_RETENTION policies for DLP
                for ptype in (PolicyType.SECURITY, PolicyType.COMPLIANCE, PolicyType.DATA_RETENTION):  # type: ignore
                    try:
                        res = engine.evaluate_and_enforce(tenant_s, ptype, ctx)  # type: ignore
                        if isinstance(res, dict):
                            dec = str(res.get("decision", "")).lower()
                            # Map engine decisions to DLP actions
                            if dec == "denied":
                                policy_action = "BLOCK"
                                break
                            elif dec == "requires_approval":
                                policy_action = "REQUIRE_APPROVAL"
                                # keep looking for BLOCK which is stronger
                            elif dec == "warning" and policy_action not in ("BLOCK", "REQUIRE_APPROVAL"):
                                policy_action = "REDACT"
                    except Exception:
                        continue
        except Exception as exc:  # noqa: BLE001
            logger.debug("DLP policy lookup failed: %s", exc)

        # ── 3. Decide action — never silently allow violation ──────────
        action, reason = _decide_action(classification_s, has_sensitive, categories, dest_norm, policy_override=policy_action)

        # Fail-closed override: if detection error and restricted, already has_sensitive True -> BLOCK
        # Ensure restricted leak never returns WARN silently
        if has_sensitive and classification_s in _RESTRICTED_LEVELS and action == "WARN":
            action = "BLOCK"
            reason = f"elevated WARN to BLOCK for {classification_s} leak to {dest_norm} — fail closed"

        # ── 4. Redaction payload if needed ─────────────────────────────
        redacted_text: str | None = None
        if action == "REDACT":
            try:
                redacted_text = apply_redaction(sample, classification_s)
            except Exception as exc:  # noqa: BLE001
                logger.debug("apply_redaction failed: %s", exc)
                redacted_text = "[REDACTED]"

        # ── 5. Idempotency + emit GovernanceDLPEvent ────────────────────
        chash = _content_hash(sample)
        # resource for idempotency is destination normalized + classification hint
        idem_resource = f"{dest_norm}:{classification_s}"
        idem_key = _idempotency_key(tenant_s, actor_s, idem_resource, chash)

        # Safe details — never persist raw content or secrets, only fingerprints/categories
        details: dict[str, Any] = {
            "classification": classification_s,
            "destination": dest_norm,
            "destination_raw": dest_s[:120],
            "has_sensitive": has_sensitive,
            "categories": categories,
            "counts": counts,
            "fingerprints": fingerprints[:20],
            "pii": pii,
            "secrets": list(secrets.keys()) if isinstance(secrets, dict) else [],
            "action": action,
            "reason": reason[:500],
            "content_length": len(sample),
            "content_hash": _fingerprint(sample),  # sha256[:16] only
            "policy_action": policy_action,
            "redacted": bool(redacted_text is not None),
        }

        event_type = "violation" if action in ("BLOCK", "REQUIRE_APPROVAL") else ("redact" if action == "REDACT" else "warn")
        if action == "REDACT":
            event_type = "redact"
        elif action == "WARN":
            event_type = "warn"

        # Idempotency check: if event with same key exists, return it
        existing: GovernanceDLPEvent | None = None
        try:
            stmt = select(GovernanceDLPEvent).where(GovernanceDLPEvent.idempotency_key == idem_key)
            result = await db.execute(stmt)
            existing = result.scalars().first()
        except Exception as exc:  # noqa: BLE001
            logger.debug("DLP idempotency lookup failed: %s", exc)

        if existing is not None:
            # Update action/details if decision changed? Keep idempotent but refresh details
            # Return existing event info without creating duplicate
            _audit(tenant_s, actor_s, f"governance.dlp.{action.lower()}", dest_s, {"idempotency_hit": True, "existing_id": str(existing.id), "action": action})
            return {
                "action": action,
                "reason": reason,
                "has_sensitive": has_sensitive,
                "categories": categories,
                "counts": counts,
                "fingerprints": fingerprints,
                "redacted": redacted_text,
                "redacted_text": redacted_text,
                "event_id": str(existing.id),
                "idempotency_key": idem_key,
                "detection": detection,
                "existing": True,
                "details": details,
            }

        # Create event
        row = GovernanceDLPEvent(
            tenant=tenant_s,
            event_type=event_type,
            actor=actor_s,
            resource=dest_s[:256],
            action=action,
            details=details,
            idempotency_key=idem_key,
        )
        db.add(row)
        try:
            await db.flush()
            await db.refresh(row)
        except IntegrityError:
            # Race: another scan inserted same key concurrently — fetch existing
            await db.rollback()
            try:
                stmt2 = select(GovernanceDLPEvent).where(GovernanceDLPEvent.idempotency_key == idem_key)
                result2 = await db.execute(stmt2)
                existing2 = result2.scalars().first()
                if existing2 is not None:
                    _audit(tenant_s, actor_s, f"governance.dlp.{action.lower()}", dest_s, {"idempotency_race": True, "existing_id": str(existing2.id), "action": action})
                    return {
                        "action": action,
                        "reason": reason,
                        "has_sensitive": has_sensitive,
                        "categories": categories,
                        "counts": counts,
                        "fingerprints": fingerprints,
                        "redacted": redacted_text,
                        "redacted_text": redacted_text,
                        "event_id": str(existing2.id),
                        "idempotency_key": idem_key,
                        "detection": detection,
                        "existing": True,
                        "details": details,
                    }
            except Exception:
                pass
            # If still no existing, re-raise
            raise
        except Exception:
            # For other flush errors, ensure fail-closed: do not silently allow
            logger.exception("DLP event persist failed — fail closed")
            # Still return BLOCK decision even if persist failed
            if action not in ("BLOCK", "REQUIRE_APPROVAL") and has_sensitive and classification_s in _RESTRICTED_LEVELS:
                action = "BLOCK"
                reason = f"DLP persist failure — fail closed BLOCK for {classification_s} to {dest_norm}"
            return {
                "action": action,
                "reason": reason,
                "has_sensitive": has_sensitive,
                "categories": categories,
                "counts": counts,
                "fingerprints": fingerprints,
                "redacted": redacted_text,
                "redacted_text": redacted_text,
                "event_id": None,
                "idempotency_key": idem_key,
                "detection": detection,
                "existing": False,
                "persist_error": True,
                "details": details,
            }

        _audit(
            tenant_s,
            actor_s,
            f"governance.dlp.{action.lower()}",
            dest_s,
            {
                "classification": classification_s,
                "destination": dest_norm,
                "has_sensitive": has_sensitive,
                "categories": categories,
                "action": action,
                "event_id": str(row.id),
            },
        )

        return {
            "action": action,
            "reason": reason,
            "has_sensitive": has_sensitive,
            "categories": categories,
            "counts": counts,
            "fingerprints": fingerprints,
            "redacted": redacted_text,
            "redacted_text": redacted_text,
            "event_id": str(row.id),
            "idempotency_key": idem_key,
            "detection": detection,
            "existing": False,
            "details": details,
        }


dlp_service = DLPService()
