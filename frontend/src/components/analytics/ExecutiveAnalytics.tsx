"use client";

/* eslint-disable react-hooks/set-state-in-effect -- authoritative backend load and tenant/workspace switch reset */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalTable } from "@/components/ui/BrutalTable";
import {
  AnalyticsMetric,
  formatCentsUsd,
  formatDecimal,
  formatInt,
  formatRatioPercent,
  formatUsd,
} from "@/components/analytics/AnalyticsMetric";
import { AnalyticsTrend, type TrendDatum } from "@/components/analytics/AnalyticsTrend";
import type {
  AnalyticsAiBreakdown,
  AnalyticsAlertsSummary,
  AnalyticsBudgetsStatus,
  AnalyticsCostSummary,
  AnalyticsCostTrend,
  AnalyticsDashboardOverview,
  AnalyticsDashboardSnapshot,
  AnalyticsDora,
  AnalyticsMarketplaceSummary,
  AnalyticsMetricPoint,
  AnalyticsModelComparison,
  AnalyticsQualityIssues,
  AnalyticsRecommendations,
  AnalyticsSecuritySummary,
  AnalyticsSloBreaches,
  AnalyticsSloStatus,
  DatagovDashboard,
  EnterpriseIntegrationsMetrics,
  SecOpsRiskSnapshots,
  SecurityDashboardFull,
  SecurityFindingsSummary,
  SecurityRiskScore,
  SecurityRiskSummary,
  SreDashboard,
  SreReliabilityScore,
} from "@/types/analytics";
import type { AdminOverview } from "@/types/admin";
import type { AiUsagePage, WorkflowHealth as WorkflowHealthLegacy } from "@/types/api";
import type { SreAnalytics, AiopsStatus, ObservabilityAnomalies } from "@/types/observability";
import type { ObservabilityDashboard } from "@/types/api";
import type { SecOpsDashboard, SecOpsRiskSnapshot } from "@/types/security";
import type {
  GovernanceDriftResponse,
  GovernanceEvidenceCoverage,
  GovernancePosture,
  GovernancePostureHistoryResponse,
  GovernanceTrendsResponse,
} from "@/types/governance";
import type { UsageSummary, ForecastResult, ModelComparison, Paginated, AggregationBucket, CostAnomaly } from "@/types/finops";
import { isForecastReady } from "@/types/finops";
import type { KnowledgeFreshnessStats, KnowledgeUsageStats } from "@/types/knowledge";
import type { WorkflowAnomaly, WorkflowHealthSummary, WorkflowListItem } from "@/types/workflows";
import type { MLModel, MLRisk, MLProvider } from "@/types/ml";
import type { DatasetListItem, DataPipelineListItem } from "@/types/data-platform";
import type { IntegrationItem } from "@/types/api";

const LOGIN_PATH = "/auth/login";

type RangeId = "24h" | "7d" | "30d" | "90d";

const RANGES: Array<{ id: RangeId; label: string; days: number; hours: number }> = [
  { id: "24h", label: "24H", days: 1, hours: 24 },
  { id: "7d", label: "7D", days: 7, hours: 168 },
  { id: "30d", label: "30D", days: 30, hours: 720 },
  { id: "90d", label: "90D", days: 90, hours: 2160 },
];

function windowIso(days: number): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end.getTime() - Math.max(days, 1) * 86400 * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string | null {
  if (typeof value === "string" && value.trim() !== "") return value;
  return null;
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline/60 py-1.5 last:border-b-0">
      <span className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface" title={value}>
        {value}
      </span>
    </div>
  );
}

/** Verbatim renderer for heterogeneous backend objects: primitives only. */
function PrimitiveRows({ data }: { data: unknown }) {
  if (!data || typeof data !== "object") {
    return (
      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">No values reported.</p>
    );
  }
  const entries = Object.entries(data).filter(
    ([key, value]) =>
      !key.startsWith("_") &&
      (typeof value === "string" || typeof value === "number" || typeof value === "boolean") &&
      String(value).trim() !== "",
  );
  if (entries.length === 0) {
    return (
      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">No values reported.</p>
    );
  }
  return (
    <div>
      {entries.map(([key, value]) => (
        <StatRow
          key={key}
          label={key.replace(/_/g, " ")}
          value={typeof value === "boolean" ? (value ? "yes" : "no") : String(value)}
        />
      ))}
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

type ScopeKind = "tenant" | "default" | "default-sensitive" | "global";

function ScopeBadge({ scope }: { scope: ScopeKind }) {
  if (scope === "tenant") {
    return (
      <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
        Tenant-scoped
      </span>
    );
  }
  if (scope === "global") {
    return (
      <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
        Backend scope: global — not tenant-filtered
      </span>
    );
  }
  if (scope === "default-sensitive") {
    return (
      <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
        Not tenant-scoped — API authorization required
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
      Backend scope: default / unauthenticated
    </span>
  );
}

function DomainCard({
  eyebrow,
  title,
  source,
  scope,
  linkHref,
  linkLabel,
  loading,
  error,
  onRetry,
  emptyTitle,
  emptyDescription,
  children,
}: {
  eyebrow: string;
  title: string;
  source: string;
  scope: ScopeKind;
  linkHref: string;
  linkLabel: string;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  emptyTitle: string;
  emptyDescription?: string;
  children: ReactNode;
}) {
  return (
    <BrutalCard
      eyebrow={eyebrow}
      title={title}
      actions={
        <div className="flex flex-wrap gap-2">
          <BrutalButton variant="ghost" size="sm" href={linkHref}>
            {linkLabel}
          </BrutalButton>
          <BrutalButton variant="ghost" size="sm" href="/ai">
            Ask AI
          </BrutalButton>
        </div>
      }
    >
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
        Source: {source}
      </p>
      <div className="mb-4">
        <ScopeBadge scope={scope} />
      </div>
      <PanelBody
        loading={loading}
        error={error}
        onRetry={onRetry}
        emptyTitle={emptyTitle}
        emptyDescription={emptyDescription}
      >
        {children}
      </PanelBody>
    </BrutalCard>
  );
}

interface MetricSeries {
  name: string;
  points: AnalyticsMetricPoint[];
}

interface SloRow {
  service: string;
  total_measurements?: number;
  compliant?: number;
  compliance_rate?: number;
}

export function ExecutiveAnalytics() {
  const [range, setRange] = useState<RangeId>("30d");
  const [loading, setLoading] = useState(true);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);

  const [adminOverview, setAdminOverview] = useState<AdminOverview | null>(null);
  const [adminOverviewError, setAdminOverviewError] = useState<string | null>(null);
  const [overview, setOverview] = useState<AnalyticsDashboardOverview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<AnalyticsDashboardSnapshot | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [dora, setDora] = useState<AnalyticsDora | null>(null);
  const [doraError, setDoraError] = useState<string | null>(null);
  const [costs, setCosts] = useState<AnalyticsCostSummary | null>(null);
  const [costsError, setCostsError] = useState<string | null>(null);
  const [costTrend, setCostTrend] = useState<AnalyticsCostTrend | null>(null);
  const [costTrendError, setCostTrendError] = useState<string | null>(null);
  const [modelComparison, setModelComparison] = useState<AnalyticsModelComparison | null>(null);
  const [modelComparisonError, setModelComparisonError] = useState<string | null>(null);
  const [aiBreakdown, setAiBreakdown] = useState<AnalyticsAiBreakdown | null>(null);
  const [aiBreakdownError, setAiBreakdownError] = useState<string | null>(null);
  const [secDash, setSecDash] = useState<SecurityDashboardFull | null>(null);
  const [secDashError, setSecDashError] = useState<string | null>(null);
  const [analyticsSec, setAnalyticsSec] = useState<AnalyticsSecuritySummary | null>(null);
  const [analyticsSecError, setAnalyticsSecError] = useState<string | null>(null);
  const [secFindings, setSecFindings] = useState<SecurityFindingsSummary | null>(null);
  const [secFindingsError, setSecFindingsError] = useState<string | null>(null);
  const [secRisk, setSecRisk] = useState<SecurityRiskSummary | null>(null);
  const [secRiskError, setSecRiskError] = useState<string | null>(null);
  const [secScore, setSecScore] = useState<SecurityRiskScore | null>(null);
  const [secScoreError, setSecScoreError] = useState<string | null>(null);
  const [alertsSummary, setAlertsSummary] = useState<AnalyticsAlertsSummary | null>(null);
  const [alertsSummaryError, setAlertsSummaryError] = useState<string | null>(null);
  const [budgetsStatus, setBudgetsStatus] = useState<AnalyticsBudgetsStatus | null>(null);
  const [budgetsStatusError, setBudgetsStatusError] = useState<string | null>(null);
  const [sloStatus, setSloStatus] = useState<AnalyticsSloStatus | null>(null);
  const [sloStatusError, setSloStatusError] = useState<string | null>(null);
  const [sloBreaches, setSloBreaches] = useState<AnalyticsSloBreaches | null>(null);
  const [sloBreachesError, setSloBreachesError] = useState<string | null>(null);
  const [qualityIssues, setQualityIssues] = useState<AnalyticsQualityIssues | null>(null);
  const [qualityIssuesError, setQualityIssuesError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<AnalyticsRecommendations | null>(null);
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null);
  const [marketplace, setMarketplace] = useState<AnalyticsMarketplaceSummary | null>(null);
  const [marketplaceError, setMarketplaceError] = useState<string | null>(null);
  const [metricTrends, setMetricTrends] = useState<MetricSeries[] | null>(null);
  const [metricTrendsError, setMetricTrendsError] = useState<string | null>(null);

  const [secops, setSecops] = useState<SecOpsDashboard | null>(null);
  const [secopsError, setSecopsError] = useState<string | null>(null);
  const [secopsRisk, setSecopsRisk] = useState<SecOpsRiskSnapshot | null>(null);
  const [secopsRiskError, setSecopsRiskError] = useState<string | null>(null);
  const [riskSnapshots, setRiskSnapshots] = useState<SecOpsRiskSnapshots | null>(null);
  const [riskSnapshotsError, setRiskSnapshotsError] = useState<string | null>(null);
  const [sre, setSre] = useState<SreAnalytics | null>(null);
  const [sreError, setSreError] = useState<string | null>(null);
  const [sreDash, setSreDash] = useState<SreDashboard | null>(null);
  const [sreDashError, setSreDashError] = useState<string | null>(null);
  const [reliability, setReliability] = useState<SreReliabilityScore | null>(null);
  const [reliabilityError, setReliabilityError] = useState<string | null>(null);
  const [obsDash, setObsDash] = useState<ObservabilityDashboard | null>(null);
  const [obsDashError, setObsDashError] = useState<string | null>(null);
  const [anomalies, setAnomalies] = useState<ObservabilityAnomalies | null>(null);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);
  const [aiops, setAiops] = useState<AiopsStatus | null>(null);
  const [aiopsError, setAiopsError] = useState<string | null>(null);
  const [fatigue, setFatigue] = useState<Record<string, unknown> | null>(null);
  const [fatigueError, setFatigueError] = useState<string | null>(null);

  const [governance, setGovernance] = useState<GovernancePosture | null>(null);
  const [governanceError, setGovernanceError] = useState<string | null>(null);
  const [govTrends, setGovTrends] = useState<GovernanceTrendsResponse | null>(null);
  const [govTrendsError, setGovTrendsError] = useState<string | null>(null);
  const [govHistory, setGovHistory] = useState<GovernancePostureHistoryResponse | null>(null);
  const [govHistoryError, setGovHistoryError] = useState<string | null>(null);
  const [govEvidence, setGovEvidence] = useState<GovernanceEvidenceCoverage | null>(null);
  const [govEvidenceError, setGovEvidenceError] = useState<string | null>(null);
  const [govDrift, setGovDrift] = useState<GovernanceDriftResponse | null>(null);
  const [govDriftError, setGovDriftError] = useState<string | null>(null);
  const [datagov, setDatagov] = useState<DatagovDashboard | null>(null);
  const [datagovError, setDatagovError] = useState<string | null>(null);

  const [finopsUsage, setFinopsUsage] = useState<UsageSummary | null>(null);
  const [finopsUsageError, setFinopsUsageError] = useState<string | null>(null);
  const [finopsBuckets, setFinopsBuckets] = useState<Paginated<AggregationBucket> | null>(null);
  const [finopsBucketsError, setFinopsBucketsError] = useState<string | null>(null);
  const [finopsForecast, setFinopsForecast] = useState<ForecastResult | null>(null);
  const [finopsForecastError, setFinopsForecastError] = useState<string | null>(null);
  const [finopsAnomalies, setFinopsAnomalies] = useState<Paginated<CostAnomaly> | null>(null);
  const [finopsAnomaliesError, setFinopsAnomaliesError] = useState<string | null>(null);
  const [finopsModels, setFinopsModels] = useState<ModelComparison | null>(null);
  const [finopsModelsError, setFinopsModelsError] = useState<string | null>(null);

  const [knowledgeFresh, setKnowledgeFresh] = useState<KnowledgeFreshnessStats | null>(null);
  const [knowledgeFreshError, setKnowledgeFreshError] = useState<string | null>(null);
  const [knowledgeUsage, setKnowledgeUsage] = useState<KnowledgeUsageStats | null>(null);
  const [knowledgeUsageError, setKnowledgeUsageError] = useState<string | null>(null);
  const [workflowHealth, setWorkflowHealth] = useState<WorkflowHealthSummary | WorkflowHealthLegacy | null>(null);
  const [workflowHealthError, setWorkflowHealthError] = useState<string | null>(null);
  const [workflowAnomalies, setWorkflowAnomalies] = useState<{ items: WorkflowAnomaly[] } | null>(null);
  const [workflowAnomaliesError, setWorkflowAnomaliesError] = useState<string | null>(null);
  const [workflowsListed, setWorkflowsListed] = useState<{ items: WorkflowListItem[] } | null>(null);
  const [workflowsListedError, setWorkflowsListedError] = useState<string | null>(null);
  const [mlModels, setMlModels] = useState<MLModel[] | null>(null);
  const [mlModelsError, setMlModelsError] = useState<string | null>(null);
  const [mlRisks, setMlRisks] = useState<MLRisk[] | null>(null);
  const [mlRisksError, setMlRisksError] = useState<string | null>(null);
  const [mlProviders, setMlProviders] = useState<MLProvider[] | null>(null);
  const [mlProvidersError, setMlProvidersError] = useState<string | null>(null);
  const [aiUsage, setAiUsage] = useState<AiUsagePage | null>(null);
  const [aiUsageError, setAiUsageError] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<{ items: DatasetListItem[] } | null>(null);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [pipelines, setPipelines] = useState<{ items: DataPipelineListItem[] } | null>(null);
  const [pipelinesError, setPipelinesError] = useState<string | null>(null);
  const [integrations, setIntegrations] = useState<EnterpriseIntegrationsMetrics | null>(null);
  const [integrationsError, setIntegrationsError] = useState<string | null>(null);
  const [integrationsListed, setIntegrationsListed] = useState<{ items: IntegrationItem[]; total: number } | null>(null);
  const [integrationsListedError, setIntegrationsListedError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  const sessionExpired = useCallback(() => {
    useAuthStore.getState().markExpired();
    window.location.href = LOGIN_PATH;
  }, []);

  const clearAll = useCallback(() => {
    setAdminOverview(null);
    setAdminOverviewError(null);
    setOverview(null);
    setOverviewError(null);
    setSnapshot(null);
    setSnapshotError(null);
    setDora(null);
    setDoraError(null);
    setCosts(null);
    setCostsError(null);
    setCostTrend(null);
    setCostTrendError(null);
    setModelComparison(null);
    setModelComparisonError(null);
    setAiBreakdown(null);
    setAiBreakdownError(null);
    setSecDash(null);
    setSecDashError(null);
    setAnalyticsSec(null);
    setAnalyticsSecError(null);
    setSecFindings(null);
    setSecFindingsError(null);
    setSecRisk(null);
    setSecRiskError(null);
    setSecScore(null);
    setSecScoreError(null);
    setAlertsSummary(null);
    setAlertsSummaryError(null);
    setBudgetsStatus(null);
    setBudgetsStatusError(null);
    setSloStatus(null);
    setSloStatusError(null);
    setSloBreaches(null);
    setSloBreachesError(null);
    setQualityIssues(null);
    setQualityIssuesError(null);
    setRecommendations(null);
    setRecommendationsError(null);
    setMarketplace(null);
    setMarketplaceError(null);
    setMetricTrends(null);
    setMetricTrendsError(null);
    setSecops(null);
    setSecopsError(null);
    setSecopsRisk(null);
    setSecopsRiskError(null);
    setRiskSnapshots(null);
    setRiskSnapshotsError(null);
    setSre(null);
    setSreError(null);
    setSreDash(null);
    setSreDashError(null);
    setReliability(null);
    setReliabilityError(null);
    setObsDash(null);
    setObsDashError(null);
    setAnomalies(null);
    setAnomaliesError(null);
    setAiops(null);
    setAiopsError(null);
    setFatigue(null);
    setFatigueError(null);
    setGovernance(null);
    setGovernanceError(null);
    setGovTrends(null);
    setGovTrendsError(null);
    setGovHistory(null);
    setGovHistoryError(null);
    setGovEvidence(null);
    setGovEvidenceError(null);
    setGovDrift(null);
    setGovDriftError(null);
    setDatagov(null);
    setDatagovError(null);
    setFinopsUsage(null);
    setFinopsUsageError(null);
    setFinopsBuckets(null);
    setFinopsBucketsError(null);
    setFinopsForecast(null);
    setFinopsForecastError(null);
    setFinopsAnomalies(null);
    setFinopsAnomaliesError(null);
    setFinopsModels(null);
    setFinopsModelsError(null);
    setKnowledgeFresh(null);
    setKnowledgeFreshError(null);
    setKnowledgeUsage(null);
    setKnowledgeUsageError(null);
    setWorkflowHealth(null);
    setWorkflowHealthError(null);
    setWorkflowAnomalies(null);
    setWorkflowAnomaliesError(null);
    setWorkflowsListed(null);
    setWorkflowsListedError(null);
    setMlModels(null);
    setMlModelsError(null);
    setMlRisks(null);
    setMlRisksError(null);
    setMlProviders(null);
    setMlProvidersError(null);
    setAiUsage(null);
    setAiUsageError(null);
    setDatasets(null);
    setDatasetsError(null);
    setPipelines(null);
    setPipelinesError(null);
    setIntegrations(null);
    setIntegrationsError(null);
    setIntegrationsListed(null);
    setIntegrationsListedError(null);
  }, []);

  const loadAll = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const activeRange = RANGES.find((r) => r.id === range) ?? RANGES[2];
    const { days, hours } = activeRange;
    const window = windowIso(days);
    const anomaliesSupported = hours <= 720;
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);

    async function settle<T>(
      load: () => Promise<T>,
      apply: (value: T) => void,
      fail: (message: string | null) => void,
    ) {
      try {
        const value = await load();
        if (controller.signal.aborted || seq !== seqRef.current) return;
        apply(value);
        fail(null);
      } catch (e) {
        if (controller.signal.aborted || seq !== seqRef.current) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        if (e instanceof ApiError && e.kind === "forbidden") {
          fail("Backend denied access: additional authorization is required for your role.");
          return;
        }
        if (e instanceof ApiError && e.status === 404) {
          fail("Not found on the backend.");
          return;
        }
        if (e instanceof ApiError && e.status === 409) {
          fail("Changed on the server — use Refresh to reload.");
          return;
        }
        fail(e instanceof Error ? e.message : "Unavailable");
      }
    }

    // NOTE (Phase 28, C1): the analytics/security POST endpoints below are
    // pure-read aggregation RPCs (no backend mutation). Mutating analytics
    // endpoints (report generation, export, forecast creation, anomaly
    // detection, aggregation runs, metric/cost recording) are never called.
    await Promise.all([
      settle(() => api.adminOverview(token), setAdminOverview, (m) => setAdminOverviewError(m)),
      settle(() => api.analyticsDashboardOverview(token), setOverview, (m) => setOverviewError(m)),
      settle(
        () => api.analyticsDashboard(token, { start_time: window.start, end_time: window.end }),
        setSnapshot,
        (m) => setSnapshotError(m),
      ),
      settle(
        () => api.analyticsDora(token, { start_time: window.start, end_time: window.end }),
        setDora,
        (m) => setDoraError(m),
      ),
      settle(
        () => api.analyticsCostsSummary(token, { group_by: "organization", start_time: window.start, end_time: window.end }),
        setCosts,
        (m) => setCostsError(m),
      ),
      settle(
        () =>
          api.analyticsCostsTrend(token, {
            granularity: range === "24h" ? "hour" : "day",
            start_time: window.start,
            end_time: window.end,
          }),
        setCostTrend,
        (m) => setCostTrendError(m),
      ),
      settle(
        () => api.analyticsAiModelComparison(token, { start_time: window.start, end_time: window.end }),
        setModelComparison,
        (m) => setModelComparisonError(m),
      ),
      settle(
        () => api.analyticsAiBreakdown(token, { start_time: window.start, end_time: window.end }),
        setAiBreakdown,
        (m) => setAiBreakdownError(m),
      ),
      settle(() => api.securityDashboardFull(token, days), setSecDash, (m) => setSecDashError(m)),
      settle(() => api.analyticsSecuritySummary(token), setAnalyticsSec, (m) => setAnalyticsSecError(m)),
      settle(() => api.securityFindingsSummary(token), setSecFindings, (m) => setSecFindingsError(m)),
      settle(() => api.securityRiskSummary(token), setSecRisk, (m) => setSecRiskError(m)),
      settle(() => api.securityRiskScore(token), setSecScore, (m) => setSecScoreError(m)),
      settle(() => api.analyticsAlertsSummary(token), setAlertsSummary, (m) => setAlertsSummaryError(m)),
      settle(() => api.analyticsBudgetsStatus(token), setBudgetsStatus, (m) => setBudgetsStatusError(m)),
      settle(() => api.analyticsSloStatus(token), setSloStatus, (m) => setSloStatusError(m)),
      settle(() => api.analyticsSloBreaches(token), setSloBreaches, (m) => setSloBreachesError(m)),
      settle(() => api.analyticsQualityIssues(token, { limit: 20 }), setQualityIssues, (m) => setQualityIssuesError(m)),
      settle(() => api.analyticsRecommendations(token, { limit: 20 }), setRecommendations, (m) => setRecommendationsError(m)),
      settle(() => api.analyticsMarketplaceSummary(token), setMarketplace, (m) => setMarketplaceError(m)),
      settle(() => api.secOpsDashboard(token), setSecops, (m) => setSecopsError(m)),
      settle(() => api.secOpsRisk(token), setSecopsRisk, (m) => setSecopsRiskError(m)),
      settle(() => api.secOpsRiskSnapshots(token, 30), setRiskSnapshots, (m) => setRiskSnapshotsError(m)),
      settle(() => api.sreAnalytics(token, days), setSre, (m) => setSreError(m)),
      settle(() => api.sreDashboard(token), setSreDash, (m) => setSreDashError(m)),
      settle(() => api.sreReliabilityScore(token, { days }), setReliability, (m) => setReliabilityError(m)),
      settle(() => api.observabilityDashboard(token), setObsDash, (m) => setObsDashError(m)),
      settle(
        () =>
          anomaliesSupported
            ? api.observabilityAnomalies(token, { window_hours: hours, limit: 20 })
            : Promise.reject(new Error(`${activeRange.label} is not supported by this source (window_hours max 720).`)),
        setAnomalies,
        (m) => setAnomaliesError(m),
      ),
      settle(() => api.observabilityAiopsStatus(token), setAiops, (m) => setAiopsError(m)),
      settle(
        () => api.observabilityAlertFatigue(token).then((v) => v as unknown as Record<string, unknown>),
        setFatigue,
        (m) => setFatigueError(m),
      ),
      settle(() => api.governancePosture(token, { scope_type: "tenant" }), setGovernance, (m) => setGovernanceError(m)),
      settle(() => api.governanceTrends(token, days), setGovTrends, (m) => setGovTrendsError(m)),
      settle(
        () => api.governancePostureHistory(token, { scope_type: "tenant", limit: 20 }),
        setGovHistory,
        (m) => setGovHistoryError(m),
      ),
      settle(() => api.governanceEvidenceCoverage(token), setGovEvidence, (m) => setGovEvidenceError(m)),
      settle(() => api.governanceDrift(token, { limit: 20 }), setGovDrift, (m) => setGovDriftError(m)),
      settle(() => api.datagovDashboard(token), setDatagov, (m) => setDatagovError(m)),
      settle(
        () => api.finopsUsageSummary(token, { start: window.start, end: window.end }),
        setFinopsUsage,
        (m) => setFinopsUsageError(m),
      ),
      settle(
        () => api.finopsAggregations(token, { granularity: "day", start: window.start, end: window.end, limit: 100 }),
        setFinopsBuckets,
        (m) => setFinopsBucketsError(m),
      ),
      settle(() => api.finopsForecast(token, { horizon_days: Math.min(days, 90) }), setFinopsForecast, (m) =>
        setFinopsForecastError(m),
      ),
      settle(() => api.finopsAnomalies(token, { limit: 20 }), setFinopsAnomalies, (m) => setFinopsAnomaliesError(m)),
      settle(
        () => api.finopsModelsCompare(token, { start: window.start, end: window.end }),
        setFinopsModels,
        (m) => setFinopsModelsError(m),
      ),
      settle(() => api.knowledgeFreshnessStats(token), setKnowledgeFresh, (m) => setKnowledgeFreshError(m)),
      settle(
        () =>
          anomaliesSupported
            ? api.knowledgeUsageStats(token, { since_hours: hours })
            : Promise.reject(new Error(`${activeRange.label} is not supported by this source (since_hours max 720).`)),
        setKnowledgeUsage,
        (m) => setKnowledgeUsageError(m),
      ),
      settle(() => api.workflowHealthSummary(token), setWorkflowHealth, (m) => setWorkflowHealthError(m)),
      settle(() => api.workflowAnomalies(token, 10), setWorkflowAnomalies, (m) => setWorkflowAnomaliesError(m)),
      settle(() => api.workflowsList(token, { limit: 10 }), setWorkflowsListed, (m) => setWorkflowsListedError(m)),
      settle(() => api.mlModels(token), setMlModels, (m) => setMlModelsError(m)),
      settle(() => api.mlRisks(token), setMlRisks, (m) => setMlRisksError(m)),
      settle(() => api.mlProviders(token), setMlProviders, (m) => setMlProvidersError(m)),
      settle(() => api.aiUsage(token, 10), setAiUsage, (m) => setAiUsageError(m)),
      settle(() => api.dataDatasets(token, { limit: 20 }), setDatasets, (m) => setDatasetsError(m)),
      settle(() => api.dataPipelines(token, { limit: 20 }), setPipelines, (m) => setPipelinesError(m)),
      settle(() => api.enterpriseIntegrationsMetrics(token), setIntegrations, (m) => setIntegrationsError(m)),
      settle(() => api.integrationsList(token), setIntegrationsListed, (m) => setIntegrationsListedError(m)),
    ]);

    // Recorded-metric trends: discover names first, then query up to three.
    // Each step is seq-guarded so tenant switches never leak across contexts.
    try {
      const list = await api.analyticsMetricsList(token);
      if (controller.signal.aborted || seq !== seqRef.current) return;
      const names = (list.metrics ?? []).filter((n) => typeof n === "string" && n.length > 0).slice(0, 3);
      if (names.length === 0) {
        setMetricTrends([]);
      } else {
        const trend = await api.analyticsMetricsTrend(token, {
          metric_names: names,
          granularity: range === "24h" ? "hour" : "day",
          start_time: window.start,
          end_time: window.end,
        });
        if (controller.signal.aborted || seq !== seqRef.current) return;
        const byName = new Map<string, AnalyticsMetricPoint[]>();
        for (const point of trend.trend ?? []) {
          const name = typeof point.metric_name === "string" ? point.metric_name : "";
          if (!name) continue;
          const bucket = byName.get(name) ?? [];
          bucket.push(point);
          byName.set(name, bucket);
        }
        setMetricTrends(names.map((name) => ({ name, points: byName.get(name) ?? [] })));
      }
    } catch (e) {
      if (controller.signal.aborted || seq !== seqRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setMetricTrendsError("Unavailable");
    }

    if (controller.signal.aborted || seq !== seqRef.current) return;
    setRefreshedAt(new Date().toLocaleString());
    setLoading(false);
  }, [range, sessionExpired]);

  useEffect(() => {
    void loadAll();
    const handler = () => {
      if (abortRef.current) abortRef.current.abort();
      seqRef.current += 1;
      clearAll();
      setRefreshedAt(null);
      setLoading(true);
      void loadAll();
    };
    window.addEventListener("tenant:switched", handler as EventListener);
    window.addEventListener("workspace:switched", handler as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", handler as EventListener);
      window.removeEventListener("workspace:switched", handler as EventListener);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [loadAll, clearAll]);

  const activeRange = RANGES.find((r) => r.id === range) ?? RANGES[2];
  const retry = () => void loadAll();

  const costTrendData: TrendDatum[] = (costTrend?.trend ?? [])
    .filter((p) => typeof p.total_usd === "number" && typeof p.period === "string")
    .map((p) => ({
      key: String(p.period),
      label: String(p.period),
      value: Number(p.total_usd),
      title: `${p.period}: ${formatUsd(p.total_usd) ?? "—"} across ${p.entry_count ?? 0} entries`,
    }));

  const bucketData: TrendDatum[] = (finopsBuckets?.items ?? [])
    .filter((b) => typeof b.bucket_start === "string")
    .map((b) => ({
      key: b.id,
      label: String(b.bucket_start),
      value: b.total_cents,
      title: `${b.bucket_start}: ${formatCentsUsd(b.total_cents) ?? "—"} across ${b.record_count} records`,
    }));

  const govViolationTrend: TrendDatum[] = (govTrends?.items ?? [])
    .filter((p) => typeof p.computed_at === "string")
    .map((p, index) => ({
      key: `${p.computed_at}-${index}`,
      label: String(p.computed_at),
      value: p.violations_24h,
      title: `${p.computed_at}: ${p.violations_24h} violations, ${p.open_exceptions} open exceptions`,
    }));

  const mlByStatus = new Map<string, number>();
  for (const model of mlModels ?? []) {
    const status = typeof model.status === "string" && model.status.length > 0 ? model.status : "unknown";
    mlByStatus.set(status, (mlByStatus.get(status) ?? 0) + 1);
  }

  const openMlRisks = (mlRisks ?? []).filter((r) => (r.status ?? "").toLowerCase() !== "resolved");

  const reliabilityScore = num((reliability as Record<string, unknown> | null)?.score);
  const reliabilityGrade = str((reliability as Record<string, unknown> | null)?.grade);
  const reliabilityComponents = (reliability as Record<string, unknown> | null)?.components;
  const reliabilityMethodology = (reliability as Record<string, unknown> | null)?.methodology as
    | { note?: unknown }
    | undefined;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border border-outline bg-surface-container px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant"
            aria-live="polite"
          >
            <span className="h-2 w-2 bg-muted" aria-hidden="true" />
            Realtime: UNAVAILABLE
          </span>
          <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            {refreshedAt ? `Refreshed ${refreshedAt}` : "Loading executive analytics…"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="Time range" className="flex border border-outline">
            {RANGES.map((r) => (
              <button
                key={r.id}
                type="button"
                aria-pressed={range === r.id}
                onClick={() => setRange(r.id)}
                className={`px-3 py-1 font-mono text-xs uppercase tracking-widest ${
                  range === r.id ? "bg-primary-container text-on-surface" : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <BrutalButton variant="ghost" size="sm" onClick={retry} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
          <BrutalButton variant="ghost" size="sm" href="/ai">
            Ask AI about analytics
          </BrutalButton>
        </div>
      </div>

      <p className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
        Scope legend — Tenant-scoped: server-derived tenant. Backend scope: default / unauthenticated: open
        /analytics/* and /security/* routers called with tenant=default. Backend scope: global: authenticated
        but not tenant-filtered by the backend. No metric is fabricated; missing data renders as honest states.
      </p>

      <BrutalCard eyebrow="Executive overview" title="Organization at a glance">
        <div className="mb-4">
          <ScopeBadge scope="tenant" />
        </div>
        <PanelBody
          loading={loading}
          error={adminOverviewError ?? overviewError ?? snapshotError}
          onRetry={retry}
          emptyTitle="No overview reported"
          emptyDescription="The backend returned no organization overview for this range."
        >
          {adminOverview || overview || snapshot ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <AnalyticsMetric label="Organizations (global admin)" value={formatInt(adminOverview?.total_organizations)} hint={adminOverview ? undefined : "Requires backend superuser authorization"} />
                <AnalyticsMetric label="Users (global admin)" value={formatInt(adminOverview?.total_users)} />
                <AnalyticsMetric label="Repositories (global admin)" value={formatInt(adminOverview?.total_repositories)} />
                <AnalyticsMetric label="Agent runs (global admin)" value={formatInt(adminOverview?.total_agent_runs)} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <AnalyticsMetric label="Lifetime cost (USD)" value={formatUsd(overview?.total_cost_usd)} hint="Backend reporting period" />
                <AnalyticsMetric label="Window cost (USD)" value={formatUsd(snapshot?.costs?.total_usd)} hint={`${activeRange.label} window`} />
                <AnalyticsMetric label="Window deploys/day" value={formatDecimal(snapshot?.dora?.deployment_frequency)} />
                <AnalyticsMetric label="Window MTTR (min)" value={formatDecimal(snapshot?.dora?.mttr_minutes)} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <AnalyticsMetric label="Window findings" value={formatInt(snapshot?.security?.total_findings)} />
                <AnalyticsMetric label="Window active alerts" value={formatInt(snapshot?.alerts?.active)} />
                <AnalyticsMetric label="Window open findings" value={formatInt(snapshot?.security?.open)} />
                <AnalyticsMetric label="Events processed (lifetime)" value={formatInt(overview?.events?.processed)} />
              </div>
            </div>
          ) : null}
        </PanelBody>
      </BrutalCard>

      <BrutalCard eyebrow="Trends" title="Backend-provided history only">
        <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
          Source: Analytics + FinOps + Governance
        </p>
        <div className="mb-4">
          <ScopeBadge scope="default" />
        </div>
        <PanelBody
          loading={loading}
          error={costTrendError ?? metricTrendsError ?? finopsBucketsError ?? govTrendsError}
          onRetry={retry}
          emptyTitle="Insufficient data"
          emptyDescription="No historical buckets were returned for this range."
        >
          {costTrend || metricTrends || finopsBuckets || govTrends ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                  Cost over time (USD, {activeRange.label})
                </p>
                <AnalyticsTrend data={costTrendData} ariaLabel="Cost trend in USD" emptyMessage="No cost buckets reported." />
              </div>
              <div>
                <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                  Spend buckets (FinOps, cents)
                </p>
                <AnalyticsTrend
                  data={bucketData}
                  ariaLabel="FinOps spend buckets in cents"
                  emptyMessage="No aggregation buckets. Buckets materialize only after an aggregation run."
                />
              </div>
              <div>
                <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                  Governance violations over time
                </p>
                <AnalyticsTrend data={govViolationTrend} ariaLabel="Governance violations trend" emptyMessage="No governance trend points reported." />
              </div>
              {(metricTrends ?? []).map((series) => (
                <div key={series.name}>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Metric: {series.name}
                  </p>
                  <AnalyticsTrend
                    data={series.points
                      .filter((p) => typeof p.value === "number" && typeof p.period_start === "string")
                      .map((p, index) => ({
                        key: `${p.period_start}-${index}`,
                        label: String(p.period_start),
                        value: Number(p.value),
                        title: `${p.period_start}: sum ${p.value} (n=${p.count ?? 0}, avg ${p.avg ?? "—"})`,
                      }))}
                    ariaLabel={`Recorded metric ${series.name}`}
                    emptyMessage="No buckets recorded for this metric."
                  />
                </div>
              ))}
              {(metricTrends ?? []).length === 0 && !loading ? (
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                  No recorded metrics exposed by /analytics/metrics/list.
                </p>
              ) : null}
            </div>
          ) : null}
        </PanelBody>
      </BrutalCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <DomainCard
          eyebrow="Engineering"
          title="Delivery performance"
          source="Analytics (DORA)"
          scope="default"
          linkHref="/code"
          linkLabel="Open Code Intelligence"
          loading={loading}
          error={doraError ?? costsError}
          onRetry={retry}
          emptyTitle="No delivery metrics"
          emptyDescription="The backend returned no DORA metrics for this range."
        >
          {dora || costs ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Deployment frequency" value={dora?.deployment_frequency != null ? `${formatDecimal(dora.deployment_frequency)} / day` : null} />
                <AnalyticsMetric label="Lead time" value={dora?.lead_time_minutes != null ? `${formatDecimal(dora.lead_time_minutes)} min` : null} hint="0 when no lead-time events are recorded" />
                <AnalyticsMetric label="Change failure rate" value={formatRatioPercent(dora?.change_failure_rate)} />
                <AnalyticsMetric label="MTTR" value={dora?.mttr_minutes != null ? `${formatDecimal(dora.mttr_minutes)} min` : null} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Cost entries" value={formatInt(costs?.entry_count)} hint={`${activeRange.label} window`} />
                <AnalyticsMetric label="Estimated share (USD)" value={formatUsd(costs?.estimated_usd)} />
              </div>
              <p className="text-xs text-on-surface-variant">
                Repository-level code intelligence is per-repository: an organization rollup is not exposed by
                the API.
              </p>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="AI"
          title="Model usage and cost"
          source="Analytics (model comparison)"
          scope="default"
          linkHref="/ai"
          linkLabel="Open AI workspace"
          loading={loading}
          error={modelComparisonError ?? aiBreakdownError}
          onRetry={retry}
          emptyTitle="No AI usage reported"
          emptyDescription="The backend returned no model comparison for this range."
        >
          {modelComparison || aiBreakdown ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="AI cost (USD)" value={formatUsd(aiBreakdown?.total_ai_cost_usd)} hint={`${activeRange.label} window`} />
                <AnalyticsMetric label="AI cost entries" value={formatInt(aiBreakdown?.entry_count)} />
              </div>
              <BrutalTable
                columns={[
                  { key: "model", header: "Model", render: (r) => <span className="font-mono text-xs">{r.model ?? "—"}</span> },
                  { key: "calls", header: "Calls", render: (r) => formatInt(r.calls) ?? "—" },
                  { key: "success", header: "Success", render: (r) => (r.success_rate != null ? `${formatDecimal(r.success_rate)}%` : "—") },
                  { key: "latency", header: "Avg ms", render: (r) => formatDecimal(r.avg_latency_ms) ?? "—" },
                  { key: "cost", header: "Cost USD", render: (r) => formatUsd(r.total_cost_usd) ?? "—" },
                ]}
                rows={(modelComparison?.comparison ?? []).slice(0, 8)}
                emptyMessage="No models compared"
              />
              <p className="text-xs text-on-surface-variant">
                Latency and success fields are null when call metadata was not recorded. Token costs are
                never calculated in the browser.
              </p>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Operations"
          title="Reliability and incidents"
          source="SRE"
          scope="global"
          linkHref="/observability"
          linkLabel="Open Observability"
          loading={loading}
          error={sreError ?? sreDashError ?? reliabilityError}
          onRetry={retry}
          emptyTitle="No operations data"
          emptyDescription="The backend returned no SRE analytics for this range."
        >
          {sre || sreDash || reliability ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Incidents" value={formatInt(sre?.incidents.total)} hint={`${activeRange.label}; backend scope is global`} />
                <AnalyticsMetric label="Open incidents" value={formatInt(sre?.incidents.open)} />
                <AnalyticsMetric label="MTTR" value={sre?.incidents.mttr_hours != null ? `${formatDecimal(sre.incidents.mttr_hours)} h` : null} />
                <AnalyticsMetric label="Change failure rate" value={formatRatioPercent(sre?.deployments.change_failure_rate)} />
                <AnalyticsMetric label="Firing alerts" value={formatInt(sre?.alerts.firing)} />
                <AnalyticsMetric label="Active (SRE dashboard)" value={formatInt(sreDash?.incidents?.active)} />
                <AnalyticsMetric label="Severe active" value={formatInt(sreDash?.incidents?.severe)} />
                <AnalyticsMetric label="Services" value={formatInt(sreDash?.services?.total)} />
              </div>
              <div>
                <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                  Reliability score (backend-explained)
                </p>
                {reliabilityScore != null || reliabilityGrade ? (
                  <div className="space-y-2">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <AnalyticsMetric label="Score" value={reliabilityScore != null ? formatDecimal(reliabilityScore) : null} />
                      <AnalyticsMetric label="Grade" value={reliabilityGrade} />
                    </div>
                    {reliabilityComponents && typeof reliabilityComponents === "object" ? (
                      <div>
                        {Object.entries(reliabilityComponents).map(([name, component]) => {
                          const c = component as Record<string, unknown>;
                          const score = num(c.score);
                          return (
                            <StatRow
                              key={name}
                              label={name.replace(/_/g, " ")}
                              value={score != null ? `${formatDecimal(score)} — ${str(c.explanation) ?? ""}` : str(c.explanation) ?? "no measurement data available"}
                            />
                          );
                        })}
                      </div>
                    ) : null}
                    {str(reliabilityMethodology?.note) ? (
                      <p className="text-xs text-on-surface-variant">{str(reliabilityMethodology?.note)}</p>
                    ) : null}
                  </div>
                ) : (
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                    Score unavailable — components without data are excluded, never guessed.
                  </p>
                )}
              </div>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Operations"
          title="Observability signals"
          source="Observability"
          scope="tenant"
          linkHref="/observability"
          linkLabel="Open Observability"
          loading={loading}
          error={obsDashError ?? anomaliesError ?? aiopsError ?? fatigueError}
          onRetry={retry}
          emptyTitle="No observability data"
          emptyDescription="The backend returned no observability signals."
        >
          {obsDash || anomalies || aiops || fatigue ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Services" value={formatInt(obsDash?.services)} />
                <AnalyticsMetric label="Anomalies in window" value={formatInt(anomalies?.total)} hint={activeRange.label} />
              </div>
              {obsDash && Object.keys(obsDash.health ?? {}).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Service health (first 10 reported)
                  </p>
                  <PrimitiveRows data={obsDash.health} />
                </div>
              ) : null}
              {(anomalies?.items ?? []).length > 0 ? (
                <BrutalTable
                  columns={[
                    { key: "metric", header: "Metric", render: (r) => <span className="font-mono text-xs">{r.metric_name ?? "—"}</span> },
                    { key: "severity", header: "Severity", render: (r) => <BrutalBadge>{r.severity ?? "—"}</BrutalBadge> },
                    { key: "deviation", header: "Z", render: (r) => formatDecimal(r.deviation) ?? "—" },
                    { key: "hypothesis", header: "Hypothesis", render: (r) => (r.is_hypothesis ? "yes" : "no") },
                  ]}
                  rows={(anomalies?.items ?? []).slice(0, 8)}
                  emptyMessage="No anomalies"
                />
              ) : null}
              {aiops && aiops.stages.length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    AIOps pipeline stages
                  </p>
                  <ol className="list-decimal space-y-1 pl-5 text-sm text-on-surface">
                    {aiops.stages.map((stage) => (
                      <li key={stage}>{stage}</li>
                    ))}
                  </ol>
                  {aiops.disclaimer ? <p className="mt-1 text-xs text-on-surface-variant">{aiops.disclaimer}</p> : null}
                </div>
              ) : null}
              {fatigue ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Alert fatigue (fixed 24h backend window)
                  </p>
                  <PrimitiveRows data={fatigue} />
                </div>
              ) : null}
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Security"
          title="Threat operations"
          source="SecOps"
          scope="tenant"
          linkHref="/security"
          linkLabel="Open Security"
          loading={loading}
          error={secopsError ?? secopsRiskError ?? riskSnapshotsError}
          onRetry={retry}
          emptyTitle="No SecOps data"
          emptyDescription="The backend returned no security operations summary."
        >
          {secops || secopsRisk || riskSnapshots ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Alerts" value={formatInt(secops?.alerts.total)} />
                <AnalyticsMetric label="Findings" value={formatInt(secops?.findings.total)} />
                <AnalyticsMetric label="Cases" value={formatInt(secops?.cases.total)} />
                <AnalyticsMetric label="Indicators" value={formatInt(secops?.indicators.total)} />
                <AnalyticsMetric label="Latest risk score" value={secopsRisk?.risk_score != null ? formatDecimal(secopsRisk.risk_score) : null} hint="Backend-reported; heuristic, not a legal conclusion" />
                <AnalyticsMetric label="Risk snapshots" value={formatInt(riskSnapshots?.items?.length)} hint="Newest-first backend order" />
              </div>
              {secops && Object.keys(secops.alerts.by_status ?? {}).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Alerts by status
                  </p>
                  <PrimitiveRows data={secops.alerts.by_status} />
                </div>
              ) : null}
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Security"
          title="Findings and risk posture"
          source="Security platform"
          scope="default-sensitive"
          linkHref="/security"
          linkLabel="Open Security"
          loading={loading}
          error={secDashError ?? analyticsSecError ?? secFindingsError ?? secRiskError ?? secScoreError}
          onRetry={retry}
          emptyTitle="No security findings"
          emptyDescription="The backend returned no security summary for this range."
        >
          {secDash || analyticsSec || secFindings || secRisk || secScore ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label={`Findings (${activeRange.label})`} value={formatInt(secDash?.total_findings)} />
                <AnalyticsMetric label="Open (lifetime)" value={formatInt(analyticsSec?.open)} />
                <AnalyticsMetric label="Critical open (lifetime)" value={formatInt(analyticsSec?.open_critical)} />
                <AnalyticsMetric label="Risk score" value={secRisk?.risk_score != null ? formatDecimal(secRisk.risk_score) : null} hint={`Level: ${secRisk?.risk_level ?? "—"} (backend heuristic)`} />
                <AnalyticsMetric label="Risk score (0–100)" value={secScore?.score != null ? formatDecimal(secScore.score, 1) : null} hint={`Level: ${secScore?.level ?? "—"} (backend heuristic)`} />
                <AnalyticsMetric label="Gate pass rate" value={secDash?.gate_status?.pass_rate != null ? `${formatDecimal(secDash.gate_status.pass_rate, 1)}%` : null} />
                <AnalyticsMetric label="Compliance score" value={secDash?.compliance_score != null ? formatDecimal(secDash.compliance_score) : null} hint="100 − 5×critical/high − 2×medium. Heuristic, not legal compliance." />
                <AnalyticsMetric label="Scans evaluated" value={formatInt(analyticsSec?.scans_count)} />
              </div>
              {secDash && secDash.severity_breakdown && Object.keys(secDash.severity_breakdown).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Severity breakdown
                  </p>
                  <PrimitiveRows data={secDash.severity_breakdown} />
                </div>
              ) : null}
              {(secDash?.top_risks ?? []).length > 0 ? (
                <BrutalTable
                  columns={[
                    { key: "rule", header: "Rule", render: (r) => <span className="font-mono text-xs">{r.rule ?? "—"}</span> },
                    { key: "severity", header: "Severity", render: (r) => <BrutalBadge>{r.severity ?? "—"}</BrutalBadge> },
                    { key: "score", header: "Risk", render: (r) => formatDecimal(r.risk_score) ?? "—" },
                  ]}
                  rows={(secDash?.top_risks ?? []).slice(0, 5)}
                  emptyMessage="No top risks"
                />
              ) : null}
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Governance"
          title="Policy posture"
          source="Governance"
          scope="tenant"
          linkHref="/governance"
          linkLabel="Open Governance"
          loading={loading}
          error={governanceError ?? govEvidenceError ?? govDriftError}
          onRetry={retry}
          emptyTitle="No governance posture"
          emptyDescription="The backend returned no governance posture."
        >
          {governance || govEvidence || govDrift ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Total policies" value={formatInt(governance?.total_policies)} />
                <AnalyticsMetric label="Active policies" value={formatInt(governance?.active_policies)} />
                <AnalyticsMetric label="Violations (24h)" value={formatInt(governance?.violations_24h)} />
                <AnalyticsMetric label="Open exceptions" value={formatInt(governance?.open_exceptions)} />
                <AnalyticsMetric label="Verified controls" value={formatInt(governance?.verified_controls)} />
                <AnalyticsMetric label="Failing controls" value={formatInt(governance?.failing_controls)} />
                <AnalyticsMetric label="Evidence valid" value={formatInt(govEvidence?.valid)} />
                <AnalyticsMetric label="Evidence expired" value={formatInt(govEvidence?.expired)} />
              </div>
              <p className="text-xs text-on-surface-variant">
                Computed {governance?.computed_at ?? "—"}. Risk values are backend-reported only and are never
                reinterpreted here.
              </p>
              {(govDrift?.items ?? []).length > 0 ? (
                <BrutalTable
                  columns={[
                    { key: "type", header: "Finding", render: (r) => <span className="font-mono text-xs">{r.finding_type}</span> },
                    { key: "severity", header: "Severity", render: (r) => <BrutalBadge>{r.severity}</BrutalBadge> },
                    { key: "status", header: "Status", render: (r) => r.status },
                  ]}
                  rows={(govDrift?.items ?? []).slice(0, 8)}
                  emptyMessage="No drift findings"
                />
              ) : null}
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Governance"
          title="Data stewardship"
          source="Data Governance"
          scope="tenant"
          linkHref="/governance"
          linkLabel="Open Governance"
          loading={loading}
          error={datagovError ?? govHistoryError}
          onRetry={retry}
          emptyTitle="No stewardship data"
          emptyDescription="The backend returned no data governance summary."
        >
          {datagov || govHistory ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Assets" value={formatInt(datagov?.assets_total)} />
                <AnalyticsMetric label="Classifications" value={formatInt(datagov?.classifications_total)} />
                <AnalyticsMetric label="Retention expiring" value={formatInt(datagov?.retention_expiring)} />
                <AnalyticsMetric label="Posture snapshots" value={formatInt(govHistory?.total)} hint="Newest-first backend order" />
              </div>
              {datagov?.assets_by_classification && Object.keys(datagov.assets_by_classification).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Assets by classification
                  </p>
                  <PrimitiveRows data={datagov.assets_by_classification} />
                </div>
              ) : null}
              <p className="text-xs text-on-surface-variant">
                Backend substitutes 0 when a stewardship source is unavailable; zeros here cannot be
                distinguished from true zeros.
              </p>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Data"
          title="Platform activity"
          source="Data Platform"
          scope="tenant"
          linkHref="/data"
          linkLabel="Open Data Platform"
          loading={loading}
          error={datasetsError ?? pipelinesError}
          onRetry={retry}
          emptyTitle="No datasets or pipelines"
          emptyDescription="The backend returned no datasets or pipelines."
        >
          {datasets || pipelines ? (
            <div className="space-y-4">
              {(datasets?.items ?? []).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Datasets (first {(datasets?.items ?? []).slice(0, 10).length} listed — no backend total)
                  </p>
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Dataset", render: (r) => <span className="font-bold">{r.name}</span> },
                      { key: "status", header: "Status", render: (r) => <BrutalBadge>{r.status}</BrutalBadge> },
                      { key: "classification", header: "Classification", render: (r) => r.classification },
                    ]}
                    rows={(datasets?.items ?? []).slice(0, 10)}
                    emptyMessage="No datasets"
                  />
                </div>
              ) : null}
              {(pipelines?.items ?? []).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Pipelines (first {(pipelines?.items ?? []).slice(0, 10).length} listed — no backend total)
                  </p>
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Pipeline", render: (r) => <span className="font-bold">{r.name}</span> },
                      { key: "status", header: "Status", render: (r) => <BrutalBadge>{r.status}</BrutalBadge> },
                    ]}
                    rows={(pipelines?.items ?? []).slice(0, 10)}
                    emptyMessage="No pipelines"
                  />
                </div>
              ) : null}
              <p className="text-xs text-on-surface-variant">
                Organization-level data-quality rollups are not exposed by the API; quality is per-dataset in
                the Data Platform workspace.
              </p>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="FinOps"
          title="Spend and forecast"
          source="FinOps"
          scope="tenant"
          linkHref="/finops"
          linkLabel="Open FinOps"
          loading={loading}
          error={finopsUsageError ?? finopsForecastError ?? finopsAnomaliesError ?? finopsModelsError ?? finopsBucketsError}
          onRetry={retry}
          emptyTitle="No FinOps data"
          emptyDescription="The backend returned no spend summary for this range."
        >
          {finopsUsage || finopsForecast || finopsAnomalies || finopsModels ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label={`Spend (${activeRange.label})`} value={formatCentsUsd(finopsUsage?.spend_cents)} hint="Integer cents ÷ 100; never mixed with analytics USD floats at source" />
                <AnalyticsMetric label="Cost records" value={formatInt(finopsUsage?.cost_records)} />
                <AnalyticsMetric label="Tokens" value={formatInt(finopsUsage?.total_tokens)} />
                <AnalyticsMetric
                  label="Forecast"
                  value={
                    finopsForecast && isForecastReady(finopsForecast)
                      ? (formatCentsUsd(finopsForecast.predicted_cents) ?? "—")
                      : null
                  }
                  hint={
                    finopsForecast && isForecastReady(finopsForecast)
                      ? `Quality ${finopsForecast.quality ?? "—"} · confidence ${finopsForecast.confidence ?? "—"} · ${finopsForecast.method ?? "linear_baseline"}`
                      : `Insufficient data (${finopsForecast && !isForecastReady(finopsForecast) ? (finopsForecast.reason ?? "fewer than 7 spend days") : "—"})`
                  }
                />
              </div>
              {(finopsAnomalies?.items ?? []).length > 0 ? (
                <BrutalTable
                  columns={[
                    { key: "dimension", header: "Dimension", render: (r) => <span className="font-mono text-xs">{`${r.dimension_key}:${r.dimension_value}`}</span> },
                    { key: "severity", header: "Severity", render: (r) => <BrutalBadge>{r.severity}</BrutalBadge> },
                    { key: "observed", header: "Observed", render: (r) => formatCentsUsd(r.observed_cents) ?? "—" },
                    { key: "baseline", header: "Baseline", render: (r) => formatCentsUsd(r.baseline_cents) ?? "—" },
                  ]}
                  rows={(finopsAnomalies?.items ?? []).slice(0, 8)}
                  emptyMessage="No anomalies"
                />
              ) : null}
              {(finopsModels?.items ?? []).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Model spend ({finopsModels?.start ?? "—"} → {finopsModels?.end ?? "—"})
                  </p>
                  <BrutalTable
                    columns={[
                      { key: "model", header: "Model", render: (r) => <span className="font-mono text-xs">{`${r.provider ?? "—"}/${r.model ?? "—"}`}</span> },
                      { key: "spend", header: "Spend", render: (r) => formatCentsUsd(r.spend_cents) ?? "—" },
                      { key: "requests", header: "Requests", render: (r) => formatInt(r.requests) ?? "—" },
                    ]}
                    rows={(finopsModels?.items ?? []).slice(0, 8)}
                    emptyMessage="No model spend"
                  />
                  {finopsModels?.note ? <p className="mt-1 text-xs text-on-surface-variant">{finopsModels.note}</p> : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Platform"
          title="Workflows and automation"
          source="Workflow"
          scope="tenant"
          linkHref="/workflows"
          linkLabel="Open Workflows"
          loading={loading}
          error={workflowHealthError ?? workflowAnomaliesError ?? workflowsListedError}
          onRetry={retry}
          emptyTitle="No workflow data"
          emptyDescription="The backend returned no workflow health."
        >
          {workflowHealth || workflowAnomalies || workflowsListed ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Runs (lifetime)" value={formatInt(workflowHealth?.total)} />
                <AnalyticsMetric label="Succeeded" value={formatInt(workflowHealth?.success)} />
                <AnalyticsMetric label="Failed" value={formatInt(workflowHealth?.failed)} />
                <AnalyticsMetric label="Success rate" value={workflowHealth?.success_rate != null ? `${formatDecimal(workflowHealth.success_rate, 1)}%` : null} hint="Backend percent, verbatim" />
              </div>
              {(workflowsListed?.items ?? []).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Workflows (first {(workflowsListed?.items ?? []).slice(0, 8).length} listed — no backend total)
                  </p>
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Workflow", render: (r) => <span className="font-bold">{r.name}</span> },
                      { key: "status", header: "Status", render: (r) => <BrutalBadge>{r.status}</BrutalBadge> },
                    ]}
                    rows={(workflowsListed?.items ?? []).slice(0, 8)}
                    emptyMessage="No workflows"
                  />
                </div>
              ) : null}
              {(workflowAnomalies?.items ?? []).length > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Run anomalies (backend heuristic: &gt;60s or failed)
                  </p>
                  <BrutalTable
                    columns={[
                      { key: "run", header: "Run", render: (r) => <span className="font-mono text-xs">{r.run_id}</span> },
                      { key: "type", header: "Type", render: (r) => r.type },
                      { key: "duration", header: "Duration ms", render: (r) => formatInt(r.duration_ms) ?? "—" },
                    ]}
                    rows={(workflowAnomalies?.items ?? []).slice(0, 8)}
                    emptyMessage="No anomalies"
                  />
                </div>
              ) : null}
              <p className="text-xs text-on-surface-variant">
                Organization-level agent runs are not exposed by the API (run history is per-user). See the
                Agents workspace.
              </p>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Platform"
          title="Models, risks and AI usage"
          source="AI / ML platform"
          scope="tenant"
          linkHref="/ml"
          linkLabel="Open AI / ML"
          loading={loading}
          error={mlModelsError ?? mlRisksError ?? mlProvidersError ?? aiUsageError}
          onRetry={retry}
          emptyTitle="No model inventory"
          emptyDescription="The backend returned no models."
        >
          {mlModels || mlRisks || mlProviders || aiUsage ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Registered models" value={formatInt(mlModels?.length)} hint="Complete tenant registry (unbounded list)" />
                <AnalyticsMetric label="Providers" value={formatInt(mlProviders?.length)} />
                <AnalyticsMetric label="Open risks" value={formatInt(openMlRisks.length)} hint="Excludes resolved" />
                <AnalyticsMetric label="AI actions sampled" value={formatInt(aiUsage?.items?.length)} hint="Bounded sample of recent actions" />
              </div>
              {mlByStatus.size > 0 ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Models by status
                  </p>
                  <PrimitiveRows data={Object.fromEntries(mlByStatus)} />
                </div>
              ) : null}
              {aiUsage?.totals && typeof aiUsage.totals === "object" ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    AI development usage totals (last 1000 rows window)
                  </p>
                  <PrimitiveRows data={aiUsage.totals} />
                </div>
              ) : null}
              <p className="text-xs text-on-surface-variant">
                Prompt contents are never rendered here. Latency and token series are not exposed by the API.
              </p>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Platform"
          title="Knowledge health"
          source="Knowledge"
          scope="tenant"
          linkHref="/knowledge"
          linkLabel="Open Knowledge"
          loading={loading}
          error={knowledgeFreshError ?? knowledgeUsageError}
          onRetry={retry}
          emptyTitle="No knowledge stats"
          emptyDescription="The backend returned no knowledge statistics."
        >
          {knowledgeFresh || knowledgeUsage ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Documents" value={formatInt(knowledgeFresh?.total)} />
                <AnalyticsMetric label="Fresh" value={formatInt(knowledgeFresh?.fresh)} hint="Score ≥ 0.7" />
                <AnalyticsMetric label="Aging" value={formatInt(knowledgeFresh?.aging)} />
                <AnalyticsMetric label="Stale" value={formatInt(knowledgeFresh?.stale)} />
                <AnalyticsMetric label={`Queries (${activeRange.label})`} value={formatInt(knowledgeUsage?.total_queries)} />
                <AnalyticsMetric label="Avg latency" value={knowledgeUsage?.avg_latency_ms != null ? `${formatDecimal(knowledgeUsage.avg_latency_ms)} ms` : null} />
                <AnalyticsMetric label="Unique users" value={formatInt(knowledgeUsage?.unique_users)} />
              </div>
              {(knowledgeUsage?.top_terms ?? []).length > 0 ? (
                <p className="text-xs text-on-surface-variant">
                  Top terms: {(knowledgeUsage?.top_terms ?? []).slice(0, 10).join(", ")}
                </p>
              ) : null}
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Platform"
          title="Integration estate"
          source="Enterprise integrations"
          scope="tenant"
          linkHref="/integrations"
          linkLabel="Open Integrations"
          loading={loading}
          error={integrationsError ?? integrationsListedError}
          onRetry={retry}
          emptyTitle="No integration metrics"
          emptyDescription="The backend returned no integration overview."
        >
          {integrations || integrationsListed ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Integrations" value={formatInt(integrations?.total_integrations ?? integrationsListed?.total)} />
                <AnalyticsMetric label="Active integrations" value={formatInt(integrations?.active_integrations)} />
                <AnalyticsMetric label="Connections" value={formatInt(integrations?.total_connections)} />
                <AnalyticsMetric label="Active connections" value={formatInt(integrations?.active_connections)} />
                <AnalyticsMetric label="Sync jobs" value={formatInt(integrations?.total_sync_jobs)} />
              </div>
              {(integrations?.providers ?? []).length > 0 ? (
                <p className="text-xs text-on-surface-variant">
                  Providers: {(integrations?.providers ?? []).join(", ")}
                </p>
              ) : null}
              <p className="text-xs text-on-surface-variant">
                Credential material is write-only and never appears here. Per-integration health lives in the
                Integrations workspace.
              </p>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Operations"
          title="SLOs, budgets and quality"
          source="Analytics (SLO, budgets, quality)"
          scope="default"
          linkHref="/observability"
          linkLabel="Open Observability"
          loading={loading}
          error={sloStatusError ?? sloBreachesError ?? budgetsStatusError ?? qualityIssuesError ?? marketplaceError}
          onRetry={retry}
          emptyTitle="No SLO data"
          emptyDescription="The backend returned no SLO, budget, or quality signals."
        >
          {sloStatus || sloBreaches || budgetsStatus || qualityIssues || marketplace ? (
            <div className="space-y-4">
              {sloStatus && Object.keys(sloStatus).length > 0 ? (
                <BrutalTable
                  columns={[
                    { key: "service", header: "Service", render: (r: SloRow) => <span className="font-mono text-xs">{r.service}</span> },
                    { key: "measured", header: "Measured", render: (r: SloRow) => formatInt(r.total_measurements) ?? "—" },
                    { key: "compliant", header: "Compliant", render: (r: SloRow) => formatInt(r.compliant) ?? "—" },
                    { key: "rate", header: "Rate (backend)", render: (r: SloRow) => (r.compliance_rate != null ? formatDecimal(r.compliance_rate) : "—") },
                  ]}
                  rows={Object.entries(sloStatus)
                    .slice(0, 8)
                    .map(([service, status]) => ({ service, ...status }))}
                  emptyMessage="No SLO measurements"
                />
              ) : null}
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="SLO breaches" value={formatInt(sloBreaches?.count)} />
                <AnalyticsMetric label="Budgets tracked" value={formatInt(budgetsStatus?.count)} hint="Spend is computed only after an explicit budget check" />
                <AnalyticsMetric label="Quality issues" value={formatInt(qualityIssues?.count)} />
                <AnalyticsMetric label="Marketplace events" value={formatInt(marketplace?.total_events)} />
              </div>
            </div>
          ) : null}
        </DomainCard>

        <DomainCard
          eyebrow="Platform"
          title="Alerts, recommendations and budgets"
          source="Analytics (alerts, recommendations)"
          scope="default"
          linkHref="/observability"
          linkLabel="Open Observability"
          loading={loading}
          error={alertsSummaryError ?? recommendationsError}
          onRetry={retry}
          emptyTitle="No alert data"
          emptyDescription="The backend returned no alert or recommendation signals."
        >
          {alertsSummary || recommendations ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <AnalyticsMetric label="Alert rules" value={formatInt(alertsSummary?.total_alerts)} />
                <AnalyticsMetric label="Active rules" value={formatInt(alertsSummary?.active)} />
                <AnalyticsMetric label="Triggered today" value={formatInt(alertsSummary?.triggered_today)} />
                <AnalyticsMetric label="Recommendations" value={formatInt(recommendations?.count)} />
              </div>
              {(recommendations?.recommendations ?? []).length > 0 ? (
                <BrutalTable
                  columns={[
                    { key: "title", header: "Recommendation", render: (r) => <span className="font-bold">{r.title ?? r.category ?? "—"}</span> },
                    { key: "priority", header: "Priority", render: (r) => <BrutalBadge>{r.priority ?? "—"}</BrutalBadge> },
                    { key: "impact", header: "Impact USD", render: (r) => formatUsd(r.estimated_impact_usd) ?? "—" },
                  ]}
                  rows={(recommendations?.recommendations ?? []).slice(0, 8)}
                  emptyMessage="No recommendations"
                />
              ) : null}
            </div>
          ) : null}
        </DomainCard>
      </div>

      <BrutalCard eyebrow="Executive insights" title="Generated analysis">
        {loading ? (
          <LoadingPanel />
        ) : (
          <div className="space-y-4">
            <BrutalEmptyState
              title="Not exposed by API"
              description="No backend endpoint provides executive insights. Use Ask AI for manual analysis."
            />
            <div className="flex flex-wrap gap-2">
              <BrutalButton variant="ghost" size="sm" href="/ai">
                Ask AI for manual analysis
              </BrutalButton>
            </div>
          </div>
        )}
      </BrutalCard>

      <p className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
        Methodology — FinOps cents are integers divided by 100 for USD display and never mixed with analytics
        USD floats at source. Risk, compliance and reliability scores are backend heuristics rendered verbatim,
        never legal conclusions. SRE analytics queries are authenticated but not tenant-filtered by the
        backend. Data-governance zeros may be degraded-path fallbacks. No number here is generated,
        interpolated, or smoothed on the client.
      </p>
    </div>
  );
}
