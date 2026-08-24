"""Volume 57 — AIGateService pre-invocation gate.

Tenant-scoped, AsyncSession, fail-closed for RESTRICTED/SECRET when policy
engine unavailable. Never persists or logs raw secret values.

Decisions: ALLOW / DENY / REDACT / ANONYMIZE / REQUIRE_APPROVAL

Steps:
  1. Normalize classification (already classified input).
  2. PolicyEngine check (wrapped, per-tenant dir, context with
     classification/tenant/resource/provider/region/purpose/identity/
     environment/action).
  3. Provider check against governance/ai_governance AIGovernancePolicy
     blocked_providers if available.
  4. Region / residency cross-border flag.
  5. Approval path via governance/approval_workflows when decision is
     REQUIRE_APPROVAL.

Do not persist secret values — only sha256[:16] fingerprints and categories.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────

_RESTRICTED_LEVELS: set[str] = {"RESTRICTED", "SECRET"}
_ALL_LEVELS: set[str] = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "SECRET"}

# cross-border markers — conservative: any explicit external marker triggers flag
_CROSS_BORDER_MARKERS: set[str] = {
    "external",
    "cross-border",
    "cross_border",
    "cross",
    "international",
    "unknown",
}

# allowed decision set for this gate
_GATE_DECISIONS: set[str] = {"ALLOW", "DENY", "REDACT", "ANONYMIZE", "REQUIRE_APPROVAL"}

# PolicyEngine decision -> gate decision mapping
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
    """Best-effort audit; never raises, never logs raw secrets."""
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
                "governance_ai_gate",
                resource_id,
                "success",
                safe_details,
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_ai_gate", resource_id, "success", safe_details)
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _is_cross_border(region: str | None, provider: str | None = None) -> bool:
    """Heuristic cross-border detection.

    Flags when region explicitly indicates external/cross-border/international,
    or contains 'cross'. Never assumes tenant home region; only flags
    explicit external markers to avoid false positives, but RESTRICTED/SECRET
    still requires approval for any non-empty region that is not clearly domestic.
    """
    if not region:
        return False
    r = str(region).strip().lower().replace(" ", "_").replace("-", "_")
    if not r:
        return False
    if r in _CROSS_BORDER_MARKERS:
        return True
    if "cross" in r:
        return True
    if r in ("eu", "cn", "ru", "ir", "kp"):
        return True
    # regions like "eu-west-1", "ap-northeast-1" treated as cross-border for restricted data
    # we conservatively flag external region prefixes outside domestic default
    # If provider is known and region looks like cloud region with non-us prefix
    if r.startswith("eu_") or r.startswith("eu-") or r.startswith("ap_") or r.startswith("ap-"):
        return True
    return False


def _normalize_classification(level: str | None) -> str:
    if not level:
        return "INTERNAL"
    lvl = str(level).strip().upper()
    if lvl in _ALL_LEVELS:
        return lvl
    # map legacy REGULATED -> RESTRICTED
    if lvl == "REGULATED":
        return "RESTRICTED"
    return "INTERNAL"


def _engine_storage_dir(tenant: str) -> str:
    # tenant-isolated directory to avoid cross-tenant leakage (mirrors retention/DSR pattern)
    safe_tenant = str(tenant).strip().replace("/", "_").replace("\\", "_")[:64]
    return f"policy_engine_data_{safe_tenant}"


def _ai_governance_storage_dir(tenant: str) -> str:
    safe_tenant = str(tenant).strip().replace("/", "_").replace("\\", "_")[:64]
    return f"ai_governance_data_{safe_tenant}"


class AIGateService:
    """Pre-invocation gate for AI/model calls."""

    async def check(
        self,
        db: AsyncSession,
        tenant: str,
        actor: str,
        data_classification: str,
        provider: str,
        region: str | None = None,
        purpose: str | None = None,
        resource: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether an AI invocation may proceed.

        Args:
            db: AsyncSession (tenant-scoped, not used for policy engine file store
                but accepted for interface consistency).
            tenant: tenant scope (required).
            actor: calling user / service identity (required).
            data_classification: already-classified level for the input/output
                (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED/SECRET).
            provider: LLM provider name (e.g., openai, anthropic).
            region: processing region (for residency/cross-border check).
            purpose: purpose of processing (e.g., rag, summary, code-gen).
            resource: target resource identifier (model name, endpoint, etc.).

        Returns:
            dict with keys: decision (ALLOW/DENY/REDACT/ANONYMIZE/REQUIRE_APPROVAL),
            reason, classification, provider, region, cross_border, policy, approval.
            Never contains raw secret values.

        Fail-closed: if PolicyEngine unavailable and classification is
        RESTRICTED/SECRET, returns DENY.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not actor or not str(actor).strip():
            raise ValueError("actor is required")
        tenant_s = str(tenant).strip()
        actor_s = str(actor).strip()
        classification = _normalize_classification(data_classification)
        provider_s = str(provider).strip() if provider and str(provider).strip() else ""
        region_s = str(region).strip() if region and str(region).strip() else None
        purpose_s = str(purpose).strip() if purpose and str(purpose).strip() else ""
        resource_s = str(resource).strip() if resource and str(resource).strip() else ""

        if classification not in _ALL_LEVELS:
            classification = "INTERNAL"

        # Validate provider required for provider checks
        if not provider_s:
            # provider missing is a policy violation for restricted data
            if classification in _RESTRICTED_LEVELS:
                _audit(tenant_s, actor_s, "governance.ai_gate.denied", resource_s, {"classification": classification, "reason": "provider required for restricted data"})
                return {
                    "decision": "DENY",
                    "reason": "provider is required for RESTRICTED/SECRET data — fail closed",
                    "classification": classification,
                    "provider": provider_s,
                    "region": region_s,
                    "cross_border": False,
                    "policy": None,
                    "approval": None,
                }

        cross_border = _is_cross_border(region_s, provider_s)

        # ── 1. Provider block check via AIGovernancePolicy blocked_providers ──
        blocked_reason: str | None = None
        try:
            from app.governance.ai_governance import AIGovernanceManager  # type: ignore

            # Try tenant-specific dir then default dir
            mgr: Any | None = None
            for stor in (_ai_governance_storage_dir(tenant_s), "ai_governance_data"):
                try:
                    m = AIGovernanceManager(storage_dir=stor)  # type: ignore
                    # list_policies will return [] if no data; we still keep manager
                    mgr = m
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("AIGovernanceManager init failed for %s: %s", stor, exc)
                    continue
            if mgr is not None:
                try:
                    policies = mgr.list_policies(tenant_s)  # type: ignore[attr-defined]
                except TypeError:
                    policies = mgr.list_policies(tenant_s, None)  # type: ignore
                for pol in policies or []:
                    if not getattr(pol, "enabled", True):
                        continue
                    bps: list = list(getattr(pol, "blocked_providers", []) or [])
                    # normalize for comparison
                    bps_norm = [str(x).strip().lower() for x in bps if x and str(x).strip()]
                    if provider_s.lower() in bps_norm:
                        blocked_reason = f"provider '{provider_s}' blocked by AI governance policy '{getattr(pol, 'name', pol.id)}'"
                        break
                    # also check blocked_models if resource is a model name
                    if resource_s:
                        bms: list = list(getattr(pol, "blocked_models", []) or [])
                        bms_norm = [str(x).strip().lower() for x in bms if x and str(x).strip()]
                        if resource_s.lower() in bms_norm:
                            blocked_reason = f"model '{resource_s}' blocked by AI governance policy '{getattr(pol, 'name', pol.id)}'"
                            break
        except ImportError as exc:
            logger.debug("ai_governance not available: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("provider block check failed: %s", exc)

        if blocked_reason:
            _audit(tenant_s, actor_s, "governance.ai_gate.denied", resource_s, {"classification": classification, "provider": provider_s, "reason": blocked_reason})
            return {
                "decision": "DENY",
                "reason": blocked_reason,
                "classification": classification,
                "provider": provider_s,
                "region": region_s,
                "cross_border": cross_border,
                "policy": {"blocked": True, "reason": blocked_reason},
                "approval": None,
            }

        # ── 2. Region / residency cross-border check ──────────────────────
        # For RESTRICTED/SECRET, cross-border requires approval (fail-closed to REQUIRE_APPROVAL)
        # For SECRET, some policies would deny outright — we map to REQUIRE_APPROVAL then caller may deny
        region_reason: str | None = None
        if cross_border and classification in _RESTRICTED_LEVELS:
            region_reason = f"cross-border processing flagged (region={region_s}) for {classification} data — approval required"
            # Do not return yet; let policy engine also vote, but remember to elevate to REQUIRE_APPROVAL if policy allows
        elif cross_border and classification == "CONFIDENTIAL":
            # confidential cross-border is REDACT-level caution but still allow with warning
            region_reason = f"cross-border processing for CONFIDENTIAL data (region={region_s})"

        # ── 3. PolicyEngine check (wrapped, tenant dir) ───────────────────
        policy_decision: str | None = None
        policy_raw: dict | None = None
        policy_matched: list[str] = []
        policy_error: str | None = None

        # Build context as described in spec
        context: dict[str, Any] = {
            "classification": classification,
            "data_classification": classification,
            "tenant": tenant_s,
            "resource": resource_s,
            "provider": provider_s,
            "region": region_s or "",
            "purpose": purpose_s,
            "identity": actor_s,
            "actor": actor_s,
            "environment": region_s or "",
            "action": "ai.invoke",
            "decision": classification,
            # also provide nested aliases for field paths like "identity.id"
            "user": {"id": actor_s},
            "subject": {"id": actor_s},
        }

        engine: Any | None = None
        try:
            from app.governance.policy_engine import PolicyEngine, PolicyType  # type: ignore

            # Try tenant-isolated dir first, fallback to default
            for stor in (_engine_storage_dir(tenant_s), "policy_engine_data"):
                try:
                    eng = PolicyEngine(storage_dir=stor)  # type: ignore
                    # Probe that it loaded
                    _ = eng.list_policies(org_id=tenant_s)  # type: ignore
                    engine = eng
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("PolicyEngine init failed for %s: %s", stor, exc)
                    continue
            if engine is None:
                raise RuntimeError("PolicyEngine unavailable — no storage dir initialized")

            # Evaluate relevant policy types — spec says DATA/AI types
            # Evaluate AI_USAGE, LLM_PROVIDER, AI_MODEL, PROMPT, SECURITY and merge to most restrictive
            candidates: list[str] = []
            # We evaluate per type and collect final_decision strings
            for ptype in (PolicyType.AI_USAGE, PolicyType.LLM_PROVIDER, PolicyType.AI_MODEL, PolicyType.PROMPT, PolicyType.AI_AGENT, PolicyType.SECURITY):
                try:
                    res = engine.evaluate_and_enforce(tenant_s, ptype, context)  # type: ignore[attr-defined]
                    if not isinstance(res, dict):
                        continue
                    dec = str(res.get("decision", "allowed")).lower()
                    candidates.append(dec)
                    if res.get("matched_policies"):
                        policy_matched.extend([str(x) for x in res["matched_policies"]])
                    # keep last raw for diagnostics but merge candidates
                    policy_raw = res
                except Exception as exc:  # noqa: BLE001
                    logger.debug("evaluate_and_enforce failed for %s: %s", ptype, exc)
                    continue

            # Merge candidates to most restrictive
            # Priority: denied > requires_approval > escalated > warning > allowed
            priority_order = ["denied", "escalated", "requires_approval", "rollback", "retry", "warning", "custom", "allowed", "not_applicable"]
            # invert to severity: lower index = more restrictive for denied/escalated
            severity_rank: dict[str, int] = {d: i for i, d in enumerate(priority_order)}
            best: str | None = None
            best_rank = 999
            for c in candidates:
                r = severity_rank.get(c, 50)
                if r < best_rank:
                    best_rank = r
                    best = c
            policy_decision = best if best is not None else "allowed"
        except ImportError as exc:
            policy_error = f"policy_engine not available: {exc}"
            logger.debug("%s", policy_error)
        except Exception as exc:  # noqa: BLE001
            policy_error = str(exc)
            logger.debug("PolicyEngine evaluation failed: %s", exc)

        # ── Fail-closed for RESTRICTED/SECRET when engine unavailable ─────
        if policy_decision is None and classification in _RESTRICTED_LEVELS:
            _audit(tenant_s, actor_s, "governance.ai_gate.denied", resource_s, {"classification": classification, "reason": "fail-closed: policy engine unavailable for restricted data", "provider": provider_s, "region": region_s})
            return {
                "decision": "DENY",
                "reason": "fail-closed: policy engine unavailable for RESTRICTED/SECRET data",
                "classification": classification,
                "provider": provider_s,
                "region": region_s,
                "cross_border": cross_border,
                "policy": {"decision": None, "error": policy_error, "matched": []},
                "approval": None,
            }

        # If engine unavailable but classification is not restricted, allow with warning
        if policy_decision is None:
            # Check cross-border elevation before allowing
            if region_reason and classification in _RESTRICTED_LEVELS:
                # elevate to REQUIRE_APPROVAL via approval workflow
                approval_info = await self._maybe_require_approval(
                    tenant=tenant_s, actor=actor_s, resource=resource_s, classification=classification, reason=region_reason
                )
                _audit(tenant_s, actor_s, "governance.ai_gate.require_approval", resource_s, {"classification": classification, "reason": region_reason, "provider": provider_s, "region": region_s})
                return {
                    "decision": "REQUIRE_APPROVAL",
                    "reason": region_reason,
                    "classification": classification,
                    "provider": provider_s,
                    "region": region_s,
                    "cross_border": cross_border,
                    "policy": {"decision": None, "error": policy_error, "matched": policy_matched},
                    "approval": approval_info,
                }
            _audit(tenant_s, actor_s, "governance.ai_gate.allowed", resource_s, {"classification": classification, "provider": provider_s, "region": region_s})
            return {
                "decision": "ALLOW",
                "reason": "no policy matched — allowed (engine unavailable but data not restricted)",
                "classification": classification,
                "provider": provider_s,
                "region": region_s,
                "cross_border": cross_border,
                "policy": {"decision": None, "error": policy_error, "matched": []},
                "approval": None,
            }

        # Map engine decision to gate decision
        gate_decision = _ENGINE_TO_GATE.get(str(policy_decision).lower(), "ALLOW")

        # Elevate due to cross-border for restricted/secret even if policy allowed
        if gate_decision == "ALLOW" and cross_border and classification in _RESTRICTED_LEVELS and region_reason:
            gate_decision = "REQUIRE_APPROVAL"

        # ── 4. Approval if required ───────────────────────────────────────
        approval_info: dict | None = None
        if gate_decision == "REQUIRE_APPROVAL":
            reason = region_reason or f"policy requires approval for {classification} data (provider={provider_s}, purpose={purpose_s})"
            if policy_raw and policy_raw.get("matched_policies"):
                reason = f"policy requires approval — matched {policy_matched} — {reason}"
            approval_info = await self._maybe_require_approval(
                tenant=tenant_s, actor=actor_s, resource=resource_s or provider_s, classification=classification, reason=reason
            )
            _audit(tenant_s, actor_s, "governance.ai_gate.require_approval", resource_s, {"classification": classification, "provider": provider_s, "region": region_s, "reason": reason, "policy_decision": policy_decision, "matched": policy_matched})
            return {
                "decision": "REQUIRE_APPROVAL",
                "reason": reason,
                "classification": classification,
                "provider": provider_s,
                "region": region_s,
                "cross_border": cross_border,
                "policy": {"decision": policy_decision, "gate_decision": gate_decision, "matched": policy_matched, "raw": self._sanitize_policy_raw(policy_raw)},
                "approval": approval_info,
            }

        if gate_decision == "DENY":
            reason = f"policy denied AI invocation for {classification} data (provider={provider_s})"
            if policy_raw and policy_matched:
                reason = f"policy denied — matched {policy_matched} — {reason}"
            _audit(tenant_s, actor_s, "governance.ai_gate.denied", resource_s, {"classification": classification, "provider": provider_s, "region": region_s, "policy_decision": policy_decision, "matched": policy_matched})
            return {
                "decision": "DENY",
                "reason": reason,
                "classification": classification,
                "provider": provider_s,
                "region": region_s,
                "cross_border": cross_border,
                "policy": {"decision": policy_decision, "gate_decision": gate_decision, "matched": policy_matched, "raw": self._sanitize_policy_raw(policy_raw)},
                "approval": None,
            }

        if gate_decision in ("REDACT", "ANONYMIZE"):
            reason = f"policy requires {gate_decision.lower()} for {classification} data before AI invocation"
            _audit(tenant_s, actor_s, f"governance.ai_gate.{gate_decision.lower()}", resource_s, {"classification": classification, "provider": provider_s, "policy_decision": policy_decision})
            return {
                "decision": gate_decision,
                "reason": reason,
                "classification": classification,
                "provider": provider_s,
                "region": region_s,
                "cross_border": cross_border,
                "policy": {"decision": policy_decision, "gate_decision": gate_decision, "matched": policy_matched, "raw": self._sanitize_policy_raw(policy_raw)},
                "approval": None,
            }

        # ALLOW
        _audit(tenant_s, actor_s, "governance.ai_gate.allowed", resource_s, {"classification": classification, "provider": provider_s, "region": region_s, "policy_decision": policy_decision})
        return {
            "decision": "ALLOW",
            "reason": f"allowed for {classification} data (provider={provider_s})",
            "classification": classification,
            "provider": provider_s,
            "region": region_s,
            "cross_border": cross_border,
            "policy": {"decision": policy_decision, "gate_decision": gate_decision, "matched": policy_matched, "raw": self._sanitize_policy_raw(policy_raw)},
            "approval": None,
        }

    def _sanitize_policy_raw(self, raw: dict | None) -> dict | None:
        """Strip raw content from policy engine details — keep only safe metadata."""
        if not raw or not isinstance(raw, dict):
            return None
        safe: dict = {}
        for k, v in raw.items():
            if k in ("prompt", "content", "secret", "raw_value", "value", "match"):
                continue
            if k == "results" and isinstance(v, list):
                # keep only id/effect/decisions, strip constraint actual values that may contain secrets
                safe_results = []
                for r in v:
                    if not isinstance(r, dict):
                        safe_results.append(r)
                        continue
                    sr: dict = {}
                    for rk, rv in r.items():
                        if rk == "details" and isinstance(rv, list):
                            # keep field/operator/passed but redact actual/expected that might leak
                            safe_details = []
                            for d in rv:
                                if not isinstance(d, dict):
                                    safe_details.append(d)
                                    continue
                                sd = {kk: vv for kk, vv in d.items() if kk not in ("actual", "expected")}
                                sd["actual"] = "[REDACTED]" if d.get("actual") else None
                                # expected is policy value, safe to keep but truncate
                                exp = d.get("expected")
                                if isinstance(exp, str) and len(exp) > 100:
                                    sd["expected"] = exp[:100]
                                else:
                                    sd["expected"] = exp
                                safe_details.append(sd)
                            sr[rk] = safe_details
                        elif rk in ("actual", "value", "secret"):
                            continue
                        else:
                            sr[rk] = rv
                    safe_results.append(sr)
                safe[k] = safe_results
            else:
                safe[k] = v
        return safe

    async def _maybe_require_approval(
        self,
        tenant: str,
        actor: str,
        resource: str,
        classification: str,
        reason: str,
    ) -> dict[str, Any]:
        """Best-effort create approval workflow; fallback to stub if engine unavailable."""
        try:
            from app.governance.approval_workflows import (  # type: ignore
                ApprovalRequest,
                ApprovalRole,
                ApprovalStatus,
                ApprovalStep,
                ApprovalType,
                ApprovalWorkflow,
                ApprovalWorkflowEngine,
            )

            stor = f"approval_engine_data_{tenant}"
            try:
                engine = ApprovalWorkflowEngine(storage_dir=stor)  # type: ignore
            except Exception:
                engine = ApprovalWorkflowEngine()  # type: ignore

            wf_id = str(uuid.uuid4())
            try:
                step = ApprovalStep(
                    id=str(uuid.uuid4()),
                    name="ai-gate-approval",
                    role=ApprovalRole.APPROVER,  # type: ignore
                    required_approvers=1,
                    order=0,
                    wait_for_previous=True,
                    timeout_hours=48,
                    escalation_after_hours=24,
                )
            except Exception:
                step = ApprovalStep(
                    id=str(uuid.uuid4()),
                    name="ai-gate-approval",
                    role=ApprovalRole.ADMIN,  # type: ignore
                    required_approvers=1,
                )  # type: ignore

            workflow = ApprovalWorkflow(
                id=wf_id,
                org_id=tenant,
                name=f"ai-gate:{classification}:{resource[:32]}",
                description=f"AI gate approval required: {reason}",
                type=ApprovalType.COMPLIANCE,  # type: ignore
                target_type="ai_invocation",
                target_id=resource or actor,
                steps=[step],
                status=ApprovalStatus.PENDING,  # type: ignore
                initiated_by=actor,
                metadata={"classification": classification, "reason": reason, "resource": resource},
            )
            engine.create_workflow(workflow)
            req = ApprovalRequest(
                id=str(uuid.uuid4()),
                workflow_id=wf_id,
                org_id=tenant,
                requester=actor,
                target_type="ai_invocation",
                target_id=resource or actor,
                reason=reason,
                status=ApprovalStatus.PENDING,  # type: ignore
                metadata={"classification": classification},
            )
            engine.submit_request(req)
            return {"workflow_id": wf_id, "request_id": req.id, "status": "pending", "reason": reason}
        except ImportError as exc:
            logger.debug("approval_workflows not available, stub: %s", exc)
            return {"stub": True, "status": "pending", "reason": reason}
        except Exception as exc:  # noqa: BLE001
            logger.debug("approval workflow create failed, stub: %s", exc)
            return {"stub": True, "status": "pending", "reason": reason, "error": str(exc)}


ai_gate_service = AIGateService()
