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
  AgentCatalogDetail,
  AgentCatalogEntry,
  AgentTimelineEvent,
  AgentV2Run,
  AgentV2RunDetail,
} from "@/types/agents";
import { RATIONALE_PREVIEW_CHARS } from "@/types/agents";
import type { AgentCheckpointOut, AgentOut, AgentPlanOut } from "@/types/code";
import type { AgentFeedback } from "@/types/agents";

/** Backend run payload carries token/attempt counters the shared type omits. */
type AiRun = AgentOut & {
  tokens_used?: number | null;
  attempts?: number | null;
};

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

function statusTone(status: string | undefined): "yellow" | "muted" | "error" | "default" {
  if (status === "completed" || status === "COMPLETED" || status === "success" || status === "APPROVED" || status === "idle") return "yellow";
  if (status === "failed" || status === "FAILED" || status === "error" || status === "DENIED") return "error";
  if (status === "running" || status === "RUNNING" || status === "blocked" || status === "cancelled" || status === "CANCELLED") return "muted";
  return "default";
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

/** Truncated plain-text preview with bounded full view. Never HTML, never "reasoning". */
function TruncatedText({ label, text, previewChars = RATIONALE_PREVIEW_CHARS }: { label: string; text: string; previewChars?: number }) {
  const [expanded, setExpanded] = useState(false);
  if (!text) return null;
  const needsTruncation = text.length > previewChars;
  return (
    <div className="border border-outline bg-surface p-3">
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{label}</p>
      {!expanded ? (
        <>
          <p className="whitespace-pre-wrap break-words text-sm text-on-surface">
            {needsTruncation ? text.slice(0, previewChars) : text}
          </p>
          {needsTruncation ? (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="mt-2 font-mono text-xs uppercase tracking-widest text-primary-container hover:underline"
            >
              View more
            </button>
          ) : null}
        </>
      ) : (
        <>
          <p className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-sm text-on-surface">{text}</p>
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="mt-2 font-mono text-xs uppercase tracking-widest text-primary-container hover:underline"
          >
            Show less
          </button>
        </>
      )}
    </div>
  );
}

type TabId = "overview" | "catalog" | "runs" | "executions" | "timeline";

const NOT_EXPOSED: Array<{ capability: string; reason: string }> = [
  { capability: "Memory", reason: "No backend endpoint exposes agent memory or context." },
  { capability: "Version history", reason: "Agent configs carry a version string only; no history endpoint exists." },
  { capability: "Schedules / triggers", reason: "No backend endpoint exposes agent schedules or triggers." },
  { capability: "Audit history", reason: "No backend endpoint exposes an agent audit event stream." },
];

export function AgentWorkspace() {
  const pushToast = useToastStore((s) => s.push);
  const [active, setActive] = useState<TabId>("overview");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [catalog, setCatalog] = useState<AgentCatalogEntry[] | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedAgentName, setSelectedAgentName] = useState<string | null>(null);
  const [agentInfo, setAgentInfo] = useState<AgentCatalogDetail | null>(null);
  const [agentInfoError, setAgentInfoError] = useState<string | null>(null);
  const [agentInfoLoading, setAgentInfoLoading] = useState(false);

  const [v2Runs, setV2Runs] = useState<AgentV2Run[] | null>(null);
  const [v2RunsError, setV2RunsError] = useState<string | null>(null);
  const [v2AgentFilter, setV2AgentFilter] = useState("ALL");
  const [v2Offset, setV2Offset] = useState(0);
  const [selectedV2RunId, setSelectedV2RunId] = useState<string | null>(null);
  const [v2RunDetail, setV2RunDetail] = useState<AgentV2RunDetail | null>(null);
  const [v2RunDetailError, setV2RunDetailError] = useState<string | null>(null);
  const [v2RunDetailLoading, setV2RunDetailLoading] = useState(false);

  const [aiRuns, setAiRuns] = useState<AiRun[] | null>(null);
  const [aiRunsError, setAiRunsError] = useState<string | null>(null);
  const [aiRepoFilter, setAiRepoFilter] = useState("");
  const [aiStatusFilter, setAiStatusFilter] = useState("ALL");
  const [selectedAiRunId, setSelectedAiRunId] = useState<string | null>(null);
  const [aiRunDetail, setAiRunDetail] = useState<AiRun | null>(null);
  const [aiPlans, setAiPlans] = useState<AgentPlanOut[]>([]);
  const [aiCheckpoints, setAiCheckpoints] = useState<AgentCheckpointOut[]>([]);
  const [aiFeedback, setAiFeedback] = useState<AgentFeedback[]>([]);
  const [aiDetailError, setAiDetailError] = useState<string | null>(null);
  const [aiDetailLoading, setAiDetailLoading] = useState(false);

  const [modal, setModal] = useState<
    | { kind: "enqueue" }
    | { kind: "v2-run"; agentName: string }
    | { kind: "v2-pipeline" }
    | { kind: "plan-create" }
    | { kind: "plan-approve"; plan: AgentPlanOut }
    | { kind: "checkpoint-save" }
    | { kind: "feedback-submit" }
    | { kind: "cancel-run" }
    | null
  >(null);
  const [submitting, setSubmitting] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [execError, setExecError] = useState<string | null>(null);
  const [lastExecResult, setLastExecResult] = useState<Record<string, unknown> | null>(null);
  const [draft, setDraft] = useState({
    repository_id: "",
    agent_type: "refactor",
    name: "agent",
    goal: "",
    branch: "main",
    model: "",
    budget_tokens: "",
    task: "",
    organization_id: "",
    pipeline_agents: "",
    plan_name: "Plan",
    plan_steps: "",
    plan_rationale: "",
    checkpoint_summary: "",
    checkpoint_final: false,
    feedback_type: "CONTINUE",
    feedback_message: "",
    approved_by: "",
    cancel_reason: "",
  });

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

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
    setCatalogError(null);
    setV2RunsError(null);
    setAiRunsError(null);

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

    await Promise.all([
      settle(() => api.agentsV2Catalog(), setCatalog, setCatalogError),
      settle(
        () => api.agentsV2Runs(token, { agentName: v2AgentFilter !== "ALL" ? v2AgentFilter : undefined, limit: 20, offset: v2Offset }),
        setV2Runs,
        setV2RunsError,
      ),
      settle(
        () =>
          api.aiDevListAgents(token, {
            repositoryId: aiRepoFilter.trim() || undefined,
            status: aiStatusFilter !== "ALL" ? aiStatusFilter : undefined,
            limit: 50,
          }),
        (value) => setAiRuns(Array.isArray(value?.items) ? value.items : []),
        setAiRunsError,
      ),
    ]);

    if (!controller.signal.aborted && seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, [v2AgentFilter, v2Offset, aiRepoFilter, aiStatusFilter]);

  const loadAgentInfo = useCallback(async (agentName: string) => {
    setAgentInfoLoading(true);
    setAgentInfoError(null);
    try {
      const info = await api.agentsV2Info(agentName);
      setAgentInfo(info);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setAgentInfoError(e instanceof Error ? e.message : "Agent info unavailable");
    } finally {
      setAgentInfoLoading(false);
    }
  }, []);

  const loadV2RunDetail = useCallback(async (runId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setV2RunDetailLoading(true);
    setV2RunDetailError(null);
    try {
      const detail = await api.agentsV2RunGet(token, runId);
      setV2RunDetail(detail);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setV2RunDetailError(e instanceof Error ? e.message : "Run unavailable");
    } finally {
      setV2RunDetailLoading(false);
    }
  }, []);

  const loadAiRunDetail = useCallback(async (runId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setAiDetailLoading(true);
    setAiDetailError(null);
    try {
      const [agent, plansData, checkpointsData, feedbackData] = await Promise.all([
        api.aiDevGetAgent(token, runId),
        api.aiDevAgentPlans(token, runId),
        api.aiDevAgentCheckpoints(token, runId),
        api.agentsAiDevFeedback(token, runId),
      ]);
      setAiRunDetail(agent);
      setAiPlans(Array.isArray(plansData.items) ? plansData.items : []);
      setAiCheckpoints(Array.isArray(checkpointsData.items) ? checkpointsData.items : []);
      setAiFeedback(Array.isArray(feedbackData.items) ? feedbackData.items : []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setAiDetailError(e instanceof Error ? e.message : "Run unavailable");
    } finally {
      setAiDetailLoading(false);
    }
  }, []);

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
      pushToast("error", e instanceof Error ? e.message : fallback);
    },
    [pushToast],
  );

  function resetDraft() {
    setDraft({
      repository_id: "",
      agent_type: "refactor",
      name: "agent",
      goal: "",
      branch: "main",
      model: "",
      budget_tokens: "",
      task: "",
      organization_id: "",
      pipeline_agents: "",
      plan_name: "Plan",
      plan_steps: "",
      plan_rationale: "",
      checkpoint_summary: "",
      checkpoint_final: false,
      feedback_type: "CONTINUE",
      feedback_message: "",
      approved_by: "",
      cancel_reason: "",
    });
  }

  function parseJsonArray(raw: string, field: string): Array<Record<string, unknown>> {
    const trimmed = raw.trim();
    if (!trimmed) return [];
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      throw new Error(`${field} is not valid JSON`);
    }
    if (!Array.isArray(parsed)) throw new Error(`${field} must be a JSON array`);
    return parsed as Array<Record<string, unknown>>;
  }

  async function handleEnqueue() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.repository_id.trim()) {
      pushToast("warning", "Repository ID is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.agentsEnqueue(token, {
        repository_id: draft.repository_id.trim(),
        agent_type: draft.agent_type.trim() || "refactor",
        name: draft.name.trim() || "agent",
        goal: draft.goal.trim() || undefined,
        branch: draft.branch.trim() || "main",
        model: draft.model.trim() || undefined,
        budget_tokens: draft.budget_tokens.trim() ? Number(draft.budget_tokens) : undefined,
      });
      setModal(null);
      pushToast("success", `Agent run ${result.id.slice(0, 8)} enqueued`);
      setSelectedAiRunId(result.id);
      setActive("executions");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to enqueue agent", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleExecuteAiRun() {
    if (!selectedAiRunId) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setExecuting(true);
    setExecError(null);
    try {
      const result = await api.agentsExecute(token, selectedAiRunId);
      pushToast("success", `Execution finished with status ${result.status}`);
      void loadAiRunDetail(selectedAiRunId);
      void loadAll();
    } catch (e) {
      if (e instanceof ApiError && e.kind === "timeout") {
        setExecError("EXECUTION REQUEST TIMED OUT — the server may still be processing. Check the run status; do not assume it stopped.");
        return;
      }
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setExecError(e instanceof Error ? e.message : "Execution failed");
    } finally {
      setExecuting(false);
    }
  }

  async function handleCancelAiRun() {
    if (!modal || modal.kind !== "cancel-run" || !selectedAiRunId) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.aiDevAgentCancel(token, selectedAiRunId, draft.cancel_reason.trim() || undefined);
      setModal(null);
      pushToast("success", `Run ${result.status}`);
      void loadAiRunDetail(selectedAiRunId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to cancel run", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePlanCreate() {
    if (!selectedAiRunId) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    let steps: Array<Record<string, unknown>> = [];
    try {
      steps = parseJsonArray(draft.plan_steps, "Steps");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      await api.agentsPlanCreate(token, selectedAiRunId, {
        name: draft.plan_name.trim() || "Plan",
        steps,
        rationale: draft.plan_rationale.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Plan recorded");
      void loadAiRunDetail(selectedAiRunId);
    } catch (e) {
      notifyError(e, "Failed to record plan");
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePlanApprove() {
    if (!modal || modal.kind !== "plan-approve" || !selectedAiRunId) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.approved_by.trim()) {
      pushToast("warning", "Approver identity is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.aiDevAgentApprovePlan(token, selectedAiRunId, modal.plan.id, {
        approved: true,
        approved_by: draft.approved_by.trim(),
      });
      setModal(null);
      pushToast("success", `Plan ${result.approved ? "approved" : "decided"}`);
      void loadAiRunDetail(selectedAiRunId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to approve plan", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCheckpointSave() {
    if (!selectedAiRunId) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.agentsCheckpointSave(token, selectedAiRunId, {
        summary: draft.checkpoint_summary.trim() || undefined,
        is_final: draft.checkpoint_final,
      });
      setModal(null);
      pushToast("success", "Checkpoint saved");
      void loadAiRunDetail(selectedAiRunId);
    } catch (e) {
      notifyError(e, "Failed to save checkpoint");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleFeedbackSubmit() {
    if (!selectedAiRunId) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.agentsFeedbackSubmit(token, selectedAiRunId, {
        feedback_type: draft.feedback_type || "CONTINUE",
        message: draft.feedback_message.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Feedback recorded");
      void loadAiRunDetail(selectedAiRunId);
    } catch (e) {
      notifyError(e, "Failed to record feedback");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleV2Run() {
    if (!modal || modal.kind !== "v2-run") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.task.trim()) {
      pushToast("warning", "Task input is required");
      return;
    }
    setExecuting(true);
    setExecError(null);
    try {
      const result = await api.agentsV2RunAgent(token, modal.agentName, {
        task: draft.task.trim(),
        organizationId: draft.organization_id.trim() || undefined,
        repositoryId: draft.repository_id.trim() || undefined,
      });
      setModal(null);
      setLastExecResult(result as unknown as Record<string, unknown>);
      pushToast("success", `Agent finished with status ${result.status} · run ${result.run_id.slice(0, 8)}`);
      void loadAll();
    } catch (e) {
      if (e instanceof ApiError && e.kind === "timeout") {
        setExecError("EXECUTION REQUEST TIMED OUT — the server may still be processing. Check run history; do not assume it stopped.");
        return;
      }
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setExecError(e instanceof Error ? e.message : "Agent execution failed");
    } finally {
      setExecuting(false);
    }
  }

  async function handleV2Pipeline() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const agents = draft.pipeline_agents.split(",").map((s) => s.trim()).filter(Boolean);
    if (agents.length === 0 || !draft.task.trim()) {
      pushToast("warning", "At least one agent and a task are required");
      return;
    }
    setExecuting(true);
    setExecError(null);
    try {
      const result = await api.agentsV2Pipeline(token, {
        agents,
        task: draft.task.trim(),
        organizationId: draft.organization_id.trim() || undefined,
        repositoryId: draft.repository_id.trim() || undefined,
      });
      setModal(null);
      setLastExecResult(result as unknown as Record<string, unknown>);
      pushToast("success", `Pipeline finished with status ${result.status}`);
      void loadAll();
    } catch (e) {
      if (e instanceof ApiError && e.kind === "timeout") {
        setExecError("EXECUTION REQUEST TIMED OUT — the server may still be processing. Check run history; do not assume it stopped.");
        return;
      }
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setExecError(e instanceof Error ? e.message : "Pipeline execution failed");
    } finally {
      setExecuting(false);
    }
  }

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
      setCatalog(null);
      setAgentInfo(null);
      setV2Runs(null);
      setV2RunDetail(null);
      setAiRuns(null);
      setAiRunDetail(null);
      setAiPlans([]);
      setAiCheckpoints([]);
      setAiFeedback([]);
      setSelectedAgentName(null);
      setSelectedV2RunId(null);
      setSelectedAiRunId(null);
      setV2Offset(0);
      setLastExecResult(null);
      setExecError(null);
      setCatalogError(null);
      setV2RunsError(null);
      setAiRunsError(null);
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
    if (selectedAgentName) {
      void loadAgentInfo(selectedAgentName);
    } else {
      setAgentInfo(null);
      setAgentInfoError(null);
    }
  }, [selectedAgentName, loadAgentInfo]);

  useEffect(() => {
    if (selectedV2RunId) {
      void loadV2RunDetail(selectedV2RunId);
    } else {
      setV2RunDetail(null);
      setV2RunDetailError(null);
    }
  }, [selectedV2RunId, loadV2RunDetail]);

  useEffect(() => {
    if (selectedAiRunId) {
      void loadAiRunDetail(selectedAiRunId);
    } else {
      setAiRunDetail(null);
      setAiPlans([]);
      setAiCheckpoints([]);
      setAiFeedback([]);
      setAiDetailError(null);
    }
  }, [selectedAiRunId, loadAiRunDetail]);

  const canRepoRead = hasPermission(permissions, PERMISSIONS.repoRead);
  const canRepoWrite = hasPermission(permissions, PERMISSIONS.repoWrite);

  const timelineEvents: AgentTimelineEvent[] = [];
  if (selectedV2RunId && v2RunDetail) {
    timelineEvents.push({
      id: `${v2RunDetail.id}-created`,
      kind: "RUN_CREATED",
      label: "RUN CREATED",
      detail: `${v2RunDetail.agent} · model ${v2RunDetail.model_used ?? "—"}`,
      at: v2RunDetail.created_at ?? null,
    });
    timelineEvents.push({
      id: `${v2RunDetail.id}-status`,
      kind: "RUN_STATUS",
      label: `STATUS · ${v2RunDetail.status}`,
      detail: `${v2RunDetail.tokens_used ?? 0} tokens${v2RunDetail.duration_ms ? ` · ${v2RunDetail.duration_ms}ms` : ""}${v2RunDetail.error ? ` · ${v2RunDetail.error.slice(0, 120)}` : ""}`,
      at: null,
    });
    const toolCalls = v2RunDetail.extra?.tool_calls ?? [];
    if (toolCalls.length > 0) {
      const succeeded = toolCalls.filter((t) => t.success).length;
      timelineEvents.push({
        id: `${v2RunDetail.id}-tools`,
        kind: "RUN_STATUS",
        label: "TOOL CALLS RECORDED",
        detail: `${toolCalls.length} calls · ${succeeded} succeeded (success/duration only — no payloads)`,
        at: null,
      });
    }
  }
  if (selectedAiRunId && aiRunDetail) {
    timelineEvents.push({
      id: `${aiRunDetail.id}-created`,
      kind: "RUN_CREATED",
      label: "RUN CREATED",
      detail: `${aiRunDetail.agent_type} · ${aiRunDetail.name}`,
      at: typeof aiRunDetail.created_at === "string" ? aiRunDetail.created_at : null,
    });
    aiPlans.forEach((plan, index) => {
      timelineEvents.push({
        id: `plan-${plan.id}`,
        kind: "PLAN_CREATED",
        label: `PLAN ${index + 1} · ${plan.approved ? "APPROVED" : plan.rejected ? "REJECTED" : "PENDING"}`,
        detail: `${plan.name} · ${plan.plan_type}`,
        at: null,
      });
    });
    [...aiCheckpoints]
      .sort((a, b) => a.sequence - b.sequence)
      .forEach((checkpoint) => {
        timelineEvents.push({
          id: `checkpoint-${checkpoint.id}`,
          kind: "CHECKPOINT_CREATED",
          label: `CHECKPOINT #${checkpoint.sequence}${checkpoint.is_final ? " · FINAL" : ""}`,
          detail: checkpoint.summary || "no summary",
          at: null,
        });
      });
    aiFeedback.forEach((feedback) => {
      timelineEvents.push({
        id: `feedback-${feedback.id}`,
        kind: "FEEDBACK",
        label: `FEEDBACK · ${feedback.feedback_type}`,
        detail: (feedback.message || "no message").slice(0, 160),
        at: feedback.created_at ?? null,
      });
    });
    timelineEvents.push({
      id: `${aiRunDetail.id}-status`,
      kind: "RUN_STATUS",
      label: `STATUS · ${aiRunDetail.status}`,
      detail: `${aiRunDetail.tokens_used ?? 0} tokens used${aiRunDetail.last_error ? ` · ${String(aiRunDetail.last_error).slice(0, 120)}` : ""}`,
      at: typeof aiRunDetail.end_time === "string" ? aiRunDetail.end_time : null,
    });
  }

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "catalog", label: "Catalog" },
    { id: "runs", label: "Runs" },
    { id: "executions", label: "Executions" },
    { id: "timeline", label: "Timeline" },
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
          {!canRepoRead && !canRepoWrite ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Read-only view · no repository permissions
            </span>
          ) : null}
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div role="tablist" aria-label="Agent sections" className="flex flex-wrap gap-2">
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
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Catalog" title="Registered agents">
            <PanelBody loading={loading} error={catalogError} onRetry={() => void loadAll()} emptyTitle="No agents registered" emptyDescription="The backend registry publishes the available agent catalog.">
              {catalog && catalog.length > 0 ? (
                <div className="space-y-1">
                  <StatRow label="Agents listed" value={String(catalog.length)} />
                  {catalog.slice(0, 6).map((agent) => (
                    <StatRow key={agent.name} label={agent.name} value={`${agent.role} · v${agent.version}`} />
                  ))}
                  <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Listed count only — the backend reports no totals.</p>
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Runs" title="My recent runs">
            <PanelBody loading={loading} error={v2RunsError} onRetry={() => void loadAll()} emptyTitle="No runs" emptyDescription="Runs you execute are listed here (user-scoped history).">
              {v2Runs ? (
                v2Runs.length > 0 ? (
                  <ul className="max-h-64 space-y-2 overflow-y-auto">
                    {v2Runs.slice(0, 6).map((run) => (
                      <li key={run.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs text-on-surface">{run.agent}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {formatDateTime(run.created_at)}{run.tokens_used ? ` · ${run.tokens_used} tokens` : ""}
                          </p>
                        </div>
                        <BrutalBadge tone={statusTone(run.status)}>{run.status}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <BrutalEmptyState title="No runs" description="Runs you execute are listed here (user-scoped history)." />
                )
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Executions" title="Agent executions">
            <PanelBody loading={loading} error={aiRunsError} onRetry={() => void loadAll()} emptyTitle="No executions" emptyDescription="Repository agent executions appear here once enqueued.">
              {aiRuns && aiRuns.length > 0 ? (
                <div className="space-y-1">
                  <StatRow label="Executions listed" value={String(aiRuns.length)} />
                  {["running", "completed", "failed"].map((s) => (
                    <StatRow key={s} label={s} value={String(aiRuns.filter((r) => r.status === s).length)} />
                  ))}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "catalog" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Catalog" title="Agent registry">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Published by the backend registry. No authentication required to browse.</p>
            <PanelBody loading={loading} error={catalogError} onRetry={() => void loadAll()} emptyTitle="No agents registered" emptyDescription="The backend registry publishes the available agent catalog.">
              {catalog && catalog.length > 0 ? (
                <ul className="space-y-2">
                  {catalog.map((agent) => (
                    <li key={agent.name}>
                      <button
                        type="button"
                        aria-label={`View agent ${agent.name}`}
                        onClick={() => setSelectedAgentName(agent.name)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${agent.name === selectedAgentName ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{agent.name}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {agent.role} · v{agent.version}
                          </p>
                        </div>
                        <BrutalBadge tone="default">{agent.role}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Catalog" title="Agent detail">
              <PanelBody loading={agentInfoLoading} error={agentInfoError} onRetry={() => selectedAgentName && void loadAgentInfo(selectedAgentName)} emptyTitle="Nothing selected" emptyDescription="Select an agent to inspect its configuration and guardrails.">
                {agentInfo ? (
                  <div className="space-y-1">
                    <StatRow label="Name" value={agentInfo.name} />
                    <StatRow label="Role" value={agentInfo.role} />
                    <StatRow label="Version" value={agentInfo.version} />
                    <StatRow label="Description" value={agentInfo.description || "—"} />
                    <StatRow label="Model" value={agentInfo.model} />
                    <StatRow label="Temperature" value={String(agentInfo.temperature)} />
                    <StatRow label="Permissions" value={(agentInfo.permissions ?? []).join(", ") || "—"} />
                    <StatRow label="Human approval" value={agentInfo.require_human_approval ? "required" : "not required"} />
                    <div className="flex flex-wrap gap-2 pt-2">
                      <BrutalButton
                        size="sm"
                        variant="primary"
                        aria-label={`Run agent ${agentInfo.name}`}
                        onClick={() => { resetDraft(); setModal({ kind: "v2-run", agentName: agentInfo.name }); }}
                      >
                        Run agent
                      </BrutalButton>
                      <BrutalButton
                        size="sm"
                        variant="ghost"
                        aria-label="Run agent pipeline"
                        onClick={() => { resetDraft(); setDraft((d) => ({ ...d, pipeline_agents: agentInfo.name })); setModal({ kind: "v2-pipeline" }); }}
                      >
                        Run pipeline
                      </BrutalButton>
                    </div>
                    {(agentInfo.goals ?? []).length > 0 ? (
                      <div className="pt-1">
                        <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Goals</p>
                        <ul className="space-y-1">
                          {agentInfo.goals.slice(0, 8).map((goal, index) => (
                            <li key={index} className="border border-outline bg-surface px-2 py-1 text-sm text-on-surface">{goal}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>
            {(executing || execError || lastExecResult) && (
              <div className="mt-6">
                <BrutalCard eyebrow="Execution" title="Agent execution">
                  {executing ? (
                    <div className="space-y-1" role="status" aria-live="polite">
                      <p className="font-mono text-xs uppercase tracking-widest text-primary-container">AGENT EXECUTION · SERVER-SIDE · LONG-RUNNING OPERATION</p>
                      <p className="text-sm text-on-surface-variant">The agent is executing on the backend. This request may take several minutes.</p>
                      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">STATUS: REQUEST IN PROGRESS · REALTIME: UNAVAILABLE</p>
                    </div>
                  ) : null}
                  {execError ? <p className="mt-2 text-xs text-error">{execError}</p> : null}
                  {!executing && lastExecResult ? (
                    <div className="mt-2 space-y-1">
                      <StatRow label="Run" value={String(lastExecResult.run_id ?? lastExecResult.workflow_id ?? "—")} />
                      <StatRow label="Status" value={String(lastExecResult.status ?? "—")} />
                    </div>
                  ) : null}
                </BrutalCard>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {active === "runs" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Runs" title="My run history">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Agent" value={v2AgentFilter} onChange={(e) => { setV2AgentFilter(e.target.value); setV2Offset(0); }} options={[{ label: "All agents", value: "ALL" }, ...(catalog ?? []).map((a) => ({ label: a.name, value: a.name }))]} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
            </div>
            <p className="mb-2 font-mono text-xs text-on-surface-variant">User-scoped history — runs from other users never appear here.</p>
            <PanelBody loading={loading} error={v2RunsError} onRetry={() => void loadAll()} emptyTitle="No runs" emptyDescription="Runs you execute are listed here.">
              {v2Runs && v2Runs.length > 0 ? (
                <div className="space-y-2">
                  <ul className="max-h-96 space-y-2 overflow-y-auto">
                    {v2Runs.map((run) => (
                      <li key={run.id}>
                        <button
                          type="button"
                          aria-label={`View run ${run.id}`}
                          onClick={() => setSelectedV2RunId(run.id)}
                          className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${run.id === selectedV2RunId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                        >
                          <div className="min-w-0">
                            <p className="truncate font-mono text-xs text-on-surface">{run.agent}</p>
                            <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                              {formatDateTime(run.created_at)}{run.tokens_used ? ` · ${run.tokens_used} tokens` : ""}
                            </p>
                          </div>
                          <BrutalBadge tone={statusTone(run.status)}>{run.status}</BrutalBadge>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="flex gap-2">
                    <BrutalButton variant="ghost" size="sm" disabled={v2Offset === 0} onClick={() => setV2Offset((o) => Math.max(o - 20, 0))}>Prev</BrutalButton>
                    <BrutalButton variant="ghost" size="sm" disabled={v2Runs.length < 20} onClick={() => setV2Offset((o) => o + 20)}>Next</BrutalButton>
                  </div>
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Runs" title="Run detail">
              <PanelBody loading={v2RunDetailLoading} error={v2RunDetailError} onRetry={() => selectedV2RunId && void loadV2RunDetail(selectedV2RunId)} emptyTitle="Nothing selected" emptyDescription="Select a run to inspect its safe execution metadata.">
                {v2RunDetail ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <BrutalBadge tone={statusTone(v2RunDetail.status)}>{v2RunDetail.status}</BrutalBadge>
                      <span className="font-mono text-xs text-on-surface-variant">{v2RunDetail.agent}</span>
                    </div>
                    <StatRow label="Run ID" value={v2RunDetail.id} />
                    <StatRow label="Model" value={v2RunDetail.model_used || "—"} />
                    <StatRow label="Tokens" value={v2RunDetail.tokens_used !== null && v2RunDetail.tokens_used !== undefined ? String(v2RunDetail.tokens_used) : "—"} />
                    <StatRow label="Duration" value={v2RunDetail.duration_ms !== null && v2RunDetail.duration_ms !== undefined ? `${v2RunDetail.duration_ms}ms` : "—"} />
                    <StatRow label="Created" value={formatDateTime(v2RunDetail.created_at)} />
                    {v2RunDetail.error ? <StatRow label="Error" value={v2RunDetail.error.slice(0, 200)} /> : null}
                    {v2RunDetail.extra ? (
                      <div className="border-t border-outline pt-2">
                        <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Decision metadata</p>
                        {v2RunDetail.extra.confidence !== null && v2RunDetail.extra.confidence !== undefined ? (
                          <StatRow label="Confidence" value={String(v2RunDetail.extra.confidence)} />
                        ) : null}
                        {v2RunDetail.extra.risk ? <StatRow label="Risk" value={v2RunDetail.extra.risk} /> : null}
                        {(v2RunDetail.extra.files_affected ?? []).length > 0 ? (
                          <StatRow label="Files" value={(v2RunDetail.extra.files_affected ?? []).slice(0, 5).join(", ")} />
                        ) : null}
                        {(v2RunDetail.extra?.tool_calls ?? []).length > 0 ? (
                          <StatRow
                            label="Tool calls"
                            value={`${(v2RunDetail.extra?.tool_calls ?? []).length} recorded · ${(v2RunDetail.extra?.tool_calls ?? []).filter((t) => t.success).length} succeeded`}
                          />
                        ) : null}
                      </div>
                    ) : null}
                    {typeof v2RunDetail.output === "string" && v2RunDetail.output ? (
                      <div className="border-t border-outline pt-2">
                        <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Run output</p>
                        <p className="max-h-48 overflow-y-auto whitespace-pre-wrap break-words border border-outline bg-surface p-3 text-sm text-on-surface">
                          {v2RunDetail.output.slice(0, RATIONALE_PREVIEW_CHARS)}
                          {v2RunDetail.output.length > RATIONALE_PREVIEW_CHARS ? "…" : ""}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "executions" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Executions" title="Agent executions">
            <div className="mb-3 space-y-2">
              <BrutalInput label="Repository ID" value={aiRepoFilter} onChange={(e) => setAiRepoFilter(e.target.value)} placeholder="optional uuid" />
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-28 flex-1">
                  <BrutalSelect label="Status" value={aiStatusFilter} onChange={(e) => setAiStatusFilter(e.target.value)} options={["ALL", "pending", "running", "completed", "failed", "cancelled"].map((s) => ({ label: s, value: s }))} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
                {canRepoWrite ? (
                  <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setDraft((d) => ({ ...d, repository_id: aiRepoFilter.trim() })); setModal({ kind: "enqueue" }); }}>
                    Enqueue agent
                  </BrutalButton>
                ) : null}
              </div>
            </div>
            <PanelBody loading={loading} error={aiRunsError} onRetry={() => void loadAll()} emptyTitle="No executions" emptyDescription="Repository agent executions appear here once enqueued.">
              {aiRuns && aiRuns.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {aiRuns.map((run) => (
                    <li key={run.id}>
                      <button
                        type="button"
                        aria-label={`View execution ${run.id}`}
                        onClick={() => setSelectedAiRunId(run.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${run.id === selectedAiRunId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{run.name}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {run.agent_type} · {run.tokens_used ?? 0} tokens
                          </p>
                        </div>
                        <BrutalBadge tone={statusTone(run.status)}>{run.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Executions" title="Execution detail">
            <PanelBody loading={aiDetailLoading} error={aiDetailError} onRetry={() => selectedAiRunId && void loadAiRunDetail(selectedAiRunId)} emptyTitle="Nothing selected" emptyDescription="Select an execution to inspect its plans, checkpoints and feedback.">
              {aiRunDetail ? (
                <div className="space-y-1">
                  <StatRow label="Name" value={aiRunDetail.name} />
                  <StatRow label="Type" value={aiRunDetail.agent_type} />
                  <StatRow label="Status" value={aiRunDetail.status} />
                  <StatRow label="Goal" value={aiRunDetail.goal || "—"} />
                  <StatRow label="Model" value={aiRunDetail.model || "—"} />
                  <StatRow label="Tokens used" value={String(aiRunDetail.tokens_used ?? 0)} />
                  <StatRow label="Attempts" value={String(aiRunDetail.attempts ?? 0)} />
                  {aiRunDetail.last_error ? <StatRow label="Last error" value={String(aiRunDetail.last_error).slice(0, 200)} /> : null}
                  <StatRow label="Started" value={formatDateTime(aiRunDetail.start_time)} />
                  <StatRow label="Ended" value={formatDateTime(aiRunDetail.end_time)} />
                  {canRepoWrite ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <BrutalButton size="sm" variant="primary" aria-label="Execute run" onClick={() => void handleExecuteAiRun()} disabled={executing}>
                        {executing ? "Executing…" : "Execute"}
                      </BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Cancel run" onClick={() => { resetDraft(); setModal({ kind: "cancel-run" }); }}>
                        Cancel
                      </BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Record plan" onClick={() => { resetDraft(); setModal({ kind: "plan-create" }); }}>
                        Record plan
                      </BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Save checkpoint" onClick={() => { resetDraft(); setModal({ kind: "checkpoint-save" }); }}>
                        Checkpoint
                      </BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Feedback" onClick={() => { resetDraft(); setModal({ kind: "feedback-submit" }); }}>
                        Feedback
                      </BrutalButton>
                    </div>
                  ) : (
                    <p className="pt-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Execution controls require repository:write</p>
                  )}
                  {executing ? (
                    <div className="border border-outline bg-surface p-3" role="status" aria-live="polite">
                      <p className="font-mono text-xs uppercase tracking-widest text-primary-container">AGENT EXECUTION · SERVER-SIDE · LONG-RUNNING OPERATION</p>
                      <p className="mt-1 text-sm text-on-surface-variant">The agent is executing on the backend. This request may take several minutes.</p>
                      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">STATUS: REQUEST IN PROGRESS · REALTIME: UNAVAILABLE</p>
                    </div>
                  ) : null}
                  {execError && !executing ? <p className="pt-1 text-xs text-error">{execError}</p> : null}
                  {typeof aiRunDetail.result === "string" && aiRunDetail.result ? (
                    <div className="border-t border-outline pt-2">
                      <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Run output</p>
                      <p className="max-h-48 overflow-y-auto whitespace-pre-wrap break-words border border-outline bg-surface p-3 text-sm text-on-surface">
                        {aiRunDetail.result.slice(0, RATIONALE_PREVIEW_CHARS)}
                        {aiRunDetail.result.length > RATIONALE_PREVIEW_CHARS ? "…" : ""}
                      </p>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="space-y-6">
            <BrutalCard eyebrow="Executions" title="Plans">
              {aiPlans.length > 0 ? (
                <ul className="max-h-72 space-y-2 overflow-y-auto">
                  {aiPlans.map((plan) => (
                    <li key={plan.id} className="border border-outline bg-surface p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="truncate text-sm text-on-surface">{plan.name}</p>
                        <BrutalBadge tone={plan.approved ? "yellow" : plan.rejected ? "error" : "default"}>
                          {plan.approved ? "approved" : plan.rejected ? "rejected" : "pending"}
                        </BrutalBadge>
                      </div>
                      <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {plan.plan_type} · {Array.isArray(plan.steps) ? plan.steps.length : 0} steps
                        {plan.approved_by ? ` · by ${plan.approved_by}` : ""}
                      </p>
                      {canRepoWrite && !plan.approved && !plan.rejected ? (
                        <div className="mt-2">
                          <BrutalButton
                            size="sm"
                            variant="ghost"
                            aria-label="Approve plan"
                            onClick={() => { resetDraft(); setModal({ kind: "plan-approve", plan }); }}
                          >
                            Approve plan
                          </BrutalButton>
                        </div>
                      ) : null}
                      {typeof plan.rationale === "string" && plan.rationale ? (
                        <div className="mt-2">
                          <TruncatedText label="PLAN RATIONALE" text={plan.rationale} />
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <BrutalEmptyState title="No plans" description="Plans recorded for this execution appear here." />
              )}
            </BrutalCard>

            <BrutalCard eyebrow="Executions" title="Checkpoints & feedback">
              {aiCheckpoints.length > 0 ? (
                <ul className="mb-3 max-h-56 space-y-2 overflow-y-auto">
                  {[...aiCheckpoints]
                    .sort((a, b) => a.sequence - b.sequence)
                    .map((checkpoint) => (
                      <li key={checkpoint.id} className="border border-outline bg-surface p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="font-mono text-xs text-on-surface">#{checkpoint.sequence} · {checkpoint.summary || "no summary"}</p>
                          {checkpoint.is_final ? <BrutalBadge tone="yellow">final</BrutalBadge> : null}
                        </div>
                      </li>
                    ))}
                </ul>
              ) : (
                <BrutalEmptyState title="No checkpoints" description="Durable checkpoints appear here once saved." />
              )}
              {aiFeedback.length > 0 ? (
                <ul className="max-h-56 space-y-2 overflow-y-auto">
                  {aiFeedback.map((feedback) => (
                    <li key={feedback.id} className="border border-outline bg-surface p-3">
                      <p className="font-mono text-xs uppercase tracking-widest text-primary-container">{feedback.feedback_type}</p>
                      <p className="mt-1 truncate text-sm text-on-surface">{feedback.message || "no message"}</p>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        by {feedback.created_by || "—"} · {formatDateTime(feedback.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "timeline" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Timeline" title="Execution timeline">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
              Record history only — never internal reasoning. Select a run in Runs or Executions first.
            </p>
            {timelineEvents.length > 0 ? (
              <ol className="max-h-[32rem] space-y-2 overflow-y-auto">
                {timelineEvents.map((event) => (
                  <li key={event.id} className="border border-outline bg-surface p-3">
                    <p className="font-mono text-xs uppercase tracking-widest text-primary-container">{event.label}</p>
                    <p className="mt-1 truncate text-sm text-on-surface" title={event.detail}>{event.detail}</p>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      {event.at ? formatDateTime(event.at) : "order only — no timestamp returned"}
                    </p>
                  </li>
                ))}
              </ol>
            ) : (
              <BrutalEmptyState title="No timeline" description="Select a run to build its operational timeline from returned records." />
            )}
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Limitation" title="Not exposed by API">
              <p className="mb-2 text-sm text-on-surface-variant">
                The following capabilities have no backing backend endpoint and are intentionally absent — not hidden:
              </p>
              <ul className="space-y-2">
                {NOT_EXPOSED.map((item) => (
                  <li key={item.capability} className="border border-outline bg-surface p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-bold text-on-surface">{item.capability}</p>
                      <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
                    </div>
                    <p className="mt-1 text-xs text-on-surface-variant">{item.reason}</p>
                  </li>
                ))}
              </ul>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      <BrutalCard eyebrow="Intelligence" title="Ask AI">
        <p className="mb-3 text-xs text-on-surface-variant">
          Open the AI workspace to discuss these agents. Only identifiers you quote yourself travel with the link — no payloads attached.
        </p>
        <BrutalButton variant="yellow" size="sm" href="/ai">Ask AI about agents</BrutalButton>
      </BrutalCard>

      <BrutalModal open={modal?.kind === "enqueue"} title="Enqueue agent" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleEnqueue()} disabled={submitting}>{submitting ? "Enqueuing…" : "Enqueue"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput id="enqueue-repository-id" label="Repository ID" value={draft.repository_id} onChange={(e) => setDraft((d) => ({ ...d, repository_id: e.target.value }))} placeholder="uuid" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Agent type" value={draft.agent_type} onChange={(e) => setDraft((d) => ({ ...d, agent_type: e.target.value }))} placeholder="refactor" />
            <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          </div>
          <BrutalInput label="Goal" value={draft.goal} onChange={(e) => setDraft((d) => ({ ...d, goal: e.target.value }))} placeholder="what the agent should achieve" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Branch" value={draft.branch} onChange={(e) => setDraft((d) => ({ ...d, branch: e.target.value }))} />
            <BrutalInput label="Model" value={draft.model} onChange={(e) => setDraft((d) => ({ ...d, model: e.target.value }))} placeholder="backend default" />
          </div>
          <BrutalInput label="Budget tokens" value={draft.budget_tokens} onChange={(e) => setDraft((d) => ({ ...d, budget_tokens: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "v2-run"} title="Run agent?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleV2Run()} disabled={executing}>{executing ? "Starting…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">
            This operation executes the agent server-side and may take several minutes. Do not close the operation while the request is in progress.
          </p>
          {modal?.kind === "v2-run" ? <StatRow label="Agent" value={modal.agentName} /> : null}
          <StatRow label="Type" value="Agent Run" />
          <BrutalInput label="Task" value={draft.task} onChange={(e) => setDraft((d) => ({ ...d, task: e.target.value }))} placeholder="describe the task (max 10000 chars)" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Organization ID" value={draft.organization_id} onChange={(e) => setDraft((d) => ({ ...d, organization_id: e.target.value }))} placeholder="optional" />
            <BrutalInput label="Repository ID" value={draft.repository_id} onChange={(e) => setDraft((d) => ({ ...d, repository_id: e.target.value }))} placeholder="optional" />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "v2-pipeline"} title="Run agent pipeline?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleV2Pipeline()} disabled={executing}>{executing ? "Starting…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">
            Agents run sequentially server-side and this may take several minutes. Do not close the operation while the request is in progress.
          </p>
          <StatRow label="Type" value="Pipeline Execute" />
          <BrutalInput label="Agents (comma-separated)" value={draft.pipeline_agents} onChange={(e) => setDraft((d) => ({ ...d, pipeline_agents: e.target.value }))} placeholder="planner, reviewer" />
          <BrutalInput label="Task" value={draft.task} onChange={(e) => setDraft((d) => ({ ...d, task: e.target.value }))} placeholder="describe the task" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Organization ID" value={draft.organization_id} onChange={(e) => setDraft((d) => ({ ...d, organization_id: e.target.value }))} placeholder="optional" />
            <BrutalInput label="Repository ID" value={draft.repository_id} onChange={(e) => setDraft((d) => ({ ...d, repository_id: e.target.value }))} placeholder="optional" />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "plan-create"} title="Record plan" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePlanCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.plan_name} onChange={(e) => setDraft((d) => ({ ...d, plan_name: e.target.value }))} />
          <BrutalInput label="Steps (JSON array)" value={draft.plan_steps} onChange={(e) => setDraft((d) => ({ ...d, plan_steps: e.target.value }))} placeholder='[{"name": "scan"}]' />
          <BrutalInput label="Rationale" value={draft.plan_rationale} onChange={(e) => setDraft((d) => ({ ...d, plan_rationale: e.target.value }))} placeholder="optional plain-text rationale" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "plan-approve"} title="Approve plan?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePlanApprove()} disabled={submitting}>{submitting ? "Approving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          {modal?.kind === "plan-approve" ? <StatRow label="Plan" value={modal.plan.name} /> : null}
          <BrutalInput label="Approved by" value={draft.approved_by} onChange={(e) => setDraft((d) => ({ ...d, approved_by: e.target.value }))} placeholder="your identity (email or user id)" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "checkpoint-save"} title="Save checkpoint" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleCheckpointSave()} disabled={submitting}>{submitting ? "Saving…" : "Save"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Summary" value={draft.checkpoint_summary} onChange={(e) => setDraft((d) => ({ ...d, checkpoint_summary: e.target.value }))} placeholder="what this checkpoint captures" />
          <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            <input type="checkbox" checked={draft.checkpoint_final} onChange={(e) => setDraft((d) => ({ ...d, checkpoint_final: e.target.checked }))} />
            Final checkpoint
          </label>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "feedback-submit"} title="Submit feedback" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleFeedbackSubmit()} disabled={submitting}>{submitting ? "Submitting…" : "Submit"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Type" value={draft.feedback_type} onChange={(e) => setDraft((d) => ({ ...d, feedback_type: e.target.value }))} placeholder="CONTINUE" />
          <BrutalInput label="Message" value={draft.feedback_message} onChange={(e) => setDraft((d) => ({ ...d, feedback_message: e.target.value }))} placeholder="human guidance for the run" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "cancel-run"} title="Cancel execution?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Keep running</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleCancelAiRun()} disabled={submitting}>{submitting ? "Cancelling…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-sm text-on-surface-variant">Cancellation is recorded server-side against the authoritative run state.</p>
          <BrutalInput label="Reason" value={draft.cancel_reason} onChange={(e) => setDraft((d) => ({ ...d, cancel_reason: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>
    </div>
  );
}
