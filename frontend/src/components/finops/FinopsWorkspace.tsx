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
import { BrutalTable } from "@/components/ui/BrutalTable";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
import { useToastStore } from "@/stores/toast";
import type {
  AggregationBucket,
  AggregationRunResult,
  BudgetEvaluation,
  ChargebackReport,
  CostAllocation,
  CostAnomaly,
  CostsPage,
  FinOpsBudget,
  FinOpsCostRecord,
  FinOpsPolicy,
  FinOpsRecommendation,
  ForecastResult,
  GateDecision,
  ModelComparison,
  PricingVersion,
  UsageSummary,
} from "@/types/finops";
import {
  ANOMALY_SEVERITIES,
  BUDGET_PERIODS,
  BUDGET_STATUSES,
  COST_BASES,
  ENFORCEMENTS,
  GROUP_KEYS,
  POLICY_ACTIONS,
  REPORT_TYPES,
  formatCents,
  isForecastReady,
} from "@/types/finops";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function budgetTone(status: string | undefined): "yellow" | "muted" | "error" | "default" {
  if (status === "ACTIVE") return "yellow";
  if (status === "WARNING") return "error";
  if (status === "EXCEEDED") return "error";
  return "muted";
}

function severityTone(severity: string | undefined): "error" | "yellow" | "muted" | "default" {
  if (severity === "CRITICAL" || severity === "HIGH") return "error";
  if (severity === "MEDIUM") return "yellow";
  return "muted";
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface" title={value}>{value}</span>
    </div>
  );
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

/** Pure-CSS bars over real aggregation buckets. No chart library, no derived metrics. */
function TrendBars({ buckets }: { buckets: AggregationBucket[] }) {
  const ordered = [...buckets]
    .filter((b) => b.bucket_start)
    .sort((a, b) => String(a.bucket_start).localeCompare(String(b.bucket_start)))
    .slice(-30);
  if (ordered.length === 0) {
    return <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">No buckets reported.</p>;
  }
  const max = Math.max(...ordered.map((b) => b.total_cents), 1);
  return (
    <div className="flex h-28 items-end gap-1" role="img" aria-label={`Spend trend over ${ordered.length} buckets`}>
      {ordered.map((b) => (
        <div
          key={b.id}
          className="min-w-0 flex-1 border border-outline bg-primary-container"
          style={{ height: `${Math.max(Math.round((b.total_cents / max) * 100), 3)}%` }}
          title={`${b.bucket_start}: ${formatCents(b.total_cents)} across ${b.record_count} records`}
        />
      ))}
    </div>
  );
}

type TabId = "overview" | "usage" | "costs" | "budgets" | "forecast" | "anomalies" | "pricing" | "governance" | "intelligence";

type PendingModal =
  | { kind: "budget-create" }
  | { kind: "budget-update"; budget: FinOpsBudget }
  | { kind: "pricing-create" }
  | { kind: "pricing-deprecate"; pricing: PricingVersion }
  | { kind: "allocation-create" }
  | { kind: "policy-create" }
  | { kind: "policy-update"; policy: FinOpsPolicy }
  | null;

const PAGE_SIZE = 25;

export function FinopsWorkspace() {
  const pushToast = useToastStore((s) => s.push);
  const [active, setActive] = useState<TabId>("overview");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [costs, setCosts] = useState<CostsPage | null>(null);
  const [costsError, setCostsError] = useState<string | null>(null);
  const [costOffset, setCostOffset] = useState(0);
  const [costFilters, setCostFilters] = useState({
    provider: "",
    model: "",
    workspace: "",
    project: "",
    service: "",
    environment: "",
    cost_basis: "ALL",
    start: "",
    end: "",
  });
  const [selectedCostId, setSelectedCostId] = useState<string | null>(null);

  const [budgets, setBudgets] = useState<FinOpsBudget[] | null>(null);
  const [budgetsError, setBudgetsError] = useState<string | null>(null);
  const [budgetStatusFilter, setBudgetStatusFilter] = useState("ALL");
  const [selectedBudgetId, setSelectedBudgetId] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<BudgetEvaluation | null>(null);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [evaluationLoading, setEvaluationLoading] = useState(false);

  const [buckets, setBuckets] = useState<AggregationBucket[] | null>(null);
  const [bucketsError, setBucketsError] = useState<string | null>(null);

  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [horizonDays, setHorizonDays] = useState("30");

  const [anomalies, setAnomalies] = useState<CostAnomaly[] | null>(null);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [lookbackDays, setLookbackDays] = useState("14");

  const [pricing, setPricing] = useState<PricingVersion[] | null>(null);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [pricingProviderFilter, setPricingProviderFilter] = useState("");
  const [pricingStatusFilter, setPricingStatusFilter] = useState("ALL");
  const [selectedPricingId, setSelectedPricingId] = useState<string | null>(null);

  const [allocations, setAllocations] = useState<CostAllocation[] | null>(null);
  const [allocationsError, setAllocationsError] = useState<string | null>(null);

  const [policies, setPolicies] = useState<FinOpsPolicy[] | null>(null);
  const [policiesError, setPoliciesError] = useState<string | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  const [gateResult, setGateResult] = useState<GateDecision | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);
  const [gateRunning, setGateRunning] = useState(false);
  const [gateDraft, setGateDraft] = useState({
    operation: "",
    identity: "",
    estimated_cents: "",
    workspace: "",
    project: "",
    model: "",
    provider: "",
    reason: "",
  });

  const [reports, setReports] = useState<ChargebackReport[] | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [reportTypeFilter, setReportTypeFilter] = useState("ALL");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [reportDraft, setReportDraft] = useState({ report_type: "showback", start: "", end: "", group_by: "workspace" });
  const [reportRunning, setReportRunning] = useState(false);

  const [comparison, setComparison] = useState<ModelComparison | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [compareProvider, setCompareProvider] = useState("");

  const [recommendations, setRecommendations] = useState<FinOpsRecommendation[] | null>(null);
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null);
  const [recTypeFilter, setRecTypeFilter] = useState("ALL");
  const [recStatusFilter, setRecStatusFilter] = useState("ALL");
  const [generatingRecs, setGeneratingRecs] = useState(false);

  const [aggResult, setAggResult] = useState<AggregationRunResult | null>(null);
  const [aggError, setAggError] = useState<string | null>(null);
  const [aggRunning, setAggRunning] = useState(false);
  const [aggDraft, setAggDraft] = useState({ granularity: "day", start: "", end: "" });

  const [modal, setModal] = useState<PendingModal>(null);
  const [submitting, setSubmitting] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    amount: "",
    scope_type: "tenant",
    scope_value: "",
    provider: "",
    model: "",
    environment: "",
    currency: "USD",
    period: "monthly",
    warning_threshold: "0.8",
    hard_limit_threshold: "1.0",
    enforcement: "alert",
    owner: "",
    approval_policy: "none",
    enabled: "true",
    status: "ACTIVE",
    pricing_provider: "",
    pricing_model: "",
    pricing_resource: "",
    pricing_unit: "tokens",
    pricing_input: "",
    pricing_output: "",
    pricing_request: "",
    pricing_currency: "USD",
    pricing_effective_from: "",
    pricing_effective_until: "",
    pricing_reason: "",
    allocation_key: "",
    allocation_share: "",
    allocation_workspace: "",
    allocation_project: "",
    allocation_service: "",
    allocation_environment: "",
    allocation_basis: "direct",
    policy_name: "",
    policy_workspace: "",
    policy_project: "",
    policy_model: "",
    policy_provider: "",
    policy_operation: "",
    policy_max_cents: "",
    policy_action: "alert",
    policy_owner: "",
    policy_enabled: "true",
  });

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

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
      if (e instanceof ApiError && e.status === 429) {
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
    setSummaryError(null);
    setCostsError(null);
    setBudgetsError(null);
    setBucketsError(null);
    setForecastError(null);
    setAnomaliesError(null);
    setPricingError(null);
    setAllocationsError(null);
    setPoliciesError(null);
    setReportsError(null);
    setComparisonError(null);
    setRecommendationsError(null);

    async function settle<T>(load: () => Promise<T>, set: (value: T | null) => void, onError: (message: string) => void) {
      try {
        const value = await load();
        if (controller.signal.aborted || seq !== seqRef.current) return;
        set(value);
      } catch (e) {
        if (controller.signal.aborted || seq !== seqRef.current) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        onError(e instanceof Error ? e.message : "Unavailable");
      }
    }

    const horizon = Math.min(Math.max(Number(horizonDays) || 30, 1), 90);
    await Promise.all([
      settle(() => api.finopsUsageSummary(token, {}), setSummary, setSummaryError),
      settle(
        () =>
          api.finopsCostsFiltered(token, {
            provider: costFilters.provider.trim() || undefined,
            model: costFilters.model.trim() || undefined,
            workspace: costFilters.workspace.trim() || undefined,
            project: costFilters.project.trim() || undefined,
            service: costFilters.service.trim() || undefined,
            environment: costFilters.environment.trim() || undefined,
            cost_basis: costFilters.cost_basis !== "ALL" ? costFilters.cost_basis : undefined,
            start: costFilters.start.trim() || undefined,
            end: costFilters.end.trim() || undefined,
            limit: PAGE_SIZE,
            offset: costOffset,
          }),
        setCosts,
        setCostsError,
      ),
      settle(
        () => api.finopsBudgets(token, { status: budgetStatusFilter !== "ALL" ? budgetStatusFilter : undefined }),
        (value) => setBudgets(value?.items ?? []),
        setBudgetsError,
      ),
      settle(
        () => api.finopsAggregations(token, { granularity: "day", limit: 60 }),
        (value) => setBuckets(value?.items ?? []),
        setBucketsError,
      ),
      settle(() => api.finopsForecast(token, { horizon_days: horizon }), setForecast, setForecastError),
      settle(
        () =>
          api.finopsAnomalies(token, {
            severity: severityFilter !== "ALL" ? severityFilter : undefined,
            status: statusFilter !== "ALL" ? statusFilter : undefined,
            limit: 100,
          }),
        (value) => setAnomalies(value?.items ?? []),
        setAnomaliesError,
      ),
      settle(
        () =>
          api.finopsPricing(token, {
            provider: pricingProviderFilter.trim() || undefined,
            status: pricingStatusFilter !== "ALL" ? pricingStatusFilter : undefined,
          }),
        (value) => setPricing(value?.items ?? []),
        setPricingError,
      ),
      settle(
        () => api.finopsAllocations(token, { limit: 100, offset: 0 }),
        (value) => setAllocations(value?.items ?? []),
        setAllocationsError,
      ),
      settle(
        () => api.finopsPolicies(token),
        (value) => setPolicies(value?.items ?? []),
        setPoliciesError,
      ),
      settle(
        () => api.finopsReports(token, { report_type: reportTypeFilter !== "ALL" ? reportTypeFilter : undefined }),
        (value) => setReports(value?.items ?? []),
        setReportsError,
      ),
      settle(
        () => api.finopsModelsCompare(token, { provider: compareProvider.trim() || undefined }),
        setComparison,
        setComparisonError,
      ),
      settle(
        () =>
          api.finopsRecommendations(token, {
            rec_type: recTypeFilter !== "ALL" ? recTypeFilter : undefined,
            status: recStatusFilter !== "ALL" ? recStatusFilter : undefined,
            limit: 100,
          }),
        (value) => setRecommendations(value?.items ?? []),
        setRecommendationsError,
      ),
    ]);

    if (!controller.signal.aborted && seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, [costFilters, costOffset, budgetStatusFilter, horizonDays, severityFilter, statusFilter, pricingProviderFilter, pricingStatusFilter, reportTypeFilter, compareProvider, recTypeFilter, recStatusFilter]);

  const loadEvaluation = useCallback(async (budgetId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setEvaluationLoading(true);
    setEvaluationError(null);
    try {
      const result = await api.finopsBudgetEvaluate(token, budgetId);
      setEvaluation(result);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setEvaluationError(e instanceof Error ? e.message : "Budget evaluation unavailable");
    } finally {
      setEvaluationLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let activeFlag = true;
    api
      .whoami(token)
      .then((whoami) => {
        if (activeFlag) setPermissions(whoami.permissions ?? []);
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
      setSummary(null);
      setCosts(null);
      setBudgets(null);
      setBuckets(null);
      setForecast(null);
      setAnomalies(null);
      setEvaluation(null);
      setPricing(null);
      setAllocations(null);
      setPolicies(null);
      setReports(null);
      setComparison(null);
      setRecommendations(null);
      setGateResult(null);
      setAggResult(null);
      setSelectedCostId(null);
      setSelectedBudgetId(null);
      setSelectedAnomalyId(null);
      setSelectedPricingId(null);
      setSelectedPolicyId(null);
      setSelectedReportId(null);
      setCostOffset(0);
      setSummaryError(null);
      setCostsError(null);
      setBudgetsError(null);
      setBucketsError(null);
      setForecastError(null);
      setAnomaliesError(null);
      setPricingError(null);
      setAllocationsError(null);
      setPoliciesError(null);
      setReportsError(null);
      setComparisonError(null);
      setRecommendationsError(null);
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
    if (selectedBudgetId) {
      void loadEvaluation(selectedBudgetId);
    } else {
      setEvaluation(null);
    }
  }, [selectedBudgetId, loadEvaluation]);

  const canAdmin = hasPermission(permissions, PERMISSIONS.billingAdmin);
  const canRead = hasPermission(permissions, PERMISSIONS.billingRead) || canAdmin;
  const selectedCost: FinOpsCostRecord | null = costs?.items.find((c) => c.id === selectedCostId) ?? null;
  const selectedAnomaly: CostAnomaly | null = anomalies?.find((a) => a.id === selectedAnomalyId) ?? null;
  const openAnomalies = anomalies?.filter((a) => a.status === "OPEN") ?? [];

  function openModal(next: PendingModal) {
    setDraft({
      name: "",
      amount: "",
      scope_type: "tenant",
      scope_value: "",
      provider: "",
      model: "",
      environment: "",
      currency: "USD",
      period: "monthly",
      warning_threshold: "0.8",
      hard_limit_threshold: "1.0",
      enforcement: "alert",
      owner: "",
      approval_policy: "none",
      enabled: "true",
      status: "ACTIVE",
      pricing_provider: "",
      pricing_model: "",
      pricing_resource: "",
      pricing_unit: "tokens",
      pricing_input: "",
      pricing_output: "",
      pricing_request: "",
      pricing_currency: "USD",
      pricing_effective_from: "",
      pricing_effective_until: "",
      pricing_reason: "",
      allocation_key: "",
      allocation_share: "",
      allocation_workspace: "",
      allocation_project: "",
      allocation_service: "",
      allocation_environment: "",
      allocation_basis: "direct",
      policy_name: "",
      policy_workspace: "",
      policy_project: "",
      policy_model: "",
      policy_provider: "",
      policy_operation: "",
      policy_max_cents: "",
      policy_action: "alert",
      policy_owner: "",
      policy_enabled: "true",
    });
    setModal(next);
  }

  async function handleBudgetCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const amount = Number(draft.amount);
    if (!draft.name.trim() || !Number.isFinite(amount) || amount <= 0) {
      pushToast("warning", "Name and a positive amount in cents are required");
      return;
    }
    setSubmitting(true);
    try {
      await api.finopsBudgetCreate(token, {
        name: draft.name.trim(),
        amount_cents: Math.round(amount),
        scope_type: draft.scope_type,
        scope_value: draft.scope_value.trim(),
        provider: draft.provider.trim(),
        model: draft.model.trim(),
        environment: draft.environment.trim(),
        currency: draft.currency.trim() || "USD",
        period: draft.period,
        warning_threshold: Number(draft.warning_threshold) || 0.8,
        hard_limit_threshold: Number(draft.hard_limit_threshold) || 1.0,
        enforcement: draft.enforcement,
        owner: draft.owner.trim(),
        approval_policy: draft.approval_policy.trim() || "none",
      });
      setModal(null);
      pushToast("success", "Budget created");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create budget", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleBudgetUpdate() {
    if (!modal || modal.kind !== "budget-update") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        name: draft.name.trim() || undefined,
        warning_threshold: draft.warning_threshold.trim() ? Number(draft.warning_threshold) : undefined,
        hard_limit_threshold: draft.hard_limit_threshold.trim() ? Number(draft.hard_limit_threshold) : undefined,
        enforcement: draft.enforcement,
        enabled: draft.enabled === "true",
        owner: draft.owner.trim() || undefined,
        approval_policy: draft.approval_policy.trim() || undefined,
        status: draft.status,
      };
      if (draft.amount.trim()) {
        const amount = Number(draft.amount);
        if (!Number.isFinite(amount) || amount <= 0) {
          pushToast("warning", "Amount must be a positive number of cents");
          setSubmitting(false);
          return;
        }
        body.amount_cents = Math.round(amount);
      }
      const cleaned = Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined));
      await api.finopsBudgetUpdate(token, modal.budget.id, cleaned);
      setModal(null);
      pushToast("success", "Budget updated");
      void loadAll();
      void loadEvaluation(modal.budget.id);
    } catch (e) {
      notifyError(e, "Failed to update budget", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  function applyCostFilters() {
    setCostOffset(0);
    setSelectedCostId(null);
    void loadAll();
  }

  async function handlePricingCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.pricing_provider.trim()) {
      pushToast("warning", "Provider is required");
      return;
    }
    setSubmitting(true);
    try {
      const num = (raw: string) => (raw.trim() ? Number(raw) : 0);
      await api.finopsPricingCreate(token, {
        provider: draft.pricing_provider.trim(),
        model: draft.pricing_model.trim(),
        resource: draft.pricing_resource.trim(),
        unit: draft.pricing_unit.trim() || "tokens",
        input_price_cents_per_m: num(draft.pricing_input),
        output_price_cents_per_m: num(draft.pricing_output),
        request_price_cents: num(draft.pricing_request),
        currency: draft.pricing_currency.trim() || "USD",
        effective_from: draft.pricing_effective_from.trim() || undefined,
        effective_until: draft.pricing_effective_until.trim() || undefined,
        source: "manual",
        reason: draft.pricing_reason.trim(),
      });
      setModal(null);
      pushToast("success", "Pricing version created — prior versions remain immutable history");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create pricing version", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePricingDeprecate() {
    if (!modal || modal.kind !== "pricing-deprecate") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.finopsPricingDeprecate(token, modal.pricing.id);
      setModal(null);
      pushToast("success", "Pricing version deprecated");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to deprecate pricing version", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAllocationCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!selectedCostId || !draft.allocation_key.trim()) {
      pushToast("warning", "Select a cost record and provide an allocation key");
      return;
    }
    const share = Number(draft.allocation_share);
    if (!Number.isFinite(share) || share <= 0 || share > 1) {
      pushToast("warning", "Share must be in (0, 1]; splits for one record must sum to 1.0");
      return;
    }
    setSubmitting(true);
    try {
      await api.finopsAllocationCreate(token, {
        cost_record_id: selectedCostId,
        splits: [
          {
            allocation_key: draft.allocation_key.trim(),
            share,
            target_workspace: draft.allocation_workspace.trim(),
            target_project: draft.allocation_project.trim(),
            target_service: draft.allocation_service.trim(),
            target_environment: draft.allocation_environment.trim(),
          },
        ],
        basis: draft.allocation_basis.trim() || "direct",
      });
      setModal(null);
      pushToast("success", "Allocation recorded — retries with the same key return the existing row");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to record allocation", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAggregationRun() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setAggRunning(true);
    setAggError(null);
    try {
      const result = await api.finopsAggregationRun(token, {
        granularity: aggDraft.granularity,
        start: aggDraft.start.trim() || undefined,
        end: aggDraft.end.trim() || undefined,
      });
      setAggResult(result);
      pushToast("success", `Aggregation wrote ${result.buckets} buckets from ${result.records_scanned} records`);
      void loadAll();
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        pushToast("warning", "You don't have permission to perform this action");
        return;
      }
      setAggError(e instanceof Error ? e.message : "Aggregation run failed");
    } finally {
      setAggRunning(false);
    }
  }

  async function handleAnomalyDetect() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const lookback = Math.min(Math.max(Number(lookbackDays) || 14, 7), 60);
    setDetecting(true);
    try {
      const result = await api.finopsAnomalyDetect(token, lookback);
      pushToast(
        "success",
        result.total === 0 ? "Detection complete — no anomalies" : `Detection complete — ${result.total} anomal${result.total === 1 ? "y" : "ies"}`,
      );
      void loadAll();
    } catch (e) {
      notifyError(e, "Anomaly detection failed", () => void loadAll());
    } finally {
      setDetecting(false);
    }
  }

  async function handleRecommendationsGenerate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setGeneratingRecs(true);
    try {
      const result = await api.finopsRecommendationsGenerate(token);
      pushToast(
        "success",
        result.total === 0 ? "No recommendations — nothing evidence-backed to suggest" : `Generated ${result.total} recommendation${result.total === 1 ? "" : "s"}`,
      );
      void loadAll();
    } catch (e) {
      notifyError(e, "Recommendation generation failed", () => void loadAll());
    } finally {
      setGeneratingRecs(false);
    }
  }

  async function handlePolicyCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.policy_name.trim()) {
      pushToast("warning", "Policy name is required");
      return;
    }
    setSubmitting(true);
    try {
      await api.finopsPolicyCreate(token, {
        name: draft.policy_name.trim(),
        workspace: draft.policy_workspace.trim(),
        project: draft.policy_project.trim(),
        model: draft.policy_model.trim(),
        provider: draft.policy_provider.trim(),
        operation: draft.policy_operation.trim(),
        max_estimated_cents: draft.policy_max_cents.trim() ? Number(draft.policy_max_cents) : undefined,
        action: draft.policy_action,
        owner: draft.policy_owner.trim(),
      });
      setModal(null);
      pushToast("success", "Policy created");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create policy", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePolicyUpdate() {
    if (!modal || modal.kind !== "policy-update") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        action: draft.policy_action,
        enabled: draft.policy_enabled === "true",
      };
      if (draft.policy_name.trim()) body.name = draft.policy_name.trim();
      if (draft.policy_workspace.trim()) body.workspace = draft.policy_workspace.trim();
      if (draft.policy_project.trim()) body.project = draft.policy_project.trim();
      if (draft.policy_model.trim()) body.model = draft.policy_model.trim();
      if (draft.policy_provider.trim()) body.provider = draft.policy_provider.trim();
      if (draft.policy_operation.trim()) body.operation = draft.policy_operation.trim();
      if (draft.policy_owner.trim()) body.owner = draft.policy_owner.trim();
      if (draft.policy_max_cents.trim()) body.max_estimated_cents = Number(draft.policy_max_cents);
      await api.finopsPolicyUpdate(token, modal.policy.id, body);
      setModal(null);
      pushToast("success", "Policy updated");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update policy", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGateEvaluate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!gateDraft.operation.trim()) {
      pushToast("warning", "Operation is required");
      return;
    }
    setGateRunning(true);
    setGateError(null);
    try {
      const result = await api.finopsGateEvaluate(token, {
        operation: gateDraft.operation.trim(),
        identity: gateDraft.identity.trim() || undefined,
        estimated_cents: gateDraft.estimated_cents.trim() ? Number(gateDraft.estimated_cents) : 0,
        workspace: gateDraft.workspace.trim() || undefined,
        project: gateDraft.project.trim() || undefined,
        model: gateDraft.model.trim() || undefined,
        provider: gateDraft.provider.trim() || undefined,
        reason: gateDraft.reason.trim() || undefined,
      });
      setGateResult(result);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setGateError(e instanceof Error ? e.message : "Gate evaluation failed");
    } finally {
      setGateRunning(false);
    }
  }

  async function handleReportGenerate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setReportRunning(true);
    try {
      const result = await api.finopsReportGenerate(token, reportDraft.report_type, {
        start: reportDraft.start.trim() || undefined,
        end: reportDraft.end.trim() || undefined,
        group_by: reportDraft.group_by,
      });
      pushToast(
        "success",
        (result as { deduplicated?: boolean }).deduplicated
          ? "Report already existed for this period — returned existing row"
          : `Report generated: ${formatCents(result.total_cents)} across ${result.lines.length} groups`,
      );
      void loadAll();
    } catch (e) {
      notifyError(e, "Report generation failed", () => void loadAll());
    } finally {
      setReportRunning(false);
    }
  }

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "usage", label: "Usage" },
    { id: "costs", label: "Costs" },
    { id: "budgets", label: "Budgets" },
    { id: "forecast", label: "Forecast" },
    { id: "anomalies", label: "Anomalies" },
    { id: "pricing", label: "Pricing" },
    { id: "governance", label: "Governance" },
    { id: "intelligence", label: "Intelligence" },
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
          {!canRead && !canAdmin ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Read-only view · no FinOps permissions
            </span>
          ) : null}
          {canAdmin ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Admin actions enabled
            </span>
          ) : null}
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div role="tablist" aria-label="FinOps sections" className="flex flex-wrap gap-2">
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
            <BrutalCard eyebrow="Actual" title="Current usage">
              <PanelBody loading={loading} error={summaryError} onRetry={() => void loadAll()} emptyTitle="No usage reported" emptyDescription="Usage appears once cost records are recorded for this tenant.">
                {summary ? (
                  <div className="space-y-3">
                    <StatRow label="Spend" value={formatCents(summary.spend_cents)} />
                    <StatRow label="Cost records" value={String(summary.cost_records)} />
                    <StatRow label="Total tokens" value={summary.total_tokens.toLocaleString("en-US")} />
                    <StatRow label="AI executions" value={String(summary.ai_executions)} />
                    <StatRow label="AI tokens" value={summary.ai_tokens.toLocaleString("en-US")} />
                    <StatRow label="AI cost" value={formatCents(summary.ai_cost_cents)} />
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Actual" title="Spend trend">
              <PanelBody loading={loading} error={bucketsError} onRetry={() => void loadAll()} emptyTitle="No trend data" emptyDescription="Daily aggregations appear once the aggregation worker has run.">
                {buckets ? <TrendBars buckets={buckets} /> : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Budget" title="Budget utilization">
              <PanelBody loading={loading} error={budgetsError} onRetry={() => void loadAll()} emptyTitle="No budgets" emptyDescription="Create a budget to track spend against limits.">
                {budgets && budgets.length > 0 ? (
                  <ul className="space-y-2">
                    {budgets.slice(0, 5).map((b) => (
                      <li key={b.id} className="flex items-center justify-between gap-2 border border-outline-variant bg-surface px-3 py-2">
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-on-surface">{b.name}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">{formatCents(b.amount_cents, b.currency)} · {b.period}</span>
                        </span>
                        <BrutalBadge tone={budgetTone(b.status)}>{b.status}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <BrutalCard eyebrow="Forecast" title="Spend forecast">
              <PanelBody loading={loading} error={forecastError} onRetry={() => void loadAll()} emptyTitle="No forecast" emptyDescription="The backend needs at least 7 days with spend before it can forecast.">
                {forecast ? (
                  isForecastReady(forecast) ? (
                    <div className="space-y-3">
                      <StatRow label="Predicted" value={formatCents(forecast.predicted_cents)} />
                      <StatRow label="Daily rate" value={formatCents(forecast.daily_rate_cents)} />
                      <StatRow label="Horizon" value={`${forecast.horizon_days} days`} />
                      <StatRow label="Confidence" value={String(forecast.confidence)} />
                      <StatRow label="Quality" value={forecast.quality} />
                      {forecast.budget_exhaustion_date ? (
                        <StatRow label="Budget exhaustion" value={formatDateTime(forecast.budget_exhaustion_date)} />
                      ) : null}
                      {forecast.cached ? <p className="font-mono text-xs text-on-surface-variant">Served from cache (10 min TTL).</p> : null}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <BrutalBadge tone="muted">INSUFFICIENT_DATA</BrutalBadge>
                      <p className="text-sm text-on-surface-variant">{forecast.reason}</p>
                    </div>
                  )
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Anomaly" title="Open anomalies">
              <PanelBody loading={loading} error={anomaliesError} onRetry={() => void loadAll()} emptyTitle="No anomalies" emptyDescription="Statistical anomalies appear here once detected.">
                {anomalies ? (
                  openAnomalies.length > 0 ? (
                    <ul className="space-y-2">
                      {openAnomalies.slice(0, 5).map((a) => (
                        <li key={a.id} className="flex items-center justify-between gap-2 border border-outline-variant bg-surface px-3 py-2">
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-bold text-on-surface">{a.dimension_key}={a.dimension_value || "(empty)"}</span>
                            <span className="block truncate font-mono text-xs text-on-surface-variant">observed {formatCents(a.observed_cents)} vs baseline {formatCents(a.baseline_cents)}</span>
                          </span>
                          <BrutalBadge tone={severityTone(a.severity)}>{a.severity}</BrutalBadge>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <BrutalEmptyState title="No open anomalies" description="All detected anomalies are resolved or none were found." />
                  )
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "usage" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Actual" title="Usage summary">
            <PanelBody loading={loading} error={summaryError} onRetry={() => void loadAll()} emptyTitle="No usage reported" emptyDescription="Usage appears once cost records are recorded for this tenant.">
              {summary ? (
                <div className="space-y-3">
                  <StatRow label="Cost records" value={String(summary.cost_records)} />
                  <StatRow label="Total tokens" value={summary.total_tokens.toLocaleString("en-US")} />
                  <StatRow label="AI executions" value={String(summary.ai_executions)} />
                  <StatRow label="AI tokens" value={summary.ai_tokens.toLocaleString("en-US")} />
                  <StatRow label="Spend" value={formatCents(summary.spend_cents)} />
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Actual" title="Usage by record">
              <p className="mb-3 text-xs text-on-surface-variant">Usage quantities (requests, input/output/cached tokens, latency) come from governed cost records — there is no separate usage-records endpoint. Use the Costs tab filters to scope by provider, model, workspace, project, service or period.</p>
              <PanelBody loading={loading} error={costsError} onRetry={() => void loadAll()} emptyTitle="No usage rows" emptyDescription="No cost records match the current filters.">
                {costs && costs.items.length > 0 ? (
                  <BrutalTable<FinOpsCostRecord>
                    columns={[
                      { key: "provider", header: "Provider / Model", render: (r) => <span className="font-mono text-xs">{r.provider || "—"} / {r.model || "—"}</span> },
                      { key: "requests", header: "Requests", render: (r) => <span className="font-mono text-xs">{r.requests.toLocaleString("en-US")}</span> },
                      { key: "tokens", header: "In / Out / Cached", render: (r) => <span className="font-mono text-xs">{r.input_tokens.toLocaleString("en-US")} / {r.output_tokens.toLocaleString("en-US")} / {r.cached_tokens.toLocaleString("en-US")}</span> },
                      { key: "latency", header: "Latency ms", render: (r) => <span className="font-mono text-xs">{r.latency_ms ?? "—"}</span> },
                      { key: "basis", header: "Basis", render: (r) => <BrutalBadge tone={r.cost_basis === "unpriced" ? "muted" : "default"}>{r.cost_basis}</BrutalBadge> },
                    ]}
                    rows={costs.items}
                  />
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "costs" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Actual" title="Filters">
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Provider" value={costFilters.provider} onChange={(e) => setCostFilters((f) => ({ ...f, provider: e.target.value }))} />
                <BrutalInput label="Model" value={costFilters.model} onChange={(e) => setCostFilters((f) => ({ ...f, model: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Workspace" value={costFilters.workspace} onChange={(e) => setCostFilters((f) => ({ ...f, workspace: e.target.value }))} />
                <BrutalInput label="Project" value={costFilters.project} onChange={(e) => setCostFilters((f) => ({ ...f, project: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Service" value={costFilters.service} onChange={(e) => setCostFilters((f) => ({ ...f, service: e.target.value }))} />
                <BrutalInput label="Environment" value={costFilters.environment} onChange={(e) => setCostFilters((f) => ({ ...f, environment: e.target.value }))} />
              </div>
              <BrutalSelect label="Cost basis" value={costFilters.cost_basis} onChange={(e) => setCostFilters((f) => ({ ...f, cost_basis: e.target.value }))} options={[{ value: "ALL", label: "All bases" }, ...COST_BASES.map((b) => ({ value: b, label: b }))]} />
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Start (ISO)" value={costFilters.start} onChange={(e) => setCostFilters((f) => ({ ...f, start: e.target.value }))} placeholder="2026-08-01" />
                <BrutalInput label="End (ISO)" value={costFilters.end} onChange={(e) => setCostFilters((f) => ({ ...f, end: e.target.value }))} placeholder="2026-09-10" />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={applyCostFilters}>Apply filters</BrutalButton>
            </div>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Actual" title="Cost records">
              <PanelBody loading={loading} error={costsError} onRetry={() => void loadAll()} emptyTitle="No cost records" emptyDescription="No records match the current filters.">
                {costs && costs.items.length > 0 ? (
                  <div className="space-y-3">
                    <BrutalTable<FinOpsCostRecord>
                      columns={[
                        { key: "occurred", header: "Occurred", render: (r) => <span className="font-mono text-xs">{formatDateTime(r.occurred_at)}</span> },
                        { key: "scope", header: "Provider / Model / Svc", render: (r) => <span className="font-mono text-xs">{r.provider || "—"} / {r.model || "—"} / {r.service || "—"}</span> },
                        { key: "amount", header: "Amount", render: (r) => <span className="font-mono text-xs">{formatCents(r.amount_cents, r.currency)}</span> },
                        { key: "basis", header: "Basis", render: (r) => <BrutalBadge tone={r.cost_basis === "unpriced" ? "muted" : "default"}>{r.cost_basis}</BrutalBadge> },
                        { key: "detail", header: "Detail", render: (r) => <BrutalButton variant="ghost" size="sm" onClick={() => setSelectedCostId(r.id)}>View</BrutalButton> },
                      ]}
                      rows={costs.items}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-mono text-xs text-on-surface-variant">
                        Page total: {formatCents(costs.spend_cents)} · showing {costs.items.length} of {costs.total} records
                      </p>
                      <div className="flex gap-2">
                        <BrutalButton variant="ghost" size="sm" disabled={costOffset === 0} onClick={() => setCostOffset((o) => Math.max(o - PAGE_SIZE, 0))}>Prev</BrutalButton>
                        <BrutalButton variant="ghost" size="sm" disabled={costOffset + costs.items.length >= costs.total} onClick={() => setCostOffset((o) => o + PAGE_SIZE)}>Next</BrutalButton>
                      </div>
                    </div>
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>

            {selectedCost ? (
              <div className="mt-6">
                <BrutalCard eyebrow="Actual" title="Record detail">
                  <div className="space-y-3">
                    <StatRow label="ID" value={selectedCost.id} />
                    <StatRow label="Amount" value={formatCents(selectedCost.amount_cents, selectedCost.currency)} />
                    <StatRow label="Basis" value={selectedCost.cost_basis} />
                    <StatRow label="Provider" value={selectedCost.provider || "—"} />
                    <StatRow label="Model" value={selectedCost.model || "—"} />
                    <StatRow label="Workspace" value={selectedCost.workspace || "—"} />
                    <StatRow label="Project" value={selectedCost.project || "—"} />
                    <StatRow label="Service" value={selectedCost.service || "—"} />
                    <StatRow label="Environment" value={selectedCost.environment || "—"} />
                    <StatRow label="Region" value={selectedCost.region || "—"} />
                    <StatRow label="Operation" value={selectedCost.operation || "—"} />
                    <StatRow label="Actor" value={selectedCost.actor || "—"} />
                    <StatRow label="Source" value={`${selectedCost.source_type}:${selectedCost.source_id}`} />
                    <StatRow label="Pricing version" value={selectedCost.pricing_version_id ?? "none (unpriced)"} />
                    <StatRow label="Occurred" value={formatDateTime(selectedCost.occurred_at)} />
                    <div className="pt-1">
                      <BrutalButton variant="ghost" size="sm" onClick={() => setSelectedCostId(null)}>Close detail</BrutalButton>
                    </div>
                  </div>
                </BrutalCard>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {active === "budgets" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Budget" title="Budgets">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-32 flex-1">
                <BrutalSelect label="Status" value={budgetStatusFilter} onChange={(e) => setBudgetStatusFilter(e.target.value)} options={[{ value: "ALL", label: "All statuses" }, ...BUDGET_STATUSES.map((s) => ({ value: s, label: s }))]} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              {canAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "budget-create" })}>New budget</BrutalButton>
              ) : null}
            </div>
            <PanelBody loading={loading} error={budgetsError} onRetry={() => void loadAll()} emptyTitle="No budgets" emptyDescription="Create a budget to track spend against a limit.">
              {budgets && budgets.length > 0 ? (
                <ul className="space-y-2">
                  {budgets.map((b) => (
                    <li key={b.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedBudgetId(b.id)}
                        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${b.id === selectedBudgetId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-on-surface">{b.name}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">{formatCents(b.amount_cents, b.currency)} · {b.period} · {b.scope_type}{b.scope_value ? `:${b.scope_value}` : ""}</span>
                        </span>
                        <BrutalBadge tone={budgetTone(b.status)}>{b.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Budget" title="Evaluation">
              <PanelBody loading={evaluationLoading} error={evaluationError} onRetry={() => selectedBudgetId && void loadEvaluation(selectedBudgetId)} emptyTitle="Nothing selected" emptyDescription="Select a budget to evaluate current-period spend against its thresholds.">
                {evaluation ? (
                  <div className="space-y-3">
                    <StatRow label="Budget" value={evaluation.name} />
                    <StatRow label="Limit" value={formatCents(evaluation.amount_cents, evaluation.currency)} />
                    <StatRow label="Spend (period)" value={formatCents(evaluation.spend_cents, evaluation.currency)} />
                    <StatRow label="Utilization" value={`${(evaluation.utilization * 100).toFixed(1)}%`} />
                    <StatRow label="Status" value={evaluation.status} />
                    <StatRow label="Enforcement" value={evaluation.enforcement} />
                    {evaluation.period_start ? <StatRow label="Period start" value={formatDateTime(evaluation.period_start)} /> : null}
                    {evaluation.period_end ? <StatRow label="Period end" value={formatDateTime(evaluation.period_end)} /> : null}
                    {evaluation.evaluation === "skipped" ? (
                      <p className="font-mono text-xs text-on-surface-variant">Evaluation skipped: budget is suspended, closed or disabled.</p>
                    ) : null}
                    <div className="flex flex-wrap gap-2 pt-1">
                      <BrutalButton variant="ghost" size="sm" onClick={() => selectedBudgetId && void loadEvaluation(selectedBudgetId)}>Re-evaluate</BrutalButton>
                      {canAdmin ? (
                        <BrutalButton variant="ghost" size="sm" onClick={() => {
                          const b = budgets?.find((x) => x.id === selectedBudgetId);
                          if (!b) return;
                          setDraft((d) => ({
                            ...d,
                            name: b.name,
                            warning_threshold: String(b.warning_threshold),
                            hard_limit_threshold: String(b.hard_limit_threshold),
                            enforcement: b.enforcement,
                            owner: b.owner,
                            approval_policy: b.approval_policy,
                            enabled: b.enabled ? "true" : "false",
                            status: b.status,
                          }));
                          setModal({ kind: "budget-update", budget: b });
                        }}>Edit budget</BrutalButton>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "forecast" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Forecast" title="Spend forecast">
            <p className="mb-3 text-xs text-on-surface-variant">Backend-authoritative linear-baseline forecast. No forecasting is performed in the browser. A cached response is labeled as cached.</p>
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="w-32">
                <BrutalInput label="Horizon days (1–90)" value={horizonDays} onChange={(e) => setHorizonDays(e.target.value)} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Regenerate</BrutalButton>
            </div>
            <PanelBody loading={loading} error={forecastError} onRetry={() => void loadAll()} emptyTitle="No forecast" emptyDescription="The backend needs at least 7 days with spend before it can forecast.">
              {forecast ? (
                isForecastReady(forecast) ? (
                  <div className="space-y-3">
                    <StatRow label="Predicted spend" value={formatCents(forecast.predicted_cents)} />
                    <StatRow label="Daily rate" value={formatCents(forecast.daily_rate_cents)} />
                    <StatRow label="Horizon" value={`${forecast.horizon_days} days`} />
                    <StatRow label="Method" value={forecast.method} />
                    <StatRow label="Confidence" value={String(forecast.confidence)} />
                    <StatRow label="Quality" value={forecast.quality} />
                    <StatRow label="Basis buckets" value={String(forecast.basis_buckets)} />
                    <StatRow label="Period start" value={formatDateTime(forecast.period_start)} />
                    {forecast.budget_exhaustion_date ? (
                      <StatRow label="Budget exhaustion" value={formatDateTime(forecast.budget_exhaustion_date)} />
                    ) : null}
                    {forecast.cached ? <p className="font-mono text-xs text-on-surface-variant">Served from cache (10 min TTL).</p> : null}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <BrutalBadge tone="muted">INSUFFICIENT_DATA</BrutalBadge>
                    <p className="text-sm text-on-surface-variant">{forecast.reason}</p>
                    <StatRow label="Basis buckets" value={String(forecast.basis_buckets)} />
                  </div>
                )
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Forecast" title="Daily spend basis">
            <p className="mb-3 text-xs text-on-surface-variant">Actual daily buckets the forecast baseline is derived from.</p>
            <PanelBody loading={loading} error={bucketsError} onRetry={() => void loadAll()} emptyTitle="No buckets" emptyDescription="Daily aggregations appear once the aggregation worker has run.">
              {buckets ? <TrendBars buckets={buckets} /> : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "anomalies" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Anomaly" title="Detected anomalies">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Severity" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} options={[{ value: "ALL", label: "All severities" }, ...ANOMALY_SEVERITIES.map((s) => ({ value: s, label: s }))]} />
              </div>
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} options={["ALL", "OPEN", "ACKNOWLEDGED", "RESOLVED"].map((s) => ({ value: s, label: s }))} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
            </div>
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Detection runs server-side only. There is no acknowledge/resolve endpoint — status here is informational.</p>
            <PanelBody loading={loading} error={anomaliesError} onRetry={() => void loadAll()} emptyTitle="No anomalies" emptyDescription="Anomalies are detected per dimension-day with z-score ≥ 2.0.">
              {anomalies && anomalies.length > 0 ? (
                <ul className="space-y-2">
                  {anomalies.map((a) => (
                    <li key={a.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedAnomalyId(a.id)}
                        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${a.id === selectedAnomalyId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-on-surface">{a.dimension_key}={a.dimension_value || "(empty)"}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">{formatDateTime(a.bucket_start)} · z={a.deviation}</span>
                        </span>
                        <BrutalBadge tone={severityTone(a.severity)}>{a.severity}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Anomaly" title="Evidence">
              <PanelBody loading={loading} error={anomaliesError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select an anomaly to inspect its baseline, observed spend and evidence window.">
                {selectedAnomaly ? (
                  <div className="space-y-3">
                    <StatRow label="Dimension" value={`${selectedAnomaly.dimension_key}=${selectedAnomaly.dimension_value || "(empty)"}`} />
                    <StatRow label="Severity" value={selectedAnomaly.severity} />
                    <StatRow label="Status" value={selectedAnomaly.status} />
                    <StatRow label="Bucket" value={formatDateTime(selectedAnomaly.bucket_start)} />
                    <StatRow label="Baseline" value={formatCents(selectedAnomaly.baseline_cents)} />
                    <StatRow label="Observed" value={formatCents(selectedAnomaly.observed_cents)} />
                    <StatRow label="Deviation (z)" value={String(selectedAnomaly.deviation)} />
                    <StatRow label="Confidence" value={String(selectedAnomaly.confidence)} />
                    {(() => {
                      const ev = selectedAnomaly.evidence as { window_days?: number; history?: number[] };
                      if (!ev || typeof ev !== "object") return null;
                      return (
                        <>
                          {ev.window_days !== undefined ? <StatRow label="Window days" value={String(ev.window_days)} /> : null}
                          {Array.isArray(ev.history) ? <StatRow label="History (cents)" value={ev.history.join(", ")} /> : null}
                        </>
                      );
                    })()}
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "pricing" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Governance" title="Pricing versions">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalInput label="Provider" value={pricingProviderFilter} onChange={(e) => setPricingProviderFilter(e.target.value)} />
              </div>
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Status" value={pricingStatusFilter} onChange={(e) => setPricingStatusFilter(e.target.value)} options={[{ value: "ALL", label: "All" }, { value: "ACTIVE", label: "ACTIVE" }, { value: "DEPRECATED", label: "DEPRECATED" }]} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              {canAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "pricing-create" })}>New version</BrutalButton>
              ) : null}
            </div>
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Versions are immutable history — new prices create new versions; only ACTIVE ↔ DEPRECATED transitions are allowed.</p>
            <PanelBody loading={loading} error={pricingError} onRetry={() => void loadAll()} emptyTitle="No pricing versions" emptyDescription="Without effective pricing, records are stored as UNPRICED with zero amount — never invented.">
              {pricing && pricing.length > 0 ? (
                <ul className="space-y-2">
                  {pricing.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedPricingId(p.id)}
                        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${p.id === selectedPricingId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-on-surface">{p.provider}{p.model ? `/${p.model}` : ""} · v{p.version}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">in {p.input_price_cents_per_m}c/M · out {p.output_price_cents_per_m}c/M · {p.currency}</span>
                        </span>
                        <BrutalBadge tone={p.status === "ACTIVE" ? "yellow" : "muted"}>{p.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Governance" title="Version detail">
              <PanelBody loading={loading} error={pricingError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select a pricing version to inspect its rates and effective window.">
                {(() => {
                  const row = pricing?.find((x) => x.id === selectedPricingId) ?? null;
                  if (!row) return null;
                  return (
                    <div className="space-y-3">
                      <StatRow label="Provider" value={row.provider} />
                      <StatRow label="Model" value={row.model || "—"} />
                      <StatRow label="Resource" value={row.resource || "—"} />
                      <StatRow label="Unit" value={row.unit} />
                      <StatRow label="Input / M" value={`${row.input_price_cents_per_m}c`} />
                      <StatRow label="Output / M" value={`${row.output_price_cents_per_m}c`} />
                      <StatRow label="Request" value={`${row.request_price_cents}c`} />
                      <StatRow label="Currency" value={row.currency} />
                      <StatRow label="Effective from" value={formatDateTime(row.effective_from)} />
                      <StatRow label="Effective until" value={formatDateTime(row.effective_until)} />
                      <StatRow label="Source" value={row.source} />
                      <StatRow label="Operator" value={row.operator || "—"} />
                      {row.reason ? <StatRow label="Reason" value={row.reason} /> : null}
                      {canAdmin && row.status === "ACTIVE" ? (
                        <div className="pt-1">
                          <BrutalButton variant="ghost" size="sm" onClick={() => setModal({ kind: "pricing-deprecate", pricing: row })}>Deprecate</BrutalButton>
                        </div>
                      ) : null}
                    </div>
                  );
                })()}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "governance" ? (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            <BrutalCard eyebrow="Governance" title="Policies">
              <div className="mb-3 flex gap-2">
                {canAdmin ? (
                  <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "policy-create" })}>New policy</BrutalButton>
                ) : null}
              </div>
              <PanelBody loading={loading} error={policiesError} onRetry={() => void loadAll()} emptyTitle="No policies" emptyDescription="Policies gate expensive operations: ALLOW, WARN, REQUIRE_APPROVAL or BLOCK.">
                {policies && policies.length > 0 ? (
                  <ul className="space-y-2">
                    {policies.map((p) => (
                      <li key={p.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedPolicyId(p.id)}
                          className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${p.id === selectedPolicyId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-bold text-on-surface">{p.name}</span>
                            <span className="block truncate font-mono text-xs text-on-surface-variant">{p.provider || "*"} · {p.operation || "*"} · cap {p.max_estimated_cents ?? "—"}</span>
                          </span>
                          <BrutalBadge tone={p.enabled ? (p.action === "block" ? "error" : "yellow") : "muted"}>{p.enabled ? p.action : "disabled"}</BrutalBadge>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Governance" title="Policy detail">
              <PanelBody loading={loading} error={policiesError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select a policy to inspect or edit it.">
                {(() => {
                  const policy = policies?.find((x) => x.id === selectedPolicyId) ?? null;
                  if (!policy) return null;
                  return (
                    <div className="space-y-3">
                      <StatRow label="Name" value={policy.name} />
                      <StatRow label="Action" value={policy.action} />
                      <StatRow label="Workspace" value={policy.workspace || "—"} />
                      <StatRow label="Project" value={policy.project || "—"} />
                      <StatRow label="Model" value={policy.model || "—"} />
                      <StatRow label="Provider" value={policy.provider || "—"} />
                      <StatRow label="Operation" value={policy.operation || "—"} />
                      <StatRow label="Max cents" value={policy.max_estimated_cents !== null ? String(policy.max_estimated_cents) : "—"} />
                      <StatRow label="Owner" value={policy.owner || "—"} />
                      {canAdmin ? (
                        <div className="pt-1">
                          <BrutalButton variant="ghost" size="sm" onClick={() => {
                            setDraft((d) => ({
                              ...d,
                              policy_name: policy.name,
                              policy_workspace: policy.workspace,
                              policy_project: policy.project,
                              policy_model: policy.model,
                              policy_provider: policy.provider,
                              policy_operation: policy.operation,
                              policy_max_cents: policy.max_estimated_cents !== null ? String(policy.max_estimated_cents) : "",
                              policy_action: policy.action,
                              policy_owner: policy.owner,
                              policy_enabled: policy.enabled ? "true" : "false",
                            }));
                            setModal({ kind: "policy-update", policy });
                          }}>Edit policy</BrutalButton>
                        </div>
                      ) : null}
                    </div>
                  );
                })()}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Governance" title="Gate tester">
              <p className="mb-3 text-xs text-on-surface-variant">Dry-run the expensive-operation gate. The server recomputes cost from pricing and takes the maximum — client estimates are never trusted alone. REQUIRE_APPROVAL reuses the Zero Trust JIT flow.</p>
              <div className="space-y-2">
                <BrutalInput label="Operation" value={gateDraft.operation} onChange={(e) => setGateDraft((d) => ({ ...d, operation: e.target.value }))} placeholder="model.train" />
                <div className="grid grid-cols-2 gap-2">
                  <BrutalInput label="Provider" value={gateDraft.provider} onChange={(e) => setGateDraft((d) => ({ ...d, provider: e.target.value }))} />
                  <BrutalInput label="Model" value={gateDraft.model} onChange={(e) => setGateDraft((d) => ({ ...d, model: e.target.value }))} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <BrutalInput label="Est. cents" value={gateDraft.estimated_cents} onChange={(e) => setGateDraft((d) => ({ ...d, estimated_cents: e.target.value }))} placeholder="5000" />
                  <BrutalInput label="Reason" value={gateDraft.reason} onChange={(e) => setGateDraft((d) => ({ ...d, reason: e.target.value }))} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void handleGateEvaluate()} disabled={gateRunning}>
                  {gateRunning ? "Evaluating…" : "Evaluate gate"}
                </BrutalButton>
              </div>
              {gateError ? <p className="mt-3 text-xs text-error">{gateError}</p> : null}
              {gateResult ? (
                <div className="mt-3 border-t border-outline pt-2">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Decision</span>
                    <BrutalBadge tone={gateResult.allowed ? "yellow" : "error"}>{gateResult.decision}</BrutalBadge>
                  </div>
                  <StatRow label="Reason" value={gateResult.reason} />
                  <StatRow label="Effective est." value={formatCents(gateResult.estimated_cents)} />
                  {gateResult.approval_id ? <StatRow label="Approval" value={gateResult.approval_id} /> : null}
                  {gateResult.policy_id ? <StatRow label="Policy" value={gateResult.policy_id} /> : null}
                </div>
              ) : null}
            </BrutalCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <BrutalCard eyebrow="Governance" title="Allocations">
              <p className="mb-2 text-xs text-on-surface-variant">Attribution of a cost record to target dimensions. Select the record in the Costs tab, then record a split here.</p>
              {canAdmin ? (
                <div className="mb-2">
                  <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "allocation-create" })} disabled={!selectedCostId}>Allocate selected</BrutalButton>
                </div>
              ) : null}
              <PanelBody loading={loading} error={allocationsError} onRetry={() => void loadAll()} emptyTitle="No allocations" emptyDescription="Allocated cents trace back to a cost record with provenance.">
                {allocations && allocations.length > 0 ? (
                  <ul className="space-y-2">
                    {allocations.slice(0, 8).map((a) => (
                      <li key={a.id} className="border border-outline-variant bg-surface px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate font-mono text-xs text-on-surface">{a.allocation_key} · share {a.share}</span>
                          <span className="font-mono text-xs text-on-surface">{formatCents(a.amount_cents)}</span>
                        </div>
                        <StatRow label="Target" value={[a.target_workspace, a.target_project, a.target_service].filter(Boolean).join(" / ") || "—"} />
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Governance" title="Reports">
              <p className="mb-2 text-xs text-on-surface-variant">Showback is informational attribution from cost records; chargeback traces every cent to an allocation row. No double counting.</p>
              <div className="mb-3 flex flex-wrap items-end gap-2">
                <div className="min-w-28 flex-1">
                  <BrutalSelect label="Saved type" value={reportTypeFilter} onChange={(e) => setReportTypeFilter(e.target.value)} options={[{ value: "ALL", label: "All types" }, ...REPORT_TYPES.map((t) => ({ value: t, label: t }))]} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              </div>
              <div className="mb-3 space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <BrutalSelect label="Type" value={reportDraft.report_type} onChange={(e) => setReportDraft((d) => ({ ...d, report_type: e.target.value }))} options={REPORT_TYPES.map((t) => ({ value: t, label: t }))} />
                  <BrutalSelect label="Group by" value={reportDraft.group_by} onChange={(e) => setReportDraft((d) => ({ ...d, group_by: e.target.value }))} options={GROUP_KEYS.map((g) => ({ value: g, label: g }))} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <BrutalInput label="Start (ISO)" value={reportDraft.start} onChange={(e) => setReportDraft((d) => ({ ...d, start: e.target.value }))} />
                  <BrutalInput label="End (ISO)" value={reportDraft.end} onChange={(e) => setReportDraft((d) => ({ ...d, end: e.target.value }))} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void handleReportGenerate()} disabled={reportRunning}>
                  {reportRunning ? "Generating…" : "Generate report"}
                </BrutalButton>
              </div>
              <PanelBody loading={loading} error={reportsError} onRetry={() => void loadAll()} emptyTitle="No reports" emptyDescription="Generated reports persist with their scope and provenance.">
                {reports && reports.length > 0 ? (
                  <ul className="space-y-2">
                    {reports.slice(0, 8).map((r) => (
                      <li key={r.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedReportId(r.id)}
                          className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${r.id === selectedReportId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-bold text-on-surface">{r.report_type} · {formatCents(r.total_cents)}</span>
                            <span className="block truncate font-mono text-xs text-on-surface-variant">{formatDateTime(r.period_start)} → {formatDateTime(r.period_end)}</span>
                          </span>
                          <BrutalBadge tone="default">{r.lines.length} groups</BrutalBadge>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Governance" title="Report detail">
              <PanelBody loading={loading} error={reportsError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select a report to inspect its lines and provenance.">
                {(() => {
                  const report = reports?.find((x) => x.id === selectedReportId) ?? null;
                  if (!report) return null;
                  return (
                    <div className="space-y-3">
                      <StatRow label="Type" value={report.report_type} />
                      <StatRow label="Total" value={formatCents(report.total_cents)} />
                      <div>
                        <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Lines</p>
                        {report.lines.length > 0 ? (
                          <ul className="space-y-1">
                            {report.lines.slice(0, 10).map((line) => (
                              <li key={line.group} className="flex items-center justify-between gap-2 border border-outline-variant bg-surface px-2 py-1">
                                <span className="truncate font-mono text-xs text-on-surface">{line.group}</span>
                                <span className="font-mono text-xs text-on-surface">{formatCents(line.total_cents)}</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="font-mono text-xs text-on-surface-variant">No lines.</p>
                        )}
                      </div>
                      {Object.entries(report.provenance ?? {}).map(([k, v]) => (
                        <StatRow key={k} label={k.replace(/_/g, " ")} value={String(v)} />
                      ))}
                    </div>
                  );
                })()}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "intelligence" ? (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <BrutalCard eyebrow="Intelligence" title="Model comparison">
              <p className="mb-2 text-xs text-on-surface-variant">Read-only comparison from recorded costs and effective pricing. FinOps never switches models — selection stays governed by AI Gateway policy.</p>
              <div className="mb-3 flex flex-wrap items-end gap-2">
                <div className="min-w-32 flex-1">
                  <BrutalInput label="Provider" value={compareProvider} onChange={(e) => setCompareProvider(e.target.value)} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              </div>
              <PanelBody loading={loading} error={comparisonError} onRetry={() => void loadAll()} emptyTitle="No comparison" emptyDescription="Comparisons appear once cost records exist for the period.">
                {comparison && comparison.items.length > 0 ? (
                  <div className="space-y-2">
                    {comparison.cached ? <p className="font-mono text-xs text-on-surface-variant">Served from cache (10 min TTL).</p> : null}
                    <BrutalTable<{ provider: string; model: string; spend_cents: number; requests: number; tokens: number; cost_per_request_cents: number | null; avg_latency_ms: number | null }>
                      columns={[
                        { key: "model", header: "Provider / Model", render: (r) => <span className="font-mono text-xs">{r.provider || "—"} / {r.model || "—"}</span> },
                        { key: "spend", header: "Spend", render: (r) => <span className="font-mono text-xs">{formatCents(r.spend_cents)}</span> },
                        { key: "cpr", header: "Cost / req", render: (r) => <span className="font-mono text-xs">{r.cost_per_request_cents !== null ? formatCents(r.cost_per_request_cents) : "—"}</span> },
                        { key: "lat", header: "Avg ms", render: (r) => <span className="font-mono text-xs">{r.avg_latency_ms ?? "—"}</span> },
                      ]}
                      rows={comparison.items}
                    />
                    <p className="font-mono text-xs text-on-surface-variant">{comparison.note}</p>
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Intelligence" title="Recommendations">
              <div className="mb-3 flex flex-wrap items-end gap-2">
                <div className="min-w-28 flex-1">
                  <BrutalSelect label="Type" value={recTypeFilter} onChange={(e) => setRecTypeFilter(e.target.value)} options={[{ value: "ALL", label: "All types" }, { value: "cheaper_model", label: "cheaper_model" }, { value: "model_concentration", label: "model_concentration" }, { value: "batch_requests", label: "batch_requests" }, { value: "pricing_coverage", label: "pricing_coverage" }]} />
                </div>
                <div className="min-w-28 flex-1">
                  <BrutalSelect label="Status" value={recStatusFilter} onChange={(e) => setRecStatusFilter(e.target.value)} options={["ALL", "OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"].map((s) => ({ value: s, label: s }))} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
                {canAdmin ? (
                  <BrutalButton variant="primary" size="sm" onClick={() => void handleRecommendationsGenerate()} disabled={generatingRecs}>
                    {generatingRecs ? "Generating…" : "Generate"}
                  </BrutalButton>
                ) : null}
              </div>
              <p className="mb-2 font-mono text-xs text-on-surface-variant">Every rule cites evidence. Savings that cannot be derived reliably are reported as UNKNOWN — never fabricated.</p>
              <PanelBody loading={loading} error={recommendationsError} onRetry={() => void loadAll()} emptyTitle="No recommendations" emptyDescription="Generate evidence-based recommendations from the last 30 days of records.">
                {recommendations && recommendations.length > 0 ? (
                  <ul className="space-y-2">
                    {recommendations.map((r) => (
                      <li key={r.id} className="border border-outline-variant bg-surface px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-bold text-on-surface">{r.title}</span>
                          <BrutalBadge tone={r.savings_known ? "yellow" : "muted"}>{r.savings_known ? formatCents(typeof r.savings === "number" ? r.savings : 0) : "UNKNOWN savings"}</BrutalBadge>
                        </div>
                        <StatRow label="Type" value={r.rec_type} />
                        <StatRow label="Confidence" value={String(r.confidence)} />
                        <StatRow label="Risk" value={r.risk} />
                        <StatRow label="Status" value={r.status} />
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <BrutalCard eyebrow="Intelligence" title="Anomaly detection">
              <p className="mb-2 text-xs text-on-surface-variant">Server-side z-score detection over the lookback window (7–60 days). Detections are deduplicated per dimension-day — no alert storms. Admin only.</p>
              {canAdmin ? (
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-32">
                    <BrutalInput label="Lookback days" value={lookbackDays} onChange={(e) => setLookbackDays(e.target.value)} />
                  </div>
                  <BrutalButton variant="ghost" size="sm" onClick={() => void handleAnomalyDetect()} disabled={detecting}>
                    {detecting ? "Detecting…" : "Run detection"}
                  </BrutalButton>
                </div>
              ) : (
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Detection requires admin</p>
              )}
            </BrutalCard>

            <BrutalCard eyebrow="Intelligence" title="Aggregation run">
              <p className="mb-2 text-xs text-on-surface-variant">Materializes spend buckets that power the trend views. Admin only.</p>
              {canAdmin ? (
                <div className="space-y-2">
                  <BrutalSelect label="Granularity" value={aggDraft.granularity} onChange={(e) => setAggDraft((d) => ({ ...d, granularity: e.target.value }))} options={["hour", "day", "week", "month"].map((g) => ({ value: g, label: g }))} />
                  <div className="grid grid-cols-2 gap-2">
                    <BrutalInput label="Start (ISO)" value={aggDraft.start} onChange={(e) => setAggDraft((d) => ({ ...d, start: e.target.value }))} />
                    <BrutalInput label="End (ISO)" value={aggDraft.end} onChange={(e) => setAggDraft((d) => ({ ...d, end: e.target.value }))} />
                  </div>
                  <BrutalButton variant="ghost" size="sm" onClick={() => void handleAggregationRun()} disabled={aggRunning}>
                    {aggRunning ? "Running…" : "Run aggregation"}
                  </BrutalButton>
                </div>
              ) : (
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Aggregation runs require admin</p>
              )}
              {aggError ? <p className="mt-2 text-xs text-error">{aggError}</p> : null}
              {aggResult ? (
                <div className="mt-2 border-t border-outline pt-2">
                  <StatRow label="Buckets" value={String(aggResult.buckets)} />
                  <StatRow label="Scanned" value={String(aggResult.records_scanned)} />
                  <StatRow label="Granularity" value={aggResult.granularity} />
                </div>
              ) : null}
            </BrutalCard>

            <BrutalCard eyebrow="Intelligence" title="Ask AI">
              <p className="mb-3 text-xs text-on-surface-variant">Open the AI workspace to discuss this tenant&apos;s spend. No financial payload is attached — bring only the figures you choose to quote.</p>
              <BrutalButton variant="yellow" size="sm" href="/ai">Ask AI about spend</BrutalButton>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      <BrutalModal open={modal?.kind === "budget-create"} title="New budget" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleBudgetCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} placeholder="prod-monthly" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Amount (cents)" value={draft.amount} onChange={(e) => setDraft((d) => ({ ...d, amount: e.target.value }))} placeholder="100000" />
            <BrutalInput label="Currency" value={draft.currency} onChange={(e) => setDraft((d) => ({ ...d, currency: e.target.value }))} placeholder="USD" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Period" value={draft.period} onChange={(e) => setDraft((d) => ({ ...d, period: e.target.value }))} options={BUDGET_PERIODS.map((p) => ({ value: p, label: p }))} />
            <BrutalSelect label="Enforcement" value={draft.enforcement} onChange={(e) => setDraft((d) => ({ ...d, enforcement: e.target.value }))} options={ENFORCEMENTS.map((x) => ({ value: x, label: x }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Warning threshold (0–1)" value={draft.warning_threshold} onChange={(e) => setDraft((d) => ({ ...d, warning_threshold: e.target.value }))} />
            <BrutalInput label="Hard limit (0–1+)" value={draft.hard_limit_threshold} onChange={(e) => setDraft((d) => ({ ...d, hard_limit_threshold: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Scope type" value={draft.scope_type} onChange={(e) => setDraft((d) => ({ ...d, scope_type: e.target.value }))} options={["tenant", "provider", "model", "workspace", "project", "service", "environment"].map((s) => ({ value: s, label: s }))} />
            <BrutalInput label="Scope value" value={draft.scope_value} onChange={(e) => setDraft((d) => ({ ...d, scope_value: e.target.value }))} placeholder="empty = whole tenant" />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <BrutalInput label="Provider" value={draft.provider} onChange={(e) => setDraft((d) => ({ ...d, provider: e.target.value }))} />
            <BrutalInput label="Model" value={draft.model} onChange={(e) => setDraft((d) => ({ ...d, model: e.target.value }))} />
            <BrutalInput label="Environment" value={draft.environment} onChange={(e) => setDraft((d) => ({ ...d, environment: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
            <BrutalInput label="Approval policy" value={draft.approval_policy} onChange={(e) => setDraft((d) => ({ ...d, approval_policy: e.target.value }))} placeholder="none" />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "budget-update"} title="Update budget?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleBudgetUpdate()} disabled={submitting}>{submitting ? "Saving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Changes apply to a financial governance object and are audited server-side. Omitted fields keep their current values.</p>
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          <BrutalInput label="Amount (cents, empty = keep)" value={draft.amount} onChange={(e) => setDraft((d) => ({ ...d, amount: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Warning threshold" value={draft.warning_threshold} onChange={(e) => setDraft((d) => ({ ...d, warning_threshold: e.target.value }))} />
            <BrutalInput label="Hard limit" value={draft.hard_limit_threshold} onChange={(e) => setDraft((d) => ({ ...d, hard_limit_threshold: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Enforcement" value={draft.enforcement} onChange={(e) => setDraft((d) => ({ ...d, enforcement: e.target.value }))} options={ENFORCEMENTS.map((x) => ({ value: x, label: x }))} />
            <BrutalSelect label="Status" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))} options={BUDGET_STATUSES.map((s) => ({ value: s, label: s }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Enabled" value={draft.enabled} onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.value }))} options={[{ value: "true", label: "enabled" }, { value: "false", label: "disabled" }]} />
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
          </div>
          <BrutalInput label="Approval policy" value={draft.approval_policy} onChange={(e) => setDraft((d) => ({ ...d, approval_policy: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "pricing-create"} title="New pricing version" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePricingCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider" value={draft.pricing_provider} onChange={(e) => setDraft((d) => ({ ...d, pricing_provider: e.target.value }))} placeholder="acme" />
            <BrutalInput label="Model" value={draft.pricing_model} onChange={(e) => setDraft((d) => ({ ...d, pricing_model: e.target.value }))} placeholder="gpt-x" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Resource" value={draft.pricing_resource} onChange={(e) => setDraft((d) => ({ ...d, pricing_resource: e.target.value }))} />
            <BrutalInput label="Unit" value={draft.pricing_unit} onChange={(e) => setDraft((d) => ({ ...d, pricing_unit: e.target.value }))} placeholder="tokens" />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <BrutalInput label="Input c/M" value={draft.pricing_input} onChange={(e) => setDraft((d) => ({ ...d, pricing_input: e.target.value }))} placeholder="50" />
            <BrutalInput label="Output c/M" value={draft.pricing_output} onChange={(e) => setDraft((d) => ({ ...d, pricing_output: e.target.value }))} placeholder="150" />
            <BrutalInput label="Request c" value={draft.pricing_request} onChange={(e) => setDraft((d) => ({ ...d, pricing_request: e.target.value }))} placeholder="0" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Currency" value={draft.pricing_currency} onChange={(e) => setDraft((d) => ({ ...d, pricing_currency: e.target.value }))} />
            <BrutalInput label="Reason" value={draft.pricing_reason} onChange={(e) => setDraft((d) => ({ ...d, pricing_reason: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Effective from (ISO)" value={draft.pricing_effective_from} onChange={(e) => setDraft((d) => ({ ...d, pricing_effective_from: e.target.value }))} />
            <BrutalInput label="Effective until (ISO)" value={draft.pricing_effective_until} onChange={(e) => setDraft((d) => ({ ...d, pricing_effective_until: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "pricing-deprecate"} title="Deprecate pricing version?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePricingDeprecate()} disabled={submitting}>{submitting ? "Deprecating…" : "Confirm"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">The version becomes DEPRECATED and stops pricing new usage. Historical records keep the version that was effective for them.</p>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "allocation-create"} title="Allocate cost record" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleAllocationCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record split"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <StatRow label="Cost record" value={selectedCostId ?? "—"} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Allocation key" value={draft.allocation_key} onChange={(e) => setDraft((d) => ({ ...d, allocation_key: e.target.value }))} placeholder="ws1-share" />
            <BrutalInput label="Share (0–1]" value={draft.allocation_share} onChange={(e) => setDraft((d) => ({ ...d, allocation_share: e.target.value }))} placeholder="1.0" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Target workspace" value={draft.allocation_workspace} onChange={(e) => setDraft((d) => ({ ...d, allocation_workspace: e.target.value }))} />
            <BrutalInput label="Target project" value={draft.allocation_project} onChange={(e) => setDraft((d) => ({ ...d, allocation_project: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Target service" value={draft.allocation_service} onChange={(e) => setDraft((d) => ({ ...d, allocation_service: e.target.value }))} />
            <BrutalInput label="Target environment" value={draft.allocation_environment} onChange={(e) => setDraft((d) => ({ ...d, allocation_environment: e.target.value }))} />
          </div>
          <BrutalInput label="Basis" value={draft.allocation_basis} onChange={(e) => setDraft((d) => ({ ...d, allocation_basis: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "policy-create"} title="New cost policy" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePolicyCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.policy_name} onChange={(e) => setDraft((d) => ({ ...d, policy_name: e.target.value }))} placeholder="cap-training-spend" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.policy_workspace} onChange={(e) => setDraft((d) => ({ ...d, policy_workspace: e.target.value }))} />
            <BrutalInput label="Project" value={draft.policy_project} onChange={(e) => setDraft((d) => ({ ...d, policy_project: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider" value={draft.policy_provider} onChange={(e) => setDraft((d) => ({ ...d, policy_provider: e.target.value }))} />
            <BrutalInput label="Model" value={draft.policy_model} onChange={(e) => setDraft((d) => ({ ...d, policy_model: e.target.value }))} />
          </div>
          <BrutalInput label="Operation" value={draft.policy_operation} onChange={(e) => setDraft((d) => ({ ...d, policy_operation: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Action" value={draft.policy_action} onChange={(e) => setDraft((d) => ({ ...d, policy_action: e.target.value }))} options={POLICY_ACTIONS.map((a) => ({ value: a, label: a }))} />
            <BrutalInput label="Max est. cents" value={draft.policy_max_cents} onChange={(e) => setDraft((d) => ({ ...d, policy_max_cents: e.target.value }))} placeholder="10000" />
          </div>
          <BrutalInput label="Owner" value={draft.policy_owner} onChange={(e) => setDraft((d) => ({ ...d, policy_owner: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "policy-update"} title="Edit policy" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePolicyUpdate()} disabled={submitting}>{submitting ? "Saving…" : "Save"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.policy_name} onChange={(e) => setDraft((d) => ({ ...d, policy_name: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Action" value={draft.policy_action} onChange={(e) => setDraft((d) => ({ ...d, policy_action: e.target.value }))} options={POLICY_ACTIONS.map((a) => ({ value: a, label: a }))} />
            <BrutalSelect label="Enabled" value={draft.policy_enabled} onChange={(e) => setDraft((d) => ({ ...d, policy_enabled: e.target.value }))} options={[{ value: "true", label: "enabled" }, { value: "false", label: "disabled" }]} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.policy_workspace} onChange={(e) => setDraft((d) => ({ ...d, policy_workspace: e.target.value }))} />
            <BrutalInput label="Project" value={draft.policy_project} onChange={(e) => setDraft((d) => ({ ...d, policy_project: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider" value={draft.policy_provider} onChange={(e) => setDraft((d) => ({ ...d, policy_provider: e.target.value }))} />
            <BrutalInput label="Model" value={draft.policy_model} onChange={(e) => setDraft((d) => ({ ...d, policy_model: e.target.value }))} />
          </div>
          <BrutalInput label="Operation" value={draft.policy_operation} onChange={(e) => setDraft((d) => ({ ...d, policy_operation: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Max est. cents" value={draft.policy_max_cents} onChange={(e) => setDraft((d) => ({ ...d, policy_max_cents: e.target.value }))} />
            <BrutalInput label="Owner" value={draft.policy_owner} onChange={(e) => setDraft((d) => ({ ...d, policy_owner: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>
    </div>
  );
}
