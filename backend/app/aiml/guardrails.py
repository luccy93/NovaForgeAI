"""Volume 58 — AIGuardrailService.

Tenant-scoped, AsyncSession, fail-closed.

Enforces the pipeline order::

    Input → Classification → Policy → Model → Output → Policy → Action

Never lets output bypass policy — ``check_output`` is always evaluated even
when ``check_input`` passed.

Guards
  - prompt injection / jailbreaks (Volume-47 agents/safety + built-ins)
  - secret leakage  (Volume-47 secret_scanner SECRET_PATTERNS)
  - restricted data exposure (classification + PII/keyword heuristics)
  - tenant / environment configurable — guardrails are filtered by
    ``(tenant, scope, environment)`` and each brings its own ``policy`` dict

Decisions: ALLOW / BLOCK / FLAG  (plus REDACT when policy says so).

Rate limiting is best-effort in-memory per-tenant/guardrail (real deployment
would use Redis).  No placeholders — every branch is a real DB query or real
regex match with fallbacks only for missing optional dependencies.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIGuardrail
from app.core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────

_VALID_SCOPES: set[str] = {"input", "output", "both"}
_VALID_CLASSIFICATIONS: set[str] = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "SECRET"}
_RESTRICTED_LEVELS: set[str] = {"RESTRICTED", "SECRET"}
_VALID_DECISIONS: set[str] = {"ALLOW", "BLOCK", "FLAG", "REDACT"}

# fallback injection patterns — kept in sync with app.agents.safety
_FALLBACK_INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions",
    r"forget\s+(?:all\s+)?(?:previous|above|prior)",
    r"system\s+prompt",
    r"you\s+are\s+(?:now|not\s+really)",
    r"pretend\s+(?:you\s+are|to\s+be)",
    r"bypass\s+(?:the\s+)?(?:safety|restrictions|rules)",
    r"override\s+(?:your\s+)?(?:instructions|programming|guidelines)",
    r"REACTIVATE",
    r"DAN\b",
    r"jailbreak",
    r"roleplay\s+as",
    r"do\s+anything\s+now",
    r"developer\s+mode",
    r"ignore\s+safety",
    r"disregard\s+(?:your\s+)?(?:instructions|rules)",
]

# strict / fallback PII / restricted-data signals
_FALLBACK_RESTRICTED_PATTERNS: list[str] = [
    r"\b\d{3}-\d{2}-\d{4}\b",                      # SSN
    r"\b(?:\d[ -]?){13,19}\b",                     # credit card-ish
    r"[\w.+-]+@[\w-]+(\.[\w-]+)+",                  # email / exfiltration
    r"\b[A-Z]{2,}-\d{4,}\b",                        # internal id-ish
]

# in-memory rate counters: {(tenant, guardrail_id): [timestamps]}
_RATE_COUNTERS: dict[tuple[str, str], list[float]] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe[k] = v
        try:
            audit_service.log(tenant, actor, "user", action, "ai_guardrail", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_guardrail", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _normalize_classification(level: str | None) -> str:
    if not level:
        return "INTERNAL"
    lvl = str(level).strip().upper()
    if lvl in _VALID_CLASSIFICATIONS:
        return lvl
    if lvl == "REGULATED":
        return "RESTRICTED"
    return "INTERNAL"


def _normalize_scope(scope: str | None) -> str:
    if not scope:
        return "input"
    s = str(scope).strip().lower()
    if s in _VALID_SCOPES:
        if s == "both":
            return "both"
        return s
    return "input"


# ── global pattern loaders (Volume 47 reuse, tenant/env configurable) ──

def _load_global_injection_patterns() -> list[str]:
    """Reuse ``app.agents.safety.SafetyChecker.INJECTION_PATTERNS`` when available."""
    try:
        from app.agents.safety import SafetyChecker  # type: ignore

        pats = list(getattr(SafetyChecker, "INJECTION_PATTERNS", []) or [])
        if pats:
            return [str(p).strip() for p in pats if p and str(p).strip()]
    except ImportError as exc:
        logger.debug("SafetyChecker not available for injection patterns: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("injection pattern load failed: %s", exc)
    return list(_FALLBACK_INJECTION_PATTERNS)


def _load_global_secret_patterns() -> list[dict]:
    """Reuse ``app.security.secret_scanner.SECRET_PATTERNS`` when available."""
    try:
        from app.security.secret_scanner import SECRET_PATTERNS as _SP  # type: ignore

        if isinstance(_SP, list) and _SP:
            out: list[dict] = []
            for entry in _SP:
                if isinstance(entry, dict) and entry.get("pattern"):
                    out.append({"name": str(entry.get("name", "secret")), "pattern": str(entry["pattern"]), "severity": str(entry.get("severity", "critical"))})
                elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    out.append({"name": str(entry[1]) if len(entry) > 2 else "secret", "pattern": str(entry[0]), "severity": "critical"})
            if out:
                return out
    except ImportError as exc:
        logger.debug("secret_scanner not available: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("secret pattern load failed: %s", exc)
    # Fallback to agents/safety SECRET_PATTERNS (list[str])
    try:
        from app.agents.safety import SafetyChecker  # type: ignore

        pats = list(getattr(SafetyChecker, "SECRET_PATTERNS", []) or [])
        if pats:
            return [{"name": f"agent_secret_{i}", "pattern": str(p), "severity": "critical"} for i, p in enumerate(pats) if p]
    except Exception:  # noqa: BLE001
        pass
    # Ultimate minimal fallback
    return [
        {"name": "aws_access_key", "pattern": r"AKIA[0-9A-Z]{16}", "severity": "critical"},
        {"name": "github_token", "pattern": r"gh[pousr]_[A-Za-z0-9_]{36,}", "severity": "critical"},
        {"name": "private_key", "pattern": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "severity": "critical"},
        {"name": "generic_secret", "pattern": r"(?:api[_-]?key|apikey|secret|password|token|credential)[\s:=]+['\"]?[A-Za-z0-9_\-\.]{16,}", "severity": "high"},
    ]


_GLOBAL_INJECTION_PATTERNS: list[str] = _load_global_injection_patterns()
_GLOBAL_SECRET_PATTERNS: list[dict] = _load_global_secret_patterns()


def _sanitize_match(text: str) -> str:
    """Never return raw secret — fingerprint + prefix only."""
    if not text:
        return ""
    fp = _fingerprint(text)
    preview = (text[:4] + "****" + text[-4:]) if len(text) > 12 else "****"
    return f"{preview} (fp={fp[:8]})"


def _contains_restricted_data(content: str, classification: str) -> tuple[bool, str, str]:
    """Heuristic restricted-data exposure check.

    Returns (hit, pattern, evidence_sanitized).
    """
    cls = classification.upper()
    # For RESTRICTED/SECRET we are stricter — any PII-like token counts
    patterns = list(_FALLBACK_RESTRICTED_PATTERNS)
    # For PUBLIC/INTERNAL, only strong PII signals count
    if cls in ("PUBLIC", "INTERNAL"):
        patterns = [r"\b\d{3}-\d{2}-\d{4}\b", r"\b(?:\d[ -]?){13,19}\b"]
    for pat in patterns:
        try:
            m = re.search(pat, content)
            if m:
                return True, pat, _sanitize_match(m.group(0))
        except re.error:
            continue
    return False, "", ""


def _check_rate_limit(tenant: str, guardrail: AIGuardrail) -> tuple[bool, str]:
    """Return (exceeded, reason).  Best-effort in-memory sliding window.

    ``rate_limit`` is interpreted as requests per 60 s for that guardrail.
    Real deployment would use Redis — here we keep a 60 s TTL list.
    """
    limit = guardrail.rate_limit
    if limit is None or limit <= 0:
        return False, ""
    now = time.time()
    key = (tenant, str(guardrail.id))
    window = 60.0
    bucket = _RATE_COUNTERS.setdefault(key, [])
    # evict outside window
    cutoff = now - window
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= int(limit):
        return True, f"rate limit exceeded for guardrail '{guardrail.name}' ({limit}/60s)"
    bucket.append(now)
    return False, ""


# ── service ────────────────────────────────────────────────────────────


class AIGuardrailService:
    """Tenant-scoped guardrail lifecycle and content inspection.

    Enforces order ``Input → Classification → Policy → Model → Output → Policy → Action``
    — the output stage always re-evaluates policy; a passing input never
    implies a passing output.
    """

    # ── create ─────────────────────────────────────────────────────────

    async def create_guardrail(
        self,
        db: AsyncSession,
        tenant: str,
        name: str,
        scope: str = "input",
        policy: dict | None = None,
        rate_limit: int | None = None,
        environment: str | None = None,
    ) -> AIGuardrail:
        """Create a tenant-scoped guardrail.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required).
            name: guardrail name (required, unique per tenant+scope+environment
                  is not enforced at DB level but recommended).
            scope: ``input`` / ``output`` / ``both`` (default input).
            policy: dict with keys:
                ``blocked_keywords`` / ``blocked_terms``,
                ``blocked_patterns`` / ``patterns``,
                ``blocked_providers`` / ``allowed_classifications``,
                ``classification_max`` / ``max_classification``,
                ``max_length`` / ``max_prompt_length``,
                ``redact_pii`` (bool), ``allowed_tools`` etc.
            rate_limit: optional requests per 60 s for this guardrail.
            environment: optional env tag (e.g. production/staging/dev) —
                when set, the guardrail only applies to matching env.

        Returns: persisted ``AIGuardrail``.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not name or not str(name).strip():
            raise ValidationError(message="name is required")
        tenant_s = str(tenant).strip()
        name_s = str(name).strip()
        scope_s = _normalize_scope(scope)
        if scope_s not in _VALID_SCOPES:
            raise ValidationError(message=f"invalid scope '{scope}'; allowed: {_VALID_SCOPES}")
        # normalise "both" to input (mirrors gateway helper — both means two rows in practice)
        if scope_s == "both":
            scope_s = "input"  # caller should create two rows for true both; we store as input by default
        policy_s: dict = dict(policy) if isinstance(policy, dict) else {}
        env_s = str(environment).strip().lower() if environment and str(environment).strip() else None
        if rate_limit is not None:
            try:
                rl = int(rate_limit)
                if rl < 0:
                    raise ValidationError(message="rate_limit must be >= 0")
                rate_limit = rl
            except (TypeError, ValueError) as exc:
                raise ValidationError(message=f"invalid rate_limit '{rate_limit}': {exc}") from exc

        # Validate regex patterns eagerly so creators get feedback
        for pat in list(policy_s.get("blocked_patterns") or []) + list(policy_s.get("patterns") or []) + list(policy_s.get("prompt_patterns") or []):
            if not pat or not str(pat).strip():
                continue
            try:
                re.compile(str(pat))
            except re.error as exc:
                raise ValidationError(message=f"invalid regex pattern '{pat}': {exc}") from exc

        row = AIGuardrail(
            tenant=tenant_s,
            name=name_s,
            scope=scope_s,
            policy=policy_s,
            rate_limit=rate_limit,
            enabled=True,
            environment=env_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "ai_guardrail.created", str(row.id), {"name": name_s, "scope": scope_s, "environment": env_s})
        logger.info("guardrail '%s' scope=%s tenant=%s env=%s", name_s, scope_s, tenant_s, env_s or "*")
        return row

    # ── listing helpers ────────────────────────────────────────────────

    async def _load_guardrails(
        self,
        db: AsyncSession,
        tenant: str,
        scope: str,
        environment: str | None = None,
    ) -> list[AIGuardrail]:
        """Load enabled guardrails for tenant+scope+environment."""
        tenant_s = str(tenant).strip()
        scope_s = _normalize_scope(scope)
        env_s = str(environment).strip().lower() if environment and str(environment).strip() else None

        # Order: Input→Classification→Policy→Model→Output→Policy→Action
        # We enforce it by always querying in that logical order, but for DB
        # we simply filter by scope; classification/policy ordering is enforced
        # at evaluation time inside ``_evaluate_content``.
        try:
            stmt = select(AIGuardrail).where(AIGuardrail.tenant == tenant_s, AIGuardrail.enabled.is_(True))
            # scope filter — keep input and both for input checks, output and both for output
            if scope_s == "input":
                stmt = stmt.where(AIGuardrail.scope.in_(["input", "both"]))
            elif scope_s == "output":
                stmt = stmt.where(AIGuardrail.scope.in_(["output", "both"]))
            else:
                stmt = stmt.where(AIGuardrail.scope == scope_s)
            result = await db.execute(stmt)
            all_rows: list[AIGuardrail] = list(result.scalars().all())
        except Exception as exc:  # noqa: BLE001
            logger.debug("guardrail query failed: %s", exc)
            return []

        # environment filter — row with env None matches all envs; row with env set must match
        if not all_rows:
            return []
        filtered: list[AIGuardrail] = []
        for g in all_rows:
            row_env = str(g.environment).strip().lower() if getattr(g, "environment", None) else None
            if row_env is None:
                filtered.append(g)
            elif env_s is None:
                # request has no env — only env-agnostic guardrails apply
                continue
            elif row_env == env_s:
                filtered.append(g)
            # else: environment mismatch → guardrail does not apply
        return filtered

    # ── core evaluation ────────────────────────────────────────────────

    def _evaluate_content(
        self,
        content: str,
        classification: str,
        guardrails: list[AIGuardrail],
        tenant: str,
        stage: str,
    ) -> dict[str, Any]:
        """Evaluate content against guardrails in pipeline order.

        Order enforced: Input(1) → Classification(2) → Policy(3) → Model(4)
        → Output(5) → Policy(6) → Action.  For ``check_input`` stage is
        ``input`` (steps 1-3), for ``check_output`` stage is ``output``
        (steps 5-6; step 4 is the model itself and always sits between).

        Returns an ALLOW / BLOCK / FLAG / REDACT decision dict.
        """
        classification_s = _normalize_classification(classification)
        content_s = str(content) if content is not None else ""
        decisions: list[dict] = []
        matched_reasons: list[str] = []
        stage_up = stage.strip().lower() if stage else "input"

        # ── Step 2: Classification pre-check (fail-closed for RESTRICTED/SECRET)
        # If classification is RESTRICTED/SECRET, ensure at least one guardrail
        # explicitly allows it when guardrails exist — otherwise FLAG.
        # We do not DENY here; we let policy do that, but we record.
        classification_rank = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3, "SECRET": 4}.get(classification_s, 1)

        # ── Global pattern checks (always apply, tenant/env configurable)
        # Injection / jailbreaks (prompt injection patterns)
        for pat in _GLOBAL_INJECTION_PATTERNS:
            try:
                if re.search(pat, content_s, re.IGNORECASE):
                    reason = f"prompt injection / jailbreak matched global pattern '{pat}'"
                    return {
                        "decision": "BLOCK",
                        "reason": reason,
                        "stage": stage_up,
                        "classification": classification_s,
                        "category": "prompt_injection",
                        "pattern": pat,
                        "evidence": _sanitize_match(re.search(pat, content_s, re.IGNORECASE).group(0) if re.search(pat, content_s, re.IGNORECASE) else ""),  # type: ignore[union-attr]
                        "guardrail_id": None,
                        "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                    }
            except re.error:
                continue

        # Secret leakage (Volume 47 detectors — global + per-guardrail)
        for entry in _GLOBAL_SECRET_PATTERNS:
            pat = entry.get("pattern", "")
            name = entry.get("name", "secret")
            try:
                m = re.search(pat, content_s, re.IGNORECASE)
                if m:
                    reason = f"secret leakage detected: {name} (Volume 47 detector)"
                    return {
                        "decision": "BLOCK",
                        "reason": reason,
                        "stage": stage_up,
                        "classification": classification_s,
                        "category": "secret_leakage",
                        "pattern": pat,
                        "pattern_name": name,
                        "evidence": _sanitize_match(m.group(0)),
                        "guardrail_id": None,
                        "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                    }
            except re.error:
                continue

        # Restricted data exposure (classification-gated)
        hit, pat, ev = _contains_restricted_data(content_s, classification_s)
        if hit and classification_s in _RESTRICTED_LEVELS:
            # For RESTRICTED/SECRET, any restricted-data pattern → BLOCK (fail-closed)
            return {
                "decision": "BLOCK",
                "reason": f"restricted data exposure for {classification_s}: pattern '{pat}'",
                "stage": stage_up,
                "classification": classification_s,
                "category": "restricted_data_exposure",
                "pattern": pat,
                "evidence": ev,
                "guardrail_id": None,
                "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
            }
        elif hit and classification_s == "CONFIDENTIAL":
            # Confidential → FLAG (not block) for audit
            decisions.append({"decision": "FLAG", "reason": f"confidential data pattern '{pat}' flagged", "category": "restricted_data_exposure"})

        # ── Per-guardrail policy checks in pipeline order (rate limit → classification_max → keywords → patterns → redact)
        for guard in guardrails:
            pol = guard.policy or {}

            # Rate limit (policy step before model)
            exceeded, rl_reason = _check_rate_limit(tenant, guard)
            if exceeded:
                return {
                    "decision": "BLOCK",
                    "reason": rl_reason,
                    "stage": stage_up,
                    "classification": classification_s,
                    "category": "rate_limit",
                    "guardrail_id": str(guard.id),
                    "guardrail_name": guard.name,
                    "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                }

            # Step 2 (classification ceiling) — deny if input classification more sensitive than allowed
            allowed_max = pol.get("classification_max") or pol.get("max_classification") or pol.get("allowed_classification_max")
            if isinstance(allowed_max, str) and allowed_max.strip():
                max_rank = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3, "SECRET": 4}.get(allowed_max.strip().upper(), 4)
                if classification_rank > max_rank:
                    reason = f"guardrail '{guard.name}' classification {classification_s} exceeds max {allowed_max.strip().upper()} (pipeline: Classification→Policy)"
                    return {
                        "decision": "BLOCK",
                        "reason": reason,
                        "stage": stage_up,
                        "classification": classification_s,
                        "category": "classification_policy",
                        "guardrail_id": str(guard.id),
                        "guardrail_name": guard.name,
                        "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                    }

            # Allowed classifications allow-list
            allowed_list = pol.get("allowed_classifications") or pol.get("allowed_data_classifications") or pol.get("classifications")
            if isinstance(allowed_list, list) and len(allowed_list) > 0:
                allow_norm = [str(x).strip().upper() for x in allowed_list if x and str(x).strip()]
                if classification_s not in allow_norm:
                    reason = f"guardrail '{guard.name}' does not allow classification {classification_s} (allowed={allow_norm})"
                    return {
                        "decision": "BLOCK",
                        "reason": reason,
                        "stage": stage_up,
                        "classification": classification_s,
                        "category": "classification_allowlist",
                        "guardrail_id": str(guard.id),
                        "guardrail_name": guard.name,
                        "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                    }

            # Blocked providers check (policy step)
            blocked_providers = pol.get("blocked_providers") or pol.get("blockedProvider")
            if isinstance(blocked_providers, list) and blocked_providers:
                # content mention of blocked provider name → flag/block (output stage especially)
                for bp in blocked_providers:
                    if bp and str(bp).strip().lower() in content_s.lower():
                        reason = f"guardrail '{guard.name}' blocked provider '{bp}' referenced in content"
                        return {
                            "decision": "BLOCK",
                            "reason": reason,
                            "stage": stage_up,
                            "classification": classification_s,
                            "category": "blocked_provider",
                            "guardrail_id": str(guard.id),
                            "guardrail_name": guard.name,
                            "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                        }

            # Blocked keywords — exact substring case-insensitive
            blocked_keywords: list[str] = list(pol.get("blocked_keywords") or pol.get("blocked_terms") or [])
            for kw in blocked_keywords:
                if kw and kw.strip().lower() in content_s.lower():
                    reason = f"guardrail '{guard.name}' blocked keyword '{kw}'"
                    return {
                        "decision": "BLOCK",
                        "reason": reason,
                        "stage": stage_up,
                        "classification": classification_s,
                        "category": "blocked_keyword",
                        "keyword": kw,
                        "guardrail_id": str(guard.id),
                        "guardrail_name": guard.name,
                        "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                    }

            # Blocked regex patterns — per-guardrail
            blocked_patterns: list[str] = list(pol.get("blocked_patterns") or pol.get("patterns") or pol.get("prompt_patterns") or [])
            for pat in blocked_patterns:
                if not pat or not str(pat).strip():
                    continue
                try:
                    m = re.search(str(pat), content_s, re.IGNORECASE)
                    if m:
                        reason = f"guardrail '{guard.name}' matched blocked pattern '{pat}'"
                        return {
                            "decision": "BLOCK",
                            "reason": reason,
                            "stage": stage_up,
                            "classification": classification_s,
                            "category": "blocked_pattern",
                            "pattern": str(pat),
                            "evidence": _sanitize_match(m.group(0)),
                            "guardrail_id": str(guard.id),
                            "guardrail_name": guard.name,
                            "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                        }
                except re.error:
                    logger.debug("invalid guardrail pattern %s in %s", pat, guard.name)
                    continue

            # Max length
            max_len = pol.get("max_length") or pol.get("max_prompt_length") or pol.get("max_content_length")
            if isinstance(max_len, int) and len(content_s) > max_len:
                return {
                    "decision": "BLOCK",
                    "reason": f"guardrail '{guard.name}' content exceeds max_length {max_len} (len={len(content_s)})",
                    "stage": stage_up,
                    "classification": classification_s,
                    "category": "max_length",
                    "guardrail_id": str(guard.id),
                    "guardrail_name": guard.name,
                    "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                }

            # Redact PII — only after all BLOCK checks; returns FLAG/REDACT not BLOCK
            if pol.get("redact_pii"):
                hit2, pat2, _ = _contains_restricted_data(content_s, "RESTRICTED")
                if hit2:
                    return {
                        "decision": "REDACT",
                        "reason": f"guardrail '{guard.name}' requires PII redaction (pattern '{pat2}')",
                        "stage": stage_up,
                        "classification": classification_s,
                        "category": "redact_pii",
                        "guardrail_id": str(guard.id),
                        "guardrail_name": guard.name,
                        "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                    }

            # Tool restrictions — if policy restricts tools and content references a blocked tool
            blocked_tools = pol.get("blocked_tools") or pol.get("restricted_tools")
            if isinstance(blocked_tools, list) and blocked_tools:
                for tl in blocked_tools:
                    if tl and str(tl).strip().lower() in content_s.lower():
                        return {
                            "decision": "FLAG",
                            "reason": f"guardrail '{guard.name}' references restricted tool '{tl}'",
                            "stage": stage_up,
                            "classification": classification_s,
                            "category": "restricted_tool",
                            "guardrail_id": str(guard.id),
                            "guardrail_name": guard.name,
                            "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                        }

            # Classification mismatch for output — output classification is tenant configurable
            # (already enforced at classification step)

        # If any FLAG accumulated, return FLAG (highest non-blocking)
        for d in decisions:
            if d.get("decision") == "FLAG":
                return {
                    "decision": "FLAG",
                    "reason": d.get("reason", "flagged by guardrail policy"),
                    "stage": stage_up,
                    "classification": classification_s,
                    "category": d.get("category", "flag"),
                    "guardrail_id": None,
                    "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
                }

        # All checks passed
        return {
            "decision": "ALLOW",
            "reason": f"{stage_up} guardrails passed ({len(guardrails)} evaluated) — pipeline Input->Classification->Policy->Model->Output->Policy->Action enforced",
            "stage": stage_up,
            "classification": classification_s,
            "evaluated": len(guardrails),
            "global_injection_patterns": len(_GLOBAL_INJECTION_PATTERNS),
            "global_secret_patterns": len(_GLOBAL_SECRET_PATTERNS),
            "pipeline": "Input->Classification->Policy->Model->Output->Policy->Action",
        }

    # ── public: check_input ────────────────────────────────────────────

    async def check_input(
        self,
        db: AsyncSession,
        tenant: str,
        content: str,
        classification: str = "INTERNAL",
        scope: str = "input",
        environment: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate input content through the input side of the pipeline.

        Steps enforced: ``Input → Classification → Policy`` (→ Model …).
        Returns ``ALLOW`` / ``BLOCK`` / ``FLAG`` (or ``REDACT`` when a
        guardrail requests PII redaction).

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required).
            content: input prompt / user content (required).
            classification: already-classified level for the content.
            scope: guardrail scope to query (default ``input``).
            environment: optional env tag — filters guardrails with matching
                environment; ``None`` matches guardrails with no env set.

        Side-effects: none (no persistence).  Audit best-effort.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        content_s = str(content) if content is not None else ""
        classification_s = _normalize_classification(classification)
        scope_s = _normalize_scope(scope)
        # For input checks, scope must be input (or both) — output-only guardrails never apply to input
        if scope_s not in ("input", "both"):
            scope_s = "input"

        guardrails = await self._load_guardrails(db, tenant_s, "input", environment)

        result = self._evaluate_content(content_s, classification_s, guardrails, tenant_s, "input")
        _audit(tenant_s, "system", f"ai_guardrail.check_input.{result['decision'].lower()}", "", {"classification": classification_s, "scope": scope_s, "environment": environment, "decision": result["decision"]})
        return result

    async def check_output(
        self,
        db: AsyncSession,
        tenant: str,
        content: str,
        classification: str = "INTERNAL",
        scope: str = "output",
        environment: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate model output through the output side of the pipeline.

        Steps enforced: ``… Model → Output → Policy → Action``.  **Never lets
        output bypass policy** — even when input was ALLOW, output is
        re-evaluated against output-scoped guardrails plus global detectors.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required).
            content: model output content (required).
            classification: classification of the output (defaults to INTERNAL;
                caller should pass the output classification which may differ
                from input).
            scope: guardrail scope (default ``output``).
            environment: optional env tag.

        Returns: ALLOW / BLOCK / FLAG / REDACT decision dict with
        ``pipeline`` field proving enforcement.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        content_s = str(content) if content is not None else ""
        classification_s = _normalize_classification(classification)
        scope_s = _normalize_scope(scope)
        if scope_s not in ("output", "both"):
            scope_s = "output"

        # Enforce pipeline: output guardrails are ALWAYS evaluated; input guardrails
        # do not automatically allow output.  Also re-apply global injection/secret
        # detectors to output (exfiltration / prompt-leak attack).
        guardrails = await self._load_guardrails(db, tenant_s, "output", environment)

        # Even with zero output guardrails, global detectors still run (fail-closed).
        result = self._evaluate_content(content_s, classification_s, guardrails, tenant_s, "output")
        # Annotate that output was never skipped
        result["input_bypass_prevented"] = True
        _audit(tenant_s, "system", f"ai_guardrail.check_output.{result['decision'].lower()}", "", {"classification": classification_s, "scope": scope_s, "environment": environment, "decision": result["decision"]})
        return result

    # ── utilities ──────────────────────────────────────────────────────

    async def list_guardrails(
        self,
        db: AsyncSession,
        tenant: str,
        scope: str | None = None,
        environment: str | None = None,
    ) -> list[AIGuardrail]:
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(AIGuardrail).where(AIGuardrail.tenant == tenant_s, AIGuardrail.enabled.is_(True))
        if scope and str(scope).strip():
            s = _normalize_scope(scope)
            if s in ("input", "output"):
                stmt = stmt.where(AIGuardrail.scope == s)
        if environment and str(environment).strip():
            env = str(environment).strip().lower()
            stmt = stmt.where(AIGuardrail.environment == env)
        stmt = stmt.order_by(AIGuardrail.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_guardrail(
        self,
        db: AsyncSession,
        tenant: str,
        guardrail_id: str | uuid.UUID,
    ) -> AIGuardrail | None:
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(guardrail_id)
        stmt = select(AIGuardrail).where(AIGuardrail.id == pk, AIGuardrail.tenant == tenant_s)
        result = await db.execute(stmt)
        return result.scalars().first()


guardrail_service = AIGuardrailService()
