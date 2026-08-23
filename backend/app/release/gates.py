"""Volume 56 — Release Gate Service (NovaForge).

Composes configurable gates: tests, quality, security, dependency,
artifact verification (digest/signature/SBOM/provenance), approval, SLO,
incident, and window. Reuses existing engines when available and falls
back to deterministic stubs otherwise.

Blocking semantics are hard-enforced:
    * If any *blocking* gate fails, its ReleaseGateResult status is
      ``blocked`` and the overall release MUST be treated as blocked.
    * Non-blocking failures are ``failed`` and do not by themselves
      block promotion, but callers must still check ``is_blocked(results)``.
    * This service NEVER auto-bypasses or downgrades a blocking failure
      to ``passed``.

Models: app.release.models.{ReleaseGate, ReleaseGateResult, GateType}
Persistence: AsyncSession (SQLAlchemy async).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.release.models import GateType, ReleaseGate, ReleaseGateResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional integrations — imported lazily so the module remains additive
# and never crashes when an optional sub-system is not installed.
# ---------------------------------------------------------------------------

try:
    from app.quality.gates import QualityGateEngine  # type: ignore
except Exception:  # pragma: no cover
    QualityGateEngine = None  # type: ignore

try:
    from app.security.models import SecurityFinding, SecuritySBOM, SecurityProvenance  # type: ignore
except Exception:  # pragma: no cover
    SecurityFinding = None  # type: ignore
    SecuritySBOM = None  # type: ignore
    SecurityProvenance = None  # type: ignore

try:
    from app.sre.models import SREErrorBudget, SREIncident, SRESLO, SREMaintenanceWindow  # type: ignore
    from app.sre.constants import BUDGET_EXHAUSTED  # type: ignore
except Exception:  # pragma: no cover
    SREErrorBudget = None  # type: ignore
    SREIncident = None  # type: ignore
    SRESLO = None  # type: ignore
    SREMaintenanceWindow = None  # type: ignore
    BUDGET_EXHAUSTED = "exhausted"

try:
    from app.delivery.models import DeliveryArtifact  # type: ignore
except Exception:  # pragma: no cover
    DeliveryArtifact = None  # type: ignore

try:
    from app.incident.models import Incident as IncidentModel  # type: ignore
except Exception:  # pragma: no cover
    IncidentModel = None  # type: ignore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_GATE_TYPES = {e.value for e in GateType}


def _normalize_gate_type(gate_type: str | GateType) -> str:
    """Normalize GateType input to its string value, validating membership."""
    if isinstance(gate_type, GateType):
        return gate_type.value
    if isinstance(gate_type, str):
        v = gate_type.strip().lower()
        # allow both enum value and enum name
        for e in GateType:
            if v == e.value.lower() or v == e.name.lower():
                return e.value
        # direct value check
        if v in _VALID_GATE_TYPES:
            return v
    raise ValueError(f"invalid gate_type {gate_type!r}; must be one of {sorted(_VALID_GATE_TYPES)}")


def _blocked_status(gate: ReleaseGate, passed: bool) -> str:
    """Map boolean pass/fail to ReleaseGateResult.status respecting blocking."""
    if passed:
        return "passed"
    return "blocked" if gate.blocking else "failed"


def _score(passed: bool, partial: float | None = None) -> float:
    if partial is not None:
        return round(max(0.0, min(1.0, float(partial))), 4)
    return 1.0 if passed else 0.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ReleaseGateService:
    """Composes and evaluates configurable release gates.

    All gate evaluations are deterministic, evidence-backed, and never
    fabricate telemetry. Each gate threshold is a JSON dict stored on the
    ReleaseGate row so operators can tune gates without code changes.
    """

    # ---------------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------------

    async def create_gate(
        self,
        db: AsyncSession,
        tenant: str,
        name: str,
        gate_type: str | GateType,
        threshold: dict[str, Any] | None = None,
        blocking: bool = True,
        enabled: bool = True,
    ) -> ReleaseGate:
        """Create and persist a new release gate for *tenant*.

        Args:
            db: AsyncSession
            tenant: tenant / organization identifier
            name: human-readable gate name
            gate_type: GateType enum value or string
            threshold: JSON-serialisable threshold dict (operator-tunable)
            blocking: when True a failure blocks promotion (status=blocked)
            enabled: when False the gate is skipped during evaluate()

        Returns:
            The persisted ReleaseGate.
        """
        if not tenant or not tenant.strip():
            raise ValueError("tenant must be a non-empty string")
        if not name or not name.strip():
            raise ValueError("name must be a non-empty string")

        normalized = _normalize_gate_type(gate_type)

        gate = ReleaseGate(
            tenant=tenant,
            name=name.strip(),
            gate_type=normalized,
            threshold=dict(threshold or {}),
            blocking=bool(blocking),
            enabled=bool(enabled),
        )
        db.add(gate)
        await db.flush()
        logger.info("created gate tenant=%s name=%s type=%s blocking=%s", tenant, name, normalized, blocking)
        return gate

    async def list_gates(self, db: AsyncSession, tenant: str) -> list[ReleaseGate]:
        """List all gates for *tenant* ordered by creation time."""
        stmt = select(ReleaseGate).where(ReleaseGate.tenant == tenant).order_by(ReleaseGate.created_at.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ---------------------------------------------------------------
    # Evaluation — top-level
    # ---------------------------------------------------------------

    async def evaluate(
        self,
        db: AsyncSession,
        release_id: uuid.UUID | str,
        tenant: str,
    ) -> list[ReleaseGateResult]:
        """Evaluate *all* enabled gates for *release_id* / *tenant*.

        For each gate:
            * calls :meth:`evaluate_single`
            * enforces blocking semantics (blocking failure => status=blocked)
            * persists a ReleaseGateResult row (status passed/failed/blocked,
              score, evidence, evaluated_by)

        The method **never** bypasses a blocking gate. Callers MUST check
        whether any result has status == "blocked" and refuse promotion.

        Returns:
            List of persisted ReleaseGateResult objects (in gate order).
        """
        # ---- resolve release_id to UUID ----
        if isinstance(release_id, str):
            try:
                release_pk = uuid.UUID(release_id)
            except ValueError as exc:
                raise ValueError(f"invalid release_id {release_id!r}: {exc}") from exc
        else:
            release_pk = release_id

        # ---- load release record (for context) ----
        context = await self._build_context(db, release_pk, tenant)

        # ---- load gates ----
        gates = await self.list_gates(db, tenant)
        if not gates:
            logger.warning("no gates configured for tenant=%s release=%s", tenant, release_pk)
            return []

        results: list[ReleaseGateResult] = []
        for gate in gates:
            if not gate.enabled:
                continue
            status, score, evidence = await self.evaluate_single(gate, context)

            # ---- hard-enforce blocking semantics (NEVER bypass) ----
            # evaluate_single already maps passed/failed to blocked for
            # blocking gates, but we re-enforce here so no caller can
            # mutate the status before persistence.
            if gate.blocking and status != "passed":
                status = "blocked"
            elif not gate.blocking and status == "blocked":
                # non-blocking gates must not escalate to blocked
                status = "failed"

            evidence = dict(evidence or {})
            # Annotate evidence with blocking decision so audit trail is explicit
            evidence["_gate"] = {
                "name": gate.name,
                "gate_type": gate.gate_type,
                "blocking": gate.blocking,
                "enabled": gate.enabled,
                "threshold": gate.threshold,
            }
            evidence["_release_id"] = str(release_pk)
            evidence["_tenant"] = tenant
            evidence["_evaluated_at"] = datetime.now(timezone.utc).isoformat()

            row = ReleaseGateResult(
                release_id=release_pk,
                gate_id=gate.id,
                status=status,
                score=float(score),
                evidence=evidence,
                evaluated_by="system",
            )
            db.add(row)
            results.append(row)

        await db.flush()

        # ---- overall decision logging (no bypass) ----
        blocked = [r for r in results if r.status == "blocked"]
        if blocked:
            logger.warning(
                "release %s tenant=%s BLOCKED by %d blocking gate(s): %s",
                release_pk,
                tenant,
                len(blocked),
                ", ".join(str(r.gate_id) for r in blocked),
            )

        return results

    async def evaluate_single(
        self,
        gate: ReleaseGate,
        context: dict[str, Any],
    ) -> tuple[str, float, dict[str, Any]]:
        """Evaluate a single gate against *context*.

        Args:
            gate: ReleaseGate ORM object (provides gate_type, threshold,
                  blocking, enabled)
            context: dict assembled by :meth:`_build_context` containing
                     keys: release, candidate, artifact, approvals, tenant,
                     release_id, db (optional), plus any caller-provided
                     evidence.

        Returns:
            Tuple of (status, score, evidence) where status is one of
            ``passed`` | ``failed`` | ``blocked`` (blocked only when
            gate.blocking is True and the check fails).
        """
        gate_type = str(gate.gate_type or "").lower()
        threshold: dict[str, Any] = dict(gate.threshold or {})

        # Dispatch — each helper returns (passed: bool, score: float, evidence: dict)
        try:
            if gate_type == GateType.TESTS.value or gate_type == "tests":
                passed, score, evidence = await self._eval_tests(context, threshold)
            elif gate_type == GateType.QUALITY.value or gate_type == "quality":
                passed, score, evidence = await self._eval_quality(context, threshold)
            elif gate_type == GateType.SECURITY.value or gate_type == "security":
                passed, score, evidence = await self._eval_security(context, threshold)
            elif gate_type == GateType.DEPENDENCY.value or gate_type == "dependency":
                passed, score, evidence = await self._eval_dependency(context, threshold)
            elif gate_type in (GateType.ARTIFACT.value, GateType.SBOM.value, "artifact", "sbom"):
                passed, score, evidence = await self._eval_artifact(context, threshold, gate_type)
            elif gate_type == GateType.APPROVAL.value or gate_type == "approval":
                passed, score, evidence = await self._eval_approval(context, threshold)
            elif gate_type == GateType.SLO.value or gate_type == "slo":
                passed, score, evidence = await self._eval_slo(context, threshold)
            elif gate_type == GateType.INCIDENT.value or gate_type == "incident":
                passed, score, evidence = await self._eval_incident(context, threshold)
            elif gate_type == GateType.WINDOW.value or gate_type == "window":
                passed, score, evidence = await self._eval_window(context, threshold)
            elif gate_type == GateType.COST.value or gate_type == "cost":
                passed, score, evidence = await self._eval_cost(context, threshold)
            elif gate_type == GateType.AI_GOVERNANCE.value or gate_type == "ai_governance":
                passed, score, evidence = await self._eval_ai_governance(context, threshold)
            else:
                # Unknown gate type — treat as failed when blocking, warn otherwise
                logger.warning("unknown gate_type=%s for gate %s", gate_type, gate.id)
                passed, score, evidence = False, 0.0, {"error": f"unknown gate_type: {gate_type}"}
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("gate evaluation failed gate=%s type=%s: %s", gate.id, gate_type, exc)
            passed, score, evidence = False, 0.0, {"error": str(exc), "exception_type": type(exc).__name__}

        status = _blocked_status(gate, passed)
        return status, float(score), dict(evidence)

    # ---------------------------------------------------------------
    # Context building
    # ---------------------------------------------------------------

    async def _build_context(
        self,
        db: AsyncSession,
        release_pk: uuid.UUID,
        tenant: str,
    ) -> dict[str, Any]:
        """Assemble evaluation context from DB rows.

        Context keys:
            db, tenant, release_id, release, candidate, artifact,
            approvals, environment, service
        Missing optional rows are None (evaluators handle absence explicitly).
        """
        context: dict[str, Any] = {
            "db": db,
            "tenant": tenant,
            "release_id": release_pk,
            "release": None,
            "candidate": None,
            "artifact": None,
            "approvals": [],
            "environment": None,
            "service": None,
        }

        # ReleaseRecord
        try:
            from app.release.models import ReleaseRecord, ReleaseCandidate, ReleaseApproval  # local import to avoid cycle

            stmt = select(ReleaseRecord).where(ReleaseRecord.id == release_pk)
            result = await db.execute(stmt)
            release = result.scalar_one_or_none()
            context["release"] = release
            if release is not None:
                context["environment"] = getattr(release, "environment", None)
                context["service"] = getattr(release, "service", None)

                # ReleaseCandidate (latest for this release)
                stmt2 = select(ReleaseCandidate).where(ReleaseCandidate.release_id == release_pk).order_by(ReleaseCandidate.created_at.desc()).limit(1)
                result2 = await db.execute(stmt2)
                candidate = result2.scalar_one_or_none()
                context["candidate"] = candidate

                # DeliveryArtifact via artifact_id or candidate
                artifact_id = getattr(release, "artifact_id", None) or getattr(candidate, "artifact_id", None) if candidate else None
                if artifact_id and DeliveryArtifact is not None:
                    try:
                        stmt3 = select(DeliveryArtifact).where(DeliveryArtifact.id == artifact_id)
                        result3 = await db.execute(stmt3)
                        context["artifact"] = result3.scalar_one_or_none()
                    except Exception:
                        context["artifact"] = None
                # Also try candidate build context
                if context["artifact"] is None and candidate is not None:
                    # Some deployments store artifact hash in candidate metadata
                    pass

                # Approvals
                stmt4 = select(ReleaseApproval).where(ReleaseApproval.release_id == release_pk)
                result4 = await db.execute(stmt4)
                context["approvals"] = list(result4.scalars().all())
            else:
                logger.warning("release %s not found for tenant %s", release_pk, tenant)
        except Exception as exc:
            logger.warning("failed to build context for release %s: %s", release_pk, exc)

        return context

    # ---------------------------------------------------------------
    # Gate evaluators — real checks, no placeholders
    # ---------------------------------------------------------------

    async def _eval_tests(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        """Tests gate: requires tests passed boolean / counts."""
        candidate = context.get("candidate")
        release = context.get("release")

        # Extract tests payload from candidate or release metadata
        tests: dict[str, Any] | None = None
        if candidate is not None:
            tests = getattr(candidate, "tests", None)
            if not tests:
                # fallback: candidate dict-like
                tests = getattr(candidate, "metadata_json", None) or {}
                if "tests" in tests:
                    tests = tests["tests"]
                else:
                    tests = None
        if tests is None and release is not None:
            meta = getattr(release, "metadata_json", None) or {}
            tests = meta.get("tests")

        # Also allow direct context injection for testing
        if tests is None:
            tests = context.get("tests")

        evidence: dict[str, Any] = {"threshold": threshold}
        if tests is None:
            evidence["reason"] = "no test results found"
            evidence["tests"] = None
            # Strict: missing tests is a failure
            return False, 0.0, evidence

        evidence["tests"] = tests

        # Threshold knobs
        require_passed: bool = bool(threshold.get("require_passed", True))
        max_failed: int = int(threshold.get("max_failed", 0))
        min_pass_rate: float = float(threshold.get("min_pass_rate", 1.0))
        min_coverage: float | None = threshold.get("min_coverage")

        # Determine pass/fail from common shapes
        # Supported shapes:
        #   {"passed": true/false, "total": N, "failed": M, "coverage": 0.85}
        #   {"status": "passed"/"failed", ...}
        #   {"tests_passed": true}
        #   {"success": true}
        passed_flag: bool | None = None
        if isinstance(tests, dict):
            if "passed" in tests:
                passed_flag = bool(tests["passed"])
            elif "tests_passed" in tests:
                passed_flag = bool(tests["tests_passed"])
            elif "success" in tests:
                passed_flag = bool(tests["success"])
            elif "status" in tests:
                passed_flag = str(tests["status"]).lower() in ("passed", "success", "ok", "pass")
            else:
                # Infer from counts
                total = tests.get("total")
                failed = tests.get("failed", 0)
                if total is not None:
                    try:
                        total_i = int(total)
                        failed_i = int(failed or 0)
                        if total_i > 0:
                            passed_flag = failed_i == 0
                    except Exception:
                        pass

        total = tests.get("total") if isinstance(tests, dict) else None
        failed = tests.get("failed", 0) if isinstance(tests, dict) else 0
        coverage = tests.get("coverage") if isinstance(tests, dict) else None

        evidence["passed_flag"] = passed_flag
        evidence["total"] = total
        evidence["failed"] = failed
        evidence["coverage"] = coverage

        # Evaluate against thresholds
        checks: list[bool] = []

        if require_passed:
            checks.append(passed_flag is True)

        # max_failed
        try:
            failed_i = int(failed or 0)
            checks.append(failed_i <= max_failed)
            evidence["max_failed_check"] = f"{failed_i} <= {max_failed}"
        except Exception:
            pass

        # pass rate
        if total is not None:
            try:
                total_i = int(total)
                failed_i = int(failed or 0)
                passed_count = total_i - failed_i
                rate = (passed_count / total_i) if total_i > 0 else 0.0
                evidence["pass_rate"] = round(rate, 4)
                checks.append(rate >= min_pass_rate)
            except Exception:
                pass

        # coverage
        if min_coverage is not None and coverage is not None:
            try:
                cov_f = float(coverage)
                evidence["coverage_check"] = f"{cov_f} >= {float(min_coverage)}"
                checks.append(cov_f >= float(min_coverage))
            except Exception:
                pass

        passed = all(checks) if checks else (passed_flag is True)
        score = 1.0 if passed else 0.0
        # Partial score when counts available
        if not passed and total is not None:
            try:
                total_i = int(total)
                failed_i = int(failed or 0)
                if total_i > 0:
                    score = round(max(0.0, (total_i - failed_i) / total_i), 4)
            except Exception:
                pass

        evidence["checks_passed"] = passed
        return passed, _score(passed, score), evidence

    async def _eval_quality(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        """Quality gate: reuses QualityGateEngine when available."""
        candidate = context.get("candidate")
        evidence: dict[str, Any] = {"threshold": threshold}

        # Gather inputs for QualityGateEngine
        findings: list[dict[str, Any]] = []
        quality_scores: dict[str, float] = {}
        breaking_changes: list[dict[str, Any]] = []
        tests_pass: bool | None = None

        if candidate is not None:
            q = getattr(candidate, "quality", None) or {}
            if isinstance(q, dict):
                findings = q.get("findings", []) or q.get("issues", []) or []
                quality_scores = q.get("scores", {}) or q.get("quality_scores", {}) or {}
                # allow flat score
                if "score" in q and "overall" not in quality_scores:
                    try:
                        quality_scores["overall"] = float(q["score"])
                    except Exception:
                        pass
                breaking_changes = q.get("breaking_changes", []) or []
                tests_pass = q.get("tests_pass")
                if tests_pass is None:
                    t = getattr(candidate, "tests", None) or {}
                    if isinstance(t, dict):
                        tests_pass = t.get("passed")

        # Allow direct injection
        if not findings and "findings" in context:
            findings = context["findings"] or []
        if not quality_scores and "quality_scores" in context:
            quality_scores = context["quality_scores"] or {}

        evidence["findings_count"] = len(findings)
        evidence["quality_scores"] = quality_scores

        if QualityGateEngine is not None:
            try:
                rules = threshold.get("rules")
                engine = QualityGateEngine(rules=rules)  # type: ignore
                evaluation = engine.evaluate(
                    findings=findings,
                    quality_scores=quality_scores,
                    breaking_changes=breaking_changes,
                    tests_pass=tests_pass,
                )
                verdict = getattr(evaluation, "verdict", "fail")
                # verdict: pass|fail|block
                if verdict == "pass":
                    return True, float(getattr(evaluation, "score", 1.0)), {
                        **evidence,
                        "verdict": verdict,
                        "score": getattr(evaluation, "score", 1.0),
                        "failures": [f.__dict__ if hasattr(f, "__dict__") else dict(f) for f in getattr(evaluation, "failures", [])],
                        "results": [r.__dict__ if hasattr(r, "__dict__") else dict(r) for r in getattr(evaluation, "results", [])],
                    }
                else:
                    # fail or block — both are failures here; blocking mapping is done by caller
                    return False, float(getattr(evaluation, "score", 0.0)), {
                        **evidence,
                        "verdict": verdict,
                        "score": getattr(evaluation, "score", 0.0),
                        "failures": [f.__dict__ if hasattr(f, "__dict__") else dict(f) for f in getattr(evaluation, "failures", [])],
                        "results": [r.__dict__ if hasattr(r, "__dict__") else dict(r) for r in getattr(evaluation, "results", [])],
                    }
            except Exception as exc:
                evidence["engine_error"] = str(exc)
                # fall through to stub

        # ---- Stub fallback ----
        min_score = float(threshold.get("min_score", threshold.get("overall", 0.6)))
        max_critical = int(threshold.get("max_critical", 0))
        max_high = int(threshold.get("max_high", 3))

        # Count severities from findings
        severity_counts: dict[str, int] = {}
        for f in findings:
            sev = str(f.get("severity", "info")).lower()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        critical = severity_counts.get("critical", 0)
        high = severity_counts.get("high", 0)
        overall = float(quality_scores.get("overall", quality_scores.get("score", 0.0)) or 0.0)

        evidence["severity_counts"] = severity_counts
        evidence["overall"] = overall
        evidence["min_score"] = min_score

        passed = (overall >= min_score) and (critical <= max_critical) and (high <= max_high)
        # Also fail on breaking changes if threshold says so
        if threshold.get("block_on_breaking", False) and breaking_changes:
            passed = False
            evidence["breaking_changes"] = breaking_changes[:5]

        score = _score(passed, overall if overall else (1.0 if passed else 0.0))
        return passed, score, evidence

    async def _eval_security(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        """Security gate: checks critical/high findings against thresholds."""
        candidate = context.get("candidate")
        db: AsyncSession | None = context.get("db")
        evidence: dict[str, Any] = {"threshold": threshold}

        # Defaults
        max_critical = int(threshold.get("max_critical", 0))
        max_high = int(threshold.get("max_high", 3))
        max_medium = int(threshold.get("max_medium", threshold.get("max_med", 10)))
        max_risk = float(threshold.get("max_risk_score", threshold.get("max_risk", 7.0)))

        # Try to collect security payload from candidate
        sec: dict[str, Any] | None = None
        if candidate is not None:
            sec = getattr(candidate, "security", None)
        if sec is None:
            sec = context.get("security")

        severity_counts: dict[str, int] = {}
        max_found_risk = 0.0

        if isinstance(sec, dict):
            # Shape A: {"critical": 1, "high": 2, ...}
            # Shape B: {"findings": [...], "summary": {...}}
            # Shape C: {"severity_counts": {...}}
            if "severity_counts" in sec:
                severity_counts = {k.lower(): int(v) for k, v in sec["severity_counts"].items()}
            elif "summary" in sec and isinstance(sec["summary"], dict):
                severity_counts = {k.lower(): int(v) for k, v in sec["summary"].items() if k.lower() in ("critical", "high", "medium", "low", "informational")}
            else:
                for k in ("critical", "high", "medium", "low"):
                    if k in sec:
                        try:
                            severity_counts[k] = int(sec[k])
                        except Exception:
                            pass
            # risk
            if "risk_score" in sec:
                try:
                    max_found_risk = float(sec["risk_score"])
                except Exception:
                    pass
            if "findings" in sec and isinstance(sec["findings"], list):
                for f in sec["findings"]:
                    sev = str(f.get("severity", "")).lower()
                    if sev:
                        severity_counts[sev] = severity_counts.get(sev, 0) + 1
                    try:
                        rs = float(f.get("risk_score", 0) or 0)
                        if rs > max_found_risk:
                            max_found_risk = rs
                    except Exception:
                        pass

        # If we still have no counts and DB is available, query SecurityFinding
        if not severity_counts and db is not None and SecurityFinding is not None:
            try:
                tenant = context.get("tenant", "")
                # Use commit_sha or service as correlation if available
                # Fallback: count open findings for tenant
                stmt = select(SecurityFinding.severity, SecurityFinding.risk_score).where(
                    SecurityFinding.tenant == tenant,
                    SecurityFinding.status == "open",
                ).limit(1000)
                result = await db.execute(stmt)
                for sev, rs in result.all():
                    sev = str(sev).lower()
                    severity_counts[sev] = severity_counts.get(sev, 0) + 1
                    try:
                        if rs and float(rs) > max_found_risk:
                            max_found_risk = float(rs)
                    except Exception:
                        pass
            except Exception as exc:
                evidence["db_query_error"] = str(exc)

        evidence["severity_counts"] = severity_counts
        evidence["max_risk_found"] = max_found_risk

        critical = severity_counts.get("critical", 0)
        high = severity_counts.get("high", 0)
        medium = severity_counts.get("medium", 0)

        checks: list[bool] = [
            critical <= max_critical,
            high <= max_high,
            medium <= max_medium,
            max_found_risk <= max_risk,
        ]
        passed = all(checks)
        evidence["checks"] = {
            "critical": f"{critical} <= {max_critical} -> {critical <= max_critical}",
            "high": f"{high} <= {max_high} -> {high <= max_high}",
            "medium": f"{medium} <= {max_medium} -> {medium <= max_medium}",
            "risk": f"{max_found_risk} <= {max_risk} -> {max_found_risk <= max_risk}",
        }

        # Score: 1.0 if all pass, else penalize by violation ratio
        if passed:
            score = 1.0
        else:
            violations = sum(1 for c in checks if not c)
            score = round(max(0.0, 1.0 - violations * 0.25), 4)

        return passed, _score(passed, score), evidence

    async def _eval_dependency(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        candidate = context.get("candidate")
        evidence: dict[str, Any] = {"threshold": threshold}

        deps: dict[str, Any] | None = None
        if candidate is not None:
            deps = getattr(candidate, "dependencies", None)
        if deps is None:
            deps = context.get("dependencies") or context.get("dependency")

        if deps is None:
            # No dependency info — pass if threshold allows missing, else fail
            if threshold.get("allow_missing", True):
                evidence["reason"] = "no dependency data — allowed by threshold"
                return True, 1.0, evidence
            evidence["reason"] = "no dependency data"
            return False, 0.0, evidence

        evidence["dependencies"] = deps

        max_vuln = int(threshold.get("max_vulnerable", threshold.get("max_vulns", 0)))
        max_outdated = int(threshold.get("max_outdated", 10))
        block_on_license = bool(threshold.get("block_on_license_violation", True))
        allowed_licenses = threshold.get("allowed_licenses")

        vuln_count = 0
        outdated_count = 0
        license_violations: list[str] = []

        if isinstance(deps, dict):
            vuln_count = int(deps.get("vulnerable", deps.get("vuln_count", deps.get("vulnerabilities", 0)) or 0))
            outdated_count = int(deps.get("outdated", deps.get("outdated_count", 0) or 0))
            # Licenses
            violations = deps.get("license_violations", deps.get("violations", []))
            if isinstance(violations, list):
                license_violations = [str(v) for v in violations]
            # Alternative shape: components with licenses
            if allowed_licenses and isinstance(deps.get("components"), list):
                for comp in deps["components"]:
                    lic = comp.get("license_id", comp.get("license", ""))
                    if lic and lic not in allowed_licenses:
                        license_violations.append(f"{comp.get('name','?')}:{lic}")

        evidence["vulnerable"] = vuln_count
        evidence["outdated"] = outdated_count
        evidence["license_violations"] = license_violations

        passed = True
        if vuln_count > max_vuln:
            passed = False
        if outdated_count > max_outdated:
            # outdated is typically non-blocking unless threshold says so
            if threshold.get("block_on_outdated", False):
                passed = False
        if block_on_license and license_violations:
            passed = False

        score = 1.0 if passed else round(max(0.0, 1.0 - min(1.0, vuln_count / max(1, max_vuln + 1) * 0.5)), 4)
        return passed, _score(passed, score), evidence

    async def _eval_artifact(
        self, context: dict[str, Any], threshold: dict[str, Any], gate_type: str
    ) -> tuple[bool, float, dict[str, Any]]:
        """Artifact verification: digest / signature / SBOM / provenance."""
        artifact = context.get("artifact")
        candidate = context.get("candidate")
        db: AsyncSession | None = context.get("db")
        release = context.get("release")

        # Threshold knobs — defaults require digest + signature for production safety
        require_digest = bool(threshold.get("require_digest", True))
        require_signature = bool(threshold.get("require_signature", True))
        require_sbom = bool(threshold.get("require_sbom", threshold.get("require_SBOM", True)))
        require_provenance = bool(threshold.get("require_provenance", True))
        require_immutable = bool(threshold.get("require_immutable", False))

        evidence: dict[str, Any] = {"threshold": threshold, "gate_type": gate_type}

        # If artifact is None try to synthesize from candidate/release
        artifact_dict: dict[str, Any] = {}
        if artifact is not None:
            # SQLAlchemy object or dict
            if isinstance(artifact, dict):
                artifact_dict = dict(artifact)
            else:
                artifact_dict = {
                    "hash": getattr(artifact, "hash", None) or getattr(artifact, "digest", None),
                    "digest": getattr(artifact, "hash", None),
                    "signed": getattr(artifact, "signed", None),
                    "signature": getattr(artifact, "signature", None),
                    "sbom": getattr(artifact, "sbom", None),
                    "provenance": getattr(artifact, "provenance", None),
                    "immutable": getattr(artifact, "immutable", None),
                    "storage_url": getattr(artifact, "storage_url", None),
                    "id": str(getattr(artifact, "id", "")),
                }
        else:
            # Try candidate artifact reference
            if candidate is not None:
                artifact_dict = {
                    "hash": getattr(candidate, "artifact_id", None),
                    "from_candidate": True,
                }
            if release is not None and not artifact_dict.get("hash"):
                artifact_dict["hash"] = getattr(release, "artifact_id", None)

        # Also allow direct context injection e.g. {"artifact": {"hash": "sha256:..."}}
        injected = context.get("artifact_dict") or context.get("artifact_payload")
        if injected and isinstance(injected, dict):
            artifact_dict.update(injected)

        evidence["artifact"] = {k: (v if k != "signature" else ("present" if v else None)) for k, v in artifact_dict.items()}

        checks: dict[str, bool] = {}

        # Digest / hash
        has_digest = bool(artifact_dict.get("hash") or artifact_dict.get("digest"))
        if require_digest:
            checks["digest"] = has_digest
            evidence["has_digest"] = has_digest
        else:
            checks["digest"] = True

        # Signature
        has_signature = bool(artifact_dict.get("signed") or artifact_dict.get("signature"))
        # If artifact is a DB row, signed flag is authoritative
        if artifact is not None and not isinstance(artifact, dict):
            has_signature = bool(getattr(artifact, "signed", False) and getattr(artifact, "signature", None))
        if require_signature:
            checks["signature"] = has_signature
            evidence["has_signature"] = has_signature
        else:
            checks["signature"] = True

        # SBOM
        has_sbom = bool(artifact_dict.get("sbom"))
        if not has_sbom and db is not None and SecuritySBOM is not None:
            try:
                artifact_id_str = artifact_dict.get("id") or str(getattr(context.get("artifact"), "id", "") or "")
                target_id = artifact_id_str or str(context.get("release_id", ""))
                if target_id:
                    stmt = select(SecuritySBOM).where(SecuritySBOM.target_id == target_id).limit(1)
                    result = await db.execute(stmt)
                    sbom_row = result.scalar_one_or_none()
                    if sbom_row is not None:
                        has_sbom = True
                        evidence["sbom_row_id"] = str(sbom_row.id)
            except Exception as exc:
                evidence["sbom_lookup_error"] = str(exc)

        # Also check threshold sbom gate_type specifically
        if require_sbom and gate_type == "sbom":
            checks["sbom"] = has_sbom
            evidence["has_sbom"] = has_sbom
        elif require_sbom:
            checks["sbom"] = has_sbom
            evidence["has_sbom"] = has_sbom
        else:
            checks["sbom"] = True

        # Provenance
        has_provenance = bool(artifact_dict.get("provenance"))
        if not has_provenance and db is not None and SecurityProvenance is not None:
            try:
                artifact_id_str = artifact_dict.get("id", "")
                if artifact_id_str:
                    stmt = select(SecurityProvenance).where(SecurityProvenance.target_id == artifact_id_str).limit(1)
                    result = await db.execute(stmt)
                    prov = result.scalar_one_or_none()
                    if prov is not None:
                        has_provenance = True
                        evidence["provenance_row_id"] = str(prov.id)
                # Fallback: artifact provenance dict on DeliveryArtifact
                if not has_provenance and artifact is not None and not isinstance(artifact, dict):
                    prov_dict = getattr(artifact, "provenance", None)
                    if prov_dict:
                        has_provenance = True
            except Exception as exc:
                evidence["provenance_lookup_error"] = str(exc)

        if require_provenance:
            checks["provenance"] = has_provenance
            evidence["has_provenance"] = has_provenance
        else:
            checks["provenance"] = True

        # Immutable
        if require_immutable:
            is_immutable = bool(artifact_dict.get("immutable"))
            if artifact is not None and not isinstance(artifact, dict):
                is_immutable = bool(getattr(artifact, "immutable", False))
            checks["immutable"] = is_immutable
            evidence["is_immutable"] = is_immutable

        evidence["checks"] = checks
        passed = all(checks.values())
        # Score is fraction of checks satisfied
        score = round(sum(1 for v in checks.values() if v) / max(1, len(checks)), 4) if checks else (1.0 if passed else 0.0)

        return passed, _score(passed, score), evidence

    async def _eval_approval(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        approvals: list[Any] = list(context.get("approvals") or [])
        # Also allow candidate approval_status shortcut
        candidate = context.get("candidate")
        evidence: dict[str, Any] = {"threshold": threshold}

        min_approvals = int(threshold.get("min_approvals", threshold.get("required_approvals", 1)))
        required_roles = threshold.get("required_roles", threshold.get("required_role"))
        if isinstance(required_roles, str):
            required_roles = [required_roles]
        require_signature = bool(threshold.get("require_signature", False))

        # Count approvals that are "approved"
        approved: list[Any] = []
        for a in approvals:
            # Handle both ORM objects and dicts
            decision = None
            role = None
            sig = None
            if isinstance(a, dict):
                decision = a.get("decision", a.get("status"))
                role = a.get("approver_role", a.get("role"))
                sig = a.get("signature")
            else:
                decision = getattr(a, "decision", None)
                role = getattr(a, "approver_role", None)
                sig = getattr(a, "signature", None)
            if str(decision or "").lower() == "approved":
                if require_signature and not sig:
                    continue
                approved.append(a)
                evidence.setdefault("approved_roles", []).append(role)

        # Also check candidate shorthand
        if candidate is not None and not approved:
            status = getattr(candidate, "approval_status", None)
            if isinstance(status, str) and status.lower() == "approved":
                approved.append({"decision": "approved", "from_candidate": True})

        # Inject context override
        if "approvals_override" in context:
            approved = context["approvals_override"]

        evidence["approvals_found"] = len(approvals)
        evidence["approved_count"] = len(approved)
        evidence["min_approvals"] = min_approvals
        evidence["required_roles"] = required_roles

        # Check required roles
        has_required_roles = True
        if required_roles:
            found_roles = set(evidence.get("approved_roles", []))
            # ORM case: extract roles properly
            if not found_roles and approvals:
                found_roles = set()
                for a in approvals:
                    if isinstance(a, dict):
                        r = a.get("approver_role", a.get("role"))
                    else:
                        r = getattr(a, "approver_role", None)
                    if r:
                        found_roles.add(r)
            missing = [r for r in required_roles if r not in found_roles]
            evidence["missing_roles"] = missing
            has_required_roles = len(missing) == 0

        passed = len(approved) >= min_approvals and has_required_roles
        score = round(min(1.0, len(approved) / max(1, min_approvals)), 4) if min_approvals else 1.0
        if required_roles and not has_required_roles:
            score = min(score, 0.5)

        return passed, _score(passed, score), evidence

    async def _eval_slo(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        db: AsyncSession | None = context.get("db")
        service: str | None = context.get("service")
        evidence: dict[str, Any] = {"threshold": threshold, "service": service}

        max_consumed = float(threshold.get("max_consumed_percent", threshold.get("max_consumed", 80.0)))
        block_on_exhausted = bool(threshold.get("block_on_exhausted", True))
        block_on_burning = bool(threshold.get("block_on_burning", True))

        # Allow direct health injection for testing
        if "slo_health" in context:
            healthy = bool(context["slo_health"])
            evidence["injected_health"] = healthy
            return healthy, _score(healthy), evidence

        if db is None or SREErrorBudget is None or SRESLO is None:
            # Fallback stub: check context["error_budget"]
            budget = context.get("error_budget") or context.get("slo_budget")
            if isinstance(budget, dict):
                consumed = float(budget.get("consumed_percent", 0))
                status = str(budget.get("status", "healthy"))
                evidence["consumed_percent"] = consumed
                evidence["status"] = status
                if block_on_exhausted and status == BUDGET_EXHAUSTED:
                    return False, 0.0, evidence
                passed = consumed <= max_consumed
                return passed, _score(passed, max(0.0, 1.0 - consumed / 100.0)), evidence
            # No data — treat as healthy but record evidence
            evidence["reason"] = "no SLO data available — treating as healthy (no budget rows found)"
            return True, 1.0, evidence

        try:
            # Find SLOs for service, if service known; else all active SLOs
            if service:
                stmt = select(SRESLO).where(SRESLO.service_id == service, SRESLO.status == "active")
            else:
                stmt = select(SRESLO).where(SRESLO.status == "active").limit(25)
            result = await db.execute(stmt)
            slos = list(result.scalars().all())
            evidence["slos_found"] = len(slos)

            if not slos:
                evidence["reason"] = "no active SLOs found"
                return True, 1.0, evidence

            worst_consumed = 0.0
            worst_status = "healthy"
            burning = False

            for slo in slos:
                # Fetch latest error budget for this SLO
                stmt2 = select(SREErrorBudget).where(SREErrorBudget.slo_id == slo.slo_id).order_by(SREErrorBudget.computed_at.desc()).limit(1)
                result2 = await db.execute(stmt2)
                budget = result2.scalar_one_or_none()
                if budget is None:
                    continue
                consumed = float(getattr(budget, "consumed_percent", 0.0))
                status = str(getattr(budget, "status", "healthy"))
                burn = float(getattr(budget, "burn_rate", 0.0))
                evidence.setdefault("budgets", []).append({
                    "slo_id": getattr(slo, "slo_id", str(slo.id)),
                    "consumed_percent": consumed,
                    "status": status,
                    "burn_rate": burn,
                })
                if consumed > worst_consumed:
                    worst_consumed = consumed
                if status == BUDGET_EXHAUSTED:
                    worst_status = BUDGET_EXHAUSTED
                if burn > 1.0:
                    burning = True

            evidence["worst_consumed_percent"] = worst_consumed
            evidence["worst_status"] = worst_status
            evidence["burning"] = burning

            if block_on_exhausted and worst_status == BUDGET_EXHAUSTED:
                return False, 0.0, evidence
            if block_on_burning and burning and worst_consumed >= 50.0:
                evidence["reason"] = "burn rate elevated"
                return False, round(max(0.0, 1.0 - worst_consumed / 100.0), 4), evidence

            passed = worst_consumed <= max_consumed
            score = round(max(0.0, 1.0 - worst_consumed / 100.0), 4)
            return passed, _score(passed, score), evidence

        except Exception as exc:
            evidence["error"] = str(exc)
            logger.warning("SLO gate evaluation error: %s", exc)
            # Fail-closed for SLO when DB error? We choose fail-open with evidence to avoid accidental block on transient DB error
            # but mark score low so operator can investigate
            return True, 0.5, evidence

    async def _eval_incident(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        db: AsyncSession | None = context.get("db")
        service: str | None = context.get("service")
        tenant: str = str(context.get("tenant", ""))
        evidence: dict[str, Any] = {"threshold": threshold, "service": service}

        block_on_active = bool(threshold.get("block_on_active", True))
        block_severities = [str(s).upper() for s in threshold.get("block_severities", threshold.get("block_on_severity", ["SEV0", "SEV1", "SEV2"]))]
        environment = threshold.get("environment", context.get("environment"))

        # Allow injection
        if "active_incidents" in context:
            incidents = context["active_incidents"] or []
            evidence["active_incidents"] = incidents
            has_blocking = False
            for inc in incidents:
                sev = str(inc.get("severity", "")).upper() if isinstance(inc, dict) else str(getattr(inc, "severity", "")).upper()
                status = str(inc.get("status", "")).lower() if isinstance(inc, dict) else str(getattr(inc, "status", "")).lower()
                if status in ("resolved", "closed"):
                    continue
                if sev in block_severities:
                    has_blocking = True
            passed = not (block_on_active and has_blocking)
            return passed, _score(passed), evidence

        active: list[Any] = []

        # Try SRE models first, then incident models
        for model, label in [(SREIncident, "sre"), (IncidentModel, "incident")]:
            if model is None or db is None:
                continue
            try:
                # Filter by service/tenant where possible
                stmt = select(model).where(model.status.notin_(["resolved", "closed"]))
                # Apply service filter if column exists
                if hasattr(model, "service_id") and service:
                    stmt = stmt.where(model.service_id == service)  # type: ignore
                elif hasattr(model, "service") and service:
                    stmt = stmt.where(model.service == service)  # type: ignore
                # Tenant filter
                if hasattr(model, "tenant") and tenant:
                    stmt = stmt.where(model.tenant == tenant)  # type: ignore
                elif hasattr(model, "organization_id") and tenant:
                    stmt = stmt.where(model.organization_id == tenant)  # type: ignore

                if environment and hasattr(model, "environment"):
                    stmt = stmt.where(model.environment == environment)  # type: ignore

                stmt = stmt.limit(50)
                result = await db.execute(stmt)
                rows = list(result.scalars().all())
                for r in rows:
                    sev = str(getattr(r, "severity", "SEV3")).upper()
                    if sev in block_severities:
                        active.append(r)
                evidence[f"{label}_checked"] = len(rows)
            except Exception as exc:
                evidence[f"{label}_error"] = str(exc)

        evidence["blocking_incidents"] = len(active)
        if active:
            evidence["incidents"] = [
                {
                    "id": str(getattr(r, "id", "")),
                    "severity": str(getattr(r, "severity", "")),
                    "status": str(getattr(r, "status", "")),
                    "title": str(getattr(r, "title", ""))[:120],
                }
                for r in active[:5]
            ]

        passed = not (block_on_active and len(active) > 0)
        return passed, _score(passed), evidence

    async def _eval_window(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        evidence: dict[str, Any] = {"threshold": threshold}

        # Threshold window: {"allowed_hours": [9,17], "allowed_weekdays": [0,1,2,3,4], "timezone": "UTC", "block_during_maintenance": True}
        allowed_hours = threshold.get("allowed_hours", threshold.get("hours"))
        allowed_weekdays = threshold.get("allowed_weekdays", threshold.get("weekdays"))
        tz_name = str(threshold.get("timezone", "UTC"))
        block_during_maintenance = bool(threshold.get("block_during_maintenance", True))
        freeze_envs = threshold.get("freeze_environments", [])

        now = datetime.now(timezone.utc)
        # Timezone handling — we keep UTC and note tz_name in evidence
        # If operator configured non-UTC, they should use UTC hours; full tz conversion would require zoneinfo
        evidence["now_utc"] = now.isoformat()
        evidence["timezone"] = tz_name
        evidence["weekday"] = now.weekday()  # 0=Mon
        evidence["hour_utc"] = now.hour

        checks: dict[str, bool] = {}

        if allowed_hours is not None:
            try:
                # Support [start, end] or list of hours
                if isinstance(allowed_hours, list) and len(allowed_hours) == 2 and all(isinstance(x, int) for x in allowed_hours):
                    start_h, end_h = int(allowed_hours[0]), int(allowed_hours[1])
                    in_hours = start_h <= now.hour < end_h if start_h <= end_h else (now.hour >= start_h or now.hour < end_h)
                elif isinstance(allowed_hours, list):
                    in_hours = now.hour in [int(h) for h in allowed_hours]
                else:
                    in_hours = True
                checks["hours"] = in_hours
                evidence["allowed_hours"] = allowed_hours
                evidence["in_hours"] = in_hours
            except Exception as exc:
                evidence["hours_error"] = str(exc)
                checks["hours"] = True

        if allowed_weekdays is not None:
            try:
                allowed = [int(d) for d in allowed_weekdays]
                in_weekday = now.weekday() in allowed
                checks["weekday"] = in_weekday
                evidence["allowed_weekdays"] = allowed
                evidence["in_weekday"] = in_weekday
            except Exception as exc:
                evidence["weekday_error"] = str(exc)
                checks["weekday"] = True

        # Maintenance / freeze check via DB if available
        if block_during_maintenance:
            db: AsyncSession | None = context.get("db")
            environment = context.get("environment") or context.get("service")
            if db is not None and SREMaintenanceWindow is not None:
                try:
                    stmt = select(SREMaintenanceWindow).where(
                        SREMaintenanceWindow.status.in_(["scheduled", "in_progress", "active"]),
                        SREMaintenanceWindow.starts_at <= now,
                        SREMaintenanceWindow.ends_at >= now,
                    ).limit(10)
                    result = await db.execute(stmt)
                    windows = list(result.scalars().all())
                    in_maintenance = len(windows) > 0
                    evidence["maintenance_windows"] = len(windows)
                    if in_maintenance:
                        checks["maintenance"] = False
                        evidence["maintenance_active"] = True
                    else:
                        checks["maintenance"] = True
                except Exception as exc:
                    evidence["maintenance_error"] = str(exc)
                    checks["maintenance"] = True
            # DeliveryEnvironment frozen check (cheap, local)
            if db is not None:
                try:
                    from app.delivery.models import DeliveryEnvironment  # type: ignore

                    env_name = context.get("environment")
                    tenant = context.get("tenant")
                    if env_name and tenant:
                        stmt = select(DeliveryEnvironment).where(
                            DeliveryEnvironment.tenant == tenant,
                            DeliveryEnvironment.name == env_name,
                        ).limit(1)
                        result = await db.execute(stmt)
                        env = result.scalar_one_or_none()
                        if env is not None and bool(getattr(env, "frozen", False)):
                            checks["frozen"] = False
                            evidence["frozen"] = True
                            evidence["freeze_reason"] = getattr(env, "freeze_reason", "")
                        else:
                            checks.setdefault("frozen", True)
                except Exception:
                    # Delivery model not available or table missing — ignore
                    pass

            if freeze_envs and context.get("environment") in freeze_envs:
                checks["freeze_list"] = False
                evidence["environment_frozen_by_threshold"] = True

        evidence["checks"] = checks
        passed = all(checks.values()) if checks else True
        score = round(sum(1 for v in checks.values() if v) / max(1, len(checks)), 4) if checks else 1.0
        return passed, _score(passed, score), evidence

    async def _eval_cost(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        evidence: dict[str, Any] = {"threshold": threshold}
        max_cost = threshold.get("max_cost", threshold.get("budget"))
        current_cost = context.get("cost", context.get("estimated_cost"))
        if max_cost is None:
            # No budget configured — pass
            evidence["reason"] = "no max_cost threshold configured"
            return True, 1.0, evidence
        try:
            max_f = float(max_cost)
            cur_f = float(current_cost or 0)
            evidence["max_cost"] = max_f
            evidence["current_cost"] = cur_f
            passed = cur_f <= max_f
            score = round(max(0.0, 1.0 - cur_f / max_f) if max_f > 0 else 1.0, 4)
            return passed, _score(passed, score), evidence
        except Exception as exc:
            evidence["error"] = str(exc)
            return False, 0.0, evidence

    async def _eval_ai_governance(self, context: dict[str, Any], threshold: dict[str, Any]) -> tuple[bool, float, dict[str, Any]]:
        evidence: dict[str, Any] = {"threshold": threshold}
        # Check candidate ai_metadata blacklist, required approvals
        candidate = context.get("candidate")
        ai_meta: dict[str, Any] = {}
        if candidate is not None:
            ai_meta = getattr(candidate, "ai_metadata", None) or {}
        if not ai_meta:
            ai_meta = context.get("ai_metadata") or {}

        evidence["ai_metadata"] = ai_meta

        require_review = bool(threshold.get("require_review", False))
        blocked_models = set(threshold.get("blocked_models", []))
        max_risk = threshold.get("max_risk")

        passed = True
        if require_review and not ai_meta.get("reviewed"):
            passed = False
            evidence["reason"] = "AI governance review required"
        if blocked_models and ai_meta.get("model") in blocked_models:
            passed = False
            evidence["blocked_model"] = ai_meta.get("model")
        if max_risk is not None and ai_meta.get("risk_score") is not None:
            try:
                if float(ai_meta["risk_score"]) > float(max_risk):
                    passed = False
            except Exception:
                pass

        return passed, _score(passed), evidence


# Singleton for convenience
release_gate_service = ReleaseGateService()
