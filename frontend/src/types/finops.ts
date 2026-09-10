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
