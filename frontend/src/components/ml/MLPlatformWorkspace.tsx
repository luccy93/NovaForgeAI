"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast";
import type {
  MLEvaluationCompare,
  MLEvaluationRun,
  MLGuardrail,
  MLModel,
  MLModelCard,
  MLModelVersion,
  MLMonitoringSnapshot,
  MLPolicyDecision,
  MLPrompt,
  MLPromptDetail,
  MLProvenance,
  MLProvider,
  MLRisk,
  MLSystemCard,
} from "@/types/ml";
import { ML_SEVERITIES, RISK_SCORE_CAVEAT } from "@/types/ml";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

function formatDateTime(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = value instanceof Date ? value : new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function StatRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  const text = value === null || value === undefined || value === "" ? "—" : String(value);
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface" title={text}>{text}</span>
    </div>
  );
}

function statusTone(status: unknown): "yellow" | "muted" | "error" | "default" {
  if (typeof status !== "string") return "default";
  const s = status.toUpperCase();
  if (s === "ACTIVE" || s === "APPROVED" || s === "AVAILABLE" || s === "PASS") return "yellow";
  if (s === "BLOCKED" || s === "FAILED" || s === "FAIL" || s === "CRITICAL" || s === "HIGH" || s === "UNAVAILABLE") return "error";
  if (s === "DRAFT" || s === "DEPRECATED" || s === "RETIRED" || s === "UNKNOWN" || s === "LOW" || s === "MEDIUM") return "muted";
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

/** Lifecycle events derived ONLY from returned rows — record history, never fabricated. */
interface TimelineEvent {
  id: string;
  label: string;
  detail: string;
  at: string | null;
}

type TabId =
  | "overview"
  | "registry"
  | "prompts"
  | "evaluations"
  | "risks"
  | "monitoring"
  | "deployments"
  | "governance"
  | "timeline";

export function MLPlatformWorkspace() {
  const pushToast = useToastStore((s) => s.push);
  const [active, setActive] = useState<TabId>("overview");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [models, setModels] = useState<MLModel[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelFilters, setModelFilters] = useState({ provider: "", name: "", status: "ALL", type: "", region: "" });
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [modelDetail, setModelDetail] = useState<MLModel | null>(null);
  const [modelDetailError, setModelDetailError] = useState<string | null>(null);
  const [modelDetailLoading, setModelDetailLoading] = useState(false);
  const [versions, setVersions] = useState<MLModelVersion[] | null>(null);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [provenance, setProvenance] = useState<MLProvenance | null>(null);
  const [provenanceError, setProvenanceError] = useState<string | null>(null);
  const [modelCards, setModelCards] = useState<MLModelCard[] | null>(null);
  const [snapshots, setSnapshots] = useState<MLMonitoringSnapshot[] | null>(null);
  const [snapshotsError, setSnapshotsError] = useState<string | null>(null);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);

  const [providers, setProviders] = useState<MLProvider[] | null>(null);
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [providerFilters, setProviderFilters] = useState({ provider: "", availability: "ALL", region: "" });
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);

  const [prompts, setPrompts] = useState<MLPrompt[] | null>(null);
  const [promptsError, setPromptsError] = useState<string | null>(null);
  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null);
  const [promptDetail, setPromptDetail] = useState<MLPromptDetail | null>(null);
  const [promptDetailError, setPromptDetailError] = useState<string | null>(null);
  const [promptDetailLoading, setPromptDetailLoading] = useState(false);

  const [evalRunId, setEvalRunId] = useState("");
  const [evalRun, setEvalRun] = useState<MLEvaluationRun | null>(null);
  const [evalRunError, setEvalRunError] = useState<string | null>(null);
  const [evalRunLoading, setEvalRunLoading] = useState(false);
  const [compareDraft, setCompareDraft] = useState({ candidate: "", baseline: "" });
  const [compareResult, setCompareResult] = useState<MLEvaluationCompare | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  const [risks, setRisks] = useState<MLRisk[] | null>(null);
  const [risksError, setRisksError] = useState<string | null>(null);
  const [riskFilters, setRiskFilters] = useState({ system: "", severity: "ALL", status: "ALL" });
  const [selectedRiskId, setSelectedRiskId] = useState<string | null>(null);
  const [guardrails, setGuardrails] = useState<MLGuardrail[] | null>(null);
  const [guardrailsError, setGuardrailsError] = useState<string | null>(null);
  const [guardrailFilters, setGuardrailFilters] = useState({ scope: "ALL", environment: "" });

  const [systemCardInput, setSystemCardInput] = useState("");
  const [systemCards, setSystemCards] = useState<MLSystemCard[] | null>(null);
  const [systemCardsError, setSystemCardsError] = useState<string | null>(null);
  const [systemCardsLoading, setSystemCardsLoading] = useState(false);
  const [policyResource, setPolicyResource] = useState("");
  const [policyDecisions, setPolicyDecisions] = useState<MLPolicyDecision[] | null>(null);
  const [policyDecisionsError, setPolicyDecisionsError] = useState<string | null>(null);
  const [policyDecisionsLoading, setPolicyDecisionsLoading] = useState(false);

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
    setModelsError(null);
    setProvidersError(null);
    setPromptsError(null);
    setRisksError(null);
    setGuardrailsError(null);

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
      settle(
        () =>
          api.mlModels(token, {
            provider: modelFilters.provider.trim() || undefined,
            name: modelFilters.name.trim() || undefined,
            status: modelFilters.status !== "ALL" ? modelFilters.status : undefined,
            type: modelFilters.type.trim() || undefined,
            region: modelFilters.region.trim() || undefined,
          }),
        setModels,
        setModelsError,
      ),
      settle(
        () =>
          api.mlProviders(token, {
            provider: providerFilters.provider.trim() || undefined,
            availability: providerFilters.availability !== "ALL" ? providerFilters.availability : undefined,
            region: providerFilters.region.trim() || undefined,
          }),
        setProviders,
        setProvidersError,
      ),
      settle(() => api.mlPrompts(token), setPrompts, setPromptsError),
      settle(
        () =>
          api.mlRisks(token, {
            system: riskFilters.system.trim() || undefined,
            severity: riskFilters.severity !== "ALL" ? riskFilters.severity : undefined,
            status: riskFilters.status !== "ALL" ? riskFilters.status : undefined,
          }),
        setRisks,
        setRisksError,
      ),
      settle(
        () =>
          api.mlGuardrails(token, {
            scope: guardrailFilters.scope !== "ALL" ? guardrailFilters.scope : undefined,
            environment: guardrailFilters.environment.trim() || undefined,
          }),
        setGuardrails,
        setGuardrailsError,
      ),
    ]);

    if (!controller.signal.aborted && seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, [modelFilters, providerFilters, riskFilters, guardrailFilters]);

  const loadModelDetail = useCallback(async (modelId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setModelDetailLoading(true);
    setModelDetailError(null);
    setVersionsLoading(true);
    setVersionsError(null);
    setSnapshotsLoading(true);
    setSnapshotsError(null);
    setProvenance(null);
    setProvenanceError(null);
    setModelCards(null);
    try {
      const [detail, vers, snaps] = await Promise.all([
        api.mlModel(token, modelId),
        api.mlModelVersions(token, modelId),
        api.mlMonitoring(token, modelId),
      ]);
      setModelDetail(detail);
      setVersions(Array.isArray(vers) ? vers : []);
      setSnapshots(Array.isArray(snaps) ? snaps : []);
      try {
        const prov = await api.mlProvenance(token, modelId);
        setProvenance(prov);
      } catch (e) {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        setProvenanceError(e instanceof Error ? e.message : "Provenance unavailable");
      }
      try {
        const cards = await api.mlModelCards(token, modelId);
        setModelCards(Array.isArray(cards) ? cards : [cards]);
      } catch {
        setModelCards([]);
      }
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      const message = e instanceof Error ? e.message : "Model unavailable";
      setModelDetailError(message);
      setVersionsError(message);
      setSnapshotsError(message);
    } finally {
      setModelDetailLoading(false);
      setVersionsLoading(false);
      setSnapshotsLoading(false);
    }
  }, []);

  const loadPromptDetail = useCallback(async (promptId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setPromptDetailLoading(true);
    setPromptDetailError(null);
    try {
      const detail = await api.mlPrompt(token, promptId);
      setPromptDetail(detail);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setPromptDetailError(e instanceof Error ? e.message : "Prompt unavailable");
    } finally {
      setPromptDetailLoading(false);
    }
  }, []);

  const loadEvalRun = useCallback(async () => {
    const runId = evalRunId.trim();
    if (!runId) {
      pushToast("warning", "Enter an evaluation run ID first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setEvalRunLoading(true);
    setEvalRunError(null);
    try {
      const run = await api.mlEvalRun(token, runId);
      setEvalRun(run);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setEvalRun(null);
      setEvalRunError(e instanceof Error ? e.message : "Evaluation run unavailable");
    } finally {
      setEvalRunLoading(false);
    }
  }, [evalRunId, pushToast]);

  const loadCompare = useCallback(async () => {
    const candidate = compareDraft.candidate.trim();
    const baseline = compareDraft.baseline.trim();
    if (!candidate || !baseline) {
      pushToast("warning", "Enter both candidate and baseline run IDs");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setCompareLoading(true);
    setCompareError(null);
    try {
      const result = await api.mlEvalCompare(token, candidate, baseline);
      setCompareResult(result);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setCompareResult(null);
      setCompareError(e instanceof Error ? e.message : "Comparison unavailable");
    } finally {
      setCompareLoading(false);
    }
  }, [compareDraft, pushToast]);

  const loadSystemCards = useCallback(async () => {
    const system = systemCardInput.trim();
    if (!system) {
      pushToast("warning", "Enter a system name or card ID first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSystemCardsLoading(true);
    setSystemCardsError(null);
    try {
      const cards = await api.mlSystemCards(token, system);
      setSystemCards(Array.isArray(cards) ? cards : [cards]);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setSystemCards(null);
      setSystemCardsError(e instanceof Error ? e.message : "System cards unavailable");
    } finally {
      setSystemCardsLoading(false);
    }
  }, [systemCardInput, pushToast]);

  const loadPolicyDecisions = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setPolicyDecisionsLoading(true);
    setPolicyDecisionsError(null);
    try {
      const res = await api.mlPolicyDecisions(token, { resource: policyResource.trim() || undefined, limit: 50 });
      setPolicyDecisions(res.decisions ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setPolicyDecisions(null);
      setPolicyDecisionsError(e instanceof Error ? e.message : "Policy decisions unavailable");
    } finally {
      setPolicyDecisionsLoading(false);
    }
  }, [policyResource]);

  useEffect(() => {
    void loadAll();
    const resetForContextSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setModels(null);
      setModelDetail(null);
      setVersions(null);
      setProvenance(null);
      setModelCards(null);
      setSnapshots(null);
      setProviders(null);
      setPrompts(null);
      setPromptDetail(null);
      setEvalRun(null);
      setCompareResult(null);
      setRisks(null);
      setGuardrails(null);
      setSystemCards(null);
      setPolicyDecisions(null);
      setSelectedModelId(null);
      setSelectedProvider(null);
      setSelectedPromptId(null);
      setSelectedRiskId(null);
      setSelectedRiskId(null);
      setModelsError(null);
      setProvidersError(null);
      setPromptsError(null);
      setRisksError(null);
      setGuardrailsError(null);
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
    if (selectedModelId) {
      void loadModelDetail(selectedModelId);
    } else {
      setModelDetail(null);
      setVersions(null);
      setProvenance(null);
      setModelCards(null);
      setSnapshots(null);
    }
  }, [selectedModelId, loadModelDetail]);

  useEffect(() => {
    if (selectedPromptId) {
      void loadPromptDetail(selectedPromptId);
    } else {
      setPromptDetail(null);
      setPromptDetailError(null);
    }
  }, [selectedPromptId, loadPromptDetail]);

  const selectedProviderDetail = providers?.find((p) => p.provider === selectedProvider) ?? null;
  const selectedRisk = risks?.find((r) => r.id === selectedRiskId) ?? null;

  const timelineEvents: TimelineEvent[] = [];
  if (modelDetail) {
    if (modelDetail.created_at) {
      timelineEvents.push({ id: `model-${modelDetail.id}-created`, label: "MODEL REGISTERED", detail: `${modelDetail.name ?? modelDetail.id} · ${modelDetail.provider ?? "—"}`, at: modelDetail.created_at });
    }
    if (modelDetail.updated_at && modelDetail.updated_at !== modelDetail.created_at) {
      timelineEvents.push({ id: `model-${modelDetail.id}-updated`, label: "MODEL UPDATED", detail: `status ${modelDetail.status ?? "—"}`, at: modelDetail.updated_at });
    }
  }
  (versions ?? []).forEach((v) => {
    if (v.created_at) {
      timelineEvents.push({ id: `version-${v.id}`, label: "VERSION CREATED", detail: `v${v.version ?? "?"} · ${v.immutable ? "immutable" : "record"}`, at: v.created_at });
    }
  });
  if (evalRun?.created_at) {
    timelineEvents.push({ id: `eval-${evalRun.id}-created`, label: "EVALUATION RUN RECORDED", detail: `status ${evalRun.status ?? "—"}`, at: evalRun.created_at });
  }
  if (evalRun?.updated_at && evalRun.updated_at !== evalRun.created_at) {
    timelineEvents.push({ id: `eval-${evalRun.id}-updated`, label: "EVALUATION RUN UPDATED", detail: `status ${evalRun.status ?? "—"}`, at: evalRun.updated_at });
  }
  timelineEvents.sort((a, b) => String(a.at ?? "").localeCompare(String(b.at ?? "")));

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "registry", label: "Registry" },
    { id: "prompts", label: "Prompts" },
    { id: "evaluations", label: "Evaluations" },
    { id: "risks", label: "Risks" },
    { id: "monitoring", label: "Monitoring" },
    { id: "deployments", label: "Deployments" },
    { id: "governance", label: "Governance" },
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
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div role="tablist" aria-label="ML sections" className="flex flex-wrap gap-2">
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
          <BrutalCard eyebrow="Registry" title="Models listed">
            <PanelBody loading={loading} error={modelsError} onRetry={() => void loadAll()} emptyTitle="No models" emptyDescription="Register a model to start tracking it here.">
              {models ? (
                <div className="space-y-1">
                  <StatRow label="Models listed" value={String(models.length)} />
                  {["ACTIVE", "APPROVED", "DRAFT", "BLOCKED"].map((s) => (
                    <StatRow key={s} label={s} value={String(models.filter((m) => m.status === s).length)} />
                  ))}
                  <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Listed count only — the backend reports no totals.</p>
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Providers" title="Providers listed">
            <PanelBody loading={loading} error={providersError} onRetry={() => void loadAll()} emptyTitle="No providers" emptyDescription="Provider registrations appear here.">
              {providers ? (
                <div className="space-y-1">
                  <StatRow label="Providers listed" value={String(providers.length)} />
                  {providers.slice(0, 6).map((p) => (
                    <StatRow key={p.provider ?? p.id} label={p.provider ?? p.id} value={p.availability ?? "—"} />
                  ))}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Risks" title="Risks listed">
            <PanelBody loading={loading} error={risksError} onRetry={() => void loadAll()} emptyTitle="No risks" emptyDescription="Risk records appear here once created.">
              {risks ? (
                <div className="space-y-1">
                  <StatRow label="Risks listed" value={String(risks.length)} />
                  {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((s) => (
                    <StatRow key={s} label={s} value={String(risks.filter((r) => r.severity === s).length)} />
                  ))}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "registry" ? (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            <BrutalCard eyebrow="Registry" title="Models">
              <div className="mb-3 grid grid-cols-2 gap-2">
                <BrutalInput label="Provider" value={modelFilters.provider} onChange={(e) => setModelFilters((f) => ({ ...f, provider: e.target.value }))} />
                <BrutalInput label="Name" value={modelFilters.name} onChange={(e) => setModelFilters((f) => ({ ...f, name: e.target.value }))} />
                <BrutalSelect label="Status" value={modelFilters.status} onChange={(e) => setModelFilters((f) => ({ ...f, status: e.target.value }))} options={["ALL", "DRAFT", "APPROVED", "ACTIVE", "DEPRECATED", "RETIRED", "BLOCKED"].map((s) => ({ label: s, value: s }))} />
                <BrutalInput label="Type" value={modelFilters.type} onChange={(e) => setModelFilters((f) => ({ ...f, type: e.target.value }))} />
              </div>
              <div className="mb-3">
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              </div>
              <PanelBody loading={loading} error={modelsError} onRetry={() => void loadAll()} emptyTitle="No models" emptyDescription="No models match the current filters.">
                {models && models.length > 0 ? (
                  <ul className="max-h-96 space-y-2 overflow-y-auto">
                    {models.map((model) => (
                      <li key={model.id}>
                        <button
                          type="button"
                          aria-label={`View model ${model.name ?? model.id}`}
                          onClick={() => setSelectedModelId(model.id)}
                          className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${model.id === selectedModelId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm text-on-surface">{model.name ?? model.id}</p>
                            <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                              {model.provider ?? "—"} · v{model.version ?? "?"}
                            </p>
                          </div>
                          <BrutalBadge tone={statusTone(model.status)}>{model.status ?? "—"}</BrutalBadge>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Registry" title="Model detail">
              <PanelBody loading={modelDetailLoading} error={modelDetailError} onRetry={() => selectedModelId && void loadModelDetail(selectedModelId)} emptyTitle="Nothing selected" emptyDescription="Select a model to inspect its metadata.">
                {modelDetail ? (
                  <div className="space-y-1">
                    <StatRow label="Name" value={modelDetail.name ?? "—"} />
                    <StatRow label="Provider" value={modelDetail.provider ?? "—"} />
                    <StatRow label="Type" value={modelDetail.type ?? "—"} />
                    <StatRow label="Version" value={modelDetail.version ?? "—"} />
                    <StatRow label="Status" value={modelDetail.status ?? "—"} />
                    <StatRow label="Risk level" value={modelDetail.risk_level ?? "—"} />
                    <StatRow label="License" value={modelDetail.license ?? "—"} />
                    <StatRow label="Region" value={modelDetail.region ?? "—"} />
                    <StatRow label="Owner" value={modelDetail.owner ?? "—"} />
                    <StatRow label="Created" value={formatDateTime(modelDetail.created_at)} />
                    <StatRow label="Updated" value={formatDateTime(modelDetail.updated_at)} />
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Registry" title="Immutable versions">
              <p className="mb-2 font-mono text-xs text-on-surface-variant">Versions are immutable once recorded — there is no edit operation.</p>
              <PanelBody loading={versionsLoading} error={versionsError} onRetry={() => selectedModelId && void loadModelDetail(selectedModelId)} emptyTitle="No versions" emptyDescription="Version history appears here once recorded for the selected model.">
                {versions && versions.length > 0 ? (
                  <ul className="max-h-96 space-y-2 overflow-y-auto">
                    {versions.map((v) => (
                      <li key={v.id} className="border border-outline bg-surface p-3">
                        <p className="font-mono text-sm text-on-surface">v{v.version ?? "?"}</p>
                        <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          eval {v.evaluation_version ?? "—"} · deploy {v.deployment_version ?? "—"} · policy {v.policy_version ?? "—"}
                        </p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          {v.immutable ? "immutable" : "mutable record"} · {formatDateTime(v.created_at)}
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <BrutalCard eyebrow="Registry" title="Providers">
              <div className="mb-3 flex flex-wrap items-end gap-2">
                <div className="min-w-28 flex-1">
                  <BrutalInput label="Provider" value={providerFilters.provider} onChange={(e) => setProviderFilters((f) => ({ ...f, provider: e.target.value }))} />
                </div>
                <div className="min-w-28 flex-1">
                  <BrutalSelect label="Availability" value={providerFilters.availability} onChange={(e) => setProviderFilters((f) => ({ ...f, availability: e.target.value }))} options={["ALL", "AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "MAINTENANCE"].map((s) => ({ label: s, value: s }))} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              </div>
              <PanelBody loading={loading} error={providersError} onRetry={() => void loadAll()} emptyTitle="No providers" emptyDescription="Provider registrations appear here.">
                {providers && providers.length > 0 ? (
                  <ul className="max-h-80 space-y-2 overflow-y-auto">
                    {providers.map((p) => (
                      <li key={p.id}>
                        <button
                          type="button"
                          aria-label={`View provider ${p.provider ?? p.id}`}
                          onClick={() => setSelectedProvider(p.provider ?? null)}
                          className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${p.provider === selectedProvider ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm text-on-surface">{p.display_name || p.provider}</p>
                            <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                              {(p.models ?? []).length} models · {(p.regions ?? []).join(", ") || "no regions"}
                            </p>
                          </div>
                          <BrutalBadge tone={statusTone(p.availability)}>{p.availability ?? "—"}</BrutalBadge>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </BrutalCard>

            <BrutalCard eyebrow="Registry" title="Provider detail">
              <PanelBody loading={loading} error={providersError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select a provider to inspect its metadata.">
                {selectedProviderDetail ? (
                  <div className="space-y-1">
                    <StatRow label="Provider" value={selectedProviderDetail.provider ?? "—"} />
                    <StatRow label="Display name" value={selectedProviderDetail.display_name ?? "—"} />
                    <StatRow label="Availability" value={selectedProviderDetail.availability ?? "—"} />
                    <StatRow label="Security" value={selectedProviderDetail.security_status ?? "—"} />
                    <StatRow label="Models" value={(selectedProviderDetail.models ?? []).join(", ") || "—"} />
                    <StatRow label="Regions" value={(selectedProviderDetail.regions ?? []).join(", ") || "—"} />
                    <StatRow label="Pricing keys" value={Object.keys(selectedProviderDetail.pricing ?? {}).join(", ") || "—"} />
                  </div>
                ) : null}
              </PanelBody>
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "prompts" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Prompts" title="Prompt registry">
            <PanelBody loading={loading} error={promptsError} onRetry={() => void loadAll()} emptyTitle="No prompts" emptyDescription="Registered prompts appear here with metadata only.">
              {prompts && prompts.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {prompts.map((prompt) => (
                    <li key={prompt.id}>
                      <button
                        type="button"
                        aria-label={`View prompt ${prompt.prompt_id ?? prompt.id}`}
                        onClick={() => setSelectedPromptId(prompt.prompt_id ?? prompt.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${prompt.prompt_id === selectedPromptId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{prompt.name ?? prompt.prompt_id}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {prompt.classification ?? "—"} · {prompt.status ?? "—"}
                          </p>
                        </div>
                        <BrutalBadge tone={statusTone(prompt.status)}>{prompt.status ?? "—"}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Prompts" title="Prompt detail">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Prompt content is never displayed — it may contain system prompts.</p>
            <PanelBody loading={promptDetailLoading} error={promptDetailError} onRetry={() => selectedPromptId && void loadPromptDetail(selectedPromptId)} emptyTitle="Nothing selected" emptyDescription="Select a prompt to inspect its metadata and version history.">
              {promptDetail ? (
                <div className="space-y-1">
                  <StatRow label="Prompt ID" value={promptDetail.prompt_id ?? "—"} />
                  <StatRow label="Name" value={promptDetail.name ?? "—"} />
                  <StatRow label="Purpose" value={promptDetail.purpose ?? "—"} />
                  <StatRow label="Classification" value={promptDetail.classification ?? "—"} />
                  <StatRow label="Compatibility" value={(promptDetail.model_compatibility ?? []).join(", ") || "—"} />
                  <StatRow label="Owner" value={promptDetail.owner ?? "—"} />
                  <StatRow label="Status" value={promptDetail.status ?? "—"} />
                  {(promptDetail.versions ?? []).length > 0 ? (
                    <div className="pt-1">
                      <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Versions (content withheld)</p>
                      <ul className="max-h-56 space-y-1 overflow-y-auto">
                        {(promptDetail.versions ?? []).map((v) => (
                          <li key={v.id} className="flex items-center justify-between gap-2 border border-outline bg-surface px-2 py-1">
                            <span className="font-mono text-xs text-on-surface">v{v.version ?? "?"}</span>
                            <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                              {v.classification ?? "—"} · {formatDateTime(v.created_at)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "evaluations" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Evaluations" title="Run lookup">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">No run-list endpoint exists — look up runs by ID. Metrics are echoed verbatim, never scored.</p>
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-48 flex-1">
                <BrutalInput label="Run ID" value={evalRunId} onChange={(e) => setEvalRunId(e.target.value)} placeholder="uuid" />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadEvalRun()} disabled={evalRunLoading}>
                {evalRunLoading ? "Loading…" : "Look up"}
              </BrutalButton>
            </div>
            {evalRunLoading ? (
              <LoadingPanel rows={2} />
            ) : evalRunError ? (
              <BrutalErrorState title="Run unavailable" description={evalRunError} onRetry={() => void loadEvalRun()} />
            ) : evalRun ? (
              <div className="space-y-1">
                <StatRow label="Status" value={evalRun.status ?? "—"} />
                <StatRow label="Suite" value={evalRun.suite_id ?? "—"} />
                <StatRow label="Model" value={evalRun.model_id ?? "—"} />
                <StatRow label="Hash" value={evalRun.reproducible_hash ?? "—"} />
                <StatRow label="Created" value={formatDateTime(evalRun.created_at)} />
                {Object.entries(evalRun.metrics ?? {}).slice(0, 10).map(([k, v]) => (
                  <StatRow key={k} label={`metric ${k}`} value={typeof v === "object" ? JSON.stringify(v).slice(0, 80) : String(v)} />
                ))}
              </div>
            ) : (
              <BrutalEmptyState title="No run loaded" description="Enter an evaluation run ID to inspect it." />
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Evaluations" title="Compare runs">
            <div className="mb-3 grid grid-cols-2 gap-2">
              <BrutalInput label="Candidate run ID" value={compareDraft.candidate} onChange={(e) => setCompareDraft((d) => ({ ...d, candidate: e.target.value }))} placeholder="uuid" />
              <BrutalInput label="Baseline run ID" value={compareDraft.baseline} onChange={(e) => setCompareDraft((d) => ({ ...d, baseline: e.target.value }))} placeholder="uuid" />
            </div>
            <div className="mb-3">
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadCompare()} disabled={compareLoading}>
                {compareLoading ? "Comparing…" : "Compare"}
              </BrutalButton>
            </div>
            {compareLoading ? (
              <LoadingPanel rows={2} />
            ) : compareError ? (
              <BrutalErrorState title="Comparison unavailable" description={compareError} onRetry={() => void loadCompare()} />
            ) : compareResult ? (
              <div className="space-y-1">
                <StatRow label="Regression" value={compareResult.regression === undefined || compareResult.regression === null ? "—" : String(compareResult.regression)} />
                {Object.entries(compareResult.metric_deltas ?? {}).slice(0, 10).map(([k, v]) => (
                  <StatRow key={k} label={`Δ ${k}`} value={String(v)} />
                ))}
              </div>
            ) : (
              <BrutalEmptyState title="No comparison" description="Enter two run IDs to compare candidate against baseline." />
            )}
          </BrutalCard>
        </div>
      ) : null}

      {active === "risks" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Risks" title="Risk records">
            <div className="mb-3 space-y-2">
              <BrutalInput label="System" value={riskFilters.system} onChange={(e) => setRiskFilters((f) => ({ ...f, system: e.target.value }))} />
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-24 flex-1">
                  <BrutalSelect label="Severity" value={riskFilters.severity} onChange={(e) => setRiskFilters((f) => ({ ...f, severity: e.target.value }))} options={["ALL", ...ML_SEVERITIES].map((s) => ({ label: s, value: s }))} />
                </div>
                <div className="min-w-24 flex-1">
                  <BrutalSelect label="Status" value={riskFilters.status} onChange={(e) => setRiskFilters((f) => ({ ...f, status: e.target.value }))} options={["ALL", "OPEN", "MITIGATED", "ACCEPTED", "CLOSED"].map((s) => ({ label: s, value: s }))} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              </div>
            </div>
            <PanelBody loading={loading} error={risksError} onRetry={() => void loadAll()} emptyTitle="No risks" emptyDescription="Risk records appear here once created.">
              {risks && risks.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {risks.map((risk) => (
                    <li key={risk.id}>
                      <button
                        type="button"
                        aria-label={`View risk ${risk.risk_id ?? risk.id}`}
                        onClick={() => setSelectedRiskId(risk.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${risk.id === selectedRiskId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{risk.risk_id ?? risk.id}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {risk.system ?? "—"} · {risk.status ?? "—"}
                          </p>
                        </div>
                        <BrutalBadge tone={statusTone(risk.severity)}>{risk.severity ?? "—"}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Risks" title="Risk detail">
            <PanelBody loading={loading} error={risksError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select a risk to inspect severity, likelihood, impact and score.">
              {selectedRisk ? (
                <div className="space-y-1">
                  <StatRow label="Risk ID" value={selectedRisk.risk_id ?? "—"} />
                  <StatRow label="System" value={selectedRisk.system ?? "—"} />
                  <StatRow label="Severity" value={selectedRisk.severity ?? "—"} />
                  <StatRow label="Likelihood" value={selectedRisk.likelihood ?? "—"} />
                  <StatRow label="Impact" value={selectedRisk.impact ?? "—"} />
                  <StatRow label="Owner" value={selectedRisk.owner ?? "—"} />
                  <StatRow label="Mitigation" value={selectedRisk.mitigation ?? "—"} />
                  <StatRow label="Status" value={selectedRisk.status ?? "—"} />
                  {selectedRisk.score !== null && selectedRisk.score !== undefined ? (
                    <div className="border border-outline bg-surface p-3">
                      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Risk score</p>
                      <p className="font-mono text-xl text-on-surface">{String(selectedRisk.score)}</p>
                      <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{RISK_SCORE_CAVEAT}</p>
                    </div>
                  ) : null}
                  <StatRow label="Created" value={formatDateTime(selectedRisk.created_at)} />
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Guardrails" title="Guardrails">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-24 flex-1">
                <BrutalSelect label="Scope" value={guardrailFilters.scope} onChange={(e) => setGuardrailFilters((f) => ({ ...f, scope: e.target.value }))} options={["ALL", "input", "output", "both"].map((s) => ({ label: s, value: s }))} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
            </div>
            <PanelBody loading={loading} error={guardrailsError} onRetry={() => void loadAll()} emptyTitle="No guardrails" emptyDescription="Guardrail definitions appear here.">
              {guardrails && guardrails.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {guardrails.map((g) => (
                    <li key={g.id} className="border border-outline bg-surface p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="truncate text-sm text-on-surface">{g.name ?? g.id}</p>
                        <BrutalBadge tone={g.enabled ? "yellow" : "muted"}>{g.enabled ? "enabled" : "disabled"}</BrutalBadge>
                      </div>
                      <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {g.scope ?? "—"}{g.rate_limit ? ` · ${g.rate_limit}/window` : ""} · {g.environment ?? "all envs"}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "monitoring" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Monitoring" title="Model snapshots">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Snapshots for the selected model, newest reported last. Values echoed verbatim — never scored.</p>
            {!selectedModelId ? (
              <BrutalEmptyState title="No model selected" description="Select a model in the Registry tab first." />
            ) : snapshotsLoading ? (
              <LoadingPanel />
            ) : snapshotsError ? (
              <BrutalErrorState title="Snapshots unavailable" description={snapshotsError} onRetry={() => void loadModelDetail(selectedModelId)} />
            ) : snapshots && snapshots.length > 0 ? (
              <ul className="max-h-96 space-y-2 overflow-y-auto">
                {snapshots.map((snap) => (
                  <li key={snap.id} className="border border-outline bg-surface p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-mono text-xs text-on-surface">{formatDateTime(snap.created_at)}</p>
                      <BrutalBadge tone={statusTone(snap.availability)}>{snap.availability ?? "—"}</BrutalBadge>
                    </div>
                    <div className="mt-1 space-y-1">
                      {snap.latency_ms !== null && snap.latency_ms !== undefined ? <StatRow label="Latency ms" value={String(snap.latency_ms)} /> : null}
                      {snap.error_rate !== null && snap.error_rate !== undefined ? <StatRow label="Error rate" value={String(snap.error_rate)} /> : null}
                      {snap.token_usage !== null && snap.token_usage !== undefined ? <StatRow label="Tokens" value={String(snap.token_usage)} /> : null}
                      {snap.cost !== null && snap.cost !== undefined ? <StatRow label="Cost" value={String(snap.cost)} /> : null}
                      {snap.quality !== null && snap.quality !== undefined ? <StatRow label="Quality" value={String(snap.quality)} /> : null}
                      {snap.safety !== null && snap.safety !== undefined ? <StatRow label="Safety" value={String(snap.safety)} /> : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <BrutalEmptyState title="No snapshots" description="No monitoring snapshots recorded for this model." />
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Monitoring" title="Provenance">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Stored version provenance echoed verbatim — never invented when absent.</p>
            {!selectedModelId ? (
              <BrutalEmptyState title="No model selected" description="Select a model in the Registry tab first." />
            ) : provenanceError ? (
              <BrutalErrorState title="Provenance unavailable" description={provenanceError} onRetry={() => void loadModelDetail(selectedModelId)} />
            ) : provenance ? (
              <div className="space-y-1">
                <StatRow label="Found" value={String(provenance.found ?? "—")} />
                {(provenance.versions ?? []).length > 0 ? (
                  <ul className="max-h-64 space-y-1 overflow-y-auto">
                    {(provenance.versions ?? []).slice(0, 20).map((v, index) => (
                      <li key={index} className="border border-outline bg-surface px-2 py-1 font-mono text-xs text-on-surface">
                        v{String((v as Record<string, unknown>).version ?? "?")}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="font-mono text-xs text-on-surface-variant">No version provenance stored.</p>
                )}
              </div>
            ) : (
              <BrutalEmptyState title="No provenance" description="Provenance appears here once recorded for the selected model." />
            )}
          </BrutalCard>
        </div>
      ) : null}

      {active === "deployments" ? (
        <BrutalCard eyebrow="Deployments" title="Deployment state">
          <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">NOT EXPOSED BY API</p>
          <p className="mt-2 text-sm text-on-surface-variant">
            Deployment state currently exists only in backend process memory and no deployment-list endpoint is available to the frontend.
          </p>
        </BrutalCard>
      ) : null}

      {active === "governance" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Governance" title="Policy decisions">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-32 flex-1">
                <BrutalInput label="Resource" value={policyResource} onChange={(e) => setPolicyResource(e.target.value)} placeholder="optional" />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadPolicyDecisions()} disabled={policyDecisionsLoading}>
                {policyDecisionsLoading ? "Loading…" : "Load"}
              </BrutalButton>
            </div>
            {policyDecisionsLoading ? (
              <LoadingPanel rows={2} />
            ) : policyDecisionsError ? (
              <BrutalErrorState title="Decisions unavailable" description={policyDecisionsError} onRetry={() => void loadPolicyDecisions()} />
            ) : policyDecisions ? (
              policyDecisions.length > 0 ? (
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {policyDecisions.map((d, index) => (
                    <li key={d.id ?? index} className="border border-outline bg-surface p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="truncate text-sm text-on-surface">{d.name ?? d.id ?? "policy"}</p>
                        <BrutalBadge tone={statusTone(d.effect)}>{d.effect ?? "—"}</BrutalBadge>
                      </div>
                      <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {d.type ?? "—"} · prio {d.priority ?? "—"} · {d.status ?? "—"}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <BrutalEmptyState title="No decisions" description="No policy decisions match." />
              )
            ) : (
              <BrutalEmptyState title="Not loaded" description="Load policy decisions for a resource scope." />
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Governance" title="System cards">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-32 flex-1">
                <BrutalInput label="System" value={systemCardInput} onChange={(e) => setSystemCardInput(e.target.value)} placeholder="name or card ID" />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadSystemCards()} disabled={systemCardsLoading}>
                {systemCardsLoading ? "Loading…" : "Look up"}
              </BrutalButton>
            </div>
            {systemCardsLoading ? (
              <LoadingPanel rows={2} />
            ) : systemCardsError ? (
              <BrutalErrorState title="System cards unavailable" description={systemCardsError} onRetry={() => void loadSystemCards()} />
            ) : systemCards ? (
              systemCards.length > 0 ? (
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {systemCards.map((c) => (
                    <li key={c.id} className="border border-outline bg-surface p-3">
                      <p className="truncate text-sm text-on-surface">{c.system ?? c.id}</p>
                      <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        models {(c.models ?? []).length} · tools {(c.tools ?? []).length} · oversight {c.human_oversight ?? "—"}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <BrutalEmptyState title="No system cards" description="No system cards match." />
              )
            ) : (
              <BrutalEmptyState title="Not loaded" description="Look up a system card by name or ID." />
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Governance" title="Model cards">
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Cards for the selected model load with its detail. Full governance lives in the Governance workspace.</p>
            {!selectedModelId ? (
              <BrutalEmptyState title="No model selected" description="Select a model in the Registry tab first." />
            ) : modelCards && modelCards.length > 0 ? (
              <ul className="max-h-80 space-y-2 overflow-y-auto">
                {modelCards.map((c) => (
                  <li key={c.id} className="border border-outline bg-surface p-3">
                    <p className="truncate text-sm text-on-surface">{c.purpose || "Model card"}</p>
                    <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      v{c.version ?? "?"} · risk {c.risk ?? "—"} · {formatDateTime(c.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <BrutalEmptyState title="No model cards" description="No cards recorded for the selected model." />
            )}
            <div className="mt-3">
              <BrutalButton variant="ghost" size="sm" href="/governance">Open Governance workspace</BrutalButton>
            </div>
          </BrutalCard>
        </div>
      ) : null}

      {active === "timeline" ? (
        <BrutalCard eyebrow="Timeline" title="Lifecycle record history">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
            Timestamps echoed from returned records only — never fabricated. Select a model or load an evaluation run first.
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
            <BrutalEmptyState title="No timeline" description="Select a model or load an evaluation run to build its record history." />
          )}
        </BrutalCard>
      ) : null}

      <BrutalCard eyebrow="Intelligence" title="Ask AI">
        <p className="mb-3 text-xs text-on-surface-variant">
          Open the AI workspace to discuss these models. Only identifiers you quote yourself travel with the link — no payloads attached.
        </p>
        <BrutalButton variant="yellow" size="sm" href="/ai">Ask AI about models</BrutalButton>
      </BrutalCard>
    </div>
  );
}
