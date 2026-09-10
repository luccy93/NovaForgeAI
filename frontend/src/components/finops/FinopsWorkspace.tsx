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
  BudgetEvaluation,
  CostAnomaly,
  CostsPage,
  FinOpsBudget,
  FinOpsCostRecord,
  ForecastResult,
  UsageSummary,
} from "@/types/finops";
import {
  ANOMALY_SEVERITIES,
  BUDGET_PERIODS,
  BUDGET_STATUSES,
  COST_BASES,
  ENFORCEMENTS,
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

type TabId = "overview" | "usage" | "costs" | "budgets" | "forecast" | "anomalies";

type PendingModal =
  | { kind: "budget-create" }
  | { kind: "budget-update"; budget: FinOpsBudget }
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
    ]);

    if (!controller.signal.aborted && seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, [costFilters, costOffset, budgetStatusFilter, horizonDays, severityFilter, statusFilter]);

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
      setSelectedCostId(null);
      setSelectedBudgetId(null);
      setSelectedAnomalyId(null);
      setCostOffset(0);
      setSummaryError(null);
      setCostsError(null);
      setBudgetsError(null);
      setBucketsError(null);
      setForecastError(null);
      setAnomaliesError(null);
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

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "usage", label: "Usage" },
    { id: "costs", label: "Costs" },
    { id: "budgets", label: "Budgets" },
    { id: "forecast", label: "Forecast" },
    { id: "anomalies", label: "Anomalies" },
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
    </div>
  );
}
