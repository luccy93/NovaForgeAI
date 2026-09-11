"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
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
import { WORKFLOW_STATUSES } from "@/types/workflows";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
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
            <PanelBody loading={loading} error={workflowsError} onRetry={() => void loadAll()} emptyTitle="No workflows" emptyDescription="Create a workflow to start automating (execution controls arrive with workflow:execute).">
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
          <p className="mb-2 font-mono text-xs text-on-surface-variant">Approval decisions arrive with execution controls. Binding hashes are verification references only.</p>
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
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      ) : null}

      {active === "schedules" ? (
        <BrutalCard eyebrow="Automation" title="Schedules">
          <p className="mb-2 font-mono text-xs text-on-surface-variant">Cron, interval, one-shot and event triggers. Creation arrives with execution controls.</p>
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
                      <BrutalBadge tone={statusTone(t.status)}>{t.status}</BrutalBadge>
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
                      <BrutalBadge tone="default">{b.current_state}</BrutalBadge>
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
    </div>
  );
}
