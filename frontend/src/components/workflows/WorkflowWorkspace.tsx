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
  WorkflowAnomaly,
  WorkflowApproval,
  WorkflowBusinessProcess,
  WorkflowDetail,
  WorkflowHealthSummary,
  WorkflowHumanTask,
  WorkflowListItem,
  WorkflowRunDetail,
  WorkflowRunListItem,
  WorkflowSchedule,
  WorkflowStepRun,
  WorkflowTemplate,
  WorkflowVersion,
} from "@/types/workflows";
import { WORKFLOW_APPROVAL_DECISIONS, WORKFLOW_STATUSES } from "@/types/workflows";

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
  if (status === "ACTIVE" || status === "COMPLETED" || status === "SUCCESS" || status === "APPROVED") return "yellow";
  if (status === "FAILED" || status === "DENIED" || status === "TIMED_OUT") return "error";
  if (status === "DRAFT" || status === "PENDING" || status === "PAUSED" || status === "WAITING" || status === "CANCELLED" || status === "EXPIRED" || status === "COMPENSATING") return "muted";
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

type TabId = "overview" | "registry" | "runs" | "approvals" | "schedules" | "automation";

export function WorkflowWorkspace() {
  const pushToast = useToastStore((s) => s.push);
  const [active, setActive] = useState<TabId>("overview");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [health, setHealth] = useState<WorkflowHealthSummary | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [anomalies, setAnomalies] = useState<WorkflowAnomaly[] | null>(null);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);

  const [workflows, setWorkflows] = useState<WorkflowListItem[] | null>(null);
  const [workflowsError, setWorkflowsError] = useState<string | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState("ALL");
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [workflowDetail, setWorkflowDetail] = useState<WorkflowDetail | null>(null);
  const [workflowDetailError, setWorkflowDetailError] = useState<string | null>(null);
  const [workflowDetailLoading, setWorkflowDetailLoading] = useState(false);
  const [versions, setVersions] = useState<WorkflowVersion[] | null>(null);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRunListItem[] | null>(null);
  const [workflowRunsError, setWorkflowRunsError] = useState<string | null>(null);
  const [workflowRunsLoading, setWorkflowRunsLoading] = useState(false);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<WorkflowRunDetail | null>(null);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [steps, setSteps] = useState<WorkflowStepRun[] | null>(null);
  const [stepsError, setStepsError] = useState<string | null>(null);
  const [stepsLoading, setStepsLoading] = useState(false);
  const [sla, setSla] = useState<import("@/types/workflows").WorkflowSla | null>(null);
  const [slaError, setSlaError] = useState<string | null>(null);
  const [slaLoading, setSlaLoading] = useState(false);

  const [approvals, setApprovals] = useState<WorkflowApproval[] | null>(null);
  const [approvalsError, setApprovalsError] = useState<string | null>(null);
  const [approvalStatus, setApprovalStatus] = useState("ALL");

  const [schedules, setSchedules] = useState<WorkflowSchedule[] | null>(null);
  const [schedulesError, setSchedulesError] = useState<string | null>(null);

  const [templates, setTemplates] = useState<WorkflowTemplate[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<WorkflowHumanTask[] | null>(null);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState("ALL");
  const [business, setBusiness] = useState<WorkflowBusinessProcess[] | null>(null);
  const [businessError, setBusinessError] = useState<string | null>(null);

  const [modal, setModal] = useState<
    | { kind: "workflow-create" }
    | { kind: "version-create"; workflow: WorkflowListItem }
    | { kind: "publish"; workflow: WorkflowListItem }
    | { kind: "trigger"; workflow: WorkflowListItem }
    | { kind: "run-control"; runId: string; action: "pause" | "resume" | "cancel" }
    | { kind: "replay"; runId: string }
    | { kind: "recover"; runId: string }
    | { kind: "approval-decide"; approval: WorkflowApproval }
    | { kind: "schedule-create" }
    | { kind: "template-create" }
    | { kind: "task-complete"; task: WorkflowHumanTask }
    | { kind: "task-reassign"; task: WorkflowHumanTask }
    | { kind: "business-transition"; process: WorkflowBusinessProcess }
    | null
  >(null);
  const [submitting, setSubmitting] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    description: "",
    workspace: "",
    version: "1.0",
    definition: "",
    inputs: "",
    outputs: "",
    owner: "",
    trigger_type: "manual",
    trigger_inputs: "",
    idempotency_key: "",
    region: "",
    decision: "APPROVED",
    binding_hash: "",
    cron: "",
    interval_seconds: "",
    event_filter: "",
    schedule_trigger_type: "schedule",
    schedule_enabled: true,
    template_name: "",
    template_description: "",
    template_category: "general",
    template_definition: "",
    template_version: "1.0",
    task_decision: "",
    task_comment: "",
    assignee: "",
    new_state: "",
    worker_id: "",
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
      pushToast("error", e instanceof Error ? e.message : fallback);
    },
    [pushToast],
  );

  function resetDraft() {
    setDraft({
      name: "",
      description: "",
      workspace: "",
      version: "1.0",
      definition: "",
      inputs: "",
      outputs: "",
      owner: "",
      trigger_type: "manual",
      trigger_inputs: "",
      idempotency_key: "",
      region: "",
      decision: "APPROVED",
      binding_hash: "",
      cron: "",
      interval_seconds: "",
      event_filter: "",
      schedule_trigger_type: "schedule",
      schedule_enabled: true,
      template_name: "",
      template_description: "",
      template_category: "general",
      template_definition: "",
      template_version: "1.0",
      task_decision: "",
      task_comment: "",
      assignee: "",
      new_state: "",
      worker_id: "",
    });
  }

  function parseJsonObject(raw: string, field: string): Record<string, unknown> {
    const trimmed = raw.trim();
    if (!trimmed) return {};
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      throw new Error(`${field} is not valid JSON`);
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`${field} must be a JSON object`);
    }
    return parsed as Record<string, unknown>;
  }

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
    setHealthError(null);
    setAnomaliesError(null);
    setWorkflowsError(null);
    setApprovalsError(null);
    setSchedulesError(null);
    setTemplatesError(null);
    setTasksError(null);
    setBusinessError(null);

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
      settle(() => api.workflowHealthSummary(token), setHealth, setHealthError),
      settle(() => api.workflowAnomalies(token, 20), (value) => setAnomalies(value?.items ?? []), setAnomaliesError),
      settle(
        () => api.workflowsList(token, { status: workflowStatus !== "ALL" ? workflowStatus : undefined, limit: 20 }),
        (value) => setWorkflows(value?.items ?? []),
        setWorkflowsError,
      ),
      settle(
        () => api.workflowApprovals(token, { status: approvalStatus !== "ALL" ? approvalStatus : undefined, limit: 20 }),
        (value) => setApprovals(value?.items ?? []),
        setApprovalsError,
      ),
      settle(() => api.workflowSchedules(token, 20), (value) => setSchedules(value?.items ?? []), setSchedulesError),
      settle(() => api.workflowTemplates(token, 20), (value) => setTemplates(value?.items ?? []), setTemplatesError),
      settle(
        () => api.workflowHumanTasks(token, { status: taskStatus !== "ALL" ? taskStatus : undefined, limit: 20 }),
        (value) => setTasks(value?.items ?? []),
        setTasksError,
      ),
      settle(() => api.workflowBusinessProcesses(token, 20), (value) => setBusiness(value?.items ?? []), setBusinessError),
    ]);

    if (!controller.signal.aborted && seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, [workflowStatus, approvalStatus, taskStatus]);

  const loadWorkflowDetail = useCallback(async (workflowId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setWorkflowDetailLoading(true);
    setWorkflowDetailError(null);
    setVersionsLoading(true);
    setVersionsError(null);
    setWorkflowRunsLoading(true);
    setWorkflowRunsError(null);
    try {
      const [detail, vers, runs] = await Promise.all([
        api.workflowGet(token, workflowId),
        api.workflowVersions(token, workflowId),
        api.workflowRuns(token, workflowId, 20),
      ]);
      setWorkflowDetail(detail);
      setVersions(vers.items ?? []);
      setWorkflowRuns(runs.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      const message = e instanceof Error ? e.message : "Workflow unavailable";
      setWorkflowDetailError(message);
      setVersionsError(message);
      setWorkflowRunsError(message);
    } finally {
      setWorkflowDetailLoading(false);
      setVersionsLoading(false);
      setWorkflowRunsLoading(false);
    }
  }, []);

  const loadRunDetail = useCallback(async (runId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setRunDetailLoading(true);
    setRunDetailError(null);
    setStepsLoading(true);
    setStepsError(null);
    try {
      const [detail, stepRuns] = await Promise.all([
        api.workflowRunGet(token, runId),
        api.workflowRunSteps(token, runId),
      ]);
      setRunDetail(detail);
      setSteps(stepRuns.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      const message = e instanceof Error ? e.message : "Run unavailable";
      setRunDetailError(message);
      setStepsError(message);
    } finally {
      setRunDetailLoading(false);
      setStepsLoading(false);
    }
  }, []);

  async function handleWorkflowCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.name.trim()) {
      pushToast("warning", "Workflow name is required");
      return;
    }
    let definition: Record<string, unknown> = {};
    let inputs: Record<string, unknown> = {};
    let outputs: Record<string, unknown> = {};
    try {
      definition = parseJsonObject(draft.definition, "Definition");
      inputs = parseJsonObject(draft.inputs, "Inputs");
      outputs = parseJsonObject(draft.outputs, "Outputs");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowCreate(token, {
        name: draft.name.trim(),
        description: draft.description.trim() || undefined,
        workspace: draft.workspace.trim() || undefined,
        version: draft.version.trim() || "1.0",
        definition,
        inputs,
        outputs,
        owner: draft.owner.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Workflow ${result.name} created`);
      setSelectedWorkflowId(result.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create workflow", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVersionCreate() {
    if (!modal || modal.kind !== "version-create") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    let definition: Record<string, unknown>;
    try {
      definition = parseJsonObject(draft.definition, "Definition");
      if (Object.keys(definition).length === 0) {
        pushToast("warning", "Definition must not be empty");
        return;
      }
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowVersionCreate(token, modal.workflow.id, {
        definition,
        version: draft.version.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Version ${result.version} recorded (immutable)`);
      void loadWorkflowDetail(modal.workflow.id);
    } catch (e) {
      notifyError(e, "Failed to record version", () => selectedWorkflowId && void loadWorkflowDetail(selectedWorkflowId));
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePublish() {
    if (!modal || modal.kind !== "publish") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowPublish(token, modal.workflow.id);
      setModal(null);
      pushToast("success", `Version ${result.version} published`);
      void loadWorkflowDetail(modal.workflow.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to publish version", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTrigger() {
    if (!modal || modal.kind !== "trigger") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    let inputs: Record<string, unknown> = {};
    try {
      inputs = parseJsonObject(draft.trigger_inputs, "Inputs");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowTrigger(token, modal.workflow.id, {
        trigger_type: draft.trigger_type || "manual",
        inputs,
        idempotency_key: draft.idempotency_key.trim() || undefined,
        region: draft.region.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Run ${result.run_id.slice(0, 8)} started — execution runs server-side`);
      setSelectedRunId(result.run_id);
      setActive("runs");
      void loadWorkflowDetail(modal.workflow.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to trigger workflow", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRunControl() {
    if (!modal || modal.kind !== "run-control") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const { runId, action } = modal;
      const result =
        action === "pause"
          ? await api.workflowRunPause(token, runId)
          : action === "resume"
            ? await api.workflowRunResume(token, runId)
            : await api.workflowRunCancel(token, runId);
      setModal(null);
      pushToast("success", `Run is now ${result.status}`);
      void loadRunDetail(runId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Run control failed", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReplay() {
    if (!modal || modal.kind !== "replay") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowRunReplay(token, modal.runId);
      setModal(null);
      pushToast("success", `Replay started as run ${result.new_run_id.slice(0, 8)}`);
      setSelectedRunId(result.new_run_id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Replay failed — only failed runs with a published version can be replayed", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRecover() {
    if (!modal || modal.kind !== "recover") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowRunRecover(token, modal.runId, draft.worker_id.trim() || undefined);
      setModal(null);
      pushToast("success", `Recovery attempted — run is ${result.status}`);
      void loadRunDetail(modal.runId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Recovery failed — the lease may still be owned", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLoadSla() {
    if (!selectedRunId) {
      pushToast("warning", "Select a run first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSlaLoading(true);
    setSlaError(null);
    try {
      const result = await api.workflowRunSla(token, selectedRunId);
      setSla(result);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.status === 404) {
        setSlaError("No business process linked to this run");
        return;
      }
      setSlaError(e instanceof Error ? e.message : "SLA unavailable");
    } finally {
      setSlaLoading(false);
    }
  }

  async function handleApprovalDecide() {
    if (!modal || modal.kind !== "approval-decide") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowApprovalDecide(token, modal.approval.id, {
        decision: draft.decision,
        binding_hash: draft.binding_hash.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Approval ${result.decision}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Approval decision failed", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleScheduleCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!selectedWorkflowId) {
      pushToast("warning", "Select a workflow in the Registry tab first");
      setModal(null);
      return;
    }
    setSubmitting(true);
    try {
      let eventFilter: Record<string, unknown> = {};
      try {
        eventFilter = parseJsonObject(draft.event_filter, "Event filter");
      } catch (e) {
        pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
        setSubmitting(false);
        return;
      }
      const result = await api.workflowScheduleCreate(token, {
        workflow_id: selectedWorkflowId,
        cron: draft.cron.trim() || undefined,
        interval_seconds: draft.interval_seconds.trim() ? Number(draft.interval_seconds) : undefined,
        event_filter: eventFilter,
        trigger_type: draft.schedule_trigger_type || "schedule",
        enabled: draft.schedule_enabled,
      });
      setModal(null);
      pushToast("success", `Schedule ${result.id.slice(0, 8)} created`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create schedule", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTemplateCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.template_name.trim()) {
      pushToast("warning", "Template name is required");
      return;
    }
    let definition: Record<string, unknown> = {};
    try {
      definition = parseJsonObject(draft.template_definition, "Definition");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowTemplateCreate(token, {
        name: draft.template_name.trim(),
        description: draft.template_description.trim(),
        category: draft.template_category.trim() || "general",
        definition,
        version: draft.template_version.trim() || "1.0",
      });
      setModal(null);
      pushToast("success", `Template ${result.name} created`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create template", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTaskComplete() {
    if (!modal || modal.kind !== "task-complete") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowTaskComplete(token, modal.task.id, {
        decision: draft.task_decision.trim() || undefined,
        comment: draft.task_comment.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Task ${result.status}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to complete task", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTaskReassign() {
    if (!modal || modal.kind !== "task-reassign") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.assignee.trim()) {
      pushToast("warning", "Assignee is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowTaskReassign(token, modal.task.id, draft.assignee.trim());
      setModal(null);
      pushToast("success", `Task reassigned to ${result.assignee}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Reassign failed", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleBusinessTransition() {
    if (!modal || modal.kind !== "business-transition") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.new_state.trim()) {
      pushToast("warning", "New state is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.workflowBusinessTransition(token, modal.process.id, draft.new_state.trim());
      setModal(null);
      pushToast("success", `Process is now ${result.current_state}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Transition failed", () => void loadAll());
    } finally {
      setSubmitting(false);
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
      setHealth(null);
      setAnomalies(null);
      setWorkflows(null);
      setWorkflowDetail(null);
      setVersions(null);
      setWorkflowRuns(null);
      setRunDetail(null);
      setSteps(null);
      setSla(null);
      setSlaError(null);
      setApprovals(null);
      setSchedules(null);
      setTemplates(null);
      setTasks(null);
      setBusiness(null);
      setSelectedWorkflowId(null);
      setSelectedRunId(null);
      setHealthError(null);
      setAnomaliesError(null);
      setWorkflowsError(null);
      setApprovalsError(null);
      setSchedulesError(null);
      setTemplatesError(null);
      setTasksError(null);
      setBusinessError(null);
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
    if (selectedWorkflowId) {
      void loadWorkflowDetail(selectedWorkflowId);
    } else {
      setWorkflowDetail(null);
      setVersions(null);
      setWorkflowRuns(null);
    }
  }, [selectedWorkflowId, loadWorkflowDetail]);

  useEffect(() => {
    if (selectedRunId) {
      void loadRunDetail(selectedRunId);
    } else {
      setRunDetail(null);
      setSteps(null);
    }
    setSla(null);
    setSlaError(null);
  }, [selectedRunId, loadRunDetail]);

  const canWorkflowExecute = hasPermission(permissions, PERMISSIONS.workflowExecute);

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "registry", label: "Registry" },
    { id: "runs", label: "Runs" },
    { id: "approvals", label: "Approvals" },
    { id: "schedules", label: "Schedules" },
    { id: "automation", label: "Automation" },
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
          {!canWorkflowExecute ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Execution controls hidden · no workflow:execute
            </span>
          ) : null}
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div role="tablist" aria-label="Workflow sections" className="flex flex-wrap gap-2">
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
          <BrutalCard eyebrow="Execution" title="Workflow health">
            <PanelBody loading={loading} error={healthError} onRetry={() => void loadAll()} emptyTitle="No health data" emptyDescription="Health aggregates are computed server-side from tenant runs.">
              {health ? (
                <div className="space-y-1">
                  <StatRow label="Total runs" value={String(health.total)} />
                  <StatRow label="Succeeded" value={String(health.success)} />
                  <StatRow label="Failed" value={String(health.failed)} />
                  <StatRow label="Success rate" value={`${health.success_rate}%`} />
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Registry" title="Workflows listed">
            <PanelBody loading={loading} error={workflowsError} onRetry={() => void loadAll()} emptyTitle="No workflows" emptyDescription="Create a workflow to start automating.">
              {workflows ? (
                <div className="space-y-1">
                  <StatRow label="Workflows listed" value={String(workflows.length)} />
                  {["ACTIVE", "DRAFT", "PAUSED"].map((s) => (
                    <StatRow key={s} label={s} value={String(workflows.filter((w) => w.status === s).length)} />
                  ))}
                  <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Listed count only — the backend reports no totals.</p>
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Execution" title="Run anomalies">
            <PanelBody loading={loading} error={anomaliesError} onRetry={() => void loadAll()} emptyTitle="No anomalies" emptyDescription="Unusual durations (&gt;60s) and failures are flagged server-side.">
              {anomalies ? (
                anomalies.length > 0 ? (
                  <ul className="max-h-64 space-y-2 overflow-y-auto">
                    {anomalies.slice(0, 8).map((a) => (
                      <li key={`${a.run_id}-${a.type}`} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs text-on-surface">{a.run_id.slice(0, 12)}…</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {a.type}{a.duration_ms ? ` · ${a.duration_ms}ms` : ""}
                          </p>
                        </div>
                        <BrutalBadge tone={a.type === "unusual_failure" ? "error" : "yellow"}>{a.type}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <BrutalEmptyState title="No anomalies" description="No unusual durations or failures detected." />
                )
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "registry" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Registry" title="Workflows">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Status" value={workflowStatus} onChange={(e) => setWorkflowStatus(e.target.value)} options={["ALL", ...WORKFLOW_STATUSES].map((s) => ({ label: s, value: s }))} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              {canWorkflowExecute ? (
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal({ kind: "workflow-create" }); }}>New workflow</BrutalButton>
              ) : null}
            </div>
            <PanelBody loading={loading} error={workflowsError} onRetry={() => void loadAll()} emptyTitle="No workflows" emptyDescription="No workflows match the current filter.">
              {workflows && workflows.length > 0 ? (
                <ul className="space-y-2">
                  {workflows.map((wf) => (
                    <li key={wf.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedWorkflowId(wf.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${wf.id === selectedWorkflowId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{wf.name}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">v{wf.version}</p>
                        </div>
                        <BrutalBadge tone={statusTone(wf.status)}>{wf.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Registry" title="Workflow detail">
            <PanelBody loading={workflowDetailLoading} error={workflowDetailError} onRetry={() => selectedWorkflowId && void loadWorkflowDetail(selectedWorkflowId)} emptyTitle="Nothing selected" emptyDescription="Select a workflow to inspect its metadata.">
              {workflowDetail ? (
                <div className="space-y-1">
                  <StatRow label="Name" value={workflowDetail.name} />
                  <StatRow label="Version" value={workflowDetail.version} />
                  <StatRow label="Status" value={workflowDetail.status} />
                  <StatRow label="Description" value={workflowDetail.description || "—"} />
                  <StatRow label="ID" value={workflowDetail.id} />
                  {canWorkflowExecute ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <BrutalButton size="sm" variant="ghost" aria-label="Record version" onClick={() => { resetDraft(); setModal({ kind: "version-create", workflow: workflowDetail }); }}>
                        Record version
                      </BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Publish version" onClick={() => setModal({ kind: "publish", workflow: workflowDetail })}>
                        Publish
                      </BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Trigger workflow" onClick={() => { resetDraft(); setModal({ kind: "trigger", workflow: workflowDetail }); }}>
                        Trigger
                      </BrutalButton>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Registry" title="Immutable versions">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Versions are immutable — changes create a new version. Content is validated server-side on creation.</p>
            <PanelBody loading={versionsLoading} error={versionsError} onRetry={() => selectedWorkflowId && void loadWorkflowDetail(selectedWorkflowId)} emptyTitle="No versions" emptyDescription="Version history appears here once recorded.">
              {versions && versions.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {versions.map((v) => (
                    <li key={v.id} className="border border-outline bg-surface p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-mono text-sm text-on-surface">v{v.version}</p>
                        <BrutalBadge tone={statusTone(v.status)}>{v.status}</BrutalBadge>
                      </div>
                      {v.dag_hash ? (
                        <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant" title={v.dag_hash}>
                          dag {v.dag_hash.slice(0, 16)}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "runs" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Execution" title="Runs">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Runs for the selected workflow, newest first. Select a workflow in the Registry tab.</p>
            <PanelBody loading={workflowRunsLoading} error={workflowRunsError} onRetry={() => selectedWorkflowId && void loadWorkflowDetail(selectedWorkflowId)} emptyTitle="No runs" emptyDescription="Runs appear here once the workflow is triggered.">
              {workflowRuns && workflowRuns.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {workflowRuns.map((r) => (
                    <li key={r.run_id}>
                      <button
                        type="button"
                        onClick={() => setSelectedRunId(r.run_id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${r.run_id === selectedRunId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs text-on-surface">{r.run_id.slice(0, 12)}…</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">exec {r.execution_id.slice(0, 12)}…</p>
                        </div>
                        <BrutalBadge tone={statusTone(r.status)}>{r.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Execution" title="Run detail">
            <PanelBody loading={runDetailLoading} error={runDetailError} onRetry={() => selectedRunId && void loadRunDetail(selectedRunId)} emptyTitle="Nothing selected" emptyDescription="Select a run to inspect its execution record.">
              {runDetail ? (
                <div className="space-y-1">
                  <StatRow label="Status" value={runDetail.status} />
                  <StatRow label="Run ID" value={runDetail.run_id} />
                  <StatRow label="Execution" value={runDetail.execution_id} />
                  <StatRow label="Version" value={runDetail.workflow_version_id} />
                  <StatRow label="Trace" value={runDetail.trace_id || "—"} />
                  {canWorkflowExecute ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      {(runDetail.status === "RUNNING" || runDetail.status === "WAITING") && (
                        <BrutalButton size="sm" variant="ghost" aria-label="Pause run" onClick={() => setModal({ kind: "run-control", runId: runDetail.run_id, action: "pause" })}>
                          Pause
                        </BrutalButton>
                      )}
                      {runDetail.status === "PAUSED" && (
                        <BrutalButton size="sm" variant="ghost" aria-label="Resume run" onClick={() => setModal({ kind: "run-control", runId: runDetail.run_id, action: "resume" })}>
                          Resume
                        </BrutalButton>
                      )}
                      {!["COMPLETED", "CANCELLED", "FAILED"].includes(runDetail.status) && (
                        <BrutalButton size="sm" variant="ghost" aria-label="Cancel run" onClick={() => setModal({ kind: "run-control", runId: runDetail.run_id, action: "cancel" })}>
                          Cancel
                        </BrutalButton>
                      )}
                      {runDetail.status === "FAILED" && (
                        <BrutalButton size="sm" variant="ghost" aria-label="Replay run" onClick={() => setModal({ kind: "replay", runId: runDetail.run_id })}>
                          Replay
                        </BrutalButton>
                      )}
                      <BrutalButton size="sm" variant="ghost" aria-label="Recover run" onClick={() => { resetDraft(); setModal({ kind: "recover", runId: runDetail.run_id }); }}>
                        Recover
                      </BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Check SLA" onClick={() => void handleLoadSla()} disabled={slaLoading}>
                        {slaLoading ? "Checking…" : "SLA"}
                      </BrutalButton>
                    </div>
                  ) : null}
                  {slaError ? <p className="pt-1 text-xs text-error">{slaError}</p> : null}
                  {sla ? (
                    <div className="border-t border-outline pt-2">
                      <StatRow label="SLA state" value={sla.current_state} />
                      <StatRow label="Deadline" value={formatDateTime(sla.sla_deadline)} />
                      <StatRow label="Breached" value={sla.breached ? "yes" : "no"} />
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <div className="space-y-6">
            <BrutalCard eyebrow="Limitation" title="DAG visualization">
              <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">NOT EXPOSED BY API</p>
              <p className="mt-2 text-sm text-on-surface-variant">
                The workflow definition currently does not expose steps/nodes or dependency edges through the available backend API.
              </p>
            </BrutalCard>

            <BrutalCard eyebrow="Execution" title="STEP-RUN TIMELINE">
              <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Backend execution order — history, not a definition.</p>
              <PanelBody loading={stepsLoading} error={stepsError} onRetry={() => selectedRunId && void loadRunDetail(selectedRunId)} emptyTitle="No step data" emptyDescription="Step runs appear here when the backend reports them for this run.">
                {steps && steps.length > 0 ? (
                  <ol className="max-h-96 space-y-2 overflow-y-auto">
                    {steps.map((s, index) => (
                      <li key={`${s.step_id}-${index}`} className="border border-outline bg-surface p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="truncate font-mono text-xs text-on-surface">{index + 1}. {s.step_id}</p>
                          <BrutalBadge tone={statusTone(s.status)}>{s.status}</BrutalBadge>
                        </div>
                        <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          attempt {s.attempt}{s.error ? ` · ${s.error.slice(0, 120)}` : ""}
                        </p>
                      </li>
                    ))}
                  </ol>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "approvals" ? (
        <BrutalCard eyebrow="Execution" title="Approvals">
          <div className="mb-3 flex max-w-xs flex-wrap items-end gap-2">
            <div className="min-w-28 flex-1">
              <BrutalSelect label="Status" value={approvalStatus} onChange={(e) => setApprovalStatus(e.target.value)} options={["ALL", "PENDING", "APPROVED", "DENIED", "EXPIRED", "CANCELLED"].map((s) => ({ label: s, value: s }))} />
            </div>
            <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
          </div>
          <p className="mb-2 font-mono text-xs text-on-surface-variant">Decisions are made by the current user as approver. Binding hashes are verification references only.</p>
          <PanelBody loading={loading} error={approvalsError} onRetry={() => void loadAll()} emptyTitle="No approvals" emptyDescription="Human approval requests appear here once raised by a run.">
            {approvals && approvals.length > 0 ? (
              <ul className="grid gap-2 md:grid-cols-2">
                {approvals.map((a) => (
                  <li key={a.id} className="border border-outline bg-surface p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="truncate font-mono text-xs text-on-surface">step {a.step_id}</p>
                      <BrutalBadge tone={statusTone(a.status)}>{a.status}</BrutalBadge>
                    </div>
                    <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      run {a.run_id.slice(0, 8)}…{a.binding_hash ? ` · bound ${a.binding_hash.slice(0, 12)}` : ""}
                    </p>
                    {canWorkflowExecute && a.status === "PENDING" ? (
                      <div className="mt-2">
                        <BrutalButton
                          size="sm"
                          variant="ghost"
                          aria-label="Decide approval"
                          onClick={() => { resetDraft(); setModal({ kind: "approval-decide", approval: a }); }}
                        >
                          Decide
                        </BrutalButton>
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      ) : null}

      {active === "schedules" ? (
        <BrutalCard eyebrow="Automation" title="Schedules">
          <p className="mb-2 font-mono text-xs text-on-surface-variant">Cron, interval, one-shot and event triggers. Select the workflow in the Registry tab to scope creation.</p>
          {canWorkflowExecute ? (
            <div className="mb-3">
              <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal({ kind: "schedule-create" }); }} disabled={!selectedWorkflowId}>
                New schedule
              </BrutalButton>
            </div>
          ) : null}
          <PanelBody loading={loading} error={schedulesError} onRetry={() => void loadAll()} emptyTitle="No schedules" emptyDescription="Scheduled and event triggers appear here once created.">
            {schedules && schedules.length > 0 ? (
              <ul className="grid gap-2 md:grid-cols-2">
                {schedules.map((s) => (
                  <li key={s.id} className="border border-outline bg-surface p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="truncate text-sm text-on-surface">{s.trigger_type}{s.cron ? ` · ${s.cron}` : ""}</p>
                      <BrutalBadge tone={s.enabled ? "yellow" : "muted"}>{s.enabled ? "enabled" : "disabled"}</BrutalBadge>
                    </div>
                    <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      workflow {s.workflow_id.slice(0, 8)}…
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      ) : null}

      {active === "automation" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Automation" title="Templates">
            {canWorkflowExecute ? (
              <div className="mb-3">
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal({ kind: "template-create" }); }}>New template</BrutalButton>
              </div>
            ) : null}
            <PanelBody loading={loading} error={templatesError} onRetry={() => void loadAll()} emptyTitle="No templates" emptyDescription="Built-in and tenant templates appear here.">
              {templates && templates.length > 0 ? (
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {templates.map((t, index) => (
                    <li key={`${t.name}-${index}`} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{t.name}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          v{t.version} · {t.category || "general"} · {t.owner || "system"}
                        </p>
                      </div>
                      <BrutalBadge tone={t.is_published ? "yellow" : "muted"}>{t.is_published ? "published" : "draft"}</BrutalBadge>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Automation" title="Human tasks">
            <div className="mb-3 max-w-xs">
              <BrutalSelect label="Status" value={taskStatus} onChange={(e) => setTaskStatus(e.target.value)} options={["ALL", "PENDING", "COMPLETED", "CANCELLED"].map((s) => ({ label: s, value: s }))} />
            </div>
            <PanelBody loading={loading} error={tasksError} onRetry={() => void loadAll()} emptyTitle="No human tasks" emptyDescription="Tasks assigned to people appear here once raised by a run.">
              {tasks && tasks.length > 0 ? (
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {tasks.map((t) => (
                    <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{t.assignee}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          run {t.run_id.slice(0, 8)}…
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <BrutalBadge tone={statusTone(t.status)}>{t.status}</BrutalBadge>
                        {canWorkflowExecute && t.status === "PENDING" ? (
                          <>
                            <BrutalButton
                              size="sm"
                              variant="ghost"
                              aria-label="Complete task"
                              onClick={() => { resetDraft(); setModal({ kind: "task-complete", task: t }); }}
                            >
                              Complete
                            </BrutalButton>
                            <BrutalButton
                              size="sm"
                              variant="ghost"
                              aria-label="Reassign task"
                              onClick={() => { resetDraft(); setModal({ kind: "task-reassign", task: t }); }}
                            >
                              Reassign
                            </BrutalButton>
                          </>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Automation" title="Business processes">
            <PanelBody loading={loading} error={businessError} onRetry={() => void loadAll()} emptyTitle="No business processes" emptyDescription="State-machine processes linked to runs appear here.">
              {business && business.length > 0 ? (
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {business.map((b) => (
                    <li key={b.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{b.current_state}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          run {b.run_id.slice(0, 8)}…
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <BrutalBadge tone="default">{b.current_state}</BrutalBadge>
                        {canWorkflowExecute ? (
                          <BrutalButton
                            size="sm"
                            variant="ghost"
                            aria-label="Transition process"
                            onClick={() => { resetDraft(); setModal({ kind: "business-transition", process: b }); }}
                          >
                            Transition
                          </BrutalButton>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      <BrutalCard eyebrow="Intelligence" title="Ask AI">
        <p className="mb-3 text-xs text-on-surface-variant">
          Open the AI workspace to discuss these workflows. Only identifiers you quote yourself travel with the link — no payloads attached.
        </p>
        <BrutalButton variant="yellow" size="sm" href="/ai">Ask AI about workflows</BrutalButton>
      </BrutalCard>

      <BrutalModal open={modal?.kind === "workflow-create"} title="New workflow" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleWorkflowCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="nightly-etl" />
          <BrutalInput label="Description" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.workspace} onChange={(e) => setDraft({ ...draft, workspace: e.target.value })} />
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft({ ...draft, owner: e.target.value })} />
          </div>
          <BrutalInput label="Initial version" value={draft.version} onChange={(e) => setDraft({ ...draft, version: e.target.value })} />
          <BrutalInput label="Definition (JSON object)" value={draft.definition} onChange={(e) => setDraft((d) => ({ ...d, definition: e.target.value }))} placeholder='{"steps": [{"id": "extract", "type": "task"}]}' />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Inputs (JSON)" value={draft.inputs} onChange={(e) => setDraft((d) => ({ ...d, inputs: e.target.value }))} placeholder="{}" />
            <BrutalInput label="Outputs (JSON)" value={draft.outputs} onChange={(e) => setDraft((d) => ({ ...d, outputs: e.target.value }))} placeholder="{}" />
          </div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Server validation rejects cycles, unknown dependencies, code execution and literal secrets (422).</p>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "version-create"} title="Record version" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleVersionCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Versions are immutable once recorded — there is no edit operation.</p>
          <BrutalInput label="Version" value={draft.version} onChange={(e) => setDraft((d) => ({ ...d, version: e.target.value }))} placeholder="1.1" />
          <BrutalInput label="Definition (JSON object)" value={draft.definition} onChange={(e) => setDraft((d) => ({ ...d, definition: e.target.value }))} placeholder='{"steps": [{"id": "extract", "type": "task"}]}' />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "publish"} title="Publish latest draft?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePublish()} disabled={submitting}>{submitting ? "Publishing…" : "Confirm"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">Publishes the latest draft version so runs can trigger against it. Already-published versions are rejected by the backend.</p>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "trigger"} title="Trigger workflow?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleTrigger()} disabled={submitting}>{submitting ? "Starting…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Triggering executes server-side immediately against the published version. Nothing runs in the browser.</p>
          <BrutalSelect label="Trigger type" value={draft.trigger_type} onChange={(e) => setDraft((d) => ({ ...d, trigger_type: e.target.value }))} options={["manual", "event", "schedule"].map((t) => ({ label: t, value: t }))} />
          <BrutalInput label="Inputs (JSON object)" value={draft.trigger_inputs} onChange={(e) => setDraft((d) => ({ ...d, trigger_inputs: e.target.value }))} placeholder="{}" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Idempotency key" value={draft.idempotency_key} onChange={(e) => setDraft((d) => ({ ...d, idempotency_key: e.target.value }))} placeholder="optional" />
            <BrutalInput label="Region" value={draft.region} onChange={(e) => setDraft((d) => ({ ...d, region: e.target.value }))} placeholder="optional" />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "run-control"} title={`${modal?.kind === "run-control" ? modal.action[0].toUpperCase() + modal.action.slice(1) : ""} run?`} onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleRunControl()} disabled={submitting}>{submitting ? "Working…" : "Confirm"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">
          {modal?.kind === "run-control" && modal.action === "cancel"
            ? "Cancelling a run with successful steps triggers server-side compensation where the definition declares handlers."
            : "The backend enforces valid state transitions and rejects anything else with 422."}
        </p>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "replay"} title="Replay failed run?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleReplay()} disabled={submitting}>{submitting ? "Replaying…" : "Confirm"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">Starts a new run from the failed one. Only failed runs with a published version can be replayed.</p>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "recover"} title="Recover stale execution?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleRecover()} disabled={submitting}>{submitting ? "Recovering…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Recovery steals the worker lease for a stale execution. If the lease is still owned, the backend refuses with 422.</p>
          <BrutalInput label="Worker ID" value={draft.worker_id} onChange={(e) => setDraft((d) => ({ ...d, worker_id: e.target.value }))} placeholder="defaults to your user id" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "approval-decide"} title="Decide approval?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleApprovalDecide()} disabled={submitting}>{submitting ? "Deciding…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Decided as the current user. Expired approvals, binding mismatches and unauthorized approvers are rejected by the backend.</p>
          <BrutalSelect label="Decision" value={draft.decision} onChange={(e) => setDraft((d) => ({ ...d, decision: e.target.value }))} options={WORKFLOW_APPROVAL_DECISIONS.map((d) => ({ label: d, value: d }))} />
          <BrutalInput label="Binding hash" value={draft.binding_hash} onChange={(e) => setDraft((d) => ({ ...d, binding_hash: e.target.value }))} placeholder="optional verification ref" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "schedule-create"} title="New schedule" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleScheduleCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <StatRow label="Workflow" value={selectedWorkflowId ?? "—"} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Cron" value={draft.cron} onChange={(e) => setDraft((d) => ({ ...d, cron: e.target.value }))} placeholder="0 2 * * *" />
            <BrutalInput label="Interval seconds" value={draft.interval_seconds} onChange={(e) => setDraft((d) => ({ ...d, interval_seconds: e.target.value }))} placeholder="optional" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Trigger type" value={draft.schedule_trigger_type} onChange={(e) => setDraft((d) => ({ ...d, schedule_trigger_type: e.target.value }))} options={["schedule", "once", "interval", "cron", "event"].map((t) => ({ label: t, value: t }))} />
            <BrutalSelect label="Enabled" value={draft.schedule_enabled ? "yes" : "no"} onChange={(e) => setDraft((d) => ({ ...d, schedule_enabled: e.target.value === "yes" }))} options={[{ label: "yes", value: "yes" }, { label: "no", value: "no" }]} />
          </div>
          <BrutalInput label="Event filter (JSON)" value={draft.event_filter} onChange={(e) => setDraft((d) => ({ ...d, event_filter: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "template-create"} title="New template" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleTemplateCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.template_name} onChange={(e) => setDraft((d) => ({ ...d, template_name: e.target.value }))} />
          <BrutalInput label="Description" value={draft.template_description} onChange={(e) => setDraft((d) => ({ ...d, template_description: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Category" value={draft.template_category} onChange={(e) => setDraft((d) => ({ ...d, template_category: e.target.value }))} />
            <BrutalInput label="Version" value={draft.template_version} onChange={(e) => setDraft((d) => ({ ...d, template_version: e.target.value }))} />
          </div>
          <BrutalInput label="Definition (JSON object)" value={draft.template_definition} onChange={(e) => setDraft((d) => ({ ...d, template_definition: e.target.value }))} placeholder="{}" />
          <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Shell actions, unbounded fan-out/loops and credential extraction are rejected (422).</p>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "task-complete"} title="Complete human task?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleTaskComplete()} disabled={submitting}>{submitting ? "Completing…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Decision" value={draft.task_decision} onChange={(e) => setDraft((d) => ({ ...d, task_decision: e.target.value }))} placeholder="optional" />
          <BrutalInput label="Comment" value={draft.task_comment} onChange={(e) => setDraft((d) => ({ ...d, task_comment: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "task-reassign"} title="Reassign human task?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleTaskReassign()} disabled={submitting}>{submitting ? "Reassigning…" : "Confirm"}</BrutalButton>
        </>
      }>
        <BrutalInput label="Assignee" value={draft.assignee} onChange={(e) => setDraft((d) => ({ ...d, assignee: e.target.value }))} placeholder="user id" />
      </BrutalModal>

      <BrutalModal open={modal?.kind === "business-transition"} title="Transition process?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleBusinessTransition()} disabled={submitting}>{submitting ? "Transitioning…" : "Confirm"}</BrutalButton>
        </>
      }>
        <BrutalInput label="New state" value={draft.new_state} onChange={(e) => setDraft((d) => ({ ...d, new_state: e.target.value }))} placeholder="state name" />
      </BrutalModal>
    </div>
  );
}
