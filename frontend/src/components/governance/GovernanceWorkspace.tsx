"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
import { useToastStore } from "@/stores/toast";
import type {
  DomainGovernResult,
  GovernanceBinding,
  GovernanceDecision,
  GovernanceDriftFinding,
  GovernanceEvaluateResult,
  GovernanceEvidence,
  GovernanceEvidenceCoverage,
  GovernanceException,
  GovernanceExplainResponse,
  GovernancePolicy,
  GovernancePolicyVersion,
  GovernancePosture,
  GovernancePostureHistoryResponse,
  GovernanceReport,
  GovernanceSimulateBatchResponse,
  GovernanceSimulateResult,
  GovernanceTrendPoint,
} from "@/types/governance";
import {
  GOVERN_ACTION_CLASSES,
  GOVERN_CLASSIFICATIONS,
  GOVERNANCE_DECISIONS,
  GOVERNANCE_DRIFT_SEVERITIES,
  GOVERNANCE_DRIFT_STATUSES,
  GOVERNANCE_EFFECTS,
  GOVERNANCE_EXCEPTION_STATUSES,
  GOVERNANCE_POLICY_STATUSES,
  GOVERNANCE_REPORT_TYPES,
  GOVERNANCE_SCOPE_TYPES,
  GOVERNANCE_VERSION_STATUSES,
} from "@/types/governance";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface" title={value}>{value}</span>
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

function parseRulesJson(raw: string): Array<Record<string, unknown>> {
  const trimmed = raw.trim();
  if (!trimmed) throw new Error("At least one rule is required");
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error("Rules are not valid JSON");
  }
  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new Error("Rules must be a non-empty JSON array");
  }
  return parsed as Array<Record<string, unknown>>;
}

function parseJsonObject(raw: string, field: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    throw new Error(`${field} must be a JSON object`);
  } catch (e) {
    if (e instanceof Error && e.message.includes("must be a JSON object")) throw e;
    throw new Error(`${field} is not valid JSON`);
  }
}

/** Renders a domain/evaluate verdict verbatim — decision, allowed, layer, reason, refs. No scores. */
function VerdictRows({ verdict }: { verdict: DomainGovernResult | GovernanceEvaluateResult }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <BrutalBadge tone={decisionTone(verdict.decision)}>{verdict.decision}</BrutalBadge>
        {"allowed" in verdict && verdict.allowed !== undefined ? (
          <BrutalBadge tone={verdict.allowed ? "default" : "error"}>{verdict.allowed ? "allowed" : "blocked"}</BrutalBadge>
        ) : null}
        {"layer" in verdict && verdict.layer ? <BrutalBadge tone="default">{String(verdict.layer)}</BrutalBadge> : null}
      </div>
      <StatRow label="Reason" value={verdict.reason || "—"} />
      {verdict.policy_id ? <StatRow label="Policy" value={String(verdict.policy_id)} /> : null}
      {verdict.version_id ? <StatRow label="Version" value={String(verdict.version_id)} /> : null}
      {verdict.binding_id ? <StatRow label="Binding" value={String(verdict.binding_id)} /> : null}
      {"approval_id" in verdict && verdict.approval_id ? <StatRow label="Approval" value={String(verdict.approval_id)} /> : null}
      {"finops_gate" in verdict && verdict.finops_gate ? <StatRow label="FinOps gate" value={String(verdict.finops_gate)} /> : null}
      {"zero_trust" in verdict && verdict.zero_trust ? (
        <StatRow
          label="Zero trust"
          value={`${String(verdict.zero_trust.decision)} · ${verdict.zero_trust.allowed ? "allowed" : "denied"}`}
        />
      ) : null}
      {"exception_id" in verdict && verdict.exception_id ? <StatRow label="Exception" value={String(verdict.exception_id)} /> : null}
    </div>
  );
}

interface GovernField {
  key: string;
  label: string;
  placeholder?: string;
  numeric?: boolean;
  options?: readonly string[];
  defaultValue?: string;
}

const GOVERN_FIELDS: Record<string, { hint: string; fields: GovernField[] }> = {
  ai: {
    hint: "Central AI policies first, then FinOps token and cost ceilings.",
    fields: [
      { key: "model", label: "Model", placeholder: "gpt-x" },
      { key: "provider", label: "Provider", placeholder: "acme" },
      { key: "use_case", label: "Use case", placeholder: "support-draft" },
      { key: "action_class", label: "Action class", options: GOVERN_ACTION_CLASSES, defaultValue: "" },
      { key: "classification", label: "Classification", options: GOVERN_CLASSIFICATIONS, defaultValue: "INTERNAL" },
      { key: "input_tokens", label: "Input tokens", numeric: true, placeholder: "0" },
      { key: "estimated_cents", label: "Estimated cents", numeric: true, placeholder: "0" },
      { key: "operation", label: "Operation", defaultValue: "ai.invoke" },
    ],
  },
  data: {
    hint: "Central policy first, then residency and destination checks.",
    fields: [
      { key: "dataset", label: "Dataset", placeholder: "events" },
      { key: "project", label: "Project", placeholder: "analytics" },
      { key: "workspace", label: "Workspace", placeholder: "prod" },
      { key: "classification", label: "Classification", options: GOVERN_CLASSIFICATIONS, defaultValue: "INTERNAL" },
      { key: "region", label: "Region", placeholder: "eu-west" },
      { key: "destination", label: "Destination", placeholder: "warehouse" },
      { key: "operation", label: "Operation", defaultValue: "data.access" },
    ],
  },
  security: {
    hint: "Central policy first, then Zero Trust authorization.",
    fields: [
      { key: "action", label: "Action", placeholder: "db.read" },
      { key: "resource", label: "Resource", placeholder: "prod-db" },
      { key: "classification", label: "Classification", options: GOVERN_CLASSIFICATIONS, defaultValue: "INTERNAL" },
      { key: "auth_strength", label: "Auth strength", placeholder: "mfa" },
      { key: "device_posture", label: "Device posture", placeholder: "managed" },
      { key: "identity", label: "Identity", placeholder: "user id" },
    ],
  },
  spend: {
    hint: "Central policy first, then the FinOps expensive-operation gate.",
    fields: [
      { key: "operation", label: "Operation", defaultValue: "spend" },
      { key: "model", label: "Model", placeholder: "gpt-x" },
      { key: "provider", label: "Provider", placeholder: "acme" },
      { key: "workspace", label: "Workspace", placeholder: "prod" },
      { key: "project", label: "Project", placeholder: "research" },
      { key: "estimated_cents", label: "Estimated cents", numeric: true, placeholder: "0" },
      { key: "budget_id", label: "Budget ID", placeholder: "optional uuid" },
    ],
  },
  integration: {
    hint: "Central policy first, then the integration transfer check.",
    fields: [
      { key: "connection_id", label: "Connection ID", placeholder: "optional uuid" },
      { key: "operation", label: "Operation", defaultValue: "integration.use" },
      { key: "destination", label: "Destination", placeholder: "https://…" },
      { key: "classification", label: "Classification", options: GOVERN_CLASSIFICATIONS, defaultValue: "INTERNAL" },
      { key: "region", label: "Region", placeholder: "eu-west" },
      { key: "scopes", label: "Scopes (comma-separated)", placeholder: "read, write" },
      { key: "estimated_cents", label: "Estimated cents", numeric: true, placeholder: "0" },
    ],
  },
  workflow: {
    hint: "Central policy plus workflow run guards (fan-out caps enforced server-side).",
    fields: [
      { key: "workflow_id", label: "Workflow ID", placeholder: "optional uuid" },
      { key: "run_id", label: "Run ID", placeholder: "optional" },
      { key: "executor", label: "Executor", placeholder: "scheduler" },
      { key: "environment", label: "Environment", placeholder: "prod" },
      { key: "classification", label: "Classification", options: GOVERN_CLASSIFICATIONS, defaultValue: "INTERNAL" },
      { key: "fan_out", label: "Fan-out", numeric: true, placeholder: "1" },
      { key: "max_fan_out", label: "Max fan-out", numeric: true, placeholder: "5" },
    ],
  },
  agent: {
    hint: "Central policy plus agent step guards (max steps enforced server-side).",
    fields: [
      { key: "agent", label: "Agent", placeholder: "researcher" },
      { key: "tool", label: "Tool", placeholder: "web.search" },
      { key: "step_number", label: "Step number", numeric: true, placeholder: "0" },
      { key: "max_steps", label: "Max steps", numeric: true, placeholder: "25" },
      { key: "classification", label: "Classification", options: GOVERN_CLASSIFICATIONS, defaultValue: "INTERNAL" },
    ],
  },
};

type TabId = "overview" | "policies" | "bindings" | "decisions" | "evidence" | "drift" | "exceptions" | "reports" | "ai-governance" | "advanced";

type PendingModal =
  | { kind: "policy-create" }
  | { kind: "version-create"; policy: GovernancePolicy }
  | { kind: "version-status"; version: GovernancePolicyVersion }
  | { kind: "binding-create" }
  | { kind: "binding-delete"; binding: GovernanceBinding }
  | { kind: "exception-approve"; exception: GovernanceException }
  | { kind: "exception-deny"; exception: GovernanceException }
  | { kind: "exception-revoke"; exception: GovernanceException }
  | { kind: "drift-resolve"; finding: GovernanceDriftFinding }
  | { kind: "drift-detect" }
  | { kind: "register-evidence" }
  | { kind: "report-generate" }
  | null;

interface EvidenceDraft {
  control_key: string;
  source_system: string;
  source_ref: string;
  source_version: string;
  result: string;
  validity_days: string;
}

export function GovernanceWorkspace() {
  const pushToast = useToastStore((s) => s.push);

  const [active, setActive] = useState<TabId>("overview");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [posture, setPosture] = useState<GovernancePosture | null>(null);
  const [postureError, setPostureError] = useState<string | null>(null);
  const [postureHistory, setPostureHistory] = useState<GovernancePostureHistoryResponse | null>(null);
  const [postureHistoryError, setPostureHistoryError] = useState<string | null>(null);
  const [evidenceCoverage, setEvidenceCoverage] = useState<GovernanceEvidenceCoverage | null>(null);
  const [evidenceCoverageError, setEvidenceCoverageError] = useState<string | null>(null);

  const [policies, setPolicies] = useState<GovernancePolicy[] | null>(null);
  const [policiesError, setPoliciesError] = useState<string | null>(null);
  const [policyStatusFilter, setPolicyStatusFilter] = useState("ALL");
  const [policyDomainFilter, setPolicyDomainFilter] = useState("");
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  const [versions, setVersions] = useState<GovernancePolicyVersion[] | null>(null);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);

  const [bindings, setBindings] = useState<GovernanceBinding[] | null>(null);
  const [bindingsError, setBindingsError] = useState<string | null>(null);
  const [bindingPolicyFilter, setBindingPolicyFilter] = useState("ALL");
  const [bindingScopeFilter, setBindingScopeFilter] = useState("ALL");

  const [decisions, setDecisions] = useState<GovernanceDecision[] | null>(null);
  const [decisionsError, setDecisionsError] = useState<string | null>(null);
  const [decisionFilter, setDecisionFilter] = useState("ALL");
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<GovernanceExplainResponse | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [explanationLoading, setExplanationLoading] = useState(false);

  const [exceptions, setExceptions] = useState<GovernanceException[] | null>(null);
  const [exceptionsError, setExceptionsError] = useState<string | null>(null);
  const [exceptionFilter, setExceptionFilter] = useState("ALL");

  const [evidence, setEvidence] = useState<GovernanceEvidence[] | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [evidenceControlFilter, setEvidenceControlFilter] = useState("");
  const [evidenceExpiredOnly, setEvidenceExpiredOnly] = useState(false);

  const [drift, setDrift] = useState<GovernanceDriftFinding[] | null>(null);
  const [driftError, setDriftError] = useState<string | null>(null);
  const [driftStatusFilter, setDriftStatusFilter] = useState("ALL");
  const [driftSeverityFilter, setDriftSeverityFilter] = useState("ALL");

  const [trends, setTrends] = useState<GovernanceTrendPoint[] | null>(null);
  const [trendsError, setTrendsError] = useState<string | null>(null);
  const [trendDays, setTrendDays] = useState("30");

  const [reports, setReports] = useState<GovernanceReport[] | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [reportTypeFilter, setReportTypeFilter] = useState("ALL");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  const [evalResult, setEvalResult] = useState<GovernanceEvaluateResult | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [evalRunning, setEvalRunning] = useState(false);
  const [evalDraft, setEvalDraft] = useState({
    scope_type: "tenant",
    scope_value: "",
    operation: "",
    context: "",
    actor: "",
    identity: "",
    enforce: false,
  });

  const [simMode, setSimMode] = useState<"single" | "batch">("single");
  const [simResult, setSimResult] = useState<GovernanceSimulateResult | GovernanceSimulateBatchResponse | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const [simRunning, setSimRunning] = useState(false);
  const [simDraft, setSimDraft] = useState({
    scope_type: "tenant",
    scope_value: "",
    operation: "",
    context: "",
    proposed: "",
    requests: "",
  });

  const [governDomain, setGovernDomain] = useState("ai");
  const [governFields, setGovernFields] = useState<Record<string, string>>({});
  const [governResult, setGovernResult] = useState<DomainGovernResult | null>(null);
  const [governError, setGovernError] = useState<string | null>(null);
  const [governRunning, setGovernRunning] = useState(false);

  const [modal, setModal] = useState<PendingModal>(null);
  const [submitting, setSubmitting] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    domain: "general",
    description: "",
    owner: "",
    rules: "",
    default_effect: "deny",
    effective_from: "",
    effective_until: "",
    reason: "",
    version_status: "ACTIVE",
    binding_policy_id: "",
    binding_version_id: "",
    binding_scope_type: "tenant",
    binding_scope_value: "",
    binding_mandatory: false,
    report_type: "posture",
    report_scope_type: "tenant",
    report_scope_value: "",
    report_days: "30",
  });
  const [evidenceDraft, setEvidenceDraft] = useState<EvidenceDraft>({
    control_key: "",
    source_system: "",
    source_ref: "",
    source_version: "",
    result: "PASS",
    validity_days: "90",
  });

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const filtersRef = useRef({
    decision: "ALL",
    exceptionStatus: "ALL",
    policyStatus: "ALL",
    policyDomain: "",
    bindingPolicy: "ALL",
    bindingScope: "ALL",
    evidenceControl: "",
    evidenceExpired: false,
    driftStatus: "ALL",
    driftSeverity: "ALL",
    reportType: "ALL",
    trendDays: "30",
  });

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
      if (e instanceof ApiError && (e.kind === "rate_limited" || e.status === 429)) {
        pushToast("warning", "Rate limited — retry shortly");
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
    setPostureHistoryError(null);
    setEvidenceCoverageError(null);
    setPoliciesError(null);
    setBindingsError(null);
    setDecisionsError(null);
    setExceptionsError(null);
    setEvidenceError(null);
    setDriftError(null);
    setTrendsError(null);
    setReportsError(null);

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
      settle(() => api.governancePosture(token), setPosture, setPostureError, "Policy posture unavailable"),
      settle(() => api.governancePostureHistory(token, { limit: 20 }), setPostureHistory, setPostureHistoryError, "Posture history unavailable"),
      settle(() => api.governanceEvidenceCoverage(token), setEvidenceCoverage, setEvidenceCoverageError, "Evidence coverage unavailable"),
      settle(
        () =>
          api.governancePolicies(token, {
            status: filters.policyStatus !== "ALL" ? filters.policyStatus : undefined,
            domain: filters.policyDomain.trim() ? filters.policyDomain.trim() : undefined,
          }),
        (value) => setPolicies(value?.items ?? null),
        setPoliciesError,
        "Policies unavailable",
      ),
      settle(
        () =>
          api.governanceBindings(token, {
            policy_id: filters.bindingPolicy !== "ALL" ? filters.bindingPolicy : undefined,
            scope_type: filters.bindingScope !== "ALL" ? filters.bindingScope : undefined,
          }),
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
        () =>
          api.governanceEvidence(token, {
            control_key: filters.evidenceControl.trim() ? filters.evidenceControl.trim() : undefined,
            expired_only: filters.evidenceExpired || undefined,
          }),
        (value) => setEvidence(value?.items ?? null),
        setEvidenceError,
        "Evidence registry unavailable",
      ),
      settle(
        () =>
          api.governanceDrift(token, {
            status: filters.driftStatus !== "ALL" ? filters.driftStatus : undefined,
            severity: filters.driftSeverity !== "ALL" ? filters.driftSeverity : undefined,
          }),
        (value) => setDrift(value?.items ?? null),
        setDriftError,
        "Drift findings unavailable",
      ),
      settle(
        () => api.governanceTrends(token, Number(filters.trendDays) || 30),
        (value) => setTrends(value?.items ?? null),
        setTrendsError,
        "Trends unavailable",
      ),
      settle(
        () =>
          api.governanceReports(token, {
            report_type: filters.reportType !== "ALL" ? filters.reportType : undefined,
          }),
        (value) => setReports(value?.items ?? null),
        setReportsError,
        "Reports unavailable",
      ),
    ]);

    if (seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, []);

  const loadVersions = useCallback(async (policyId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      const res = await api.governancePolicyVersions(token, policyId);
      setVersions(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setVersionsError(e instanceof Error ? e.message : "Versions unavailable");
    } finally {
      setVersionsLoading(false);
    }
  }, []);

  const loadExplanation = useCallback(async (decision: GovernanceDecision) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setExplanationLoading(true);
    setExplanationError(null);
    try {
      const res = await api.governanceExplainDecision(token, decision.id);
      setExplanation(res);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setExplanationError(e instanceof Error ? e.message : "Explanation unavailable");
    } finally {
      setExplanationLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let activeFlag = true;
    api
      .whoami(token)
      .then((whoami) => {
        if (activeFlag) {
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
      activeFlag = false;
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
      setPostureHistory(null);
      setEvidenceCoverage(null);
      setPolicies(null);
      setBindings(null);
      setDecisions(null);
      setExceptions(null);
      setEvidence(null);
      setDrift(null);
      setTrends(null);
      setReports(null);
      setVersions(null);
      setExplanation(null);
      setEvalResult(null);
      setSimResult(null);
      setGovernResult(null);
      setEvalError(null);
      setSimError(null);
      setGovernError(null);
      setSelectedPolicyId(null);
      setSelectedDecisionId(null);
      setSelectedReportId(null);
      setPostureError(null);
      setPostureHistoryError(null);
      setEvidenceCoverageError(null);
      setPoliciesError(null);
      setBindingsError(null);
      setDecisionsError(null);
      setExceptionsError(null);
      setEvidenceError(null);
      setDriftError(null);
      setTrendsError(null);
      setReportsError(null);
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

  useEffect(() => {
    if (selectedPolicyId) {
      void loadVersions(selectedPolicyId);
    } else {
      setVersions(null);
      setVersionsError(null);
    }
  }, [selectedPolicyId, loadVersions]);

  useEffect(() => {
    const decision = decisions?.find((d) => d.id === selectedDecisionId) ?? null;
    if (decision) {
      void loadExplanation(decision);
    } else {
      setExplanation(null);
      setExplanationError(null);
    }
  }, [selectedDecisionId, decisions, loadExplanation]);

  const canGovernanceAdmin = hasPermission(permissions, PERMISSIONS.admin);
  const canGovernanceRead = hasPermission(permissions, PERMISSIONS.orgRead) || canGovernanceAdmin;
  const approver = email?.trim() || "governance-admin";
  const selectedPolicy = policies?.find((p) => p.id === selectedPolicyId) ?? null;
  const selectedDecision = decisions?.find((d) => d.id === selectedDecisionId) ?? null;
  const selectedReport = reports?.find((r) => r.id === selectedReportId) ?? null;

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

  function applyPolicyFilters() {
    filtersRef.current.policyStatus = policyStatusFilter;
    filtersRef.current.policyDomain = policyDomainFilter;
    void loadAll();
  }

  function applyBindingFilters() {
    filtersRef.current.bindingPolicy = bindingPolicyFilter;
    filtersRef.current.bindingScope = bindingScopeFilter;
    void loadAll();
  }

  function applyEvidenceFilters() {
    filtersRef.current.evidenceControl = evidenceControlFilter;
    filtersRef.current.evidenceExpired = evidenceExpiredOnly;
    void loadAll();
  }

  function applyDriftFilters() {
    filtersRef.current.driftStatus = driftStatusFilter;
    filtersRef.current.driftSeverity = driftSeverityFilter;
    void loadAll();
  }

  function applyReportFilter() {
    filtersRef.current.reportType = reportTypeFilter;
    void loadAll();
  }

  function applyTrendDays() {
    filtersRef.current.trendDays = trendDays;
    void loadAll();
  }

  function openModal(next: PendingModal) {
    if (next?.kind === "binding-create" && selectedPolicyId && versions && versions.length > 0) {
      setDraft((d) => ({ ...d, binding_policy_id: selectedPolicyId, binding_version_id: versions[0].id }));
    }
    setModal(next);
  }

  async function handlePolicyCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.name.trim()) {
      pushToast("warning", "Policy name is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.governanceCreatePolicy(token, {
        name: draft.name.trim(),
        domain: draft.domain.trim() || "general",
        description: draft.description.trim(),
        owner: draft.owner.trim(),
      });
      setModal(null);
      pushToast("success", `Policy ${result.name} created as DRAFT`);
      setSelectedPolicyId(result.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create policy", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVersionCreate() {
    if (!modal || modal.kind !== "version-create") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    let rules: Array<Record<string, unknown>>;
    try {
      rules = parseRulesJson(draft.rules);
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid rules");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.governanceCreateVersion(token, modal.policy.id, {
        rules,
        default_effect: draft.default_effect,
        effective_from: draft.effective_from.trim() || undefined,
        effective_until: draft.effective_until.trim() || undefined,
        reason: draft.reason.trim(),
      });
      setModal(null);
      pushToast("success", `Version ${result.version} recorded as DRAFT`);
      setDraft((d) => ({ ...d, rules: "", reason: "" }));
      void loadVersions(modal.policy.id);
    } catch (e) {
      notifyError(e, "Failed to record version", () => selectedPolicyId && void loadVersions(selectedPolicyId));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVersionStatus() {
    if (!modal || modal.kind !== "version-status") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.governanceVersionStatus(token, modal.version.id, {
        status: draft.version_status,
        reason: draft.reason.trim(),
      });
      setModal(null);
      pushToast("success", `Version ${result.version} is now ${result.status}`);
      void loadVersions(result.policy_id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to transition version", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleBindingCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.binding_policy_id.trim() || !draft.binding_version_id.trim()) {
      pushToast("warning", "Policy and version are required");
      return;
    }
    setSubmitting(true);
    try {
      await api.governanceCreateBinding(token, {
        policy_id: draft.binding_policy_id.trim(),
        version_id: draft.binding_version_id.trim(),
        scope_type: draft.binding_scope_type,
        scope_value: draft.binding_scope_value.trim(),
        mandatory: draft.binding_mandatory,
      });
      setModal(null);
      pushToast("success", "Binding created");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create binding", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleBindingDelete() {
    if (!modal || modal.kind !== "binding-delete") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.governanceDeleteBinding(token, modal.binding.id);
      setModal(null);
      pushToast("success", `Binding ${modal.binding.id.slice(0, 8)} deleted`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to delete binding", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleExceptionDecision() {
    if (!modal || (modal.kind !== "exception-approve" && modal.kind !== "exception-deny")) return;
    const exception = modal.exception;
    const approve = modal.kind === "exception-approve";
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
      setModal(null);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update exception", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleExceptionRevoke() {
    if (!modal || modal.kind !== "exception-revoke") return;
    const exception = modal.exception;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.governanceRevokeException(token, exception.id);
      setModal(null);
      pushToast("success", `Exception ${exception.id.slice(0, 8)} revoked`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to revoke exception", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDriftResolve() {
    if (!modal || modal.kind !== "drift-resolve") return;
    const finding = modal.finding;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.governanceResolveDrift(token, finding.id);
      setModal(null);
      pushToast("success", `Drift finding ${finding.id.slice(0, 8)} resolved`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to resolve drift finding", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDriftDetect() {
    if (!modal || modal.kind !== "drift-detect") return;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      const result = await api.governanceDetectDrift(token);
      setModal(null);
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
    if (!modal || modal.kind !== "register-evidence") return;
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
      setModal(null);
      pushToast("success", `Evidence registered for ${result.control_key ?? "control"}`);
      setEvidenceDraft({ control_key: "", source_system: "", source_ref: "", source_version: "", result: "PASS", validity_days: "90" });
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register evidence", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReportGenerate() {
    if (!modal || modal.kind !== "report-generate") return;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      const days = Number.parseInt(draft.report_days, 10);
      const result = await api.governanceGenerateReport(token, {
        report_type: draft.report_type,
        scope_type: draft.report_scope_type,
        scope_value: draft.report_scope_value.trim(),
        days: Number.isFinite(days) && days > 0 ? days : 30,
      });
      setModal(null);
      pushToast("success", `Report ${result.id.slice(0, 8)} generated`);
      setSelectedReportId(result.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to generate report", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEvaluateTest() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!evalDraft.scope_type.trim()) {
      pushToast("warning", "Scope type is required");
      return;
    }
    setEvalRunning(true);
    setEvalError(null);
    try {
      const context = parseJsonObject(evalDraft.context, "Context");
      const result = await api.governanceEvaluate(token, {
        scope_type: evalDraft.scope_type.trim(),
        scope_value: evalDraft.scope_value.trim(),
        operation: evalDraft.operation.trim(),
        context,
        actor: evalDraft.actor.trim() || undefined,
        identity: evalDraft.identity.trim() || undefined,
        enforce: evalDraft.enforce,
      });
      setEvalResult(result);
      pushToast("success", evalDraft.enforce ? "Enforcement decision recorded" : "Evaluation complete — nothing was enforced");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setEvalError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setEvalRunning(false);
    }
  }

  async function handleSimulateTest() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSimRunning(true);
    setSimError(null);
    try {
      if (simMode === "batch") {
        const trimmed = simDraft.requests.trim();
        if (!trimmed) {
          pushToast("warning", "At least one request is required");
          setSimRunning(false);
          return;
        }
        let requests: unknown;
        try {
          requests = JSON.parse(trimmed);
        } catch {
          pushToast("warning", "Requests are not valid JSON");
          setSimRunning(false);
          return;
        }
        if (!Array.isArray(requests) || requests.length === 0) {
          pushToast("warning", "Requests must be a non-empty JSON array");
          setSimRunning(false);
          return;
        }
        const result = await api.governanceSimulate(token, {
          requests: requests as Array<Record<string, unknown>>,
        });
        setSimResult(result);
      } else {
        const context = parseJsonObject(simDraft.context, "Context");
        const proposed = parseJsonObject(simDraft.proposed, "Proposed version");
        const result = await api.governanceSimulate(token, {
          scope_type: simDraft.scope_type.trim() || "tenant",
          scope_value: simDraft.scope_value.trim(),
          operation: simDraft.operation.trim(),
          context,
          proposed: Object.keys(proposed).length > 0 ? proposed : undefined,
        });
        setSimResult(result);
      }
      pushToast("success", "Simulation complete — no side effects were applied");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setSimError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setSimRunning(false);
    }
  }

  function setGovernField(key: string, value: string) {
    const scoped = `${governDomain}.${key}`;
    setGovernFields((prev) => ({ ...prev, [scoped]: value }));
  }

  async function handleGovernRun() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const spec = GOVERN_FIELDS[governDomain];
    if (!spec) return;
    const body: Record<string, unknown> = {};
    for (const field of spec.fields) {
      const raw = (governFields[`${governDomain}.${field.key}`] ?? field.defaultValue ?? "").trim();
      if (field.key === "scopes") {
        if (raw) body.scopes = raw.split(",").map((s) => s.trim()).filter(Boolean);
        continue;
      }
      if (field.numeric) {
        if (raw) body[field.key] = Number(raw);
        continue;
      }
      if (raw) body[field.key] = raw;
      else if (field.defaultValue !== undefined && field.defaultValue !== "") body[field.key] = field.defaultValue;
    }
    setGovernRunning(true);
    setGovernError(null);
    try {
      let result: DomainGovernResult;
      if (governDomain === "ai") result = await api.governAi(token, body);
      else if (governDomain === "data") result = await api.governData(token, body);
      else if (governDomain === "security") result = await api.governSecurity(token, body);
      else if (governDomain === "spend") result = await api.governSpend(token, body);
      else if (governDomain === "integration") result = await api.governIntegration(token, body);
      else if (governDomain === "workflow") result = await api.governWorkflow(token, body);
      else result = await api.governAgent(token, body);
      setGovernResult(result);
      pushToast("success", `Domain check complete: ${result.decision}`);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setGovernError(e instanceof Error ? e.message : "Domain check failed");
    } finally {
      setGovernRunning(false);
    }
  }

  const modalTitle =
    modal?.kind === "policy-create"
      ? "Create policy"
      : modal?.kind === "version-create"
        ? "Record policy version"
        : modal?.kind === "version-status"
          ? "Transition version status?"
          : modal?.kind === "binding-create"
            ? "Create binding"
            : modal?.kind === "binding-delete"
              ? "Delete binding?"
              : modal?.kind === "exception-approve"
                ? "Approve exception?"
                : modal?.kind === "exception-deny"
                  ? "Deny exception?"
                  : modal?.kind === "exception-revoke"
                    ? "Revoke exception?"
                    : modal?.kind === "drift-resolve"
                      ? "Resolve drift finding?"
                      : modal?.kind === "drift-detect"
                        ? "Detect configuration drift?"
                        : modal?.kind === "register-evidence"
                          ? "Register evidence"
                          : modal?.kind === "report-generate"
                            ? "Generate report"
                            : "";

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "policies", label: "Policies" },
    { id: "bindings", label: "Bindings" },
    { id: "decisions", label: "Decisions" },
    { id: "evidence", label: "Evidence" },
    { id: "drift", label: "Drift" },
    { id: "exceptions", label: "Exceptions" },
    { id: "reports", label: "Reports" },
    { id: "ai-governance", label: "AI Governance" },
    { id: "advanced", label: "Advanced" },
  ];

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

      <div role="tablist" aria-label="Governance sections" className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            onClick={() => setActive(tab.id)}
            className={
              tab.id === active
                ? "border border-primary-container bg-primary-container px-4 py-2 font-mono text-xs uppercase tracking-widest text-black"
                : "border border-outline bg-transparent px-4 py-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant hover:border-on-surface hover:text-on-surface"
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {active === "overview" ? (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            <BrutalCard eyebrow="Policy" title="Policy posture">
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

            <BrutalCard eyebrow="Decision" title="Recent decisions">
              <PanelBody
                loading={loading}
                error={decisionsError}
                onRetry={() => void loadAll()}
                emptyTitle="No decisions"
                emptyDescription="Policy evaluation decisions appear here once requests are evaluated."
              >
                {decisions && decisions.length > 0 ? (
                  <ul className="max-h-72 space-y-2 overflow-y-auto">
                    {decisions.slice(0, 6).map((decision) => (
                      <li key={decision.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">
                            {decision.scope_type}:{decision.scope_value || "*"}
                          </p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            policy {decision.policy_id ? decision.policy_id.slice(0, 8) : "—"} · {decision.actor || "no actor"}
                          </p>
                        </div>
                        <BrutalBadge tone={decisionTone(decision.decision)}>{decision.decision}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <BrutalCard eyebrow="Drift" title="Open drift">
              <PanelBody
                loading={loading}
                error={driftError}
                onRetry={() => void loadAll()}
                emptyTitle="No drift findings"
                emptyDescription="Detected configuration drift appears here."
              >
                {drift ? (
                  drift.filter((f) => f.status === "OPEN").length > 0 ? (
                    <ul className="max-h-72 space-y-2 overflow-y-auto">
                      {drift.filter((f) => f.status === "OPEN").slice(0, 6).map((finding) => (
                        <li key={finding.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm text-on-surface">{finding.description || finding.finding_type}</p>
                            <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                              {finding.finding_type} · {finding.resource_type}:{finding.resource_id || "*"}
                            </p>
                          </div>
                          <BrutalBadge tone={severityTone(finding.severity)}>{finding.severity}</BrutalBadge>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <BrutalEmptyState title="No open drift" description="All findings are resolved." />
                  )
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Exception" title="Open exceptions">
              <PanelBody
                loading={loading}
                error={exceptionsError}
                onRetry={() => void loadAll()}
                emptyTitle="No exceptions"
                emptyDescription="Temporary policy exceptions appear here once requested."
              >
                {exceptions ? (
                  exceptions.filter((e) => e.status === "PENDING" || e.status === "APPROVED").length > 0 ? (
                    <ul className="max-h-72 space-y-2 overflow-y-auto">
                      {exceptions.filter((e) => e.status === "PENDING" || e.status === "APPROVED").slice(0, 6).map((exception) => (
                        <li key={exception.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm text-on-surface">{exception.justification || exception.policy_id}</p>
                            <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                              policy {exception.policy_id.slice(0, 8)} · {exception.requester || "no requester"}
                            </p>
                          </div>
                          <BrutalBadge tone={exceptionTone(exception.status)}>{exception.status}</BrutalBadge>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <BrutalEmptyState title="No open exceptions" description="All exceptions are decided or expired." />
                  )
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Trend" title="Posture history">
              <div className="mb-3 flex flex-wrap items-end gap-2">
                <div className="w-28">
                  <BrutalInput label="Days" value={trendDays} onChange={(e) => setTrendDays(e.target.value)} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={applyTrendDays}>Apply</BrutalButton>
              </div>
              <PanelBody
                loading={loading}
                error={trendsError || postureHistoryError}
                onRetry={() => void loadAll()}
                emptyTitle="No trend points"
                emptyDescription="Posture snapshots accumulate over time."
              >
                {(trends && trends.length > 0) || (postureHistory && postureHistory.items.length > 0) ? (
                  <>
                    {trends && trends.length > 0 ? (
                      <div className="max-h-56 space-y-1 overflow-y-auto">
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
                    {postureHistory && postureHistory.items.length > 0 ? (
                      <div className="mt-3 border-t border-outline pt-2">
                        <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Latest snapshots</p>
                        {postureHistory.items.slice(0, 5).map((snap) => (
                          <div key={snap.id} className="flex items-baseline justify-between gap-3 border-b border-outline py-1.5 last:border-b-0">
                            <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                              {snap.computed_at ?? "snapshot"}
                            </span>
                            <span className="truncate font-mono text-xs text-on-surface">
                              {snap.scope_type}:{snap.scope_value || "*"} · active {snap.active_policies}/{snap.total_policies}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "policies" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Policy" title="Policies">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Status" value={policyStatusFilter} onChange={(e) => setPolicyStatusFilter(e.target.value)} options={["ALL", ...GOVERNANCE_POLICY_STATUSES].map((s) => ({ label: s, value: s }))} />
              </div>
              <div className="min-w-28 flex-1">
                <BrutalInput label="Domain" value={policyDomainFilter} onChange={(e) => setPolicyDomainFilter(e.target.value)} placeholder="general" />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={applyPolicyFilters}>Apply</BrutalButton>
              {canGovernanceAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => { setDraft((d) => ({ ...d, name: "", domain: "general", description: "", owner: "" })); setModal({ kind: "policy-create" }); }}>New policy</BrutalButton>
              ) : null}
            </div>
            <PanelBody
              loading={loading}
              error={policiesError}
              onRetry={() => void loadAll()}
              emptyTitle="No policies"
              emptyDescription="Policies created on the governance plane appear here."
            >
              {policies && policies.length > 0 ? (
                <ul className="space-y-2">
                  {policies.map((policy) => (
                    <li key={policy.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedPolicyId(policy.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${policy.id === selectedPolicyId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{policy.name}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {policy.domain || "general"} · {policy.owner || "unassigned"}
                          </p>
                        </div>
                        <BrutalBadge tone={policyTone(policy.status)}>{policy.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Policy" title="Policy detail">
            <PanelBody
              loading={loading}
              error={policiesError}
              onRetry={() => void loadAll()}
              emptyTitle="Nothing selected"
              emptyDescription="Select a policy to inspect its metadata and versions."
            >
              {selectedPolicy ? (
                <div className="space-y-1">
                  <StatRow label="Name" value={selectedPolicy.name} />
                  <StatRow label="Domain" value={selectedPolicy.domain} />
                  <StatRow label="Description" value={selectedPolicy.description || "—"} />
                  <StatRow label="Owner" value={selectedPolicy.owner || "—"} />
                  <StatRow label="Status" value={selectedPolicy.status} />
                  <StatRow label="Active version" value={selectedPolicy.active_version_id ?? "none"} />
                  {canGovernanceAdmin ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <BrutalButton size="sm" variant="ghost" aria-label="Record version" onClick={() => { setDraft((d) => ({ ...d, rules: "", default_effect: "deny", effective_from: "", effective_until: "", reason: "" })); setModal({ kind: "version-create", policy: selectedPolicy }); }}>
                        Record version
                      </BrutalButton>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Policy" title="Versions">
            <PanelBody
              loading={versionsLoading}
              error={versionsError}
              onRetry={() => selectedPolicyId && void loadVersions(selectedPolicyId)}
              emptyTitle="No versions"
              emptyDescription="Active versions are immutable — changes create a new version."
            >
              {versions && versions.length > 0 ? (
                <ul className="space-y-2">
                  {versions.map((version) => (
                    <li key={version.id} className="border border-outline bg-surface p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-mono text-sm text-on-surface">v{version.version}</p>
                        <BrutalBadge tone={policyTone(version.status)}>{version.status}</BrutalBadge>
                      </div>
                      <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {version.rules?.length ?? 0} rules · {version.default_effect} · {version.checksum.slice(0, 12)}
                      </p>
                      {version.effective_until ? (
                        <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          until {formatDateTime(version.effective_until)}
                        </p>
                      ) : null}
                      {version.reason ? <p className="mt-1 text-xs text-on-surface-variant">{version.reason}</p> : null}
                      {canGovernanceAdmin && version.status !== "RETIRED" ? (
                        <div className="mt-2">
                          <BrutalButton
                            size="sm"
                            variant="ghost"
                            aria-label={`Transition version ${version.version}`}
                            onClick={() => { setDraft((d) => ({ ...d, version_status: "ACTIVE", reason: "" })); setModal({ kind: "version-status", version }); }}
                          >
                            Transition
                          </BrutalButton>
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "bindings" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Policy" title="Bindings">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Policy" value={bindingPolicyFilter} onChange={(e) => setBindingPolicyFilter(e.target.value)} options={[{ label: "All policies", value: "ALL" }, ...(policies ?? []).map((p) => ({ label: p.name, value: p.id }))]} />
              </div>
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Scope" value={bindingScopeFilter} onChange={(e) => setBindingScopeFilter(e.target.value)} options={["ALL", ...GOVERNANCE_SCOPE_TYPES].map((s) => ({ label: s, value: s }))} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={applyBindingFilters}>Apply</BrutalButton>
              {canGovernanceAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => { setDraft((d) => ({ ...d, binding_scope_type: "tenant", binding_scope_value: "", binding_mandatory: false })); openModal({ kind: "binding-create" }); }}>New binding</BrutalButton>
              ) : null}
            </div>
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Scope chain: organization → tenant → workspace → resource. Organization mandatory denies always apply first.</p>
            <PanelBody
              loading={loading}
              error={bindingsError}
              onRetry={() => void loadAll()}
              emptyTitle="No bindings"
              emptyDescription="Bindings attach a policy version to one scope node."
            >
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
                        {canGovernanceAdmin && !binding.mandatory ? (
                          <BrutalButton
                            size="sm"
                            variant="ghost"
                            aria-label="Delete binding"
                            onClick={() => setModal({ kind: "binding-delete", binding })}
                          >
                            Delete
                          </BrutalButton>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Policy" title="Binding scope">
            <PanelBody
              loading={loading}
              error={policiesError}
              onRetry={() => void loadAll()}
              emptyTitle="No policies"
              emptyDescription="Create a policy and record a version before binding it to a scope."
            >
              {policies && policies.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {policies.map((policy) => (
                    <li key={policy.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedPolicyId(policy.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${policy.id === selectedPolicyId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{policy.name}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {policy.domain || "general"} · active v{policy.active_version_id ? policy.active_version_id.slice(0, 8) : "—"}
                          </p>
                        </div>
                        <BrutalBadge tone={policyTone(policy.status)}>{policy.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "decisions" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Decision" title="Recent decisions">
            <div className="mb-3 max-w-xs">
              <BrutalSelect
                label="Decision"
                value={decisionFilter}
                onChange={(e) => updateDecisionFilter(e.target.value)}
                options={["ALL", ...GOVERNANCE_DECISIONS].map((d) => ({ label: d, value: d }))}
              />
            </div>
            <PanelBody
              loading={loading}
              error={decisionsError}
              onRetry={() => void loadAll()}
              emptyTitle="No decisions"
              emptyDescription="Policy evaluation decisions appear here once requests are evaluated."
            >
              {decisions && decisions.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {decisions.map((decision) => (
                    <li key={decision.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedDecisionId(decision.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${decision.id === selectedDecisionId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">
                            {decision.scope_type}:{decision.scope_value || "*"}
                          </p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            policy {decision.policy_id ? decision.policy_id.slice(0, 8) : "—"} · {decision.actor || "no actor"} · {decision.reason || "reason"}
                          </p>
                        </div>
                        <BrutalBadge tone={decisionTone(decision.decision)}>{decision.decision}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Decision" title="Decision detail">
            <PanelBody
              loading={loading}
              error={decisionsError}
              onRetry={() => void loadAll()}
              emptyTitle="Nothing selected"
              emptyDescription="Select a decision to inspect its policy, rule and obligations."
            >
              {selectedDecision ? (
                <div className="space-y-1">
                  <StatRow label="Decision" value={selectedDecision.decision} />
                  <StatRow label="Reason" value={selectedDecision.reason || "—"} />
                  <StatRow label="Policy" value={selectedDecision.policy_id ?? "—"} />
                  <StatRow label="Version" value={selectedDecision.version_id ?? "—"} />
                  <StatRow label="Binding" value={selectedDecision.binding_id ?? "—"} />
                  <StatRow label="Rule index" value={String(selectedDecision.rule_index ?? "—")} />
                  <StatRow label="Priority" value={String(selectedDecision.priority)} />
                  <StatRow label="Scope" value={`${selectedDecision.scope_type}:${selectedDecision.scope_value || "*"}`} />
                  <StatRow label="Approval" value={selectedDecision.approval_id || "—"} />
                  <StatRow label="Actor" value={selectedDecision.actor || "—"} />
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Decision" title="Explanation">
            <PanelBody
              loading={explanationLoading}
              error={explanationError}
              onRetry={() => selectedDecision && void loadExplanation(selectedDecision)}
              emptyTitle="No explanation"
              emptyDescription="Explanations are composed server-side from the decision record."
            >
              {explanation ? (
                <div className="space-y-1">
                  <p className="border border-outline bg-surface p-3 text-sm text-on-surface">{explanation.explanation.why}</p>
                  {explanation.explanation.policy ? (
                    <StatRow label="Policy" value={`${explanation.explanation.policy.name} (${explanation.explanation.policy.status})`} />
                  ) : null}
                  {explanation.explanation.version ? (
                    <StatRow label="Version" value={`v${explanation.explanation.version.version} (${explanation.explanation.version.status})`} />
                  ) : null}
                  {explanation.explanation.rule ? (
                    <StatRow label="Rule" value={`${explanation.explanation.rule.name ?? `rule ${explanation.explanation.rule.index}`} · ${explanation.explanation.rule.effect ?? "?"}`} />
                  ) : null}
                  {explanation.explanation.binding ? (
                    <StatRow label="Binding" value={`${explanation.explanation.binding.scope_type}:${explanation.explanation.binding.scope_value || "*"}${explanation.explanation.binding.mandatory ? " (mandatory)" : ""}`} />
                  ) : null}
                  {explanation.explanation.exception_id ? (
                    <StatRow label="Exception" value={explanation.explanation.exception_id} />
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "evidence" ? (
        <div className="grid gap-6 lg:grid-cols-3">
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

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Evidence" title="Evidence registry">
              <div className="mb-3 flex flex-wrap items-end gap-2">
                <div className="min-w-32 flex-1">
                  <BrutalInput label="Control key" value={evidenceControlFilter} onChange={(e) => setEvidenceControlFilter(e.target.value)} placeholder="control-key" />
                </div>
                <div className="min-w-32 flex-1">
                  <BrutalSelect label="Expiry" value={evidenceExpiredOnly ? "expired" : "all"} onChange={(e) => setEvidenceExpiredOnly(e.target.value === "expired")} options={[{ label: "All", value: "all" }, { label: "Expired only", value: "expired" }]} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={applyEvidenceFilters}>Apply</BrutalButton>
                {canGovernanceAdmin ? (
                  <BrutalButton size="sm" variant="ghost" aria-label="Register evidence" onClick={() => setModal({ kind: "register-evidence" })}>
                    Register
                  </BrutalButton>
                ) : null}
              </div>
              <p className="mb-2 font-mono text-xs text-on-surface-variant">Only references and hashes are stored — never control payloads.</p>
              <PanelBody
                loading={loading}
                error={evidenceError}
                onRetry={() => void loadAll()}
                emptyTitle="No evidence"
                emptyDescription="Registered control evidence appears here."
              >
                {evidence && evidence.length > 0 ? (
                  <ul className="max-h-96 space-y-2 overflow-y-auto">
                    {evidence.map((item) => (
                      <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{item.control_key}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {item.source_system} · {item.source_ref} · {item.source_version || "no version"}
                          </p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            valid until {formatDateTime(item.valid_until)}
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
        </div>
      ) : null}

      {active === "drift" ? (
        <BrutalCard
          eyebrow="Drift"
          title="Configuration drift"
          actions={
            canGovernanceAdmin ? (
              <BrutalButton
                size="sm"
                variant="ghost"
                aria-label="Detect drift"
                onClick={() => setModal({ kind: "drift-detect" })}
                disabled={submitting}
              >
                Detect
              </BrutalButton>
            ) : undefined
          }
        >
          <div className="mb-3 flex max-w-xl flex-wrap items-end gap-2">
            <div className="min-w-32 flex-1">
              <BrutalSelect label="Status" value={driftStatusFilter} onChange={(e) => setDriftStatusFilter(e.target.value)} options={["ALL", ...GOVERNANCE_DRIFT_STATUSES].map((s) => ({ label: s, value: s }))} />
            </div>
            <div className="min-w-32 flex-1">
              <BrutalSelect label="Severity" value={driftSeverityFilter} onChange={(e) => setDriftSeverityFilter(e.target.value)} options={["ALL", ...GOVERNANCE_DRIFT_SEVERITIES].map((s) => ({ label: s, value: s }))} />
            </div>
            <BrutalButton variant="ghost" size="sm" onClick={applyDriftFilters}>Apply</BrutalButton>
          </div>
          <p className="mb-2 font-mono text-xs text-on-surface-variant">Findings cover tampered or expired versions, unbound scopes and controls missing evidence. Detection never mutates silently.</p>
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
                          onClick={() => setModal({ kind: "drift-resolve", finding })}
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
      ) : null}

      {active === "exceptions" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Exceptions" title="Policy exceptions">
            <div className="mb-3 max-w-xs">
              <BrutalSelect
                label="Status"
                value={exceptionFilter}
                onChange={(e) => updateExceptionFilter(e.target.value)}
                options={["ALL", ...GOVERNANCE_EXCEPTION_STATUSES].map((s) => ({ label: s, value: s }))}
              />
            </div>
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Bounded windows (max 720h). No permanent bypass exists; high-risk exceptions need an approved JIT or workflow approval.</p>
            <PanelBody
              loading={loading}
              error={exceptionsError}
              onRetry={() => void loadAll()}
              emptyTitle="No exceptions"
              emptyDescription="Temporary policy exceptions appear here once requested."
            >
              {exceptions && exceptions.length > 0 ? (
                <ul className="space-y-2">
                  {exceptions.map((exception) => (
                    <li key={exception.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{exception.justification || exception.policy_id}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          policy {exception.policy_id.slice(0, 8)} · {exception.scope_type}:{exception.scope_value || "*"} · {exception.requester || "no requester"}
                        </p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          {formatDateTime(exception.start_at)} → {formatDateTime(exception.end_at)} · max {exception.max_duration_hours}h{exception.high_risk ? " · high-risk" : ""}
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
                              onClick={() => setModal({ kind: "exception-approve", exception })}
                            >
                              Approve
                            </BrutalButton>
                            <BrutalButton
                              size="sm"
                              variant="ghost"
                              aria-label="Deny exception"
                              onClick={() => setModal({ kind: "exception-deny", exception })}
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
                            onClick={() => setModal({ kind: "exception-revoke", exception })}
                          >
                            Revoke
                          </BrutalButton>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Exceptions" title="Exception policy scope">
            <PanelBody
              loading={loading}
              error={policiesError}
              onRetry={() => void loadAll()}
              emptyTitle="No policies"
              emptyDescription="Exceptions are always scoped to an exact policy."
            >
              {policies && policies.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
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
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "reports" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Reports" title="Reports">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Type" value={reportTypeFilter} onChange={(e) => setReportTypeFilter(e.target.value)} options={["ALL", ...GOVERNANCE_REPORT_TYPES].map((t) => ({ label: t, value: t }))} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={applyReportFilter}>Apply</BrutalButton>
              <BrutalButton variant="primary" size="sm" onClick={() => { setDraft((d) => ({ ...d, report_type: "posture", report_scope_type: "tenant", report_scope_value: "", report_days: "30" })); setModal({ kind: "report-generate" }); }}>Generate</BrutalButton>
            </div>
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Persisted runs for audit: posture, violations and compliance over a bounded window.</p>
            <PanelBody
              loading={loading}
              error={reportsError}
              onRetry={() => void loadAll()}
              emptyTitle="No reports"
              emptyDescription="Generated reports persist here with their scope and period."
            >
              {reports && reports.length > 0 ? (
                <ul className="space-y-2">
                  {reports.map((report) => (
                    <li key={report.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedReportId(report.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${report.id === selectedReportId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{report.report_type}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {report.scope_type}:{report.scope_value || "*"} · {formatDateTime(report.period_start)} → {formatDateTime(report.period_end)}
                          </p>
                        </div>
                        <BrutalBadge tone="default">{report.sections?.length ?? 0} sections</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Reports" title="Report detail">
              <PanelBody
                loading={loading}
                error={reportsError}
                onRetry={() => void loadAll()}
                emptyTitle="Nothing selected"
                emptyDescription="Select a report to inspect its summary, top risks and sections."
              >
                {selectedReport ? (
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <StatRow label="Type" value={selectedReport.report_type} />
                      <StatRow label="Violations" value={String(selectedReport.summary?.violations ?? 0)} />
                      <StatRow label="Open exceptions" value={String(selectedReport.summary?.open_exceptions ?? 0)} />
                      <StatRow label="Open drift" value={String(selectedReport.summary?.open_drift ?? 0)} />
                    </div>
                    {(selectedReport.summary?.top_risks ?? []).length > 0 ? (
                      <div>
                        <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Top risks</p>
                        <ul className="space-y-1">
                          {(selectedReport.summary.top_risks ?? []).map((risk, index) => (
                            <li key={`${risk.area}-${index}`} className="flex items-center justify-between gap-2 border border-outline bg-surface px-2 py-1">
                              <span className="truncate font-mono text-xs text-on-surface">{risk.area} · {risk.resource}</span>
                              <BrutalBadge tone={severityTone(risk.severity)}>{risk.severity}</BrutalBadge>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {(selectedReport.sections ?? []).map((section) => (
                      <div key={section.name}>
                        <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">{section.name} · {(section.items ?? []).length} items</p>
                        {(section.items ?? []).slice(0, 8).map((item, index) => (
                          <p key={index} className="truncate font-mono text-xs text-on-surface-variant">
                            {String(item.id ?? item.finding_type ?? item.policy_id ?? JSON.stringify(item)).slice(0, 96)}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "ai-governance" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="AI Governance" title="Domain check">
            <p className="mb-3 text-xs text-on-surface-variant">
              Central policy first, then the domain layer. Verdicts carry decision, allowed, layer and reason only — no scores are computed anywhere.
            </p>
            <div className="mb-3">
              <BrutalSelect
                label="Domain"
                value={governDomain}
                onChange={(e) => {
                  setGovernDomain(e.target.value);
                  setGovernResult(null);
                  setGovernError(null);
                }}
                options={Object.keys(GOVERN_FIELDS).map((d) => ({ label: d, value: d }))}
              />
            </div>
            <p className="mb-3 font-mono text-xs text-on-surface-variant">{GOVERN_FIELDS[governDomain]?.hint ?? ""}</p>
            <div className="space-y-3">
              {(GOVERN_FIELDS[governDomain]?.fields ?? []).map((field) =>
                field.options ? (
                  <BrutalSelect
                    key={field.key}
                    label={field.label}
                    value={governFields[`${governDomain}.${field.key}`] ?? field.defaultValue ?? ""}
                    onChange={(e) => setGovernField(field.key, e.target.value)}
                    options={[{ label: "—", value: "" }, ...field.options.map((o) => ({ label: o, value: o }))]}
                  />
                ) : (
                  <BrutalInput
                    key={field.key}
                    label={field.label}
                    value={governFields[`${governDomain}.${field.key}`] ?? field.defaultValue ?? ""}
                    onChange={(e) => setGovernField(field.key, e.target.value)}
                    placeholder={field.placeholder}
                  />
                ),
              )}
              <BrutalButton variant="primary" size="sm" onClick={() => void handleGovernRun()} disabled={governRunning}>
                {governRunning ? "Checking…" : "Run domain check"}
              </BrutalButton>
            </div>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="AI Governance" title="Verdict">
              {governRunning ? (
                <LoadingPanel />
              ) : governError ? (
                <BrutalErrorState title="Check failed" description={governError} onRetry={() => void handleGovernRun()} />
              ) : governResult ? (
                <VerdictRows verdict={governResult} />
              ) : (
                <BrutalEmptyState title="No check run" description="Fill the domain fields and run a check. REQUIRE_APPROVAL surfaces an approval id — approval itself happens in Zero Trust, never here." />
              )}
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "advanced" ? (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <BrutalCard eyebrow="Advanced" title="Evaluate tester">
              <p className="mb-3 text-xs text-on-surface-variant">
                Dry-run without enforcement, or enforce to record a real decision with the Zero Trust layer. Rate-limited server-side — 429 shows a retry state.
              </p>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <BrutalSelect label="Scope type" value={evalDraft.scope_type} onChange={(e) => setEvalDraft({ ...evalDraft, scope_type: e.target.value })} options={GOVERNANCE_SCOPE_TYPES.map((s) => ({ label: s, value: s }))} />
                  <BrutalInput label="Scope value" value={evalDraft.scope_value} onChange={(e) => setEvalDraft({ ...evalDraft, scope_value: e.target.value })} placeholder="scope node" />
                </div>
                <BrutalInput label="Operation" value={evalDraft.operation} onChange={(e) => setEvalDraft({ ...evalDraft, operation: e.target.value })} placeholder="data.export" />
                <BrutalInput label="Context (JSON object)" value={evalDraft.context} onChange={(e) => setEvalDraft({ ...evalDraft, context: e.target.value })} placeholder='{"region": "eu-west"}' />
                <div className="grid grid-cols-2 gap-3">
                  <BrutalInput label="Actor" value={evalDraft.actor} onChange={(e) => setEvalDraft({ ...evalDraft, actor: e.target.value })} placeholder="optional" />
                  <BrutalInput label="Identity" value={evalDraft.identity} onChange={(e) => setEvalDraft({ ...evalDraft, identity: e.target.value })} placeholder="optional" />
                </div>
                <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                  <input type="checkbox" checked={evalDraft.enforce} onChange={(e) => setEvalDraft({ ...evalDraft, enforce: e.target.checked })} />
                  Enforce (records a real decision)
                </label>
                <BrutalButton variant="primary" size="sm" onClick={() => void handleEvaluateTest()} disabled={evalRunning}>
                  {evalRunning ? "Evaluating…" : "Evaluate"}
                </BrutalButton>
              </div>
              {evalError ? <p className="mt-3 text-xs text-error">{evalError}</p> : null}
              {evalResult ? (
                <div className="mt-3 border-t border-outline pt-2">
                  <VerdictRows verdict={evalResult} />
                  <StatRow label="Evaluated at" value={formatDateTime(evalResult.effective_at)} />
                  <StatRow label="Latency ms" value={String(evalResult.latency_ms ?? "—")} />
                </div>
              ) : null}
            </BrutalCard>

            <BrutalCard eyebrow="Advanced" title="Simulate tester">
              <p className="mb-3 text-xs text-on-surface-variant">
                Simulation never has side effects. Batch mode also accepts a proposed version overlay to compare against active versions.
              </p>
              <div className="mb-3 flex gap-2">
                <BrutalButton variant={simMode === "single" ? "primary" : "ghost"} size="sm" onClick={() => setSimMode("single")}>Single</BrutalButton>
                <BrutalButton variant={simMode === "batch" ? "primary" : "ghost"} size="sm" onClick={() => setSimMode("batch")}>Batch</BrutalButton>
              </div>
              {simMode === "single" ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <BrutalSelect label="Scope type" value={simDraft.scope_type} onChange={(e) => setSimDraft({ ...simDraft, scope_type: e.target.value })} options={GOVERNANCE_SCOPE_TYPES.map((s) => ({ label: s, value: s }))} />
                    <BrutalInput label="Scope value" value={simDraft.scope_value} onChange={(e) => setSimDraft({ ...simDraft, scope_value: e.target.value })} />
                  </div>
                  <BrutalInput label="Simulated operation" value={simDraft.operation} onChange={(e) => setSimDraft({ ...simDraft, operation: e.target.value })} />
                  <BrutalInput label="Context (JSON object)" value={simDraft.context} onChange={(e) => setSimDraft({ ...simDraft, context: e.target.value })} placeholder="{}" />
                  <BrutalInput label="Proposed version (JSON object)" value={simDraft.proposed} onChange={(e) => setSimDraft({ ...simDraft, proposed: e.target.value })} placeholder="optional overlay" />
                </div>
              ) : (
                <div className="space-y-3">
                  <BrutalInput label="Requests (JSON array)" value={simDraft.requests} onChange={(e) => setSimDraft({ ...simDraft, requests: e.target.value })} placeholder='[{"scope_type": "tenant", "operation": "data.export"}]' />
                </div>
              )}
              <div className="mt-3">
                <BrutalButton variant="primary" size="sm" onClick={() => void handleSimulateTest()} disabled={simRunning}>
                  {simRunning ? "Simulating…" : "Simulate"}
                </BrutalButton>
              </div>
              {simError ? <p className="mt-3 text-xs text-error">{simError}</p> : null}
              {simResult && "items" in simResult ? (
                <div className="mt-3 border-t border-outline pt-2">
                  <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                    {simResult.total} simulated · {Object.entries(simResult.summary).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                  </p>
                  <ul className="max-h-64 space-y-1 overflow-y-auto">
                    {simResult.items.slice(0, 20).map((item, index) => (
                      <li key={index} className="flex items-center justify-between gap-2 border border-outline bg-surface px-2 py-1">
                        <span className="truncate font-mono text-xs text-on-surface">{item.scope_type}:{item.scope_value || "*"} · {item.reason || "no reason"}</span>
                        <BrutalBadge tone={decisionTone(item.decision)}>{item.decision}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {simResult && !("items" in simResult) ? (
                <div className="mt-3 border-t border-outline pt-2">
                  <div className="mb-2 flex items-center gap-2">
                    <BrutalBadge tone={decisionTone(simResult.decision)}>{simResult.decision}</BrutalBadge>
                    <BrutalBadge tone="muted">side_effects: off</BrutalBadge>
                  </div>
                  <StatRow label="Reason" value={simResult.reason || "—"} />
                  <StatRow label="Simulated at" value={formatDateTime(simResult.simulated_at)} />
                </div>
              ) : null}
            </BrutalCard>
          </div>

          <BrutalCard eyebrow="Advanced" title="Ask AI">
            <p className="mb-3 text-xs text-on-surface-variant">
              Open the AI workspace to discuss this tenant&apos;s governance posture. No decisions, policies or secrets travel with the link.
            </p>
            <BrutalButton variant="yellow" size="sm" href="/ai">Ask AI about governance</BrutalButton>
          </BrutalCard>
        </div>
      ) : null}

      <BrutalModal
        open={modal !== null}
        title={modalTitle}
        onClose={() => {
          if (!submitting) setModal(null);
        }}
        actions={
          modal !== null ? (
            <BrutalButton
              variant="primary"
              onClick={() => {
                if (modal.kind === "policy-create") {
                  void handlePolicyCreate();
                } else if (modal.kind === "version-create") {
                  void handleVersionCreate();
                } else if (modal.kind === "version-status") {
                  void handleVersionStatus();
                } else if (modal.kind === "binding-create") {
                  void handleBindingCreate();
                } else if (modal.kind === "binding-delete") {
                  void handleBindingDelete();
                } else if (modal.kind === "exception-approve" || modal.kind === "exception-deny") {
                  void handleExceptionDecision();
                } else if (modal.kind === "exception-revoke") {
                  void handleExceptionRevoke();
                } else if (modal.kind === "drift-resolve") {
                  void handleDriftResolve();
                } else if (modal.kind === "drift-detect") {
                  void handleDriftDetect();
                } else if (modal.kind === "register-evidence") {
                  void handleRegisterEvidence();
                } else if (modal.kind === "report-generate") {
                  void handleReportGenerate();
                }
              }}
              disabled={submitting}
            >
              {submitting ? "Working…" : modal.kind === "register-evidence" ? "Register" : modal.kind === "policy-create" || modal.kind === "version-create" || modal.kind === "binding-create" ? "Create" : modal.kind === "report-generate" ? "Generate" : "Confirm"}
            </BrutalButton>
          ) : undefined
        }
      >
        <p className="text-sm text-on-surface-variant">
          {modal?.kind === "policy-create"
            ? "Policies start as DRAFT. Record a version and activate it before binding."
            : modal?.kind === "version-create"
              ? `Record a new immutable version for policy ${modal.policy.name}. At least one rule is required (max 50, 64KB).`
              : modal?.kind === "version-status"
                ? `Transition version ${modal.version.version} (${modal.version.status}). ACTIVE versions can only move to SUPERSEDED or RETIRED; activation supersedes sibling versions.`
                : modal?.kind === "binding-create"
                  ? "Attach a policy version to one scope node. Mandatory bindings require organization scope."
                  : modal?.kind === "binding-delete"
                    ? `Delete the binding ${modal.binding.scope_type}:${modal.binding.scope_value || "*"}? Mandatory bindings cannot be removed this way.`
                    : modal?.kind === "exception-approve"
                      ? `Approve the exception for policy ${modal.exception.policy_id.slice(0, 8)}?`
                      : modal?.kind === "exception-deny"
                        ? `Deny the exception for policy ${modal.exception.policy_id.slice(0, 8)}?`
                        : modal?.kind === "exception-revoke"
                          ? `Revoke the approved exception for policy ${modal.exception.policy_id.slice(0, 8)}?`
                          : modal?.kind === "drift-resolve"
                            ? `Mark drift finding ${modal.finding.id.slice(0, 8)} as resolved?`
                            : modal?.kind === "drift-detect"
                              ? "Compare the current configuration against policies and evidence now?"
                              : modal?.kind === "register-evidence"
                                ? "Register a new evidence record for a control."
                                : modal?.kind === "report-generate"
                                  ? "Generate a persisted report run for the selected scope and window."
                                  : ""}
        </p>
        {modal?.kind === "policy-create" ? (
          <div className="mt-4 space-y-3">
            <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="policy name" />
            <BrutalInput label="Domain" value={draft.domain} onChange={(e) => setDraft({ ...draft, domain: e.target.value })} placeholder="general" />
            <BrutalInput label="Description" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="what this policy governs" />
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft({ ...draft, owner: e.target.value })} placeholder="team or person" />
          </div>
        ) : null}
        {modal?.kind === "version-create" ? (
          <div className="mt-4 space-y-3">
            <BrutalInput label="Rules (JSON array)" value={draft.rules} onChange={(e) => setDraft({ ...draft, rules: e.target.value })} placeholder='[{"name": "deny-egress", "effect": "deny", "condition": {...}}]' />
            <BrutalSelect label="Default effect" value={draft.default_effect} onChange={(e) => setDraft({ ...draft, default_effect: e.target.value })} options={GOVERNANCE_EFFECTS.map((fx) => ({ label: fx, value: fx }))} />
            <BrutalInput label="Effective from (ISO)" value={draft.effective_from} onChange={(e) => setDraft({ ...draft, effective_from: e.target.value })} placeholder="optional" />
            <BrutalInput label="Effective until (ISO)" value={draft.effective_until} onChange={(e) => setDraft({ ...draft, effective_until: e.target.value })} placeholder="optional" />
            <BrutalInput label="Reason" value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} placeholder="why this version exists" />
          </div>
        ) : null}
        {modal?.kind === "version-status" ? (
          <div className="mt-4 space-y-3">
            <BrutalSelect label="Status" value={draft.version_status} onChange={(e) => setDraft({ ...draft, version_status: e.target.value })} options={GOVERNANCE_VERSION_STATUSES.map((s) => ({ label: s, value: s }))} />
            <BrutalInput label="Reason" value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} placeholder="transition reason" />
          </div>
        ) : null}
        {modal?.kind === "binding-create" ? (
          <div className="mt-4 space-y-3">
            <BrutalInput label="Policy ID" value={draft.binding_policy_id} onChange={(e) => setDraft({ ...draft, binding_policy_id: e.target.value })} placeholder="policy uuid" />
            <BrutalInput label="Version ID" value={draft.binding_version_id} onChange={(e) => setDraft({ ...draft, binding_version_id: e.target.value })} placeholder="version uuid" />
            <BrutalSelect label="Scope type" value={draft.binding_scope_type} onChange={(e) => setDraft({ ...draft, binding_scope_type: e.target.value })} options={GOVERNANCE_SCOPE_TYPES.map((s) => ({ label: s, value: s }))} />
            <BrutalInput label="Scope value" value={draft.binding_scope_value} onChange={(e) => setDraft({ ...draft, binding_scope_value: e.target.value })} placeholder="scope node, empty for scope root" />
            <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
              <input type="checkbox" checked={draft.binding_mandatory} onChange={(e) => setDraft({ ...draft, binding_mandatory: e.target.checked })} />
              Mandatory (organization scope only)
            </label>
          </div>
        ) : null}
        {modal?.kind === "register-evidence" ? (
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
        {modal?.kind === "report-generate" ? (
          <div className="mt-4 space-y-3">
            <BrutalSelect label="Report type" value={draft.report_type} onChange={(e) => setDraft({ ...draft, report_type: e.target.value })} options={GOVERNANCE_REPORT_TYPES.map((t) => ({ label: t, value: t }))} />
            <BrutalSelect label="Scope type" value={draft.report_scope_type} onChange={(e) => setDraft({ ...draft, report_scope_type: e.target.value })} options={GOVERNANCE_SCOPE_TYPES.map((s) => ({ label: s, value: s }))} />
            <BrutalInput label="Scope value" value={draft.report_scope_value} onChange={(e) => setDraft({ ...draft, report_scope_value: e.target.value })} placeholder="empty for scope root" />
            <BrutalInput label="Days (1–365)" value={draft.report_days} onChange={(e) => setDraft({ ...draft, report_days: e.target.value })} placeholder="30" />
          </div>
        ) : null}
      </BrutalModal>
    </div>
  );
}
