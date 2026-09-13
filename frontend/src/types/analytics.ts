"use client";

/**
 * Executive Analytics (Phase 28, C1 read-only) — verbatim backend shapes.
 *
 * Backend: backend/app/api/analytics.py (prefix /analytics, NO auth,
 * client-supplied tenant), backend/app/api/security.py (prefix /security,
 * NO auth), backend/app/api/secops.py, backend/app/api/sre.py,
 * backend/app/api/datagov.py.
 *
 * Scope rule: /analytics/* and /security/* are called with tenant=default
 * and MUST be labeled BACKEND SCOPE: DEFAULT / UNAUTHENTICATED in the UI.
 * Never present them as tenant-scoped.
 */

/** POST /analytics/costs/summary group row — cost_service.get_cost_summary. */
export interface AnalyticsCostGroup {
  value?: string;
  total_usd?: number;
  count?: number;
  estimated_usd?: number;
}

/** POST /analytics/costs/summary response (USD floats). */
export interface AnalyticsCostSummary {
  tenant?: string;
  group_by?: string;
  start_time?: string | null;
  end_time?: string | null;
  total_usd?: number;
  entry_count?: number;
  estimated_usd?: number;
  actual_usd?: number;
  groups?: AnalyticsCostGroup[];
}

/** POST /analytics/costs/trend bucket — the only true cost time-series. */
export interface AnalyticsCostTrendPoint {
  period?: string;
  granularity?: string;
  total_usd?: number;
  entry_count?: number;
  estimated_usd?: number;
}

/** POST /analytics/costs/trend response. */
export interface AnalyticsCostTrend {
  trend?: AnalyticsCostTrendPoint[];
  count?: number;
}

/** GET /analytics/costs/ai-breakdown response (USD floats). */
export interface AnalyticsAiBreakdownSlice {
  value?: string;
  total_usd?: number;
  count?: number;
  estimated_usd?: number;
}

/** GET /analytics/costs/ai-breakdown response. */
export interface AnalyticsAiBreakdown {
  tenant?: string;
  start_time?: string | null;
  end_time?: string | null;
  total_ai_cost_usd?: number;
  actual_usd?: number;
  estimated_usd?: number;
  entry_count?: number;
  by_model?: AnalyticsAiBreakdownSlice[];
  by_provider?: AnalyticsAiBreakdownSlice[];
  by_agent?: AnalyticsAiBreakdownSlice[];
}

/** POST /analytics/metrics/query|trend bucket point. */
export interface AnalyticsMetricPoint {
  tenant?: string;
  metric_name?: string;
  granularity?: string;
  dimensions?: Record<string, unknown>;
  period_start?: string;
  value?: number;
  count?: number;
  min?: number | null;
  max?: number | null;
  avg?: number | null;
  p95?: number | null;
  p99?: number | null;
}

/** POST /analytics/metrics/query response. */
export interface AnalyticsMetricQueryResponse {
  points?: AnalyticsMetricPoint[];
  count?: number;
}

/** POST /analytics/metrics/trend response. */
export interface AnalyticsMetricTrendResponse {
  trend?: AnalyticsMetricPoint[];
  count?: number;
}

/** POST /analytics/metrics/aggregate response. */
export interface AnalyticsMetricAggregate {
  tenant?: string;
  metric_name?: string;
  sum?: number;
  avg?: number | null;
  min?: number | null;
  max?: number | null;
  count?: number;
  p95?: number | null;
  p99?: number | null;
}

/** GET /analytics/metrics/list response. */
export interface AnalyticsMetricsList {
  metrics?: string[];
  count?: number;
}

/** POST /analytics/engineering/dora response. */
export interface AnalyticsDora {
  deployment_frequency?: number;
  lead_time_minutes?: number;
  change_failure_rate?: number;
  mttr_minutes?: number;
}

/** GET /analytics/ai/model-comparison row. */
export interface AnalyticsModelComparisonRow {
  model?: string;
  providers?: string[];
  calls?: number;
  success_rate?: number;
  error_rate?: number;
  avg_latency_ms?: number | null;
  p95_latency_ms?: number | null;
  total_tokens?: number;
  avg_tokens_per_call?: number | null;
  cached_tokens?: number;
  total_cost_usd?: number;
  avg_cost_per_call_usd?: number | null;
  cost_per_1k_tokens_usd?: number | null;
}

/** GET /analytics/ai/model-comparison response. */
export interface AnalyticsModelComparison {
  comparison?: AnalyticsModelComparisonRow[];
  count?: number;
}

/** GET /analytics/security/summary response. */
export interface AnalyticsSecuritySummary {
  total_findings?: number;
  by_severity?: Record<string, number>;
  remediated?: number;
  open?: number;
  open_critical?: number;
  remediation_rate?: number;
  scans_count?: number;
  gate_failures?: number;
}

/** GET /analytics/slo/status response: {service: {...}}. */
export interface AnalyticsSloServiceStatus {
  total_measurements?: number;
  compliant?: number;
  compliance_rate?: number;
}

export type AnalyticsSloStatus = Record<string, AnalyticsSloServiceStatus>;

/** GET /analytics/slo/breaches response. */
export interface AnalyticsSloBreaches {
  breaches?: Array<Record<string, unknown>>;
  count?: number;
}

/** GET /analytics/alerts/summary response. */
export interface AnalyticsAlertsSummary {
  total_alerts?: number;
  active?: number;
  triggered_today?: number;
}

/** GET /analytics/alerts/history response. */
export interface AnalyticsAlertsHistory {
  history?: Array<Record<string, unknown>>;
  count?: number;
}

/** GET /analytics/budgets/status budget row. */
export interface AnalyticsBudgetStatus {
  budget_id?: string;
  name?: string;
  scope?: string;
  period?: string;
  limit_usd?: number;
  status?: string;
  current_spend_usd?: number | null;
  threshold_percentage?: number | null;
  remaining_usd?: number | null;
}

/** GET /analytics/budgets/status response. */
export interface AnalyticsBudgetsStatus {
  budgets?: AnalyticsBudgetStatus[];
  count?: number;
}

/** GET /analytics/quality/issues response. */
export interface AnalyticsQualityIssues {
  issues?: Array<Record<string, unknown>>;
  count?: number;
}

/** GET /analytics/recommendations row. */
export interface AnalyticsRecommendation {
  recommendation_id?: string;
  category?: string;
  title?: string;
  description?: string;
  reason?: string;
  evidence?: Record<string, unknown>;
  estimated_impact_usd?: number | null;
  confidence?: string;
  risk?: string;
  priority?: string;
  suggested_action?: string;
  status?: string;
}

/** GET /analytics/recommendations response. */
export interface AnalyticsRecommendations {
  recommendations?: AnalyticsRecommendation[];
  count?: number;
}

/** GET /analytics/forecast/{metric_name} stored-forecast row. */
export interface AnalyticsForecastPoint {
  forecast_id?: string;
  tenant?: string;
  metric_name?: string;
  forecast_date?: string;
  predicted_value?: number | null;
  confidence_lower?: number | null;
  confidence_upper?: number | null;
  scope?: string;
  methodology?: string;
  status?: string;
  created_at?: string | null;
}

/** GET /analytics/forecast/{metric_name} response. */
export interface AnalyticsMetricForecasts {
  tenant?: string;
  metric_name?: string;
  forecasts?: AnalyticsForecastPoint[];
  count?: number;
  note?: string;
}

/** GET /analytics/marketplace/summary response. */
export interface AnalyticsMarketplaceSummary {
  total_events?: number;
  unique_packages?: number;
  unique_users?: number;
  by_type?: Record<string, number>;
}

/** GET /analytics/dashboard/overview response (lifetime totals). */
export interface AnalyticsDashboardOverview {
  tenant?: string;
  events?: {
    total?: number;
    processed?: number;
    duplicates?: number;
    late?: number;
    invalid?: number;
    tenant_events?: number;
  };
  total_cost_usd?: number;
  ai_usage?: Record<string, unknown>;
  dora?: AnalyticsDora;
  alerts?: AnalyticsAlertsSummary;
}

/** POST /analytics/dashboard response — windowed snapshot, no series. */
export interface AnalyticsDashboardSnapshot {
  tenant?: string;
  start_time?: string | null;
  end_time?: string | null;
  filters?: Record<string, unknown>;
  costs?: AnalyticsCostSummary;
  ai_usage?: Record<string, unknown>;
  dora?: AnalyticsDora;
  security?: AnalyticsSecuritySummary;
  slo?: AnalyticsSloStatus;
  budgets?: AnalyticsBudgetStatus[] | Record<string, unknown>;
  alerts?: AnalyticsAlertsSummary;
  data_quality?: Record<string, unknown>;
  recommendations?: Record<string, unknown>;
}

/** GET /security/findings/summary — findings_service.get_summary. */
export interface SecurityFindingsSummary {
  total?: number;
  by_severity?: Record<string, number>;
  [key: string]: unknown;
}

/** GET /security/risk/summary — backend-weighted heuristic, verbatim only. */
export interface SecurityRiskSummary {
  total_findings?: number;
  by_severity?: Record<string, number>;
  risk_score?: number;
  risk_level?: string;
}

/** GET /security/risk/score — backend-weighted heuristic, verbatim only. */
export interface SecurityRiskScore {
  score?: number;
  level?: string;
}

/** GET /security/reports/{report_type} — generated report, shape varies. */
export interface SecurityReport {
  [key: string]: unknown;
}

/** GET /security/dashboard — dashboard_service.get_dashboard (days window). */
export interface SecurityDashboardFull {
  generated_at?: string;
  period_days?: number;
  severity_breakdown?: Record<string, number>;
  status_breakdown?: Record<string, number>;
  total_findings?: number;
  top_risks?: Array<{
    id?: string;
    severity?: string;
    rule?: string;
    message?: string;
    risk_score?: number;
    repository?: string;
  }>;
  scan_history?: Array<{
    id?: string;
    type?: string;
    status?: string;
    target?: string;
    findings?: number;
    duration_ms?: number | null;
  }>;
  gate_status?: {
    pass_rate?: number;
    total_evaluations?: number;
    blocked?: number;
    warned?: number;
    passed?: number;
  };
  /** Backend heuristic (100 - 5*critical/high - 2*medium). Never legal compliance. */
  compliance_score?: number;
  summary?: Record<string, number>;
}

/** GET /secops/risk/snapshots row — no timestamps; order is newest-first. */
export interface SecOpsRiskSnapshotRow {
  id?: string;
  risk_score?: number;
  resource?: string;
  severity?: string;
}

/** GET /secops/risk/snapshots response. */
export interface SecOpsRiskSnapshots {
  items?: SecOpsRiskSnapshotRow[];
}

/** GET /sre/dashboard response. */
export interface SreDashboard {
  services?: { total?: number; degraded?: number };
  slos?: { total?: number; exhausted_budgets?: number };
  alerts?: { firing?: number };
  incidents?: { active?: number; severe?: number };
  dependencies?: unknown;
  reliability?: unknown;
  generated_at?: string;
}

/** GET /sre/capacity/trend — point summary, NOT per-day buckets. */
export interface SreCapacityTrend {
  service_id?: string;
  metric?: string;
  samples?: number;
  current?: number | null;
  peak?: number | null;
  average?: number | null;
  limit?: number | null;
  headroom_percent?: number | null;
  growth_per_day?: number | null;
  forecast_exhaustion_at?: string | null;
  saturation?: string;
}

/** GET /sre/reliability-score — explainable components; unavailable reported, not guessed. */
export interface SreReliabilityScore {
  [key: string]: unknown;
}

/** GET /governance/dashboard (datagov) — degraded paths substitute 0; cannot be distinguished. */
export interface DatagovDashboard {
  tenant?: string;
  generated_at?: string;
  assets_total?: number;
  assets_by_classification?: Record<string, number>;
  classifications_total?: number;
  advisory_classifications?: number;
  retention_expiring?: number;
  retention_expired_items?: Array<{ asset_id?: string; state?: string }>;
  [key: string]: unknown;
}

/** GET /enterprise/integrations/metrics/overview — counts only, org-scoped. */
export interface EnterpriseIntegrationsMetrics {
  total_integrations?: number;
  active_integrations?: number;
  total_connections?: number;
  active_connections?: number;
  revoked_connections?: number;
  total_sync_jobs?: number;
  providers?: string[];
}
