"""Volume 57 — PolicyBridgeService.

Wraps governance.policy_engine.PolicyEngine — does NOT duplicate it.
Persists GovernancePolicyDecision with policy_version and returns decisions.
Provides dry-run simulate without persisting sensitive internals.

Fail-closed for restricted data (RESTRICTED/SECRET) when engine unavailable.
AsyncSession, tenant-scoped, audit best-effort, never log raw secrets.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernancePolicyDecision

logger = logging.getLogger(__name__)

_RESTRICTED_LEVELS: set[str] = {"RESTRICTED", "SECRET"}
_GATE_DECISIONS: set[str] = {"ALLOW", "DENY", "REDACT", "ANONYMIZE", "REQUIRE_APPROVAL"}

_ENGINE_TO_GATE: dict[str, str] = {
    "allowed": "ALLOW",
    "denied": "DENY",
    "requires_approval": "REQUIRE_APPROVAL",
    "warning": "REDACT",
    "escalated": "REQUIRE_APPROVAL",
    "retry": "REQUIRE_APPROVAL",
    "rollback": "DENY",
    "custom": "ANONYMIZE",
    "not_applicable": "ALLOW",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe_details: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
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
                "governance_policy_decision",
                resource_id,
                "success",
                safe_details,
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_policy_decision", resource_id, "success", safe_details)
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _engine_storage_dir(tenant: str) -> str:
    safe = str(tenant).strip().replace("/", "_").replace("\\", "_")[:64]
    return f"policy_engine_data_{safe}"


def _normalize_policy_type(value: str | Any) -> Any | None:
    """Convert string policy_type to PolicyType enum; returns enum or None.

    Caller should handle fallback to string value if import fails.
    """
    try:
        from app.governance.policy_engine import PolicyType  # type: ignore

        if isinstance(value, PolicyType):
            return value
        s = str(value).strip()
        if not s:
            return None
        # try exact value
        for m in PolicyType:
            if m.value == s.lower() or m.value == s or m.name.lower() == s.lower():
                return m
        # common aliases for Volume 57 spec
        alias: dict[str, str] = {
            "data": "security",
            "ai": "ai_usage",
            "model": "ai_model",
            "prompt": "prompt",
            "llm": "llm_provider",
            "retention": "data_retention",
        }
        norm = alias.get(s.lower(), s.lower())
        for m in PolicyType:
            if m.value == norm:
                return m
        return None
    except Exception:
        return None


def _sanitize_results(results: list[dict] | None) -> list[dict] | None:
    if not results:
        return results
    safe_out: list[dict] = []
    for r in results:
        if not isinstance(r, dict):
            safe_out.append(r)
            continue
        sr: dict = {}
        for k, v in r.items():
            if k == "details" and isinstance(v, list):
                safe_details = []
                for d in v:
                    if not isinstance(d, dict):
                        safe_details.append(d)
                        continue
                    sd = {kk: vv for kk, vv in d.items() if kk not in ("actual",)}
                    # redact actual that may contain secrets
                    if "actual" in d:
                        sd["actual"] = "[REDACTED]" if d.get("actual") else None
                    exp = d.get("expected")
                    if isinstance(exp, str) and len(exp) > 120:
                        sd["expected"] = exp[:120]
                    else:
                        sd["expected"] = exp
                    safe_details.append(sd)
                sr[k] = safe_details
            elif k in ("actual", "secret", "raw_value", "value", "match", "prompt", "content"):
                continue
            else:
                sr[k] = v
        safe_out.append(sr)
    return safe_out


def _extract_classification(context: dict | None) -> str | None:
    if not context or not isinstance(context, dict):
        return None
    for key in ("classification", "data_classification", "level", "sensitivity"):
        v = context.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip().upper()
        # nested
        if isinstance(v, dict):
            inner = v.get("classification") or v.get("level")
            if inner and isinstance(inner, str):
                return inner.strip().upper()
    return None


class PolicyBridgeService:
    """Bridge between governance PolicyEngine and datagov persistence."""

    async def evaluate(
        self,
        db: AsyncSession,
        tenant: str,
        actor: str,
        resource: str,
        policy_type: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Evaluate context against PolicyEngine and persist decision.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant scope (required).
            actor: actor identity (required).
            resource: resource identifier being governed (required).
            policy_type: PolicyType value string (e.g., ai_usage, security,
                data_retention, ai_model). Case-insensitive; unknown maps to
                SECURITY as default.
            context: evaluation context dict. Must not contain raw secrets
                — caller should pass only metadata. Classification is read
                from context["classification"] if present for fail-closed.

        Returns:
            dict with decision, reason, matched_policies, persisted row id,
            policy_version. Decision is one of ALLOW/DENY/REDACT/ANONYMIZE/
            REQUIRE_APPROVAL. On engine failure and restricted data, returns
            DENY with fail_closed=True.

        Persists GovernancePolicyDecision with policy_version (first matched
        policy's version or "1.0.0" if none matched).
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not actor or not str(actor).strip():
            raise ValueError("actor is required")
        if not resource or not str(resource).strip():
            raise ValueError("resource is required")
        if not policy_type or not str(policy_type).strip():
            raise ValueError("policy_type is required")
        tenant_s = str(tenant).strip()
        actor_s = str(actor).strip()
        resource_s = str(resource).strip()
        ptype_s = str(policy_type).strip()
        ctx: dict = dict(context) if isinstance(context, dict) else {}

        # Enrich context with tenant/resource/actor for consistent evaluation
        ctx.setdefault("tenant", tenant_s)
        ctx.setdefault("resource", resource_s)
        ctx.setdefault("actor", actor_s)
        ctx.setdefault("identity", actor_s)

        classification = _extract_classification(ctx)
        if classification is None:
            classification = _extract_classification({"classification": ctx.get("data_classification")})

        ptype_enum: Any | None = _normalize_policy_type(ptype_s)
        # Fallback for when enum import unavailable: keep string
        need_import_fallback = ptype_enum is None

        engine_error: str | None = None
        engine_result: dict | None = None
        gate_decision: str | None = None
        matched: list[str] = []
        policy_version: str | None = None
        primary_policy_id: str | None = None
        reason: str | None = None

        try:
            from app.governance.policy_engine import PolicyEngine, PolicyType  # type: ignore

            if ptype_enum is None:
                # try to map unknown to SECURITY or AI_USAGE
                try:
                    ptype_enum = PolicyType.SECURITY  # type: ignore
                except Exception:
                    ptype_enum = None
            if ptype_enum is None:
                raise RuntimeError(f"unknown policy_type '{ptype_s}'")

            # Tenant-isolated storage dir
            engine: Any | None = None
            last_exc: Exception | None = None
            for stor in (_engine_storage_dir(tenant_s), "policy_engine_data"):
                try:
                    eng = PolicyEngine(storage_dir=stor)  # type: ignore
                    engine = eng
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.debug("PolicyEngine init failed for %s: %s", stor, exc)
                    continue
            if engine is None:
                raise RuntimeError(f"PolicyEngine unavailable: {last_exc}")

            # evaluate_and_enforce is the canonical entrypoint
            engine_result = engine.evaluate_and_enforce(tenant_s, ptype_enum, ctx)  # type: ignore[attr-defined]
            if not isinstance(engine_result, dict):
                raise RuntimeError("evaluate_and_enforce returned non-dict")

            raw_decision = str(engine_result.get("decision", "allowed")).lower()
            gate_decision = _ENGINE_TO_GATE.get(raw_decision, "ALLOW")
            matched = [str(x) for x in (engine_result.get("matched_policies") or [])]
            # Resolve policy_version from matched policies
            if matched:
                primary_policy_id = matched[0]
                try:
                    pol = engine.get_policy(primary_policy_id)  # type: ignore[attr-defined]
                    if pol is not None and hasattr(pol, "version"):
                        policy_version = str(getattr(pol, "version"))
                except Exception:
                    pass
            if not policy_version:
                # fallback to engine result version or default
                policy_version = str(engine_result.get("version") or "1.0.0")
            # reason from engine results or generic
            if raw_decision == "denied":
                reason = f"policy denied access to '{resource_s}'"
                if matched:
                    reason += f" — matched {matched}"
            elif raw_decision == "requires_approval":
                reason = f"policy requires approval for '{resource_s}'"
                if matched:
                    reason += f" — matched {matched}"
            elif raw_decision == "warning":
                reason = f"policy warning — redact recommended for '{resource_s}'"
            else:
                reason = f"policy {raw_decision} for '{resource_s}'"
        except ImportError as exc:
            engine_error = f"policy_engine not available: {exc}"
            logger.debug("%s", engine_error)
        except Exception as exc:  # noqa: BLE001
            engine_error = str(exc)
            logger.debug("PolicyEngine evaluate failed: %s", exc)

        # Fail-closed for RESTRICTED/SECRET when engine unavailable
        if gate_decision is None:
            if classification and classification.upper() in _RESTRICTED_LEVELS:
                gate_decision = "DENY"
                reason = f"fail-closed: policy engine unavailable for {classification} data"
                _audit(tenant_s, actor_s, "governance.policy_bridge.denied", resource_s, {"policy_type": ptype_s, "classification": classification, "fail_closed": True})
                # Persist fail-closed decision
                row = GovernancePolicyDecision(
                    tenant=tenant_s,
                    actor=actor_s,
                    resource=resource_s,
                    policy_id=None,
                    policy_version=policy_version or "1.0.0",
                    decision=gate_decision,
                    reason=reason,
                    request_id=None,
                )
                db.add(row)
                await db.flush()
                await db.refresh(row)
                return {
                    "decision": gate_decision,
                    "reason": reason,
                    "matched_policies": matched,
                    "policy_version": policy_version or "1.0.0",
                    "policy_id": primary_policy_id,
                    "persisted_id": str(row.id),
                    "fail_closed": True,
                    "engine_error": engine_error,
                    "raw": None,
                }
            else:
                # Non-restricted with engine failure: allow with audit but warn
                gate_decision = "ALLOW"
                reason = f"no policy matched — allowed (engine unavailable, data not restricted)"
                policy_version = policy_version or "1.0.0"
                _audit(tenant_s, actor_s, "governance.policy_bridge.allowed", resource_s, {"policy_type": ptype_s, "engine_error": engine_error})

                row = GovernancePolicyDecision(
                    tenant=tenant_s,
                    actor=actor_s,
                    resource=resource_s,
                    policy_id=None,
                    policy_version=policy_version,
                    decision=gate_decision,
                    reason=reason,
                    request_id=None,
                )
                db.add(row)
                await db.flush()
                await db.refresh(row)
                return {
                    "decision": gate_decision,
                    "reason": reason,
                    "matched_policies": matched,
                    "policy_version": policy_version,
                    "policy_id": primary_policy_id,
                    "persisted_id": str(row.id),
                    "fail_closed": False,
                    "engine_error": engine_error,
                    "raw": None,
                }

        # Persist decision (sanitized reason, version)
        if not policy_version:
            policy_version = "1.0.0"
        if not reason:
            reason = f"policy {gate_decision.lower()} for '{resource_s}'"

        # Sanitize reason — never include raw secrets
        # Truncate to avoid storing huge context dumps
        safe_reason = str(reason)[:500] if reason else gate_decision

        row = GovernancePolicyDecision(
            tenant=tenant_s,
            actor=actor_s,
            resource=resource_s,
            policy_id=primary_policy_id,
            policy_version=policy_version,
            decision=gate_decision,
            reason=safe_reason,
            request_id=str(ctx.get("request_id") or "") if ctx.get("request_id") else None,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        # Audit with safe details only
        _audit(
            tenant_s,
            actor_s,
            f"governance.policy_bridge.{gate_decision.lower()}",
            resource_s,
            {
                "policy_type": ptype_s,
                "classification": classification,
                "decision": gate_decision,
                "policy_version": policy_version,
                "matched": matched[:10],
                "engine_decision": engine_result.get("decision") if isinstance(engine_result, dict) else None,
            },
        )

        return {
            "decision": gate_decision,
            "reason": safe_reason,
            "matched_policies": matched,
            "policy_version": policy_version,
            "policy_id": primary_policy_id,
            "persisted_id": str(row.id),
            "fail_closed": False,
            "engine_error": engine_error,
            "raw": {
                "engine_decision": engine_result.get("decision") if isinstance(engine_result, dict) else None,
                "policies_evaluated": engine_result.get("policies_evaluated") if isinstance(engine_result, dict) else None,
                "results": _sanitize_results(engine_result.get("results") if isinstance(engine_result, dict) else None),  # type: ignore
            } if engine_result else None,
        }

    async def simulate(
        self,
        db: AsyncSession,
        tenant: str,
        resource: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Dry-run policy evaluation without persisting.

        Args:
            db: AsyncSession (unused for persistence, accepted for parity).
            tenant: tenant scope.
            resource: resource identifier.
            context: evaluation context dict. May contain classification,
                provider, region, purpose etc. Raw secrets must never be
                passed; only categories/fingerprints are evaluated.

        Returns:
            dict with decision, matched rules (sanitized), policies_evaluated.
            Internals are hidden for sensitive data exposure check — if
            classification is RESTRICTED/SECRET and caller context suggests
            unauthorized viewer, details are redacted to decision+count only.
            Fail-closed: if engine unavailable and restricted classification,
            returns DENY.

        Does not persist any row.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not resource or not str(resource).strip():
            raise ValueError("resource is required")
        tenant_s = str(tenant).strip()
        resource_s = str(resource).strip()
        ctx: dict = dict(context) if isinstance(context, dict) else {}
        ctx.setdefault("tenant", tenant_s)
        ctx.setdefault("resource", resource_s)

        classification = _extract_classification(ctx)
        # Detect if caller is authorized to see internals
        # Heuristic: actor in context with role admin/approver/auditor can see details
        actor = str(ctx.get("actor") or ctx.get("identity") or ctx.get("requester") or "").strip().lower()
        role = str(ctx.get("role") or ctx.get("actor_role") or "").strip().lower()
        authorized_roles: set[str] = {"admin", "approver", "auditor", "security_officer", "compliance_officer", "owner", "steward"}
        is_authorized = role in authorized_roles or actor in authorized_roles

        # For restricted data, internals are hidden unless authorized
        hide_internals = bool(classification and classification.upper() in _RESTRICTED_LEVELS and not is_authorized)

        engine_error: str | None = None
        engine_result: dict | None = None
        gate_decision: str | None = None
        matched: list[str] = []

        try:
            from app.governance.policy_engine import PolicyEngine, PolicyType  # type: ignore

            engine: Any | None = None
            for stor in (_engine_storage_dir(tenant_s), "policy_engine_data"):
                try:
                    eng = PolicyEngine(storage_dir=stor)  # type: ignore
                    engine = eng
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("PolicyEngine init failed for %s: %s", stor, exc)
                    continue
            if engine is None:
                raise RuntimeError("PolicyEngine unavailable")

            # Simulate by evaluating all active policies for each relevant type and merging
            # Use simulate_policy if available, otherwise evaluate_all per type
            # Prefer evaluate_and_enforce aggregation for fidelity
            all_results: list[dict] = []
            all_matched: list[str] = []
            candidates: list[str] = []

            # Try to list policies to cover all types the engine knows
            try:
                policies = engine.list_policies(org_id=tenant_s, status=None)  # type: ignore
                # collect distinct types actually present
                types_present: set[Any] = set()
                for p in policies or []:
                    try:
                        types_present.add(p.type)  # type: ignore
                    except Exception:
                        continue
                if not types_present:
                    types_present = {PolicyType.SECURITY, PolicyType.AI_USAGE}  # fallback
            except Exception:
                types_present = set()
                for t in (PolicyType.SECURITY, PolicyType.AI_USAGE, PolicyType.AI_MODEL, PolicyType.LLM_PROVIDER, PolicyType.PROMPT):
                    try:
                        types_present.add(t)
                    except Exception:
                        pass

            for ptype in types_present:
                try:
                    res = engine.evaluate_and_enforce(tenant_s, ptype, ctx)  # type: ignore
                    if isinstance(res, dict):
                        all_results.append(res)
                        dec = str(res.get("decision", "allowed")).lower()
                        candidates.append(dec)
                        if res.get("matched_policies"):
                            all_matched.extend([str(x) for x in res["matched_policies"]])
                except Exception as exc:  # noqa: BLE001
                    logger.debug("simulate evaluate_and_enforce failed for %s: %s", ptype, exc)
                    continue

            if candidates:
                priority = ["denied", "escalated", "requires_approval", "rollback", "retry", "warning", "custom", "allowed", "not_applicable"]
                rank = {d: i for i, d in enumerate(priority)}
                best: str | None = None
                best_r = 999
                for c in candidates:
                    r = rank.get(c, 50)
                    if r < best_r:
                        best_r = r
                        best = c
                gate_decision = _ENGINE_TO_GATE.get(str(best).lower(), "ALLOW")
                matched = list(dict.fromkeys(all_matched))  # dedupe preserve order
                # Build synthetic engine_result for response
                engine_result = {
                    "decision": best,
                    "gate_decision": gate_decision,
                    "policies_evaluated": sum(int(r.get("policies_evaluated") or 0) for r in all_results),
                    "matched_policies": matched,
                    "results": [r.get("results", []) for r in all_results if r.get("results")],
                }
                # flatten results
                flat: list[dict] = []
                for r in all_results:
                    rs = r.get("results") or []
                    if isinstance(rs, list):
                        flat.extend(rs)
                engine_result["results"] = flat
            else:
                gate_decision = "ALLOW"
                engine_result = {"decision": "allowed", "gate_decision": gate_decision, "matched_policies": [], "policies_evaluated": 0, "results": []}
        except ImportError as exc:
            engine_error = f"policy_engine not available: {exc}"
            logger.debug("%s", engine_error)
        except Exception as exc:  # noqa: BLE001
            engine_error = str(exc)
            logger.debug("PolicyBridge simulate failed: %s", exc)

        if gate_decision is None:
            if classification and classification.upper() in _RESTRICTED_LEVELS:
                return {
                    "decision": "DENY",
                    "reason": f"fail-closed: policy engine unavailable for {classification} data",
                    "matched_policies": [],
                    "policies_evaluated": 0,
                    "fail_closed": True,
                    "engine_error": engine_error,
                    "results": None,
                    "hidden": hide_internals,
                }
            gate_decision = "ALLOW"
            engine_result = {"decision": "allowed", "gate_decision": gate_decision, "matched_policies": [], "policies_evaluated": 0, "results": []}

        # Hide internals for unauthorized viewers of restricted data
        if hide_internals:
            return {
                "decision": gate_decision,
                "reason": f"dry-run {gate_decision.lower()} — details hidden for {classification} data (unauthorized viewer)",
                "matched_policies": [],  # hidden
                "matched_count": len(matched),
                "policies_evaluated": int(engine_result.get("policies_evaluated") or 0) if isinstance(engine_result, dict) else 0,
                "fail_closed": False,
                "engine_error": engine_error,
                "results": None,
                "hidden": True,
            }

        # Sanitize results before returning
        safe_results = _sanitize_results(engine_result.get("results") if isinstance(engine_result, dict) else None) if engine_result else None
        return {
            "decision": gate_decision,
            "reason": f"dry-run {gate_decision.lower()} — matched {matched}" if matched else f"dry-run {gate_decision.lower()} — no policy matched",
            "matched_policies": matched,
            "matched_count": len(matched),
            "policies_evaluated": int(engine_result.get("policies_evaluated") or 0) if isinstance(engine_result, dict) else 0,
            "fail_closed": False,
            "engine_error": engine_error,
            "results": safe_results,
            "hidden": False,
        }


policy_bridge_service = PolicyBridgeService()
