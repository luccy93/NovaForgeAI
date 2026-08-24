"""Volume 58 — AIPolicyService.

Tenant-scoped, AsyncSession, no placeholders.

Wraps ``governance.policy_engine.PolicyEngine`` (tenant-isolated JSON storage)
for AI policy lifecycle:

* create_policy — persists a Policy via PolicyEngine tenant dir
* evaluate       — wraps PolicyEngine evaluate_and_enforce, maps to
                  ALLOW/DENY/REDACT/REQUIRE_APPROVAL, sanitizes internals
* simulate       — dry-run via PolicyEngine simulate_policy, no persistence,
                  sanitized

Storage: JSON via PolicyEngine, tenant dir ``policy_engine_data_{tenant}``
fallback to ``policy_engine_data``.  Never exposes sensitive internals
(actual values, raw secrets) — actual fields are redacted and expected
truncated.

Audit best-effort via ``app.iam.audit_service`` — never raises.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)


# ── constants ──────────────────────────────────────────────────────────

_VALID_EFFECTS: set[str] = {"ALLOW", "DENY", "REDACT", "REQUIRE_APPROVAL", "WARN", "ANONYMIZE", "ESCALATE"}
_VALID_POLICY_TYPES: set[str] = {
    "ai_model",
    "ai_prompt",
    "ai_agent",
    "ai_tool",
    "ai_policy",
    "ai_usage",
    "llm_provider",
    "prompt",
    "security",
    "compliance",
    "organization",
    "repository",
    "deployment",
    "data_retention",
    "billing",
    "workspace",
}

_ENGINE_TO_GATE: dict[str, str] = {
    "allowed": "ALLOW",
    "denied": "DENY",
    "requires_approval": "REQUIRE_APPROVAL",
    "warning": "REDACT",
    "escalated": "REQUIRE_APPROVAL",
    "retry": "REQUIRE_APPROVAL",
    "rollback": "DENY",
    "custom": "REDACT",
    "not_applicable": "ALLOW",
}

_GATE_TO_EFFECT: dict[str, str] = {
    "ALLOW": "allow",
    "DENY": "deny",
    "REDACT": "warn",
    "REQUIRE_APPROVAL": "require_approval",
    "ANONYMIZE": "custom",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
            audit_service.log(tenant, actor, "user", action, "ai_policy", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_policy", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _engine_storage_dir(tenant: str) -> str:
    safe = str(tenant).strip().replace("/", "_").replace("\\", "_")[:64]
    return f"policy_engine_data_{safe}"


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
                    if "actual" in d:
                        sd["actual"] = "[REDACTED]" if d.get("actual") not in (None, "") else None
                    exp = d.get("expected")
                    if isinstance(exp, str) and len(exp) > 100:
                        sd["expected"] = exp[:100]
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


def _sanitize_policy_raw(raw: dict | None) -> dict | None:
    if not raw or not isinstance(raw, dict):
        return None
    safe: dict = {}
    for k, v in raw.items():
        if k in ("prompt", "content", "secret", "raw_value", "value", "match"):
            continue
        if k == "results" and isinstance(v, list):
            safe[k] = _sanitize_results(v)
        else:
            safe[k] = v
    return safe


def _map_policy_type(value: str) -> Any:
    """Map string policy_type to PolicyType enum. Raises ValidationError on unknown."""
    try:
        from app.governance.policy_engine import PolicyType  # type: ignore

        if not value or not str(value).strip():
            raise ValidationError(message="policy_type is required")
        s = str(value).strip()
        # try exact value match
        for m in PolicyType:
            if m.value == s.lower() or m.value == s or m.name.lower() == s.lower():
                return m
        # aliases
        alias: dict[str, str] = {
            "data": "security",
            "ai": "ai_usage",
            "model": "ai_model",
            "llm": "llm_provider",
            "retention": "data_retention",
            "ai_policy": "ai_policy",
        }
        norm = alias.get(s.lower(), s.lower())
        for m in PolicyType:
            if m.value == norm:
                return m
        raise ValidationError(message=f"invalid policy_type '{value}'; allowed: {[m.value for m in PolicyType]}")
    except ValidationError:
        raise
    except ImportError as exc:
        raise ValidationError(message=f"policy engine unavailable for policy_type mapping: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid policy_type '{value}': {exc}") from exc


def _map_effect(value: str) -> Any:
    """Map effect string to PolicyEffect enum."""
    try:
        from app.governance.policy_engine import PolicyEffect  # type: ignore

        if not value or not str(value).strip():
            raise ValidationError(message="effect is required")
        s = str(value).strip().upper()
        if s not in _VALID_EFFECTS and s not in {"ALLOW", "DENY", "WARN", "CUSTOM", "ESCALATE", "RETRY", "ROLLBACK"}:
            raise ValidationError(message=f"invalid effect '{value}'; allowed: {sorted(_VALID_EFFECTS)}")
        # canonical mapping: REDACT -> WARN, ANONYMIZE -> CUSTOM, REQUIRE_APPROVAL stays
        mapping: dict[str, str] = {
            "ALLOW": "allow",
            "DENY": "deny",
            "REDACT": "warn",
            "WARN": "warn",
            "REQUIRE_APPROVAL": "require_approval",
            "ANONYMIZE": "custom",
            "CUSTOM": "custom",
            "ESCALATE": "escalate",
            "RETRY": "retry",
            "ROLLBACK": "rollback",
        }
        eff_str = mapping.get(s)
        if eff_str is None:
            eff_str = s.lower()
        for m in PolicyEffect:
            if m.value == eff_str:
                return m
            if m.name.upper() == s:
                return m
        raise ValidationError(message=f"effect '{value}' could not be mapped to PolicyEffect")
    except ValidationError:
        raise
    except ImportError as exc:
        raise ValidationError(message=f"policy engine unavailable for effect mapping: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid effect '{value}': {exc}") from exc


def _normalize_constraints(conditions: Any) -> list[Any]:
    """Convert conditions param to list[PolicyConstraint]. Never invent."""
    try:
        from app.governance.policy_engine import ConstraintOperator, PolicyConstraint  # type: ignore
    except ImportError as exc:
        raise ValidationError(message=f"policy engine unavailable for constraints: {exc}") from exc

    if conditions is None:
        return []
    # conditions may be dict, list[dict], or already list[PolicyConstraint]
    raw_list: list[dict] = []
    if isinstance(conditions, dict):
        # single condition dict or wrapper {"constraints": [...]} or {"conditions": [...]}
        if "constraints" in conditions and isinstance(conditions["constraints"], list):
            raw_list = list(conditions["constraints"])
        elif "conditions" in conditions and isinstance(conditions["conditions"], list):
            raw_list = list(conditions["conditions"])
        elif "field" in conditions or "operator" in conditions:
            raw_list = [conditions]
        else:
            # dict of field->value treated as equals constraints
            for k, v in conditions.items():
                if k and str(k).strip():
                    raw_list.append({"field": str(k).strip(), "operator": "equals", "value": v})
    elif isinstance(conditions, list):
        raw_list = list(conditions)
    else:
        raise ValidationError(message="conditions must be a dict or list of condition dicts")

    constraints: list[Any] = []
    valid_ops = {op.value for op in ConstraintOperator}
    for idx, c in enumerate(raw_list):
        if not isinstance(c, dict):
            raise ValidationError(message=f"condition[{idx}] must be a dict")
        field = str(c.get("field") or c.get("key") or "").strip()
        if not field:
            raise ValidationError(message=f"condition[{idx}].field is required")
        op_raw = str(c.get("operator") or c.get("op") or "equals").strip().lower().replace(" ", "_").replace("-", "_")
        # normalize operator aliases
        op_alias: dict[str, str] = {
            "eq": "equals",
            "neq": "not_equals",
            "ne": "not_equals",
            "gt": "greater_than",
            "lt": "less_than",
            "gte": "greater_than",
            "lte": "less_than",
        }
        op_norm = op_alias.get(op_raw, op_raw)
        if op_norm not in valid_ops:
            raise ValidationError(message=f"condition[{idx}].operator '{op_raw}' invalid; allowed: {sorted(valid_ops)}")
        # resolve enum
        op_enum = None
        for op in ConstraintOperator:
            if op.value == op_norm:
                op_enum = op
                break
        if op_enum is None:
            raise ValidationError(message=f"operator '{op_norm}' not mapped")
        value = c.get("value")
        description = str(c.get("description") or c.get("desc") or "").strip()
        constraints.append(PolicyConstraint(field=field, operator=op_enum, value=value, description=description))
    return constraints


def _extract_classification(context: dict | None) -> str | None:
    if not context or not isinstance(context, dict):
        return None
    for key in ("classification", "data_classification", "level", "sensitivity"):
        v = context.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip().upper()
    return None


class AIPolicyService:
    """Tenant-scoped AI policy lifecycle over PolicyEngine JSON storage."""

    # ── create_policy ──────────────────────────────────────────────────

    async def create_policy(
        self,
        db: AsyncSession,
        tenant: str,
        name: str,
        policy_type: str,
        effect: str,
        priority: int = 0,
        conditions: Any | None = None,
    ) -> dict[str, Any]:
        """Create a tenant-scoped AI policy via PolicyEngine JSON storage.

        Args:
            db: AsyncSession (tenant-scoped, kept for interface parity).
            tenant: tenant id (required, non-empty, tenant-isolated dir).
            name: policy name (required, non-empty).
            policy_type: PolicyType value (e.g. ai_model, ai_usage, security).
            effect: ALLOW/DENY/REDACT/REQUIRE_APPROVAL (mapped to PolicyEffect).
            priority: integer priority (higher evaluated first).
            conditions: list/dict of constraint dicts ``{field, operator, value}``.

        Returns: dict with policy id, name, type, effect, priority, version.

        Raises: ValidationError for missing/invalid args.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not name or not str(name).strip():
            raise ValidationError(message="name is required")
        tenant_s = str(tenant).strip()
        name_s = str(name).strip()
        ptype = _map_policy_type(policy_type)
        eff = _map_effect(effect)
        try:
            prio = int(priority) if priority is not None else 0
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(message=f"priority must be integer: {exc}") from exc
        constraints = _normalize_constraints(conditions)

        # Build Policy dataclass — tenant isolated via org_id
        try:
            from app.governance.policy_engine import Policy, PolicyStatus  # type: ignore
        except ImportError as exc:
            raise ValidationError(message=f"policy engine unavailable: {exc}") from exc

        policy_id = str(uuid.uuid4())
        now = _utc_now().isoformat()
        policy = Policy(
            id=policy_id,
            org_id=tenant_s,
            name=name_s,
            description=str(conditions)[:500] if conditions else "",
            type=ptype,
            effect=eff,
            severity=__import__("app.governance.policy_engine", fromlist=["PolicySeverity"]).PolicySeverity.MEDIUM,  # type: ignore
            constraints=constraints,
            actions=[],
            priority=prio,
            tags=[],
            version="1.0.0",
            status=PolicyStatus.ACTIVE,
            created_by=tenant_s,
            created_at=now,
            updated_at=now,
            metadata={},
        )

        # Tenant-isolated storage dir via PolicyEngine
        try:
            from app.governance.policy_engine import PolicyEngine  # type: ignore

            stor = _engine_storage_dir(tenant_s)
            engine = PolicyEngine(storage_dir=stor)  # type: ignore
            engine.create_policy(policy)  # type: ignore
        except ValueError as exc:
            # duplicate id (extremely unlikely with uuid4)
            raise ValidationError(message=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("create_policy engine failure tenant=%s: %s", tenant_s, exc, exc_info=True)
            raise ValidationError(message=f"policy storage failed: {exc}") from exc

        _audit(tenant_s, tenant_s, "ai_policy.created", policy_id, {"name": name_s, "policy_type": str(policy_type), "effect": str(effect), "priority": prio})
        logger.info("ai policy '%s' created tenant=%s type=%s effect=%s", name_s, tenant_s, ptype.value, eff.value)
        return {
            "id": policy_id,
            "tenant": tenant_s,
            "name": name_s,
            "policy_type": ptype.value,
            "effect": eff.value,
            "priority": prio,
            "version": policy.version,
            "status": policy.status.value if hasattr(policy.status, "value") else str(policy.status),
            "conditions": [c.to_dict() for c in constraints] if constraints else [],
        }

    # ── evaluate ───────────────────────────────────────────────────────

    async def evaluate(
        self,
        db: AsyncSession,
        tenant: str,
        resource: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Evaluate resource+context against tenant PolicyEngine.

        Wraps ``governance.policy_engine.PolicyEngine`` tenant-isolated
        (tries ``policy_engine_data_{tenant}`` then ``policy_engine_data``).

        Returns dict with decision ALLOW/DENY/REDACT/REQUIRE_APPROVAL,
        matched policy ids, sanitized results. Never exposes sensitive internals
        (actual values redacted, expected truncated).

        Fail-closed: when engine unavailable and context indicates
        RESTRICTED/SECRET, returns DENY.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required).
            resource: resource identifier being governed (required).
            context: evaluation context dict (classification etc). Raw secrets
                must never be passed — only categories/metadata.

        Returns: decision dict with keys decision, reason, matched_policies,
                 matched_policy, policy_version, results (sanitized).
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not resource or not str(resource).strip():
            raise ValidationError(message="resource is required")
        tenant_s = str(tenant).strip()
        resource_s = str(resource).strip()
        ctx: dict = dict(context) if isinstance(context, dict) else {}
        ctx.setdefault("tenant", tenant_s)
        ctx.setdefault("resource", resource_s)
        ctx.setdefault("org_id", tenant_s)

        classification = _extract_classification(ctx)
        engine_error: str | None = None
        engine_result: dict | None = None
        gate_decision: str | None = None
        matched: list[str] = []
        policy_version: str | None = None
        primary_policy_id: str | None = None

        try:
            from app.governance.policy_engine import PolicyEngine, PolicyType  # type: ignore

            # Resolve policy_type hint from context if present
            ptype_hint: Any | None = None
            for key in ("policy_type", "type", "policyType"):
                raw_pt = ctx.get(key)
                if raw_pt and str(raw_pt).strip():
                    try:
                        ptype_hint = _map_policy_type(str(raw_pt).strip())
                        break
                    except ValidationError:
                        continue

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

            if ptype_hint is not None:
                engine_result = engine.evaluate_and_enforce(tenant_s, ptype_hint, ctx)  # type: ignore
                if not isinstance(engine_result, dict):
                    raise RuntimeError("evaluate_and_enforce returned non-dict")
                raw_decision = str(engine_result.get("decision", "allowed")).lower()
                gate_decision = _ENGINE_TO_GATE.get(raw_decision, "ALLOW")
                matched = [str(x) for x in (engine_result.get("matched_policies") or [])]
            else:
                # No hint — evaluate across all types present for tenant and merge most restrictive
                try:
                    policies = engine.list_policies(org_id=tenant_s)  # type: ignore
                    types_present: set[Any] = set()
                    for p in policies or []:
                        try:
                            types_present.add(p.type)  # type: ignore
                        except Exception:
                            continue
                    if not types_present:
                        types_present = {PolicyType.SECURITY, PolicyType.AI_USAGE}
                except Exception:
                    types_present = set()
                    for t in (PolicyType.SECURITY, PolicyType.AI_USAGE, PolicyType.AI_MODEL, PolicyType.LLM_PROVIDER, PolicyType.PROMPT):
                        try:
                            types_present.add(t)
                        except Exception:
                            pass

                all_results: list[dict] = []
                candidates: list[str] = []
                for ptype in types_present:
                    try:
                        res = engine.evaluate_and_enforce(tenant_s, ptype, ctx)  # type: ignore
                        if isinstance(res, dict):
                            all_results.append(res)
                            dec = str(res.get("decision", "allowed")).lower()
                            candidates.append(dec)
                            if res.get("matched_policies"):
                                matched.extend([str(x) for x in res["matched_policies"]])
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("evaluate_and_enforce failed for %s: %s", ptype, exc)
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
                    # synthetic engine_result for uniform handling
                    engine_result = {
                        "decision": best,
                        "gate_decision": gate_decision,
                        "policies_evaluated": sum(int(r.get("policies_evaluated") or 0) for r in all_results),
                        "matched_policies": matched,
                        "results": [r.get("results", []) for r in all_results if r.get("results")],
                    }
                    flat: list[dict] = []
                    for r in all_results:
                        rs = r.get("results") or []
                        if isinstance(rs, list):
                            flat.extend(rs)
                    engine_result["results"] = flat
                else:
                    gate_decision = "ALLOW"
                    engine_result = {"decision": "allowed", "gate_decision": gate_decision, "matched_policies": [], "policies_evaluated": 0, "results": []}
                    matched = []

            # Resolve policy_version from primary matched
            if matched:
                primary_policy_id = matched[0]
                try:
                    pol = engine.get_policy(primary_policy_id)  # type: ignore
                    if pol is not None and hasattr(pol, "version"):
                        policy_version = str(getattr(pol, "version"))
                except Exception:
                    pass
            if not policy_version:
                policy_version = str(engine_result.get("version") or "1.0.0") if isinstance(engine_result, dict) else "1.0.0"

            if not gate_decision:
                gate_decision = "ALLOW"

        except ImportError as exc:
            engine_error = f"policy_engine not available: {exc}"
            logger.debug("%s", engine_error)
        except Exception as exc:  # noqa: BLE001
            engine_error = str(exc)
            logger.debug("PolicyEngine evaluate failed: %s", exc)

        # Fail-closed for restricted data when engine unavailable
        if gate_decision is None:
            if classification and classification.upper() in {"RESTRICTED", "SECRET"}:
                gate_decision = "DENY"
                reason = f"fail-closed: policy engine unavailable for {classification} data"
                _audit(tenant_s, str(ctx.get("actor") or "system"), "ai_policy.denied", resource_s, {"classification": classification, "fail_closed": True})
                return {
                    "decision": gate_decision,
                    "reason": reason,
                    "matched_policy": None,
                    "matched_policies": [],
                    "policy_version": policy_version or "1.0.0",
                    "policy_id": None,
                    "fail_closed": True,
                    "engine_error": engine_error,
                    "results": None,
                }
            gate_decision = "ALLOW"
            engine_error = engine_error or "engine returned no decision — default ALLOW for non-restricted"

        if gate_decision not in {"ALLOW", "DENY", "REDACT", "REQUIRE_APPROVAL", "ANONYMIZE"}:
            # normalize warning/custom etc to gate set
            gate_decision = {"WARN": "REDACT", "WARNING": "REDACT", "CUSTOM": "REDACT", "ESCALATED": "REQUIRE_APPROVAL"}.get(gate_decision.upper(), "ALLOW")

        reason = f"policy {gate_decision.lower()} for '{resource_s}'"
        if matched:
            reason += f" — matched {matched[:3]}"
        if engine_error:
            reason += f" (engine: {engine_error[:80]})"

        safe_reason = str(reason)[:500]
        safe_results = _sanitize_results(engine_result.get("results") if isinstance(engine_result, dict) else None) if engine_result else None

        _audit(
            tenant_s,
            str(ctx.get("actor") or ctx.get("identity") or "system"),
            f"ai_policy.evaluate.{gate_decision.lower()}",
            resource_s,
            {"decision": gate_decision, "policy_version": policy_version, "matched": matched[:10], "classification": classification},
        )

        return {
            "decision": gate_decision,
            "reason": safe_reason,
            "matched_policy": primary_policy_id,
            "matched_policies": matched,
            "policy_version": policy_version or "1.0.0",
            "policy_id": primary_policy_id,
            "fail_closed": False,
            "engine_error": engine_error,
            "results": safe_results,
            "raw": {"engine_decision": engine_result.get("decision") if isinstance(engine_result, dict) else None, "policies_evaluated": engine_result.get("policies_evaluated") if isinstance(engine_result, dict) else None} if engine_result else None,
        }

    # ── simulate ───────────────────────────────────────────────────────

    async def simulate(
        self,
        db: AsyncSession,
        tenant: str,
        resource: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Dry-run policy evaluation without persisting.

        Wraps PolicyEngine simulate_policy / evaluate_and_enforce in tenant
        isolation but does not persist any decision. Sanitizes internals
        (actual redacted).

        Args:
            db: AsyncSession (accepted for parity, not used for persistence).
            tenant: tenant scope (required).
            resource: resource identifier (required).
            context: evaluation context dict.

        Returns: dict with decision, matched_policies (sanitized), reason,
                 dry_run=True, fail_closed flag.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not resource or not str(resource).strip():
            raise ValidationError(message="resource is required")
        tenant_s = str(tenant).strip()
        resource_s = str(resource).strip()
        ctx: dict = dict(context) if isinstance(context, dict) else {}
        ctx.setdefault("tenant", tenant_s)
        ctx.setdefault("resource", resource_s)

        classification = _extract_classification(ctx)
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

            # Prefer simulate_policy when available — otherwise evaluate_and_enforce aggregation dry-run
            # Collect policy ids for tenant
            try:
                policies = engine.list_policies(org_id=tenant_s)  # type: ignore
                policy_ids = [str(getattr(p, "id")) for p in (policies or []) if getattr(p, "id", None)]
            except Exception:
                policy_ids = []

            if policy_ids and hasattr(engine, "simulate_policy"):
                try:
                    sim = engine.simulate_policy(tenant_s, f"dry-run:{resource_s}", policy_ids, ctx)  # type: ignore
                    if sim is not None and hasattr(sim, "to_dict"):
                        sim_d = sim.to_dict()  # type: ignore
                    elif isinstance(sim, dict):
                        sim_d = sim
                    else:
                        sim_d = {}
                    # derive gate decision from simulation results
                    results = sim_d.get("results") or []
                    # sim_d has total_failed etc — map to gate
                    if sim_d.get("total_failed", 0) > 0:
                        gate_decision = "DENY"
                    elif sim_d.get("total_warnings", 0) > 0:
                        gate_decision = "REDACT"
                    else:
                        # check individual results decisions
                        decs: list[str] = []
                        for r in results:
                            if isinstance(r, dict):
                                decs.append(str(r.get("decision") or r.get("effect") or "allowed").lower())
                            else:
                                # PolicyEvaluationResult dataclass
                                try:
                                    decs.append(str(getattr(r, "decision", "allowed")).lower())
                                except Exception:
                                    pass
                        if "denied" in decs:
                            gate_decision = "DENY"
                        elif "requires_approval" in decs:
                            gate_decision = "REQUIRE_APPROVAL"
                        elif "warning" in decs:
                            gate_decision = "REDACT"
                        elif decs:
                            gate_decision = _ENGINE_TO_GATE.get(decs[0], "ALLOW")
                        else:
                            gate_decision = "ALLOW"
                    matched = [str(r.get("policy_id") or r.get("policy_name") or "") for r in results if isinstance(r, dict) and r.get("matched")]
                    engine_result = {"simulation": sim_d, "results": results, "policies_evaluated": sim_d.get("policies_evaluated") or len(results)}
                except Exception as exc:  # noqa: BLE001
                    logger.debug("simulate_policy failed, falling back to evaluate: %s", exc)
                    engine_result = None

            if engine_result is None:
                # fallback: evaluate as dry-run aggregation (no persistence)
                all_results: list[dict] = []
                candidates: list[str] = []
                types_present: set[Any] = set()
                try:
                    pols = engine.list_policies(org_id=tenant_s)  # type: ignore
                    for p in pols or []:
                        try:
                            types_present.add(p.type)  # type: ignore
                        except Exception:
                            continue
                    if not types_present:
                        types_present = {PolicyType.SECURITY, PolicyType.AI_USAGE}
                except Exception:
                    for t in (PolicyType.SECURITY, PolicyType.AI_USAGE, PolicyType.AI_MODEL):
                        try:
                            types_present.add(t)
                        except Exception:
                            pass
                for ptype in types_present:
                    try:
                        res = engine.evaluate_and_enforce(tenant_s, ptype, ctx)  # type: ignore
                        if isinstance(res, dict):
                            all_results.append(res)
                            candidates.append(str(res.get("decision", "allowed")).lower())
                            if res.get("matched_policies"):
                                matched.extend([str(x) for x in res["matched_policies"]])
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
                    engine_result = {
                        "decision": best,
                        "gate_decision": gate_decision,
                        "policies_evaluated": sum(int(r.get("policies_evaluated") or 0) for r in all_results),
                        "matched_policies": matched,
                        "results": [r.get("results", []) for r in all_results if r.get("results")],
                    }
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
            logger.debug("PolicyEngine simulate failed: %s", exc)

        if gate_decision is None:
            if classification and classification.upper() in {"RESTRICTED", "SECRET"}:
                return {
                    "decision": "DENY",
                    "reason": f"fail-closed: policy engine unavailable for {classification} data (dry-run)",
                    "matched_policies": [],
                    "policies_evaluated": 0,
                    "fail_closed": True,
                    "dry_run": True,
                    "engine_error": engine_error,
                    "results": None,
                }
            gate_decision = "ALLOW"
            engine_result = {"decision": "allowed", "gate_decision": gate_decision, "matched_policies": [], "policies_evaluated": 0, "results": []}

        safe_results = _sanitize_results(engine_result.get("results") if isinstance(engine_result, dict) else None) if engine_result else None
        return {
            "decision": gate_decision,
            "reason": f"dry-run {gate_decision.lower()} — matched {matched}" if matched else f"dry-run {gate_decision.lower()} — no policy matched",
            "matched_policies": matched,
            "matched_count": len(matched),
            "policies_evaluated": int(engine_result.get("policies_evaluated") or 0) if isinstance(engine_result, dict) else 0,
            "fail_closed": False,
            "dry_run": True,
            "engine_error": engine_error,
            "results": safe_results,
        }


policy_service = AIPolicyService()
# Backwards-compat aliases
ai_policy_service = policy_service
aipolicy_service = policy_service
