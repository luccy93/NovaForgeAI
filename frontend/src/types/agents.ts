"use client";

/**
 * Agent Platform domain types. Shapes mirror the exact backend serializers —
 * never invent fields.
 *
 * Sources:
 * - GET /agents/v2 (+/{agent}, /runs, /runs/{id}) — backend/app/api/agents_v2.py
 * - GET /ai-dev/agents* — backend/app/api/ai_dev.py (run/plan/checkpoint/
 *   feedback payloads; AgentOut/PlanOut/CheckpointOut live in types/code.ts
 *   and are reused, not duplicated here)
 *
 * Safety rules (locked Phase 24 decisions):
 * - `decision.reasoning` (v2 run response) is never represented here.
 * - Checkpoint `state` blobs are never rendered; summary/sequence only.
 * - Plan `rationale` renders as truncated plain text labeled PLAN RATIONALE.
 * - No endpoint returns version history, memory, schedules, or audit
 *   events — those capabilities are NOT EXPOSED BY API, so no types exist
 *   for them.
 */

export interface PaginatedItems<T> {
  items: T[];
  count: number;
}

/** GET /agents/v2 registry row (no auth). */
export interface AgentCatalogEntry {
  name: string;
  role: string;
  version: string;
  description: string;
  goals: string[];
}

/** GET /agents/v2/{agent} detail (no auth). */
export interface AgentCatalogDetail extends AgentCatalogEntry {
  model: string;
  temperature: number;
  permissions: string[];
  require_human_approval: boolean;
}

/** GET /agents/v2/runs row (authenticated, user-scoped). */
export interface AgentV2Run {
  id: string;
  agent: string;
  status: string;
  duration_ms?: number | null;
  tokens_used?: number | null;
  model_used?: string | null;
  error?: string | null;
  created_at?: string | null;
}

/** Safe subset of a v2 tool call (success/duration only — never payloads). */
export interface AgentV2ToolCall {
  success: boolean;
  duration_ms?: number | null;
}

/** GET /agents/v2/runs/{id} detail. `reasoning` is deliberately absent. */
export interface AgentV2RunDetail extends AgentV2Run {
  pipeline?: string | null;
  input?: unknown;
  output?: unknown;
  extra?: {
    confidence?: number | null;
    risk?: string | null;
    files_affected?: string[];
    tool_calls?: AgentV2ToolCall[];
  } | null;
}

/** POST /agents/v2/{agent}/run response (C2 execution). */
export interface AgentV2RunResult {
  run_id: string;
  agent: string;
  output?: unknown;
  status: string;
  decision?: {
    confidence?: number | null;
    risk_level?: string | null;
    files_affected?: string[];
  } | null;
  duration_ms?: number | null;
  tokens_used?: number | null;
  model_used?: string | null;
  error?: string | null;
}

/** POST /agents/v2/pipeline response (C2 execution). */
export interface AgentV2PipelineResult {
  workflow_id: string;
  status: string;
  steps: unknown[];
  errors: unknown[];
}

/** POST /ai-dev/agents request body (C2 enqueue). */
export interface AgentEnqueueBody {
  repository_id: string;
  agent_type?: string;
  name?: string;
  goal?: string;
  files?: Array<Record<string, unknown>>;
  branch?: string;
  commit_sha?: string;
  model?: string;
  throttle?: number;
  budget_tokens?: number;
  checkpoint_limit?: number;
  metadata_?: Record<string, unknown>;
}

/** POST /ai-dev/agents/{run}/feedback request body (C2). */
export interface AgentFeedbackBody {
  feedback_type?: string;
  message?: string;
  patch_id?: string;
  checkpoint_id?: string;
}

/** GET /ai-dev/agents/{run}/feedback row. */
export interface AgentFeedback {
  id: string;
  feedback_type: string;
  message?: string | null;
  patch_id?: string | null;
  checkpoint_id?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

/** Operational timeline event derived ONLY from returned records. */
export interface AgentTimelineEvent {
  id: string;
  kind:
    | "RUN_CREATED"
    | "RUN_STATUS"
    | "PLAN_CREATED"
    | "CHECKPOINT_CREATED"
    | "FEEDBACK";
  label: string;
  detail: string;
  at: string | null;
}

export const AGENT_V2_STATUSES = [
  "idle",
  "running",
  "completed",
  "failed",
  "blocked",
  "cancelled",
] as const;

/** Rationale/output preview length: presentation safeguard, not a safety claim. */
export const RATIONALE_PREVIEW_CHARS = 800;
