"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
import { useToastStore } from "@/stores/toast";
import type {
  GovernanceDecision,
  GovernanceDriftFinding,
  GovernanceEvidence,
  GovernanceEvidenceCoverage,
  GovernanceException,
  GovernancePolicy,
  GovernancePosture,
} from "@/types/governance";
import {
  GOVERNANCE_DECISIONS,
  GOVERNANCE_EXCEPTION_STATUSES,
} from "@/types/governance";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface">{value}</span>
    </div>
  );
}

function policyTone(status: string): "yellow" | "default" | "muted" {
  if (status === "ACTIVE") return "yellow";
  if (status === "SUPERSEDED" || status === "RETIRED") return "muted";
  return "default";
}

function decisionTone(decision: string): "yellow" | "default" | "muted" | "error" {
  if (decision === "ALLOW") return "default";
  if (decision === "REQUIRE_APPROVAL") return "yellow";
  if (decision === "DENY") return "error";
  return "muted";
}

function exceptionTone(status: string): "yellow" | "default" | "muted" {
  if (status === "APPROVED") return "yellow";
  if (status === "PENDING") return "default";
  return "muted";
}

function evidenceTone(expired: boolean, result: string): "yellow" | "default" | "muted" | "error" {
  if (expired) return "error";
  if (result === "FAIL") return "error";
  if (result === "PASS") return "yellow";
  return "default";
}

function severityTone(severity: string): "yellow" | "default" | "muted" | "error" {
  if (severity === "CRITICAL" || severity === "HIGH") return "error";
  if (severity === "MEDIUM") return "yellow";
  if (severity === "LOW") return "default";
  return "muted";
}

function LoadingPanel({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, index) => (
        <BrutalSkeleton key={index} className="h-8" label="Loading panel" />
      ))}
    </div>
  );
}

function PanelBody({
  loading,
  error,
  onRetry,
  children,
  emptyTitle,
  emptyDescription,
}: {
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  children: ReactNode;
  emptyTitle: string;
  emptyDescription?: string;
}) {
  if (loading) return <LoadingPanel />;
  if (error) {
    return <BrutalErrorState title="Unavailable" description={error} onRetry={onRetry} />;
  }
  if (children === undefined || children === null) {
    return <BrutalEmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return <div>{children}</div>;
}

interface EvidenceDraft {
  control_key: string;
  source_system: string;
  source_ref: string;
  source_version: string;
  result: string;
  validity_days: string;
}

type PendingMutation =
  | { kind: "exception-approve"; exception: GovernanceException }
  | { kind: "exception-deny"; exception: GovernanceException }
  | { kind: "exception-revoke"; exception: GovernanceException }
  | { kind: "drift-resolve"; finding: GovernanceDriftFinding }
  | { kind: "drift-detect" }
  | { kind: "register-evidence" }
  | null;

export function GovernanceIntelligence() {
  const pushToast = useToastStore((s) => s.push);

  const [permissions, setPermissions] = useState<string[]>([]);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [posture, setPosture] = useState<GovernancePosture | null>(null);
  const [postureError, setPostureError] = useState<string | null>(null);
  const [evidenceCoverage, setEvidenceCoverage] = useState<GovernanceEvidenceCoverage | null>(null);
  const [evidenceCoverageError, setEvidenceCoverageError] = useState<string | null>(null);

  const [policies, setPolicies] = useState<GovernancePolicy[] | null>(null);
  const [policiesError, setPoliciesError] = useState<string | null>(null);
  const [bindings, setBindings] = useState<GovernanceBindingRow[] | null>(null);
  const [bindingsError, setBindingsError] = useState<string | null>(null);

  const [decisions, setDecisions] = useState<GovernanceDecision[] | null>(null);
  const [decisionsError, setDecisionsError] = useState<string | null>(null);
  const [decisionFilter, setDecisionFilter] = useState("ALL");

  const [exceptions, setExceptions] = useState<GovernanceException[] | null>(null);
  const [exceptionsError, setExceptionsError] = useState<string | null>(null);
  const [exceptionFilter, setExceptionFilter] = useState("ALL");

  const [evidence, setEvidence] = useState<GovernanceEvidence[] | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [drift, setDrift] = useState<GovernanceDriftFinding[] | null>(null);
  const [driftError, setDriftError] = useState<string | null>(null);
  const [trends, setTrends] = useState<GovernanceTrendRow[] | null>(null);
  const [trendsError, setTrendsError] = useState<string | null>(null);

  const [pendingMutation, setPendingMutation] = useState<PendingMutation>(null);
  const [evidenceDraft, setEvidenceDraft] = useState<EvidenceDraft>({
    control_key: "",
    source_system: "",
    source_ref: "",
    source_version: "",
    result: "PASS",
    validity_days: "90",
  });
  const [submitting, setSubmitting] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const filtersRef = useRef({ decision: "ALL", exceptionStatus: "ALL" });

  const notifyError = useCallback(
    (e: unknown, fallback: string, refetch?: () => void) => {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        pushToast("warning", "You don't have permission to perform this action");
        return;
      }
      if (e instanceof ApiError && e.status === 409) {
        pushToast("info", "State changed on the server; refreshing");
        refetch?.();
        return;
      }
      pushToast("error", e instanceof Error ? e.message : fallback);
    },
    [pushToast],
  );

  const loadAll = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setPostureError(null);
    setEvidenceCoverageError(null);
    setPoliciesError(null);
    setBindingsError(null);
    setDecisionsError(null);
    setExceptionsError(null);
    setEvidenceError(null);
    setDriftError(null);
    setTrendsError(null);

    const filters = filtersRef.current;

    async function guarded<T>(load: () => Promise<T>): Promise<T | null> {
      try {
        return await load();
      } catch (e) {
        if (seq !== seqRef.current) return null;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return null;
        }
        throw e;
      }
    }

    async function settle<T>(
      load: () => Promise<T>,
      set: (value: T | null) => void,
      onError: (message: string) => void,
      errorMessage: string,
    ) {
      try {
        const value = await guarded(load);
        if (value !== null && seq === seqRef.current) set(value);
      } catch (e) {
        if (seq !== seqRef.current) return;
        onError(e instanceof Error ? e.message : errorMessage);
      }
    }

    await Promise.all([
      settle(
        () => api.governancePosture(token),
        setPosture,
        setPostureError,
        "Policy posture unavailable",
      ),
      settle(
        () => api.governanceEvidenceCoverage(token),
        setEvidenceCoverage,
        setEvidenceCoverageError,
        "Evidence coverage unavailable",
      ),
      settle(
        () => api.governancePolicies(token),
        (value) => setPolicies(value?.items ?? null),
        setPoliciesError,
        "Policies unavailable",
      ),
      settle(
        () => api.governanceBindings(token),
        (value) => setBindings(value?.items ?? null),
        setBindingsError,
        "Bindings unavailable",
      ),
      settle(
        () =>
          api.governanceDecisions(token, {
            decision: filters.decision !== "ALL" ? filters.decision : undefined,
            limit: 50,
          }),
        (value) => setDecisions(value?.items ?? null),
        setDecisionsError,
        "Decisions unavailable",
      ),
      settle(
        () =>
          api.governanceExceptions(token, {
            status: filters.exceptionStatus !== "ALL" ? filters.exceptionStatus : undefined,
            limit: 50,
          }),
        (value) => setExceptions(value?.items ?? null),
        setExceptionsError,
        "Policy exceptions unavailable",
      ),
      settle(
        () => api.governanceEvidence(token),
        (value) => setEvidence(value?.items ?? null),
        setEvidenceError,
        "Evidence registry unavailable",
      ),
      settle(
        () => api.governanceDrift(token),
        (value) => setDrift(value?.items ?? null),
        setDriftError,
        "Drift findings unavailable",
      ),
      settle(
        () => api.governanceTrends(token, 30),
        (value) => setTrends(value?.items ?? null),
        setTrendsError,
        "Trends unavailable",
      ),
    ]);

    if (seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let active = true;
    api
      .whoami(token)
      .then((whoami) => {
        if (active) {
          setPermissions(whoami.permissions ?? []);
          if (typeof whoami.email === "string") setEmail(whoami.email);
        }
      })
      .catch((e) => {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    void loadAll();

    const resetForContextSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setPosture(null);
      setEvidenceCoverage(null);
      setPolicies(null);
      setBindings(null);
      setDecisions(null);
      setExceptions(null);
      setEvidence(null);
      setDrift(null);
      setTrends(null);
      setPostureError(null);
      setEvidenceCoverageError(null);
      setPoliciesError(null);
      setBindingsError(null);
      setDecisionsError(null);
      setExceptionsError(null);
      setEvidenceError(null);
      setDriftError(null);
      setTrendsError(null);
      setLoading(true);
      void loadAll();
    };
    window.addEventListener("tenant:switched", resetForContextSwitch as EventListener);
    window.addEventListener("workspace:switched", resetForContextSwitch as EventListener);

    return () => {
      window.removeEventListener("tenant:switched", resetForContextSwitch as EventListener);
      window.removeEventListener("workspace:switched", resetForContextSwitch as EventListener);
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, [loadAll]);

  const canGovernanceAdmin = hasPermission(permissions, PERMISSIONS.admin);
  const canGovernanceRead = hasPermission(permissions, PERMISSIONS.orgRead) || canGovernanceAdmin;
  const approver = email?.trim() || "governance-admin";

  function updateDecisionFilter(value: string) {
    setDecisionFilter(value);
    filtersRef.current.decision = value;
    void loadAll();
  }

  function updateExceptionFilter(value: string) {
    setExceptionFilter(value);
    filtersRef.current.exceptionStatus = value;
    void loadAll();
  }

  async function handleExceptionDecision() {
    if (!pendingMutation || (pendingMutation.kind !== "exception-approve" && pendingMutation.kind !== "exception-deny")) return;
    const exception = pendingMutation.exception;
    const approve = pendingMutation.kind === "exception-approve";
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      const body = { approver, approval_type: "jit" };
      if (approve) {
        await api.governanceApproveException(token, exception.id, body);
        pushToast("success", `Exception ${exception.id.slice(0, 8)} approved`);
      } else {
        await api.governanceDenyException(token, exception.id, body);
        pushToast("success", `Exception ${exception.id.slice(0, 8)} denied`);
      }
      setPendingMutation(null);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update exception", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleExceptionRevoke() {
    if (!pendingMutation || pendingMutation.kind !== "exception-revoke") return;
    const exception = pendingMutation.exception;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.governanceRevokeException(token, exception.id);
      setPendingMutation(null);
      pushToast("success", `Exception ${exception.id.slice(0, 8)} revoked`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to revoke exception", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDriftResolve() {
    if (!pendingMutation || pendingMutation.kind !== "drift-resolve") return;
    const finding = pendingMutation.finding;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.governanceResolveDrift(token, finding.id);
      setPendingMutation(null);
      pushToast("success", `Drift finding ${finding.id.slice(0, 8)} resolved`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to resolve drift finding", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDriftDetect() {
    if (!pendingMutation || pendingMutation.kind !== "drift-detect") return;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      const result = await api.governanceDetectDrift(token);
      setPendingMutation(null);
      const count = result && typeof result === "object" && "findings" in result ? String((result as { findings: unknown[] }).findings?.length ?? 0) : "unknown";
      pushToast("success", `Drift detection complete · ${count} findings`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to run drift detection", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRegisterEvidence() {
    if (!pendingMutation || pendingMutation.kind !== "register-evidence") return;
    if (!evidenceDraft.control_key.trim() || !evidenceDraft.source_system.trim() || !evidenceDraft.source_ref.trim()) {
      pushToast("warning", "control key, source system and source reference are required");
      return;
    }
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      const days = Number.parseInt(evidenceDraft.validity_days, 10);
      const result = await api.governanceRegisterEvidence(token, {
        control_key: evidenceDraft.control_key.trim(),
        source_system: evidenceDraft.source_system.trim(),
        source_ref: evidenceDraft.source_ref.trim(),
        source_version: evidenceDraft.source_version.trim() || undefined,
        result: evidenceDraft.result || "PASS",
        validity_days: Number.isFinite(days) && days > 0 ? days : 90,
      });
      setPendingMutation(null);
      pushToast("success", `Evidence registered for ${result.control_key ?? "control"}`);
      setEvidenceDraft({ control_key: "", source_system: "", source_ref: "", source_version: "", result: "PASS", validity_days: "90" });
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register evidence", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  const modalTitle =
    pendingMutation?.kind === "exception-approve"
      ? "Approve exception?"
      : pendingMutation?.kind === "exception-deny"
        ? "Deny exception?"
        : pendingMutation?.kind === "exception-revoke"
          ? "Revoke exception?"
          : pendingMutation?.kind === "drift-resolve"
            ? "Resolve drift finding?"
            : pendingMutation?.kind === "drift-detect"
              ? "Detect configuration drift?"
              : pendingMutation?.kind === "register-evidence"
                ? "Register evidence"
                : "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border border-outline bg-surface-container px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant" aria-live="polite">
            <span className="h-2 w-2 bg-muted" aria-hidden="true" />
            Realtime: UNAVAILABLE
          </span>
          <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            {updatedAt ? `Updated ${updatedAt}` : "Loading…"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!canGovernanceRead ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Read-only view · no governance read permissions
            </span>
          ) : null}
          {!canGovernanceAdmin ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Admin actions hidden · no settings:admin
            </span>
          ) : null}
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <BrutalCard eyebrow="Posture" title="Policy posture">
          <PanelBody
            loading={loading}
            error={postureError}
            onRetry={() => void loadAll()}
            emptyTitle="No posture snapshot"
            emptyDescription="A posture snapshot is generated on first access."
          >
            {posture ? (
              <div className="space-y-1">
                <StatRow label="Total policies" value={String(posture.total_policies ?? 0)} />
                <StatRow label="Active policies" value={String(posture.active_policies ?? 0)} />
                <StatRow label="Violations 24h" value={String(posture.violations_24h ?? 0)} />
                <StatRow label="Open exceptions" value={String(posture.open_exceptions ?? 0)} />
                <StatRow label="Verified controls" value={String(posture.verified_controls ?? 0)} />
                <StatRow label="Failing controls" value={String(posture.failing_controls ?? 0)} />
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Evidence" title="Evidence coverage">
          <PanelBody
            loading={loading}
            error={evidenceCoverageError}
            onRetry={() => void loadAll()}
            emptyTitle="No evidence registered"
            emptyDescription="Verified control evidence appears here once registered."
          >
            {evidenceCoverage ? (
              <div className="space-y-1">
                <StatRow label="Total evidence" value={String(evidenceCoverage.total ?? 0)} />
                <StatRow label="Valid" value={String(evidenceCoverage.valid ?? 0)} />
                <StatRow label="Expired" value={String(evidenceCoverage.expired ?? 0)} />
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Trend" title="Posture trend · 30d">
          <PanelBody
            loading={loading}
            error={trendsError}
            onRetry={() => void loadAll()}
            emptyTitle="No trend points"
            emptyDescription="Posture snapshots accumulate over time."
          >
            {trends && trends.length > 0 ? (
              <div className="max-h-72 space-y-1 overflow-y-auto">
                {trends.map((point, index) => (
                  <div key={`${point.computed_at ?? "trend"}-${index}`} className="flex items-baseline justify-between gap-3 border-b border-outline py-1.5 last:border-b-0">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      {point.computed_at ?? "snapshot"}
                    </span>
                    <span className="truncate font-mono text-xs text-on-surface">
                      active {point.active_policies} · failing {point.failing_controls}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <BrutalCard eyebrow="Policies" title="Policies & bindings">
          <PanelBody
            loading={loading}
            error={policiesError || bindingsError}
            onRetry={() => void loadAll()}
            emptyTitle="No policies"
            emptyDescription="Policies created on the governance plane appear here."
          >
            {policies && policies.length > 0 ? (
              <ul className="mb-4 space-y-2">
                {policies.map((policy) => (
                  <li key={policy.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-on-surface">{policy.name}</p>
                      <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {policy.domain || "general"} · {policy.owner || "unassigned"}
                      </p>
                    </div>
                    <BrutalBadge tone={policyTone(policy.status)}>{policy.status}</BrutalBadge>
                  </li>
                ))}
              </ul>
            ) : null}
            {bindings && bindings.length > 0 ? (
              <ul className="space-y-2">
                {bindings.map((binding) => (
                  <li key={binding.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-on-surface">
                        {binding.scope_type}:{binding.scope_value || "*"}
                      </p>
                      <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        binding {binding.policy_id.slice(0, 8)} · v{binding.version_id.slice(0, 8)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {binding.mandatory ? <BrutalBadge tone="yellow">Mandatory</BrutalBadge> : null}
                      {binding.enabled ? <BrutalBadge tone="default">Enabled</BrutalBadge> : <BrutalBadge tone="muted">Disabled</BrutalBadge>}
                    </div>
                  </li>
                ))}
              </ul>
            ) : policies !== null ? null : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Exceptions" title="Policy exceptions">
          <PanelBody
            loading={loading}
            error={exceptionsError}
            onRetry={() => void loadAll()}
            emptyTitle="No exceptions"
            emptyDescription="Temporary policy exceptions appear here once requested."
          >
            {exceptions && exceptions.length > 0 ? (
              <>
                <div className="mb-3 max-w-xs">
                  <BrutalSelect
                    label="Status"
                    value={exceptionFilter}
                    onChange={(e) => updateExceptionFilter(e.target.value)}
                    options={["ALL", ...GOVERNANCE_EXCEPTION_STATUSES].map((s) => ({ label: s, value: s }))}
                  />
                </div>
                <ul className="space-y-2">
                  {exceptions.map((exception) => (
                    <li key={exception.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{exception.justification || exception.policy_id}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          policy {exception.policy_id.slice(0, 8)} · {exception.scope_type}:{exception.scope_value || "*"} · {exception.requester || "no requester"}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <BrutalBadge tone={exceptionTone(exception.status)}>{exception.status}</BrutalBadge>
                        {canGovernanceAdmin && exception.status === "PENDING" ? (
                          <>
                            <BrutalButton
                              size="sm"
                              variant="ghost"
                              aria-label="Approve exception"
                              onClick={() => setPendingMutation({ kind: "exception-approve", exception })}
                            >
                              Approve
                            </BrutalButton>
                            <BrutalButton
                              size="sm"
                              variant="ghost"
                              aria-label="Deny exception"
                              onClick={() => setPendingMutation({ kind: "exception-deny", exception })}
                            >
                              Deny
                            </BrutalButton>
                          </>
                        ) : null}
                        {canGovernanceAdmin && exception.status === "APPROVED" ? (
                          <BrutalButton
                            size="sm"
                            variant="ghost"
                            aria-label="Revoke exception"
                            onClick={() => setPendingMutation({ kind: "exception-revoke", exception })}
                          >
                            Revoke
                          </BrutalButton>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <BrutalCard eyebrow="Decisions" title="Recent decisions">
          <PanelBody
            loading={loading}
            error={decisionsError}
            onRetry={() => void loadAll()}
            emptyTitle="No decisions"
            emptyDescription="Policy evaluation decisions appear here once requests are evaluated."
          >
            {decisions && decisions.length > 0 ? (
              <>
                <div className="mb-3 max-w-xs">
                  <BrutalSelect
                    label="Decision"
                    value={decisionFilter}
                    onChange={(e) => updateDecisionFilter(e.target.value)}
                    options={["ALL", ...GOVERNANCE_DECISIONS].map((d) => ({ label: d, value: d }))}
                  />
                </div>
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {decisions.map((decision) => (
                    <li key={decision.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">
                          {decision.scope_type}:{decision.scope_value || "*"}
                        </p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          policy {decision.policy_id ? decision.policy_id.slice(0, 8) : "—"} · {decision.actor || "no actor"} · {decision.reason || "reason"}
                        </p>
                      </div>
                      <BrutalBadge tone={decisionTone(decision.decision)}>{decision.decision}</BrutalBadge>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Evidence" title="Evidence registry">
          <PanelBody
            loading={loading}
            error={evidenceError}
            onRetry={() => void loadAll()}
            emptyTitle="No evidence"
            emptyDescription="Registered control evidence appears here."
          >
            {canGovernanceAdmin ? (
              <div className="mb-3 flex justify-end">
                <BrutalButton
                  size="sm"
                  variant="ghost"
                  aria-label="Register evidence"
                  onClick={() => setPendingMutation({ kind: "register-evidence" })}
                >
                  Register
                </BrutalButton>
              </div>
            ) : null}
            {evidence && evidence.length > 0 ? (
              <ul className="max-h-80 space-y-2 overflow-y-auto">
                {evidence.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-on-surface">{item.control_key}</p>
                      <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {item.source_system} · {item.source_ref} · {item.source_version || "no version"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {item.expired ? <BrutalBadge tone="error">Expired</BrutalBadge> : null}
                      <BrutalBadge tone={evidenceTone(item.expired, item.result)}>{item.result}</BrutalBadge>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <BrutalCard
        eyebrow="Drift"
        title="Configuration drift"
        actions={
          canGovernanceAdmin ? (
            <BrutalButton
              size="sm"
              variant="ghost"
              aria-label="Detect drift"
              onClick={() => setPendingMutation({ kind: "drift-detect" })}
              disabled={submitting}
            >
              Detect
            </BrutalButton>
          ) : undefined
        }
      >
        <PanelBody
          loading={loading}
          error={driftError}
          onRetry={() => void loadAll()}
          emptyTitle="No drift findings"
          emptyDescription="Detected configuration drift appears here."
        >
          {drift && drift.length > 0 ? (
            <ul className="space-y-2">
              {drift.map((finding) => (
                <li key={finding.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-on-surface">{finding.description || finding.finding_type}</p>
                    <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      {finding.finding_type} · {finding.resource_type}:{finding.resource_id || "*"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <BrutalBadge tone={severityTone(finding.severity)}>{finding.severity}</BrutalBadge>
                    <BrutalBadge tone={finding.status === "OPEN" ? "default" : "muted"}>{finding.status}</BrutalBadge>
                    {canGovernanceAdmin && finding.status === "OPEN" ? (
                      <BrutalButton
                        size="sm"
                        variant="ghost"
                        aria-label="Resolve drift"
                        onClick={() => setPendingMutation({ kind: "drift-resolve", finding })}
                        disabled={submitting}
                      >
                        Resolve
                      </BrutalButton>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </PanelBody>
      </BrutalCard>

      <BrutalModal
        open={pendingMutation !== null}
        title={modalTitle}
        onClose={() => {
          if (!submitting) setPendingMutation(null);
        }}
        actions={
          pendingMutation !== null ? (
            <BrutalButton
              variant="primary"
              onClick={() => {
                if (pendingMutation.kind === "exception-approve" || pendingMutation.kind === "exception-deny") {
                  void handleExceptionDecision();
                } else if (pendingMutation.kind === "exception-revoke") {
                  void handleExceptionRevoke();
                } else if (pendingMutation.kind === "drift-resolve") {
                  void handleDriftResolve();
                } else if (pendingMutation.kind === "drift-detect") {
                  void handleDriftDetect();
                } else if (pendingMutation.kind === "register-evidence") {
                  void handleRegisterEvidence();
                }
              }}
              disabled={submitting}
            >
              {submitting ? "Working…" : pendingMutation.kind === "register-evidence" ? "Register" : "Confirm"}
            </BrutalButton>
          ) : undefined
        }
      >
        <p className="text-sm text-on-surface-variant">
          {pendingMutation?.kind === "exception-approve"
            ? `Approve the exception for policy ${pendingMutation.exception.policy_id.slice(0, 8)}?`
            : pendingMutation?.kind === "exception-deny"
              ? `Deny the exception for policy ${pendingMutation.exception.policy_id.slice(0, 8)}?`
              : pendingMutation?.kind === "exception-revoke"
                ? `Revoke the approved exception for policy ${pendingMutation.exception.policy_id.slice(0, 8)}?`
                : pendingMutation?.kind === "drift-resolve"
                  ? `Mark drift finding ${pendingMutation.finding.id.slice(0, 8)} as resolved?`
                  : pendingMutation?.kind === "drift-detect"
                    ? "Compare the current configuration against policies and evidence now?"
                    : pendingMutation?.kind === "register-evidence"
                      ? "Register a new evidence record for a control."
                      : ""}
        </p>
        {pendingMutation?.kind === "register-evidence" ? (
          <div className="mt-4 space-y-3">
            <div className="space-y-1">
              <label htmlFor="evidence-control-key" className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                Control key
              </label>
              <input
                id="evidence-control-key"
                className="w-full border border-outline bg-surface p-2 font-mono text-sm text-on-surface focus:border-on-surface focus:outline-none"
                value={evidenceDraft.control_key}
                onChange={(e) => setEvidenceDraft({ ...evidenceDraft, control_key: e.target.value })}
                placeholder="control-key"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="evidence-source-system" className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                Source system
              </label>
              <input
                id="evidence-source-system"
                className="w-full border border-outline bg-surface p-2 font-mono text-sm text-on-surface focus:border-on-surface focus:outline-none"
                value={evidenceDraft.source_system}
                onChange={(e) => setEvidenceDraft({ ...evidenceDraft, source_system: e.target.value })}
                placeholder="e.g. aws-config"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="evidence-source-ref" className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                Source reference
              </label>
              <input
                id="evidence-source-ref"
                className="w-full border border-outline bg-surface p-2 font-mono text-sm text-on-surface focus:border-on-surface focus:outline-none"
                value={evidenceDraft.source_ref}
                onChange={(e) => setEvidenceDraft({ ...evidenceDraft, source_ref: e.target.value })}
                placeholder="rule or finding id"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label htmlFor="evidence-source-version" className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                  Source version
                </label>
                <input
                  id="evidence-source-version"
                  className="w-full border border-outline bg-surface p-2 font-mono text-sm text-on-surface focus:border-on-surface focus:outline-none"
                  value={evidenceDraft.source_version}
                  onChange={(e) => setEvidenceDraft({ ...evidenceDraft, source_version: e.target.value })}
                  placeholder="optional"
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="evidence-validity-days" className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                  Validity days
                </label>
                <input
                  id="evidence-validity-days"
                  className="w-full border border-outline bg-surface p-2 font-mono text-sm text-on-surface focus:border-on-surface focus:outline-none"
                  value={evidenceDraft.validity_days}
                  onChange={(e) => setEvidenceDraft({ ...evidenceDraft, validity_days: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-1">
              <label htmlFor="evidence-result" className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                Result
              </label>
              <select
                id="evidence-result"
                className="w-full border border-outline bg-surface p-2 font-mono text-sm text-on-surface focus:border-on-surface focus:outline-none"
                value={evidenceDraft.result}
                onChange={(e) => setEvidenceDraft({ ...evidenceDraft, result: e.target.value })}
              >
                <option value="PASS">PASS</option>
                <option value="FAIL">FAIL</option>
              </select>
            </div>
          </div>
        ) : null}
      </BrutalModal>
    </div>
  );
}

interface GovernanceBindingRow {
  id: string;
  policy_id: string;
  version_id: string;
  scope_type: string;
  scope_value: string;
  mandatory: boolean;
  enabled: boolean;
}

interface GovernanceTrendRow {
  computed_at: string | null;
  active_policies: number;
  failing_controls: number;
}