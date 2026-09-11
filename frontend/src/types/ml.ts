"use client";

/**
 * AI/ML Platform domain types. Shapes mirror the exact backend serializers
 * in backend/app/api/aiml.py (`_*_to_dict`) — never invent fields.
 *
 * Base path: /api/v1/ai. Lists return arrays (or {items}) with NO totals;
 * counts derived client-side are labeled "listed", never totals.
 *
 * Safety rules (locked Phase 25 decisions):
 * - Prompt version `content` is NEVER represented here: it may contain
 *   system prompts. Prompt forms are write-only.
 * - Risk `score` renders only alongside the backend's verbatim caveat:
 *   "governance heuristic — not a legal conclusion".
 * - No endpoint returns training jobs, inference history, deployment
 *   listings, suite/run listings, schedules, memory, or audit events —
 *   those capabilities are NOT EXPOSED BY API, so no types exist for them.
 */

export interface PaginatedItems<T> {
  items: T[];
}

/** GET /ai/models row — _model_to_dict. No credential fields exist. */
export interface MLModel {
  id: string;
  tenant?: string | null;
  provider?: string | null;
  name?: string | null;
  version?: string | null;
  type?: string | null;
  capabilities?: Record<string, unknown>;
  license?: string | null;
  region?: string | null;
  status?: string | null;
  risk_level?: string | null;
  owner?: string | null;
  model_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** GET /ai/models/{id}/versions row — _version_to_dict. Immutable. */
export interface MLModelVersion {
  id: string;
  model_id?: string | null;
  version?: string | null;
  artifact?: string | null;
  source?: string | null;
  training_metadata?: Record<string, unknown>;
  evaluation_version?: string | null;
  deployment_version?: string | null;
  policy_version?: string | null;
  provenance?: Record<string, unknown>;
  immutable?: boolean | null;
  created_at?: string | null;
}

/** GET /ai/providers row — _provider_to_dict. */
export interface MLProvider {
  id: string;
  tenant?: string | null;
  provider?: string | null;
  display_name?: string | null;
  models?: string[];
  regions?: string[];
  pricing?: Record<string, unknown>;
  data_processing_policy?: Record<string, unknown>;
  availability?: string | null;
  security_status?: string | null;
  contract_metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

/** GET /ai/prompts row — registry metadata ONLY. Version `content` is
 * deliberately absent: it may contain system prompts. */
export interface MLPrompt {
  id: string;
  tenant?: string | null;
  prompt_id?: string | null;
  name?: string | null;
  purpose?: string | null;
  classification?: string | null;
  model_compatibility?: string[];
  owner?: string | null;
  status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Prompt version metadata — content deliberately absent (see above). */
export interface MLPromptVersionMeta {
  id: string;
  prompt_id?: string | null;
  version?: string | null;
  owner?: string | null;
  purpose?: string | null;
  classification?: string | null;
  immutable?: boolean | null;
  created_at?: string | null;
}

export interface MLPromptDetail extends MLPrompt {
  version?: MLPromptVersionMeta | null;
  versions?: MLPromptVersionMeta[];
  latest_version?: MLPromptVersionMeta | null;
}

/** GET /ai/evaluations/runs/{id} — _run_to_dict. Metrics echoed verbatim. */
export interface MLEvaluationRun {
  id: string;
  tenant?: string | null;
  suite_id?: string | null;
  model_id?: string | null;
  prompt_version_id?: string | null;
  dataset_version?: string | null;
  parameters?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  artifacts?: Record<string, unknown>;
  status?: string | null;
  reproducible_hash?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** GET /ai/evaluations/compare result (service-defined shape). */
export interface MLEvaluationCompare {
  tenant?: string | null;
  candidate_run_id?: string | null;
  baseline_run_id?: string | null;
  regression?: boolean;
  metric_deltas?: Record<string, number>;
}

/** GET /ai/guardrails row. */
export interface MLGuardrail {
  id: string;
  tenant?: string | null;
  name?: string | null;
  scope?: string | null;
  policy?: Record<string, unknown>;
  rate_limit?: number | null;
  enabled?: boolean | null;
  environment?: string | null;
  created_at?: string | null;
}

/** GET /ai/risks row. `score` renders ONLY with the verbatim caveat. */
export interface MLRisk {
  id: string;
  tenant?: string | null;
  system?: string | null;
  model_id?: string | null;
  risk_id?: string | null;
  severity?: string | null;
  likelihood?: string | null;
  impact?: string | null;
  owner?: string | null;
  mitigation?: string | null;
  status?: string | null;
  score?: number | null;
  created_at?: string | null;
}

/** Verbatim backend caveat — MUST accompany any rendered risk score. */
export const RISK_SCORE_CAVEAT = "governance heuristic — not a legal conclusion";

/** GET /ai/model-cards/{model} row(s). */
export interface MLModelCard {
  id: string;
  tenant?: string | null;
  model_id?: string | null;
  purpose?: string | null;
  capabilities?: Record<string, unknown> | string[] | null;
  limitations?: Record<string, unknown> | string[] | string | null;
  risk?: string | null;
  evaluation_summary?: Record<string, unknown>;
  data_policy?: string | null;
  provider?: string | null;
  version?: string | null;
  approved_environments?: string[];
  created_at?: string | null;
}

/** GET /ai/system-cards/{system} row(s). */
export interface MLSystemCard {
  id: string;
  tenant?: string | null;
  system?: string | null;
  purpose?: string | null;
  inputs?: Record<string, unknown>;
  outputs?: Record<string, unknown>;
  models?: string[];
  tools?: string[];
  permissions?: string[];
  human_oversight?: string | null;
  failure_modes?: string[];
  evaluation?: Record<string, unknown>;
  deployment_scope?: string | null;
  created_at?: string | null;
}

/** GET /ai/monitoring/{model} snapshot row. Values echoed verbatim. */
export interface MLMonitoringSnapshot {
  id: string;
  tenant?: string | null;
  model_id?: string | null;
  provider?: string | null;
  availability?: string | null;
  latency_ms?: number | null;
  error_rate?: number | null;
  token_usage?: number | null;
  cost?: number | null;
  quality?: number | null;
  safety?: number | null;
  drift?: Record<string, unknown>;
  created_at?: string | null;
}

/** GET /ai/provenance/{model} — stored metadata echoed verbatim, never invented. */
export interface MLProvenance {
  model_id: string;
  tenant?: string | null;
  provider?: string | null;
  name?: string | null;
  version?: string | null;
  versions?: Array<Record<string, unknown>>;
  provenance?: Record<string, unknown>;
  latest_provenance?: Record<string, unknown>;
  training_metadata?: Record<string, unknown>;
  found?: boolean;
}

/** GET /ai/policies/decisions row (governance policy engine mirror). */
export interface MLPolicyDecision {
  id?: string | null;
  name?: string | null;
  type?: string | null;
  effect?: string | null;
  priority?: number | null;
  status?: string | null;
  version?: string | null;
}

/** POST /ai/deployments response (C2 — in-memory backend record). */
export interface MLDeployment {
  id: string;
  tenant?: string | null;
  model_id?: string | null;
  version?: string | null;
  environment?: string | null;
  provider?: string | null;
  approved_by?: string | null;
  requested_by?: string | null;
  status?: string | null;
  metadata?: Record<string, unknown>;
  model_name?: string | null;
  created_at?: string | null;
  rolled_back_at?: string | null;
  rolled_back_by?: string | null;
}

/** POST /ai/gateway/route response (C2 read-effect action). */
export interface MLGatewayRoute {
  decision: string;
  reason?: string | null;
  classification?: string | null;
  cross_border?: boolean | null;
  model_id?: string | null;
  model_name?: string | null;
  model_version?: string | null;
  provider?: string | null;
  region?: string | null;
  cost_estimate?: number | null;
  latency_estimate_ms?: number | null;
  quality_estimate?: number | null;
  score?: number | null;
  purpose?: string | null;
  budget?: number | null;
}

/** POST /ai/gateway/invoke response (C2 — provider is backend-MOCKED). */
export interface MLGatewayInvokeResult {
  model_id?: string | null;
  model_name?: string | null;
  model_version?: string | null;
  provider?: string | null;
  region?: string | null;
  classification?: string | null;
  purpose?: string | null;
  prompt_fingerprint?: string | null;
  output?: unknown;
  cost?: number | null;
  latency_ms?: number | null;
  tokens?: number | null;
  provider_call?: Record<string, unknown>;
}

/** POST /ai/monitoring/drift response (C2 read-effect action). */
export interface MLDriftResult {
  drift_detected?: boolean;
  data_drift?: boolean;
  quality_drift?: boolean;
  insufficient_data?: boolean;
  sufficient_data?: boolean;
  sample_count?: number;
  window?: number;
  reason?: string | null;
  details?: Record<string, unknown>;
}

/** POST /ai/guardrails/check-{input,output} + /ai/policies/evaluate|simulate (C2). */
export interface MLCheckResult {
  decision: string;
  reason?: string | null;
  allowed?: boolean;
  [key: string]: unknown;
}

export const ML_MODEL_STATUSES = ["DRAFT", "APPROVED", "ACTIVE", "DEPRECATED", "RETIRED", "BLOCKED"] as const;
export const ML_PROVIDER_AVAILABILITY = ["AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "MAINTENANCE"] as const;
export const ML_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export const ML_APPROVAL_DECISIONS = ["approved", "rejected", "approve", "reject", "allow", "deny"] as const;

/** Rationale/output preview length: presentation safeguard, not a safety claim. */
export const ML_PREVIEW_CHARS = 800;
