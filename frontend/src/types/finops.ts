/** Governed FinOps domain types (Phase 20, V69 backend).
 *
 * Mirrors the backend serializers in backend/app/finops/ exactly.
 * Only fields the backend actually returns are included. Money is
 * reported in integer cents with a per-record `currency` — the client
 * never converts currencies.
 */

export interface Paginated<T> {
  items: T[];
  total: number;
}

/** GET /finops/usage/summary — costing.usage_summary. AI fields are best-effort (0 on failure). */
export interface UsageSummary {
  tenant: string;
  cost_records: number;
  spend_cents: number;
  total_tokens: number;
  ai_executions: number;
  ai_tokens: number;
  ai_cost_cents: number;
}

/** One governed cost record — costing._serialize (full field set). */
export interface FinOpsCostRecord {
  id: string;
  tenant: string;
  workspace: string;
  project: string;
  service: string;
  workflow: string;
  model: string;
  provider: string;
  environment: string;
  region: string;
  resource: string;
  operation: string;
  actor: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  requests: number;
  latency_ms: number | null;
  amount_cents: number;
  currency: string;
  cost_basis: "actual" | "estimated" | "unpriced" | string;
  pricing_version_id: string | null;
  source_type: string;
  source_id: string;
  idempotency_key: string;
  occurred_at: string | null;
  deduplicated?: boolean;
}

/** GET /finops/costs — note spend_cents is the page sum, not the period total. */
export interface CostsPage extends Paginated<FinOpsCostRecord> {
  limit: number;
  offset: number;
  /** Sum of amount_cents over the returned page only. */
  spend_cents: number;
}

export type BudgetStatus = "ACTIVE" | "WARNING" | "EXCEEDED" | "SUSPENDED" | "CLOSED";
export type BudgetPeriod = "daily" | "weekly" | "monthly";
export type Enforcement = "alert" | "require_approval" | "block";

/** Governed budget — budgets._serialize. */
export interface FinOpsBudget {
  id: string;
  tenant: string;
  name: string;
  scope_type: string;
  scope_value: string;
  provider: string;
  model: string;
  environment: string;
  amount_cents: number;
  currency: string;
  period: string;
  warning_threshold: number;
  hard_limit_threshold: number;
  enforcement: string;
  enabled: boolean;
  owner: string;
  approval_policy: string;
  status: string;
}

/** GET /finops/budgets/{id} and POST /finops/budgets/{id}/evaluate. */
export interface BudgetEvaluation extends FinOpsBudget {
  spend_cents: number;
  utilization: number;
  evaluation?: string;
  period_start?: string;
  period_end?: string;
}

/** GET /finops/aggregations item. */
export interface AggregationBucket {
  id: string;
  granularity: string;
  bucket_start: string | null;
  bucket_end: string | null;
  dimensions: Record<string, unknown>;
  total_cents: number;
  record_count: number;
  total_tokens: number;
}

/** GET /finops/forecast — READY state (method is always linear_baseline server-side). */
export interface ForecastReady {
  id: string;
  tenant: string;
  forecast_type: string;
  dimensions: Record<string, unknown>;
  horizon_days: number;
  period_start: string | null;
  predicted_cents: number;
  daily_rate_cents: number;
  confidence: number;
  quality: string;
  method: string;
  basis_buckets: number;
  budget_exhaustion_date: string | null;
  status: "READY";
  cached?: boolean;
  deduplicated?: boolean;
}

/** GET /finops/forecast — explicit insufficient-data state; no forecast is fabricated. */
export interface ForecastInsufficient {
  status: "INSUFFICIENT_DATA";
  reason: string;
  basis_buckets: number;
  cached?: boolean;
}

export type ForecastResult = ForecastReady | ForecastInsufficient;

export function isForecastReady(result: ForecastResult): result is ForecastReady {
  return (result as ForecastReady).status === "READY";
}

/** GET /finops/anomalies item — anomalies._serialize. */
export interface CostAnomaly {
  id: string;
  tenant: string;
  dimension_key: string;
  dimension_value: string;
  granularity: string;
  bucket_start: string | null;
  baseline_cents: number;
  observed_cents: number;
  deviation: number;
  severity: string;
  confidence: number;
  evidence: Record<string, unknown>;
  status: string;
  deduplicated?: boolean;
}

export const BUDGET_STATUSES: BudgetStatus[] = ["ACTIVE", "WARNING", "EXCEEDED", "SUSPENDED", "CLOSED"];
export const BUDGET_PERIODS: BudgetPeriod[] = ["daily", "weekly", "monthly"];
export const ENFORCEMENTS: Enforcement[] = ["alert", "require_approval", "block"];
export const COST_BASES = ["actual", "estimated", "unpriced"] as const;
export const ANOMALY_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export const POLICY_ACTIONS = ["alert", "warn", "require_approval", "block"] as const;
export const GATE_DECISIONS = ["ALLOW", "WARN", "REQUIRE_APPROVAL", "BLOCK"] as const;
export const REPORT_TYPES = ["showback", "chargeback"] as const;
export const GROUP_KEYS = ["workspace", "project", "service", "environment", "provider", "model"] as const;

/** Versioned pricing — pricing._serialize. Rows are immutable history. */
export interface PricingVersion {
  id: string;
  tenant: string;
  provider: string;
  model: string;
  resource: string;
  unit: string;
  input_price_cents_per_m: number;
  output_price_cents_per_m: number;
  request_price_cents: number;
  storage_price_cents: number;
  compute_price_cents: number;
  currency: string;
  effective_from: string | null;
  effective_until: string | null;
  source: string;
  version: number;
  status: string;
  operator: string;
  reason: string;
}

/** Deterministic cost allocation — allocation._serialize. */
export interface CostAllocation {
  id: string;
  tenant: string;
  cost_record_id: string;
  allocation_key: string;
  target_workspace: string;
  target_project: string;
  target_service: string;
  target_environment: string;
  share: number;
  amount_cents: number;
  basis: string;
  deduplicated?: boolean;
}

export interface AllocationsPage extends Paginated<CostAllocation> {
  limit: number;
  offset: number;
}

/** Cost governance policy — governance._serialize. */
export interface FinOpsPolicy {
  id: string;
  tenant: string;
  name: string;
  workspace: string;
  project: string;
  model: string;
  provider: string;
  operation: string;
  max_estimated_cents: number | null;
  action: string;
  enabled: boolean;
  owner: string;
}

/** POST /finops/gate/evaluate — server recomputes the estimate; client value is a floor. */
export interface GateDecision {
  decision: string;
  reason: string;
  estimated_cents: number;
  approval_id: string;
  policy_id: string | null;
  allowed: boolean;
}

export interface ReportLine {
  group: string;
  total_cents: number;
  record_count?: number;
  allocation_count?: number;
}

/** Chargeback/showback report — chargeback._serialize. */
export interface ChargebackReport {
  id: string;
  tenant: string;
  report_type: string;
  period_start: string | null;
  period_end: string | null;
  scope: Record<string, unknown>;
  total_cents: number;
  lines: ReportLine[];
  provenance: Record<string, unknown>;
  deduplicated?: boolean;
}

/** Read-only provider/model comparison row — model_intelligence.compare_models. */
export interface ModelComparisonRow {
  provider: string;
  model: string;
  spend_cents: number;
  requests: number;
  tokens: number;
  cost_per_request_cents: number | null;
  tokens_per_request: number | null;
  avg_latency_ms: number | null;
  input_price_cents_per_m: number | null;
  output_price_cents_per_m: number | null;
  pricing_version: number | null;
}

export interface ModelComparison {
  items: ModelComparisonRow[];
  total: number;
  start: string;
  end: string;
  note: string;
  cached?: boolean;
}

/** Evidence-based recommendation — savings is "UNKNOWN" when not derivable. */
export interface FinOpsRecommendation {
  id: string;
  tenant: string;
  rec_type: string;
  title: string;
  evidence: Record<string, unknown>;
  estimated_savings_cents: number | null;
  savings: number | "UNKNOWN";
  savings_known: boolean;
  confidence: number;
  affected_resource: string;
  risk: string;
  status: string;
}

export interface RecommendationsGenerated {
  recommendations: FinOpsRecommendation[];
  total: number;
}

/** POST /finops/aggregations/run result. */
export interface AggregationRunResult {
  tenant: string;
  granularity: string;
  buckets: number;
  records_scanned: number;
  dimensions: Record<string, unknown>;
  start: string;
  end: string;
}

/** Format integer cents with the record's own currency. No conversion is ever applied. */
export function formatCents(amountCents: number | null | undefined, currency?: string | null): string {
  if (amountCents === null || amountCents === undefined) return "—";
  const sign = amountCents < 0 ? "-" : "";
  const abs = Math.abs(amountCents);
  const major = Math.floor(abs / 100);
  const minor = String(abs % 100).padStart(2, "0");
  const grouped = major.toLocaleString("en-US");
  const code = (currency || "").toUpperCase();
  return `${sign}${grouped}.${minor}${code ? ` ${code}` : ""}`;
}
