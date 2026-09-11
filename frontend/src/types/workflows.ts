"use client";

/**
 * Workflow Automation (V66) domain types. Shapes mirror the exact backend
 * serializers in backend/app/api/workflow.py — never invent fields.
 *
 * Notes:
 * - List endpoints return `{items}` with NO `total`; counts derived
 *   client-side are labeled "listed", never presented as totals.
 * - No endpoint returns workflow definition steps/nodes/edges, so no
 *   DAG type exists. Execution visibility comes from run + step-run
 *   records only, rendered as a chronological timeline — never a graph.
 * - The legacy `api.listWorkflowRuns` helper calls GET /workflows/runs,
 *   which does not exist: OUT OF SCOPE — BACKEND ENDPOINT NOT AVAILABLE.
 *   Per-workflow runs use `GET /{workflow_id}/runs` via workflowRuns().
 */

export interface PaginatedItems<T> {
  items: T[];
}

/** POST /workflows response. */
export interface WorkflowCreated {
  id: string;
  name: string;
  version: string;
  status: string;
}

/** GET /workflows row. */
export interface WorkflowListItem {
  id: string;
  name: string;
  version: string;
  status: string;
}

/** GET /workflows/{id} response. */
export interface WorkflowDetail extends WorkflowListItem {
  description?: string | null;
}

/** POST /workflows/{id}/versions response. */
export interface WorkflowVersionCreated {
  id: string;
  version: string;
  workflow_id: string;
}

/** GET /workflows/{id}/versions row. Immutable; no content editing exists. */
export interface WorkflowVersion {
  id: string;
  version: string;
  status: string;
  dag_hash?: string | null;
}

/** POST /workflows/{id}/publish response. */
export interface WorkflowVersionPublished {
  id: string;
  version: string;
  status: string;
}

/** POST /workflows/{id}/trigger and /run response. */
export interface WorkflowRunStarted {
  run_id: string;
  execution_id: string;
  status: string;
  workflow_version_id: string;
}

/** GET /workflows/{id}/runs row. */
export interface WorkflowRunListItem {
  run_id: string;
  status: string;
  execution_id: string;
  workflow_version_id: string;
}

/** GET /workflows/runs/{run_id} response. */
export interface WorkflowRunDetail {
  run_id: string;
  workflow_version_id: string;
  status: string;
  execution_id: string;
  trace_id?: string | null;
}

/** GET /workflows/runs/{run_id}/steps row — timeline source, not a DAG. */
export interface WorkflowStepRun {
  step_id: string;
  status: string;
  attempt: number;
  error?: string | null;
}

/** Run control responses (pause/resume/cancel). */
export interface WorkflowRunControl {
  run_id: string;
  status: string;
}

/** GET /workflows/approvals row. */
export interface WorkflowApproval {
  id: string;
  run_id: string;
  step_id: string;
  status: string;
  binding_hash?: string | null;
}

/** POST /workflows/approvals/{id}/decide response. */
export interface WorkflowApprovalDecision {
  id: string;
  status: string;
  decision: string;
}

/** GET /workflows/schedules row. */
export interface WorkflowSchedule {
  id: string;
  workflow_id: string;
  trigger_type: string;
  cron?: string | null;
  enabled: boolean;
}

/** POST /workflows/schedules response. */
export interface WorkflowScheduleCreated {
  id: string;
  workflow_id: string;
  trigger_type: string;
}

/** GET /workflows/templates row (built-in + tenant templates). */
export interface WorkflowTemplate {
  name: string;
  version: string;
  category?: string | null;
  is_published?: boolean;
  owner?: string | null;
}

/** POST /workflows/templates response. */
export interface WorkflowTemplateCreated {
  id: string;
  name: string;
  version: string;
}

/** GET /workflows/human-tasks row. */
export interface WorkflowHumanTask {
  id: string;
  assignee: string;
  status: string;
  run_id: string;
}

/** GET /workflows/business-processes row. */
export interface WorkflowBusinessProcess {
  id: string;
  current_state: string;
  run_id: string;
}

/** POST /workflows/runs/{id}/replay response (FAILED runs only). */
export interface WorkflowReplay {
  new_run_id: string;
  original_run_id: string;
  status: string;
}

/** POST /workflows/runs/{id}/recover response. */
export interface WorkflowRecovery {
  run_id: string;
  status: string;
}

/** GET /workflows/sla/{run_id} response. */
export interface WorkflowSla {
  process_id: string;
  sla_deadline: string | null;
  breached: boolean;
  current_state: string;
}

/** GET /workflows/health response (backend-computed aggregates). */
export interface WorkflowHealthSummary {
  tenant: string;
  total: number;
  success: number;
  failed: number;
  success_rate: number;
}

/** GET /workflows/anomalies row (backend heuristic, verbatim). */
export interface WorkflowAnomaly {
  run_id: string;
  type: string;
  duration_ms?: number;
}

export const WORKFLOW_STATUSES = ["DRAFT", "ACTIVE", "PAUSED", "DEPRECATED", "RETIRED"] as const;
export const WORKFLOW_RUN_STATUSES = [
  "PENDING",
  "RUNNING",
  "WAITING",
  "PAUSED",
  "FAILED",
  "COMPENSATING",
  "COMPLETED",
  "CANCELLED",
  "TIMED_OUT",
] as const;
export const WORKFLOW_APPROVAL_STATUSES = ["PENDING", "APPROVED", "DENIED", "EXPIRED", "CANCELLED"] as const;
export const WORKFLOW_APPROVAL_DECISIONS = ["APPROVED", "DENIED", "CANCELLED"] as const;
