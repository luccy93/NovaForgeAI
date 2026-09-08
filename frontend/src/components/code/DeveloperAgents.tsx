"use client";

import { useEffect, useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import type { AgentCheckpointOut, AgentOut, AgentPlanOut } from "@/types/code";
import { devErrorMessage } from "./dev-utils";

const TERMINAL = ["completed", "done", "failed", "error", "cancelled", "canceled", "stopped"];

export function DeveloperAgents({ repoId }: { repoId: string }) {
  const [agents, setAgents] = useState<AgentOut[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AgentOut | null>(null);
  const [plans, setPlans] = useState<AgentPlanOut[]>([]);
  const [checkpoints, setCheckpoints] = useState<AgentCheckpointOut[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [approver, setApprover] = useState<string | null>(null);

  const loadList = async () => {
    const token = getToken();
    if (!token) return;
    setLoadingList(true);
    setListError(null);
    try {
      const data = await api.aiDevListAgents(token, { repositoryId: repoId });
      setAgents(Array.isArray(data.items) ? data.items : []);
    } catch (e) {
      const msg = devErrorMessage(e, "agent runs");
      if (msg) setListError(msg);
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => {
    // The panel remounts per repository (parent keys it), so this runs once per repo.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);

  // Lazily resolve who approves (governed workflow) from the current user.
  const resolveApprover = async (): Promise<string> => {
    if (approver) return approver;
    const token = getToken();
    if (!token) return "web-workspace";
    try {
      const user = await api.me(token);
      const resolved = user?.email && user.email.length > 0 ? user.email : `user:${user?.id ?? "unknown"}`;
      setApprover(resolved);
      return resolved;
    } catch {
      return "web-workspace";
    }
  };

  const loadDetail = async (runId: string) => {
    const token = getToken();
    if (!token) return;
    setLoadingDetail(true);
    setDetailError(null);
    try {
      const [agent, plansData, checkpointsData] = await Promise.all([
        api.aiDevGetAgent(token, runId),
        api.aiDevAgentPlans(token, runId),
        api.aiDevAgentCheckpoints(token, runId),
      ]);
      setDetail(agent);
      setPlans(Array.isArray(plansData.items) ? plansData.items : []);
      setCheckpoints(Array.isArray(checkpointsData.items) ? checkpointsData.items : []);
    } catch (e) {
      const msg = devErrorMessage(e, "agent details");
      if (msg) setDetailError(msg);
    } finally {
      setLoadingDetail(false);
    }
  };

  const select = (runId: string) => {
    setSelectedId(runId);
    void loadDetail(runId);
  };

  const approvePlan = async (plan: AgentPlanOut) => {
    const token = getToken();
    if (!token || !selectedId) return;
    setApproving(true);
    try {
      const approvedBy = await resolveApprover();
      await api.aiDevAgentApprovePlan(token, selectedId, plan.id, {
        approved: true,
        approved_by: approvedBy,
        reason: "Approved from the web workspace.",
      });
      void loadDetail(selectedId);
    } catch (e) {
      const msg = devErrorMessage(e, "plan approval");
      if (msg) setDetailError(msg);
    } finally {
      setApproving(false);
    }
  };

  const cancelRun = async (runId: string) => {
    const token = getToken();
    if (!token) return;
    setCancelling(true);
    try {
      await api.aiDevAgentCancel(token, runId, "Cancelled from the web workspace.");
      if (selectedId === runId) {
        void loadDetail(runId);
      } else {
        void loadList();
      }
    } catch (e) {
      const msg = devErrorMessage(e, "agent cancellation");
      if (msg) setDetailError(msg);
    } finally {
      setCancelling(false);
    }
  };

  if (loadingList) return <BrutalSkeleton className="h-32 w-full" label="Loading agent runs" />;
  if (listError) return <BrutalErrorState title="Agent runs unavailable" description={listError} onRetry={() => void loadList()} />;
  if (agents.length === 0) {
    return <BrutalEmptyState title="Agent runs" description="No agent runs exist for this repository yet." />;
  }

  return (
    <div className="space-y-3">
      <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
        Agent runs ({agents.length})
      </h3>
      <ul className="space-y-1">
        {agents.map((agent) => {
          const active = selectedId === agent.id;
          return (
            <li key={agent.id} className="border border-outline bg-surface">
              <div className="flex items-center gap-2 p-2">
                <button
                  type="button"
                  onClick={() => select(agent.id)}
                  aria-pressed={active}
                  className="min-w-0 flex-1 text-left font-mono text-xs font-bold text-on-surface hover:underline"
                >
                  {agent.name || agent.id}
                </button>
                <BrutalBadge tone={statusTone(agent.status)}>{agent.status}</BrutalBadge>
                <span className="font-mono text-[10px] text-on-surface-variant">{agent.agent_type}</span>
                {canCancel(agent.status) ? (
                  <BrutalButton
                    variant="ghost"
                    size="sm"
                    disabled={cancelling}
                    onClick={() => void cancelRun(agent.id)}
                  >
                    Cancel
                  </BrutalButton>
                ) : null}
              </div>
              {active ? (
                <div className="space-y-2 border-t border-outline-variant p-2">
                  {loadingDetail ? <BrutalSkeleton className="h-20 w-full" label="Loading agent details" /> : null}
                  {detailError ? (
                    <BrutalErrorState
                      title="Agent details unavailable"
                      description={detailError}
                      onRetry={() => (selectedId ? void loadDetail(selectedId) : undefined)}
                    />
                  ) : null}
                  {detail && !loadingDetail ? (
                    <>
                      <p className="break-words text-sm text-on-surface-variant">{detail.goal}</p>
                      {detail.last_error ? (
                        <pre className="whitespace-pre-wrap border border-error bg-surface p-2 font-mono text-[11px] text-error">
                          {detail.last_error}
                        </pre>
                      ) : null}
                      {detail.result ? (
                        <pre className="max-h-40 overflow-auto whitespace-pre-wrap border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface">
                          {detail.result}
                        </pre>
                      ) : null}
                    </>
                  ) : null}
                  {plans.length > 0 ? (
                    <div>
                      <h4 className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        Plans (governed)
                      </h4>
                      <ul className="mt-1 space-y-1">
                        {plans.map((plan) => {
                          const decided = plan.approved || plan.rejected;
                          return (
                            <li key={plan.id} className="border border-outline bg-surface p-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-mono text-xs font-bold text-on-surface">
                                  {plan.name || plan.id}
                                </span>
                                <span className="font-mono text-[10px] text-on-surface-variant">{plan.plan_type}</span>
                                {plan.approved ? <BrutalBadge tone="yellow">Approved</BrutalBadge> : null}
                                {plan.rejected ? <BrutalBadge tone="error">Rejected</BrutalBadge> : null}
                                {!decided ? (
                                  <BrutalButton size="sm" disabled={approving} onClick={() => void approvePlan(plan)}>
                                    Approve plan
                                  </BrutalButton>
                                ) : null}
                              </div>
                              {plan.approved_by ? (
                                <p className="mt-1 font-mono text-[10px] text-on-surface-variant">
                                  decided by {plan.approved_by}
                                </p>
                              ) : null}
                              {plan.rationale ? (
                                <p className="mt-1 text-sm text-on-surface-variant">{plan.rationale}</p>
                              ) : null}
                              {Array.isArray(plan.steps) && plan.steps.length > 0 ? (
                                <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
                                  {JSON.stringify(plan.steps, null, 2)}
                                </pre>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : null}
                  {checkpoints.length > 0 ? (
                    <div>
                      <h4 className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        Checkpoints
                      </h4>
                      <ul className="mt-1 space-y-1">
                        {checkpoints.map((chk, i) => (
                          <li
                            key={chk.sequence ?? i}
                            className="flex flex-wrap items-center gap-2 border border-outline bg-surface p-2"
                          >
                            <span className="font-mono text-[10px] text-on-surface-variant">#{chk.sequence}</span>
                            <span className="min-w-0 flex-1 break-words text-sm text-on-surface-variant">
                              {chk.summary}
                            </span>
                            {chk.is_final ? <BrutalBadge tone="yellow">Final</BrutalBadge> : null}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function canCancel(status: string): boolean {
  return !TERMINAL.includes(status.toLowerCase());
}

function statusTone(status: string): "yellow" | "default" | "error" | "muted" {
  const s = status.toLowerCase();
  if (s.includes("completed") || s.includes("done") || s.includes("approved")) return "yellow";
  if (s.includes("fail") || s.includes("error") || s.includes("rejected")) return "error";
  if (TERMINAL.includes(s)) return "muted";
  return "default";
}