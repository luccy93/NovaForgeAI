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
import { hasAnyPermission, hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
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
  | "timeline"
  | "gateway";

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

  const [permissions, setPermissions] = useState<string[]>([]);
  const [modal, setModal] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [execError, setExecError] = useState<string | null>(null);
  const [gatewayResult, setGatewayResult] = useState<import("@/types/ml").MLGatewayInvokeResult | null>(null);
  const [gatewayRoute, setGatewayRoute] = useState<import("@/types/ml").MLGatewayRoute | null>(null);
   
  const [driftResult, setDriftResult] = useState<import("@/types/ml").MLDriftResult | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [driftError, setDriftError] = useState<string | null>(null);
   
  const [checkResult, setCheckResult] = useState<import("@/types/ml").MLCheckResult | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [checkError, setCheckError] = useState<string | null>(null);
   
  const [evalPolicyResult, setEvalPolicyResult] = useState<import("@/types/ml").MLCheckResult | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [evalPolicyError, setEvalPolicyError] = useState<string | null>(null);
  const [lastDeployment, setLastDeployment] = useState<import("@/types/ml").MLDeployment | null>(null);
  const [riskAssess, setRiskAssess] = useState<(import("@/types/ml").MLRisk & { assessed_score?: number | null; advisory?: Record<string, unknown>; note?: string }) | null>(null);
  const [draft, setDraft] = useState({
    name: "",
    provider: "",
    version: "1.0",
    type: "foundation",
    capabilities: "",
    license: "",
    region: "",
    risk_level: "LOW",
    owner: "",
    status: "ACTIVE",
    artifact: "",
    display_name: "",
    models: "",
    regions: "",
    availability: "AVAILABLE",
    security_status: "UNKNOWN",
    prompt_id: "",
    prompt_name: "",
    purpose: "",
    classification: "INTERNAL",
    model_compatibility: "",
    content: "",
    suite_name: "",
    suite_type: "benchmark",
    dataset_id: "",
    config: "",
    run_suite_id: "",
    run_model_id: "",
    run_parameters: "",
    complete_metrics: "",
    complete_status: "",
    guardrail_name: "",
    guardrail_scope: "input",
    guardrail_policy: "",
    guardrail_rate_limit: "",
    guardrail_environment: "",
    check_content: "",
    check_classification: "INTERNAL",
    check_environment: "",
    policy_name: "",
    policy_type: "",
    policy_effect: "ALLOW",
    policy_priority: "0",
    policy_conditions: "",
    policy_resource: "",
    policy_context: "",
    risk_system: "",
    risk_model_id: "",
    risk_risk_id: "",
    risk_severity: "MEDIUM",
    risk_likelihood: "MEDIUM",
    risk_impact: "MEDIUM",
    risk_mitigation: "",
    risk_status: "",
    card_purpose: "",
    card_risk: "",
    card_version: "",
    card_environments: "",
    card_system: "",
    approval_type: "",
    approval_model_id: "",
    approval_provider: "",
    approval_version: "",
    approval_reason: "",
    approval_id: "",
    approver: "",
    decision: "approved",
    snapshot_model_id: "",
    snapshot_latency: "",
    snapshot_error_rate: "",
    snapshot_tokens: "",
    snapshot_cost: "",
    snapshot_quality: "",
    snapshot_safety: "",
    drift_model_id: "",
    drift_window: "100",
    deploy_version: "",
    deploy_environment: "production",
    deploy_provider: "",
    deploy_approved_by: "",
    rollback_id: "",
    gateway_model_id: "",
    gateway_prompt: "",
    gateway_classification: "INTERNAL",
    gateway_purpose: "",
    route_purpose: "",
    route_model_hint: "",
    route_provider_hint: "",
    route_region_hint: "",
    route_budget: "",
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
    setSnapshotsLoading(true);
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
      setLastDeployment(null);
      setGatewayResult(null);
      setGatewayRoute(null);
      setDriftResult(null);
      setCheckResult(null);
      setEvalPolicyResult(null);
      setRiskAssess(null);
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

  timelineEvents.sort((a, b) => String(a.at ?? "").localeCompare(String(b.at ?? "")));

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
      if (e instanceof ApiError && e.status === 503) {
        pushToast("warning", "Backend service temporarily unavailable — retry shortly");
        return;
      }
      pushToast("error", e instanceof Error ? e.message : fallback);
    },
    [pushToast],
  );

  const canModelWrite = hasAnyPermission(permissions, [
    PERMISSIONS.mlModelCreate as unknown as string,
    PERMISSIONS.mlModelUpdate as unknown as string,
  ] as unknown as Parameters<typeof hasAnyPermission>[1]);
  void canModelWrite;

  function resetDraft() {
    setDraft({
      name: "",
      provider: "",
      version: "1.0",
      type: "foundation",
      capabilities: "",
      license: "",
      region: "",
      risk_level: "LOW",
      owner: "",
      status: "ACTIVE",
      artifact: "",
      display_name: "",
      models: "",
      regions: "",
      availability: "AVAILABLE",
      security_status: "UNKNOWN",
      prompt_id: "",
      prompt_name: "",
      purpose: "",
      classification: "INTERNAL",
      model_compatibility: "",
      content: "",
      suite_name: "",
      suite_type: "benchmark",
      dataset_id: "",
      config: "",
      run_suite_id: "",
      run_model_id: "",
      run_parameters: "",
      complete_metrics: "",
      complete_status: "",
      guardrail_name: "",
      guardrail_scope: "input",
      guardrail_policy: "",
      guardrail_rate_limit: "",
      guardrail_environment: "",
      check_content: "",
      check_classification: "INTERNAL",
      check_environment: "",
      policy_name: "",
      policy_type: "",
      policy_effect: "ALLOW",
      policy_priority: "0",
      policy_conditions: "",
      policy_resource: "",
      policy_context: "",
      risk_system: "",
      risk_model_id: "",
      risk_risk_id: "",
      risk_severity: "MEDIUM",
      risk_likelihood: "MEDIUM",
      risk_impact: "MEDIUM",
      risk_mitigation: "",
      risk_status: "",
      card_purpose: "",
      card_risk: "",
      card_version: "",
      card_environments: "",
      card_system: "",
      approval_type: "",
      approval_model_id: "",
      approval_provider: "",
      approval_version: "",
      approval_reason: "",
      approval_id: "",
      approver: "",
      decision: "approved",
      snapshot_model_id: "",
      snapshot_latency: "",
      snapshot_error_rate: "",
      snapshot_tokens: "",
      snapshot_cost: "",
      snapshot_quality: "",
      snapshot_safety: "",
      drift_model_id: "",
      drift_window: "100",
      deploy_version: "",
      deploy_environment: "production",
      deploy_provider: "",
      deploy_approved_by: "",
      rollback_id: "",
      gateway_model_id: "",
      gateway_prompt: "",
      gateway_classification: "INTERNAL",
      gateway_purpose: "",
      route_purpose: "",
      route_model_hint: "",
      route_provider_hint: "",
      route_region_hint: "",
      route_budget: "",
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

  function splitList(raw: string): string[] {
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }

  async function authedToken(): Promise<string | null> {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return null;
    }
    return token;
  }

  async function handleModelCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.provider.trim() || !draft.name.trim() || !draft.version.trim()) {
      pushToast("warning", "Provider, name and version are required");
      return;
    }
    let capabilities: Record<string, unknown> = {};
    try {
      capabilities = parseJsonObject(draft.capabilities, "Capabilities");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlModelCreate(token, {
        provider: draft.provider.trim(),
        name: draft.name.trim(),
        version: draft.version.trim(),
        type: draft.type.trim() || "foundation",
        capabilities,
        license: draft.license.trim() || undefined,
        region: draft.region.trim() || undefined,
        risk_level: draft.risk_level,
        owner: draft.owner.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Model ${result.name ?? result.id} registered`);
      setSelectedModelId(result.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register model", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleModelVersionCreate() {
    if (!selectedModelId) return;
    const token = await authedToken();
    if (!token) return;
    if (!draft.version.trim()) {
      pushToast("warning", "Version is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlModelVersionCreate(token, selectedModelId, {
        version: draft.version.trim(),
        artifact: draft.artifact.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Version ${result.version ?? "?"} recorded (immutable)`);
      void loadModelDetail(selectedModelId);
    } catch (e) {
      notifyError(e, "Failed to record version");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleModelStatus(status: string) {
    if (!selectedModelId) return;
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      const result = await api.mlModelStatus(token, selectedModelId, status);
      setModal(null);
      pushToast("success", `Model status is now ${result.status ?? status}`);
      void loadModelDetail(selectedModelId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update status", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleModelApprove() {
    if (!selectedModelId) return;
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      await api.mlModelApprove(token, selectedModelId);
      setModal(null);
      pushToast("success", "Model approved");
      void loadModelDetail(selectedModelId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to approve model", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleModelBlock() {
    if (!selectedModelId) return;
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      await api.mlModelBlock(token, selectedModelId);
      setModal(null);
      pushToast("success", "Model blocked");
      void loadModelDetail(selectedModelId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to block model", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleProviderCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.provider.trim() || !draft.display_name.trim()) {
      pushToast("warning", "Provider key and display name are required");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlProviderCreate(token, {
        provider: draft.provider.trim(),
        display_name: draft.display_name.trim(),
        models: splitList(draft.models),
        regions: splitList(draft.regions),
        availability: draft.availability,
        security_status: draft.security_status,
      });
      setModal(null);
      pushToast("success", `Provider ${draft.provider.trim()} registered`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register provider", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleProviderAvailability() {
    if (!selectedProvider) return;
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      await api.mlProviderAvailability(token, selectedProvider, draft.availability);
      setModal(null);
      pushToast("success", `Provider availability is now ${draft.availability}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update availability", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePromptCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.prompt_id.trim() || !draft.prompt_name.trim() || !draft.content) {
      pushToast("warning", "Prompt ID, name and content are required");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlPromptCreate(token, {
        prompt_id: draft.prompt_id.trim(),
        name: draft.prompt_name.trim(),
        purpose: draft.purpose.trim() || undefined,
        classification: draft.classification,
        model_compatibility: splitList(draft.model_compatibility),
        content: draft.content,
        owner: draft.owner.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Prompt registered — content stored server-side, never displayed back");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register prompt", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePromptVersionCreate() {
    if (!selectedPromptId) return;
    const token = await authedToken();
    if (!token) return;
    if (!draft.content) {
      pushToast("warning", "Version content is required");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlPromptVersionCreate(token, selectedPromptId, {
        content: draft.content,
        owner: draft.owner.trim() || undefined,
        purpose: draft.purpose.trim() || undefined,
        classification: draft.classification,
      });
      setModal(null);
      pushToast("success", "Prompt version recorded (immutable)");
      void loadPromptDetail(selectedPromptId);
    } catch (e) {
      notifyError(e, "Failed to record prompt version");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEvalSuiteCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.name.trim() || !draft.suite_type?.trim()) {
      pushToast("warning", "Suite name and type are required");
      return;
    }
    let config: Record<string, unknown> = {};
    try {
      config = parseJsonObject(draft.config, "Config");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlEvalSuiteCreate(token, {
        name: draft.name.trim(),
        suite_type: draft.suite_type.trim(),
        dataset_id: draft.dataset_id.trim() || undefined,
        config,
      });
      setModal(null);
      pushToast("success", "Evaluation suite created");
    } catch (e) {
      notifyError(e, "Failed to create suite");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEvalRunCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.run_suite_id.trim()) {
      pushToast("warning", "Suite ID is required");
      return;
    }
    let parameters: Record<string, unknown> = {};
    try {
      parameters = parseJsonObject(draft.run_parameters, "Parameters");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlEvalRunCreate(token, {
        suite_id: draft.run_suite_id.trim(),
        model_id: draft.run_model_id.trim() || undefined,
        parameters,
      });
      setModal(null);
      pushToast("success", `Evaluation run ${result.id.slice(0, 8)} created`);
      setEvalRunId(result.id);
      setEvalRun(result);
    } catch (e) {
      notifyError(e, "Failed to create evaluation run");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEvalRunComplete() {
    if (!evalRun) return;
    const token = await authedToken();
    if (!token) return;
    let metrics: Record<string, unknown> = {};
    try {
      metrics = parseJsonObject(draft.complete_metrics, "Metrics");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlEvalRunComplete(token, evalRun.id, {
        metrics,
        status: draft.complete_status.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Run completed with status ${result.status ?? "—"}`);
      setEvalRunId(result.id);
      setEvalRun(result);
    } catch (e) {
      notifyError(e, "Failed to complete run");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGuardrailCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.guardrail_name.trim()) {
      pushToast("warning", "Guardrail name is required");
      return;
    }
    let policy: Record<string, unknown> = {};
    try {
      policy = parseJsonObject(draft.guardrail_policy, "Policy");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlGuardrailCreate(token, {
        name: draft.guardrail_name.trim(),
        scope: draft.guardrail_scope,
        policy,
        rate_limit: draft.guardrail_rate_limit.trim() ? Number(draft.guardrail_rate_limit) : undefined,
        environment: draft.guardrail_environment.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Guardrail created");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create guardrail", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGuardrailCheck(side: "input" | "output") {
    const token = await authedToken();
    if (!token) return;
    if (!draft.check_content) {
      pushToast("warning", "Content is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlGuardrailCheck(token, side, {
        content: draft.check_content,
        classification: draft.check_classification,
        environment: draft.check_environment.trim() || undefined,
      });
      setCheckResult(result);
      pushToast("success", `Guardrail check: ${result.decision}`);
    } catch (e) {
      notifyError(e, "Guardrail check failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePolicyCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.policy_name.trim() || !draft.policy_type.trim()) {
      pushToast("warning", "Policy name and type are required");
      return;
    }
    let conditions: Record<string, unknown> | undefined;
    if (draft.policy_conditions.trim()) {
      try {
        conditions = parseJsonObject(draft.policy_conditions, "Conditions");
      } catch (e) {
        pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
        return;
      }
    }
    setSubmitting(true);
    try {
      await api.mlPolicyCreate(token, {
        name: draft.policy_name.trim(),
        policy_type: draft.policy_type.trim(),
        effect: draft.policy_effect,
        priority: Number(draft.policy_priority) || 0,
        conditions,
      });
      setModal(null);
      pushToast("success", "Policy created");
    } catch (e) {
      notifyError(e, "Failed to create policy");
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePolicyEvaluate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.policy_resource.trim()) {
      pushToast("warning", "Resource is required");
      return;
    }
    let context: Record<string, unknown> = {};
    try {
      context = parseJsonObject(draft.policy_context, "Context");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlPolicyEvaluate(token, { resource: draft.policy_resource.trim(), context });
      setEvalPolicyResult(result);
      pushToast("success", `Policy decision: ${result.decision}`);
    } catch (e) {
      notifyError(e, "Policy evaluation failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePolicySimulate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.policy_resource.trim()) {
      pushToast("warning", "Resource is required");
      return;
    }
    let context: Record<string, unknown> = {};
    try {
      context = parseJsonObject(draft.policy_context, "Context");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlPolicySimulate(token, { resource: draft.policy_resource.trim(), context });
      setEvalPolicyResult(result);
      pushToast("success", `Simulation decision: ${result.decision} (no side effects)`);
    } catch (e) {
      notifyError(e, "Policy simulation failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRiskCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.risk_system.trim() || !draft.risk_risk_id.trim()) {
      pushToast("warning", "System and risk ID are required");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlRiskCreate(token, {
        system: draft.risk_system.trim(),
        model_id: draft.risk_model_id.trim() || undefined,
        risk_id: draft.risk_risk_id.trim(),
        severity: draft.risk_severity,
        likelihood: draft.risk_likelihood,
        impact: draft.risk_impact,
        owner: draft.owner.trim() || undefined,
        mitigation: draft.risk_mitigation.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Risk record created");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create risk", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRiskAssess() {
    if (!selectedRiskId) return;
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      const result = await api.mlRiskAssess(token, selectedRiskId, {
        status: draft.risk_status.trim() || undefined,
        severity: draft.risk_severity,
        likelihood: draft.risk_likelihood,
        impact: draft.risk_impact,
      });
      setRiskAssess(result);
      setModal(null);
      pushToast("success", "Risk assessed — score is a governance heuristic, not a legal conclusion");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to assess risk", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleModelCardCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!selectedModelId) {
      pushToast("warning", "Select a model first");
      setModal(null);
      return;
    }
    setSubmitting(true);
    try {
      await api.mlModelCardCreate(token, {
        model_id: selectedModelId,
        purpose: draft.card_purpose.trim() || undefined,
        risk: draft.card_risk.trim() || undefined,
        version: draft.card_version.trim() || undefined,
        approved_environments: splitList(draft.card_environments),
      });
      setModal(null);
      pushToast("success", "Model card recorded");
      void loadModelDetail(selectedModelId);
    } catch (e) {
      notifyError(e, "Failed to record model card");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSystemCardCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.card_system.trim()) {
      pushToast("warning", "System name is required");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlSystemCardCreate(token, {
        system: draft.card_system.trim(),
        purpose: draft.card_purpose.trim() || undefined,
        models: splitList(draft.models),
        human_oversight: draft.owner.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "System card recorded");
    } catch (e) {
      notifyError(e, "Failed to record system card");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApprovalCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.approval_type.trim()) {
      pushToast("warning", "Request type is required");
      return;
    }
    setSubmitting(true);
    try {
      await api.mlApprovalCreate(token, {
        request_type: draft.approval_type.trim(),
        model_id: draft.approval_model_id.trim() || undefined,
        provider: draft.approval_provider.trim() || undefined,
        version: draft.approval_version.trim() || undefined,
        reason: draft.approval_reason.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Approval requested");
    } catch (e) {
      notifyError(e, "Failed to request approval");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApprovalDecide() {
    if (!draft.approval_id.trim() || !draft.approver.trim()) {
      pushToast("warning", "Approval ID and approver are required");
      return;
    }
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      await api.mlApprovalDecide(token, draft.approval_id.trim(), {
        approver: draft.approver.trim(),
        decision: draft.decision,
      });
      setModal(null);
      pushToast("success", `Approval ${draft.decision}`);
    } catch (e) {
      notifyError(e, "Failed to decide approval");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleMonitoringSnapshot() {
    const token = await authedToken();
    if (!token) return;
    const num = (raw: string) => (raw.trim() ? Number(raw) : undefined);
    setSubmitting(true);
    try {
      await api.mlMonitoringSnapshot(token, {
        model_id: draft.snapshot_model_id.trim() || selectedModelId || undefined,
        provider: draft.provider.trim() || undefined,
        availability: draft.availability,
        latency_ms: num(draft.snapshot_latency),
        error_rate: num(draft.snapshot_error_rate),
        token_usage: num(draft.snapshot_tokens),
        cost: num(draft.snapshot_cost),
        quality: num(draft.snapshot_quality),
        safety: num(draft.snapshot_safety),
      });
      setModal(null);
      pushToast("success", "Monitoring snapshot recorded as reported");
      if (selectedModelId) void loadModelDetail(selectedModelId);
    } catch (e) {
      notifyError(e, "Failed to record snapshot");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDriftCheck() {
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      const result = await api.mlMonitoringDrift(token, {
        model_id: draft.drift_model_id.trim() || selectedModelId || undefined,
        window: draft.drift_window.trim() ? Number(draft.drift_window) : 100,
      });
      setDriftResult(result);
      pushToast(
        result.insufficient_data ? "warning" : "success",
        result.insufficient_data
          ? `Insufficient data (${result.sample_count ?? 0} samples) — no drift claimed`
          : result.drift_detected
            ? "Drift detected by backend analysis"
            : "No drift detected",
      );
    } catch (e) {
      notifyError(e, "Drift check failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGatewayRoute() {
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      const result = await api.mlGatewayRoute(token, {
        purpose: draft.route_purpose.trim() || undefined,
        data_classification: draft.gateway_classification,
        model_hint: draft.route_model_hint.trim() || undefined,
        provider_hint: draft.route_provider_hint.trim() || undefined,
        region_hint: draft.route_region_hint.trim() || undefined,
        budget: draft.route_budget.trim() ? Number(draft.route_budget) : undefined,
      });
      setGatewayRoute(result);
      pushToast("success", `Gateway routing decision: ${result.decision}`);
    } catch (e) {
      notifyError(e, "Gateway routing failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGatewayInvoke() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.gateway_model_id.trim() || !draft.gateway_prompt) {
      pushToast("warning", "Model and prompt are required");
      return;
    }
    setExecuting(true);
    setExecError(null);
    try {
      const result = await api.mlGatewayInvoke(token, {
        model_id: draft.gateway_model_id.trim(),
        prompt: draft.gateway_prompt,
        data_classification: draft.gateway_classification,
        purpose: draft.gateway_purpose.trim() || undefined,
      });
      setModal(null);
      setGatewayResult(result);
      pushToast("success", "Gateway invocation completed (mocked provider result)");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "timeout") {
        setExecError("REQUEST TIMED OUT — the server may still be processing. This does not imply cancellation.");
        return;
      }
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setExecError(e instanceof Error ? e.message : "Gateway invocation failed");
    } finally {
      setExecuting(false);
    }
  }

  async function handleDeployCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!selectedModelId) {
      pushToast("warning", "Select a model first");
      setModal(null);
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlDeploymentCreate(token, {
        model_id: selectedModelId,
        version: draft.deploy_version.trim() || undefined,
        environment: draft.deploy_environment.trim() || "production",
        provider: draft.deploy_provider.trim() || undefined,
        approved_by: draft.deploy_approved_by.trim() || undefined,
      });
      setLastDeployment(result);
      setModal(null);
      pushToast("success", `Deployment ${result.id.slice(0, 8)} recorded — keep this ID: listings are not exposed`);
      void loadModelDetail(selectedModelId);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create deployment", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeployRollback() {
    const token = await authedToken();
    if (!token) return;
    const deploymentId = draft.rollback_id.trim() || lastDeployment?.id || "";
    if (!deploymentId) {
      pushToast("warning", "A deployment ID is required (use the ID from a create response)");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.mlDeploymentRollback(token, deploymentId);
      setLastDeployment(result);
      setModal(null);
      pushToast("success", `Deployment rolled back — linked model deprecated`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to roll back deployment", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "registry", label: "Registry" },
    { id: "prompts", label: "Prompts" },
    { id: "evaluations", label: "Evaluations" },
    { id: "risks", label: "Risks" },
    { id: "monitoring", label: "Monitoring" },
    { id: "deployments", label: "Deployments" },
    { id: "gateway", label: "Gateway" },
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
                {hasPermission(permissions, PERMISSIONS.mlModelCreate) ? (
                  <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("model-create"); }}>New model</BrutalButton>
                ) : null}
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
                  {hasAnyPermission(permissions, [PERMISSIONS.mlModelVersion, PERMISSIONS.mlModelUpdate, PERMISSIONS.mlModelApprove, PERMISSIONS.mlModelBlock]) ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      {hasPermission(permissions, PERMISSIONS.mlModelVersion) ? (
                        <BrutalButton size="sm" variant="ghost" aria-label="Record version" onClick={() => { resetDraft(); setModal("version-create"); }}>
                          Record version
                        </BrutalButton>
                      ) : null}
                      {hasPermission(permissions, PERMISSIONS.mlModelUpdate) ? (
                        <BrutalButton size="sm" variant="ghost" aria-label="Set status" onClick={() => { resetDraft(); setModal("model-status"); }}>
                          Set status
                        </BrutalButton>
                      ) : null}
                      {hasPermission(permissions, PERMISSIONS.mlModelApprove) ? (
                        <BrutalButton size="sm" variant="ghost" aria-label="Approve model" onClick={() => setModal("model-approve")}>
                          Approve
                        </BrutalButton>
                      ) : null}
                      {hasPermission(permissions, PERMISSIONS.mlModelBlock) ? (
                        <BrutalButton size="sm" variant="ghost" aria-label="Block model" onClick={() => setModal("model-block")}>
                          Block
                        </BrutalButton>
                      ) : null}
                    </div>
                  ) : null}
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
                {hasPermission(permissions, PERMISSIONS.mlProviderCreate) ? (
                  <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("provider-create"); }}>New provider</BrutalButton>
                ) : null}
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
                    {hasPermission(permissions, PERMISSIONS.mlProviderUpdate) ? (
                      <div className="pt-2">
                        <BrutalButton size="sm" variant="ghost" aria-label="Set availability" onClick={() => { resetDraft(); setModal("provider-availability"); }}>
                          Set availability
                        </BrutalButton>
                      </div>
                    ) : null}
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
            {hasPermission(permissions, PERMISSIONS.mlPromptCreate) ? (
              <div className="mb-3">
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("prompt-create"); }}>New prompt</BrutalButton>
              </div>
            ) : null}
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
                  {hasPermission(permissions, PERMISSIONS.mlPromptVersion) ? (
                    <div className="pt-2">
                      <BrutalButton size="sm" variant="ghost" aria-label="Record prompt version" onClick={() => { resetDraft(); setModal("prompt-version"); }}>
                        Record version
                      </BrutalButton>
                    </div>
                  ) : null}
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
            {hasPermission(permissions, PERMISSIONS.mlEvalCreate) ? (
              <div className="mb-3 flex flex-wrap gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("eval-suite"); }}>New suite</BrutalButton>
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("eval-run"); }}>New run</BrutalButton>
              </div>
            ) : null}
            {hasAnyPermission(permissions, [PERMISSIONS.mlEvalCreate]) ? (
              <div className="mb-3 flex flex-wrap gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("eval-suite"); }}>New suite</BrutalButton>
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("eval-run"); }}>New run</BrutalButton>
              </div>
            ) : null}
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
                {hasPermission(permissions, PERMISSIONS.mlEvalComplete) ? (
                  <div className="pt-2">
                    <BrutalButton size="sm" variant="ghost" aria-label="Complete run" onClick={() => { resetDraft(); setModal("eval-complete"); }}>
                      Complete run
                    </BrutalButton>
                  </div>
                ) : null}
                {hasPermission(permissions, PERMISSIONS.mlEvalComplete) ? (
                  <div className="pt-2">
                    <BrutalButton size="sm" variant="ghost" aria-label="Complete run" onClick={() => { resetDraft(); setModal("eval-complete"); }}>
                      Complete run
                    </BrutalButton>
                  </div>
                ) : null}
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
            {hasPermission(permissions, PERMISSIONS.mlRiskCreate) ? (
              <div className="mb-3">
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("risk-create"); }}>New risk</BrutalButton>
              </div>
            ) : null}
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
                  {hasPermission(permissions, PERMISSIONS.mlRiskAssess) ? (
                    <div className="pt-2">
                      <BrutalButton size="sm" variant="ghost" aria-label="Assess risk" onClick={() => { resetDraft(); setModal("risk-assess"); }}>
                        Assess risk
                      </BrutalButton>
                    </div>
                  ) : null}
                  {riskAssess ? (
                    <div className="border border-outline bg-surface p-3">
                      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Assessed score</p>
                      <p className="font-mono text-xl text-on-surface">{riskAssess.assessed_score ?? "—"}</p>
                      <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{riskAssess.note ?? RISK_SCORE_CAVEAT}</p>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Guardrails" title="Guardrails">
            {hasPermission(permissions, PERMISSIONS.mlGuardrailCreate) ? (
              <div className="mb-3">
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("guardrail-create"); }}>New guardrail</BrutalButton>
              </div>
            ) : null}
            <div className="mb-3 rounded-none border border-outline bg-surface p-3">
              <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Check content (read-effect, no permission gate)</p>
              <div className="space-y-2">
                <BrutalInput label="Content" value={draft.check_content} onChange={(e) => setDraft((d) => ({ ...d, check_content: e.target.value }))} placeholder="text to check" />
                <div className="flex flex-wrap gap-2">
                  <BrutalButton size="sm" variant="ghost" onClick={() => void handleGuardrailCheck("input")} disabled={submitting}>Check input</BrutalButton>
                  <BrutalButton size="sm" variant="ghost" onClick={() => void handleGuardrailCheck("output")} disabled={submitting}>Check output</BrutalButton>
                </div>
              </div>
              {checkError ? <p className="mt-2 text-xs text-error">{checkError}</p> : null}
              {checkResult ? (
                <div className="mt-2 border-t border-outline pt-2">
                  <div className="mb-1 flex items-center gap-2">
                    <BrutalBadge tone={checkResult.decision === "DENY" ? "error" : checkResult.decision === "ALLOW" ? "yellow" : "default"}>{checkResult.decision}</BrutalBadge>
                  </div>
                  <StatRow label="Reason" value={checkResult.reason || "—"} />
                </div>
              ) : null}
            </div>
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
            <div className="mb-3 flex flex-wrap gap-2">
              {hasPermission(permissions, PERMISSIONS.mlMonitoringCreate) ? (
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setDraft((d) => ({ ...d, snapshot_model_id: selectedModelId ?? "" })); setModal("monitoring-snapshot"); }}>
                  Record snapshot
                </BrutalButton>
              ) : null}
              <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setDraft((d) => ({ ...d, drift_model_id: selectedModelId ?? "" })); setModal("monitoring-drift"); }} disabled={!selectedModelId}>
                Check drift
              </BrutalButton>
            </div>
            {driftError ? <p className="mb-2 text-xs text-error">{driftError}</p> : null}
            {driftResult ? (
              <div className="mb-3 border border-outline bg-surface p-3">
                <div className="mb-1 flex items-center gap-2">
                  <BrutalBadge tone={driftResult.drift_detected ? "error" : "yellow"}>
                    {driftResult.insufficient_data ? "insufficient data" : driftResult.drift_detected ? "drift detected" : "no drift"}
                  </BrutalBadge>
                  <span className="font-mono text-xs text-on-surface-variant">samples {driftResult.sample_count ?? "—"}</span>
                </div>
                {driftResult.reason ? <p className="text-xs text-on-surface-variant">{driftResult.reason}</p> : null}
              </div>
            ) : null}
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
        <div className="space-y-6">
          <BrutalCard eyebrow="Deployments" title="Deployment state">
            <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">NOT EXPOSED BY API</p>
            <p className="mt-2 text-sm text-on-surface-variant">
              Deployment state currently exists only in backend process memory and no deployment-list endpoint is available to the frontend.
            </p>
          </BrutalCard>
          <BrutalCard eyebrow="Deployments" title="Operations">
            <p className="mb-2 text-xs text-on-surface-variant">
              Deployment creation and rollback are verified endpoints. Keep the returned deployment ID — listings do not exist, and IDs are held in this view only (never persisted).
            </p>
            <div className="flex flex-wrap gap-2">
              {hasPermission(permissions, PERMISSIONS.mlDeployCreate) ? (
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("deploy-create"); }} disabled={!selectedModelId}>
                  Deploy selected model
                </BrutalButton>
              ) : null}
              {hasPermission(permissions, PERMISSIONS.mlDeployRollback) ? (
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setDraft((d) => ({ ...d, rollback_id: lastDeployment?.id ?? "" })); setModal("deploy-rollback"); }}>
                  Roll back
                </BrutalButton>
              ) : null}
            </div>
            {!selectedModelId ? (
              <p className="mt-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Select a model in the Registry tab to scope deployment.</p>
            ) : null}
            {lastDeployment ? (
              <div className="mt-3 space-y-1 border-t border-outline pt-2">
                <StatRow label="Deployment" value={lastDeployment.id} />
                <StatRow label="Status" value={lastDeployment.status ?? "—"} />
                <StatRow label="Environment" value={lastDeployment.environment ?? "—"} />
              </div>
            ) : null}
          </BrutalCard>
        </div>
      ) : null}

      {active === "gateway" ? (
        <div className="space-y-6">
          <BrutalCard eyebrow="Gateway" title="Route selection">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
              Route selection is a server-side read-effect hint — never a policy decision.
            </p>
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Purpose" value={draft.route_purpose} onChange={(e) => setDraft((d) => ({ ...d, route_purpose: e.target.value }))} placeholder="optional" />
                <BrutalInput label="Model hint" value={draft.route_model_hint} onChange={(e) => setDraft((d) => ({ ...d, route_model_hint: e.target.value }))} placeholder="optional" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Provider hint" value={draft.route_provider_hint} onChange={(e) => setDraft((d) => ({ ...d, route_provider_hint: e.target.value }))} placeholder="optional" />
                <BrutalInput label="Region hint" value={draft.route_region_hint} onChange={(e) => setDraft((d) => ({ ...d, route_region_hint: e.target.value }))} placeholder="optional" />
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-32 flex-1">
                  <BrutalInput label="Budget" value={draft.route_budget} onChange={(e) => setDraft((d) => ({ ...d, route_budget: e.target.value }))} placeholder="optional" />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void handleGatewayRoute()} disabled={submitting}>
                  {submitting ? "Routing…" : "Route"}
                </BrutalButton>
              </div>
            </div>
            {gatewayRoute ? (
              <div className="mt-3 space-y-1 border border-outline bg-surface p-3">
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">AI GATEWAY ROUTE</p>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-block border border-outline bg-surface px-2 py-1 font-mono text-[10px] uppercase tracking-widest">{gatewayRoute.decision ?? "—"}</span>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{gatewayRoute.reason ?? ""}</span>
                </div>
                <StatRow label="Model" value={gatewayRoute.model_name ?? gatewayRoute.model_id ?? "—"} />
              </div>
            ) : null}
          </BrutalCard>

          <BrutalCard eyebrow="Gateway" title="Model invoke">
            <p className="mb-2 text-xs text-on-surface-variant">
              Provider invocations run server-side against a MOCKED provider in this environment. Confirm before any payload is sent.
            </p>
            {hasPermission(permissions, PERMISSIONS.mlGatewayInvoke) ? (
              <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("gateway-invoke"); }}>
                Invoke model
              </BrutalButton>
            ) : (
              <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Gateway invoke requires aiml.gateway.invoke</p>
            )}
            {execError ? (
              <p className="mt-3 border border-error bg-surface p-2 font-mono text-xs text-error">{execError}</p>
            ) : null}
            {gatewayResult ? (
              <div className="mt-3 space-y-1 border border-outline bg-surface p-3">
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">AI GATEWAY RESULT</p>
                <p className="inline-block border border-outline bg-surface px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                  MOCKED / NON-PRODUCTION
                </p>
                <StatRow label="Model" value={gatewayResult.model_name ?? gatewayResult.model_id ?? "—"} />
                <StatRow label="Provider" value={gatewayResult.provider ?? "—"} />
                <div className="whitespace-pre-wrap break-words border border-outline bg-surface p-2 font-mono text-xs text-on-surface">
                  {typeof gatewayResult.output === "string" ? gatewayResult.output : gatewayResult.output !== null && gatewayResult.output !== undefined ? JSON.stringify(gatewayResult.output) : "—"}
                </div>
                {gatewayResult.prompt_fingerprint ? <StatRow label="Prompt fingerprint" value={gatewayResult.prompt_fingerprint} /> : null}
                {gatewayResult.provider_call ? <StatRow label="Provider call" value={JSON.stringify(gatewayResult.provider_call)} /> : null}
              </div>
            ) : null}
          </BrutalCard>
        </div>
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
            <div className="mb-3 grid grid-cols-2 gap-2">
              <div className="rounded-none border border-outline bg-surface p-3">
                <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Model cards</p>
                {hasPermission(permissions, PERMISSIONS.mlCardCreate) ? (
                  <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("model-card"); }} disabled={!selectedModelId}>
                    Record model card
                  </BrutalButton>
                ) : (
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Card creation requires aiml.card.create</p>
                )}
              </div>
              <div className="rounded-none border border-outline bg-surface p-3">
                <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">System cards</p>
                <BrutalInput label="System" value={systemCardInput} onChange={(e) => setSystemCardInput(e.target.value)} placeholder="name or card ID" />
                <div className="mt-2 flex flex-wrap gap-2">
                  <BrutalButton variant="ghost" size="sm" onClick={() => void loadSystemCards()} disabled={systemCardsLoading}>
                    {systemCardsLoading ? "Loading…" : "Look up"}
                  </BrutalButton>
                  {hasPermission(permissions, PERMISSIONS.mlSystemCardCreate) ? (
                    <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("system-card"); }}>
                      Record system card
                    </BrutalButton>
                  ) : null}
                </div>
              </div>
            </div>
            {hasPermission(permissions, PERMISSIONS.mlCardCreate) ? (
              <div className="mb-3 flex flex-wrap gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("model-card"); }} disabled={!selectedModelId}>
                  Record model card
                </BrutalButton>
                <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("system-card"); }}>
                  Record system card
                </BrutalButton>
              </div>
            ) : null}
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

          <BrutalCard eyebrow="Governance" title="Policy & approvals">
            {hasPermission(permissions, PERMISSIONS.mlPolicyCreate) ? (
              <div className="mb-3">
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal("policy-create"); }}>New policy</BrutalButton>
              </div>
            ) : null}
            <div className="mb-3 rounded-none border border-outline bg-surface p-3">
              <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Evaluate / simulate (read-effect, no permission gate)</p>
              <div className="space-y-2">
                <BrutalInput label="Resource" value={draft.policy_resource} onChange={(e) => setDraft((d) => ({ ...d, policy_resource: e.target.value }))} placeholder="model or resource id" />
                <BrutalInput label="Context (JSON)" value={draft.policy_context} onChange={(e) => setDraft((d) => ({ ...d, policy_context: e.target.value }))} placeholder="{}" />
                <div className="flex flex-wrap gap-2">
                  <BrutalButton size="sm" variant="ghost" onClick={() => void handlePolicyEvaluate()} disabled={submitting}>Evaluate</BrutalButton>
                  <BrutalButton size="sm" variant="ghost" onClick={() => void handlePolicySimulate()} disabled={submitting}>Simulate</BrutalButton>
                </div>
              </div>
              {evalPolicyError ? <p className="mt-2 text-xs text-error">{evalPolicyError}</p> : null}
              {evalPolicyResult ? (
                <div className="mt-2 border-t border-outline pt-2">
                  <div className="mb-1 flex items-center gap-2">
                    <BrutalBadge tone={evalPolicyResult.decision === "DENY" ? "error" : "yellow"}>{evalPolicyResult.decision}</BrutalBadge>
                  </div>
                  <StatRow label="Reason" value={evalPolicyResult.reason || "—"} />
                </div>
              ) : null}
            </div>
            <div className="rounded-none border border-outline bg-surface p-3">
              <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Approvals</p>
              {hasPermission(permissions, PERMISSIONS.mlApprovalCreate) ? (
                <div className="mb-2">
                  <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal("approval-create"); }}>Request approval</BrutalButton>
                </div>
              ) : null}
              <div className="space-y-2">
                <BrutalInput label="Approval ID" value={draft.approval_id} onChange={(e) => setDraft((d) => ({ ...d, approval_id: e.target.value }))} placeholder="uuid from a request response" />
                <BrutalInput label="Approver" value={draft.approver} onChange={(e) => setDraft((d) => ({ ...d, approver: e.target.value }))} placeholder="your identity" />
                <div className="flex flex-wrap items-end gap-2">
                  <div className="min-w-28 flex-1">
                    <BrutalSelect label="Decision" value={draft.decision} onChange={(e) => setDraft((d) => ({ ...d, decision: e.target.value }))} options={["approved", "rejected", "approve", "reject", "allow", "deny"].map((s) => ({ label: s, value: s }))} />
                  </div>
                  {hasPermission(permissions, PERMISSIONS.mlApprovalDecide) ? (
                    <BrutalButton variant="ghost" size="sm" onClick={() => void handleApprovalDecide()} disabled={submitting}>Decide</BrutalButton>
                  ) : null}
                </div>
              </div>
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

      <BrutalModal open={modal === "model-create"} title="Register model" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleModelCreate()} disabled={submitting}>{submitting ? "Registering…" : "Register"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput id="ml-mc-provider" label="Provider" value={draft.provider} onChange={(e) => setDraft((d) => ({ ...d, provider: e.target.value }))} />
            <BrutalInput id="ml-mc-name" label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput id="ml-mc-version" label="Version" value={draft.version} onChange={(e) => setDraft((d) => ({ ...d, version: e.target.value }))} />
            <BrutalInput id="ml-mc-type" label="Type" value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))} placeholder="foundation" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
            <BrutalInput label="Risk level" value={draft.risk_level} onChange={(e) => setDraft((d) => ({ ...d, risk_level: e.target.value }))} placeholder="LOW" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="License" value={draft.license} onChange={(e) => setDraft((d) => ({ ...d, license: e.target.value }))} />
            <BrutalInput label="Region" value={draft.region} onChange={(e) => setDraft((d) => ({ ...d, region: e.target.value }))} />
          </div>
          <BrutalInput label="Capabilities (JSON)" value={draft.capabilities} onChange={(e) => setDraft((d) => ({ ...d, capabilities: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "version-create"} title="Record model version" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleModelVersionCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Versions are immutable once recorded. Duplicates are rejected with 409.</p>
          <BrutalInput label="Version" value={draft.version} onChange={(e) => setDraft((d) => ({ ...d, version: e.target.value }))} />
          <BrutalInput label="Artifact ref" value={draft.artifact} onChange={(e) => setDraft((d) => ({ ...d, artifact: e.target.value }))} placeholder="optional storage reference" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "model-status"} title="Set model status?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleModelStatus(draft.status)} disabled={submitting}>{submitting ? "Saving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <BrutalSelect label="Status" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))} options={["DRAFT", "APPROVED", "ACTIVE", "DEPRECATED", "RETIRED", "BLOCKED"].map((s) => ({ label: s, value: s }))} />
      </BrutalModal>

      <BrutalModal open={modal === "model-approve"} title="Approve model?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleModelApprove()} disabled={submitting}>{submitting ? "Approving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">Approval transitions the model to APPROVED. Only approved or active models may be deployed or invoked.</p>
      </BrutalModal>

      <BrutalModal open={modal === "model-block"} title="Block model?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleModelBlock()} disabled={submitting}>{submitting ? "Blocking…" : "Confirm"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">Blocked models cannot be deployed or invoked until their status changes.</p>
      </BrutalModal>

      <BrutalModal open={modal === "provider-create"} title="Register provider" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleProviderCreate()} disabled={submitting}>{submitting ? "Registering…" : "Register"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider key" value={draft.provider} onChange={(e) => setDraft((d) => ({ ...d, provider: e.target.value }))} />
            <BrutalInput label="Display name" value={draft.display_name} onChange={(e) => setDraft((d) => ({ ...d, display_name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Models (comma-separated)" value={draft.models} onChange={(e) => setDraft((d) => ({ ...d, models: e.target.value }))} />
            <BrutalInput label="Regions (comma-separated)" value={draft.regions} onChange={(e) => setDraft((d) => ({ ...d, regions: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Availability" value={draft.availability} onChange={(e) => setDraft((d) => ({ ...d, availability: e.target.value }))} options={["AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "MAINTENANCE"].map((s) => ({ label: s, value: s }))} />
            <BrutalInput label="Security status" value={draft.security_status} onChange={(e) => setDraft((d) => ({ ...d, security_status: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "provider-availability"} title="Set provider availability?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleProviderAvailability()} disabled={submitting}>{submitting ? "Saving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <BrutalSelect label="Availability" value={draft.availability} onChange={(e) => setDraft((d) => ({ ...d, availability: e.target.value }))} options={["AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "MAINTENANCE"].map((s) => ({ label: s, value: s }))} />
      </BrutalModal>

      <BrutalModal open={modal === "prompt-create"} title="Register prompt" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePromptCreate()} disabled={submitting}>{submitting ? "Registering…" : "Register"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">Write-only content: stored server-side and never displayed back by this workspace.</p>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Prompt ID" value={draft.prompt_id} onChange={(e) => setDraft((d) => ({ ...d, prompt_id: e.target.value }))} />
            <BrutalInput label="Name" value={draft.prompt_name} onChange={(e) => setDraft((d) => ({ ...d, prompt_name: e.target.value }))} />
          </div>
          <BrutalInput label="Purpose" value={draft.purpose} onChange={(e) => setDraft((d) => ({ ...d, purpose: e.target.value }))} />
          <BrutalInput label="Content (one-time)" type="password" autoComplete="new-password" value={draft.content} onChange={(e) => setDraft((d) => ({ ...d, content: e.target.value }))} placeholder="••••••••" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Classification" value={draft.classification} onChange={(e) => setDraft((d) => ({ ...d, classification: e.target.value }))} />
            <BrutalInput label="Model compatibility" value={draft.model_compatibility} onChange={(e) => setDraft((d) => ({ ...d, model_compatibility: e.target.value }))} placeholder="comma-separated" />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "prompt-version"} title="Record prompt version" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePromptVersionCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">Write-only content: stored server-side and never displayed back by this workspace.</p>
          <BrutalInput label="Content (one-time)" type="password" autoComplete="new-password" value={draft.content} onChange={(e) => setDraft((d) => ({ ...d, content: e.target.value }))} placeholder="••••••••" />
          <BrutalInput label="Purpose" value={draft.purpose} onChange={(e) => setDraft((d) => ({ ...d, purpose: e.target.value }))} />
          <BrutalInput label="Classification" value={draft.classification} onChange={(e) => setDraft((d) => ({ ...d, classification: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "eval-suite"} title="New evaluation suite" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleEvalSuiteCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          <BrutalInput label="Suite type" value={draft.suite_type} onChange={(e) => setDraft((d) => ({ ...d, suite_type: e.target.value }))} placeholder="benchmark, regression, safety…" />
          <BrutalInput label="Dataset ID" value={draft.dataset_id} onChange={(e) => setDraft((d) => ({ ...d, dataset_id: e.target.value }))} placeholder="optional" />
          <BrutalInput label="Config (JSON)" value={draft.config} onChange={(e) => setDraft((d) => ({ ...d, config: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "eval-run"} title="New evaluation run" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleEvalRunCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Suite ID" value={draft.run_suite_id} onChange={(e) => setDraft((d) => ({ ...d, run_suite_id: e.target.value }))} />
          <BrutalInput label="Model ID" value={draft.run_model_id} onChange={(e) => setDraft((d) => ({ ...d, run_model_id: e.target.value }))} placeholder="optional uuid" />
          <BrutalInput label="Parameters (JSON)" value={draft.run_parameters} onChange={(e) => setDraft((d) => ({ ...d, run_parameters: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "eval-complete"} title="Complete evaluation run" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleEvalRunComplete()} disabled={submitting}>{submitting ? "Completing…" : "Complete"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Report the worker-observed metrics. Values are echoed verbatim — never scored client-side.</p>
          <BrutalInput label="Metrics (JSON)" value={draft.complete_metrics} onChange={(e) => setDraft((d) => ({ ...d, complete_metrics: e.target.value }))} placeholder='{"accuracy": 0.91}' />
          <BrutalInput label="Status" value={draft.complete_status} onChange={(e) => setDraft((d) => ({ ...d, complete_status: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "guardrail-create"} title="New guardrail" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleGuardrailCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.guardrail_name} onChange={(e) => setDraft((d) => ({ ...d, guardrail_name: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Scope" value={draft.guardrail_scope} onChange={(e) => setDraft((d) => ({ ...d, guardrail_scope: e.target.value }))} options={["input", "output", "both"].map((s) => ({ label: s, value: s }))} />
            <BrutalInput label="Environment" value={draft.guardrail_environment} onChange={(e) => setDraft((d) => ({ ...d, guardrail_environment: e.target.value }))} />
          </div>
          <BrutalInput label="Policy (JSON)" value={draft.guardrail_policy} onChange={(e) => setDraft((d) => ({ ...d, guardrail_policy: e.target.value }))} placeholder='{"blocked_keywords": []}' />
          <BrutalInput label="Rate limit" value={draft.guardrail_rate_limit} onChange={(e) => setDraft((d) => ({ ...d, guardrail_rate_limit: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "policy-create"} title="New policy" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePolicyCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Name" value={draft.policy_name} onChange={(e) => setDraft((d) => ({ ...d, policy_name: e.target.value }))} />
            <BrutalInput label="Type" value={draft.policy_type} onChange={(e) => setDraft((d) => ({ ...d, policy_type: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Effect" value={draft.policy_effect} onChange={(e) => setDraft((d) => ({ ...d, policy_effect: e.target.value }))} options={["ALLOW", "DENY", "REDACT", "REQUIRE_APPROVAL", "WARN", "ANONYMIZE", "ESCALATE"].map((s) => ({ label: s, value: s }))} />
            <BrutalInput label="Priority" value={draft.policy_priority} onChange={(e) => setDraft((d) => ({ ...d, policy_priority: e.target.value }))} />
          </div>
          <BrutalInput label="Conditions (JSON)" value={draft.policy_conditions} onChange={(e) => setDraft((d) => ({ ...d, policy_conditions: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "risk-create"} title="New risk record" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleRiskCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="System" value={draft.risk_system} onChange={(e) => setDraft((d) => ({ ...d, risk_system: e.target.value }))} />
            <BrutalInput label="Risk ID" value={draft.risk_risk_id} onChange={(e) => setDraft((d) => ({ ...d, risk_risk_id: e.target.value }))} />
          </div>
          <BrutalInput label="Model ID" value={draft.risk_model_id} onChange={(e) => setDraft((d) => ({ ...d, risk_model_id: e.target.value }))} placeholder="optional uuid" />
          <div className="grid grid-cols-3 gap-2">
            <BrutalSelect label="Severity" value={draft.risk_severity} onChange={(e) => setDraft((d) => ({ ...d, risk_severity: e.target.value }))} options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => ({ label: s, value: s }))} />
            <BrutalSelect label="Likelihood" value={draft.risk_likelihood} onChange={(e) => setDraft((d) => ({ ...d, risk_likelihood: e.target.value }))} options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => ({ label: s, value: s }))} />
            <BrutalSelect label="Impact" value={draft.risk_impact} onChange={(e) => setDraft((d) => ({ ...d, risk_impact: e.target.value }))} options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => ({ label: s, value: s }))} />
          </div>
          <BrutalInput label="Mitigation" value={draft.risk_mitigation} onChange={(e) => setDraft((d) => ({ ...d, risk_mitigation: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "risk-assess"} title="Assess risk?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleRiskAssess()} disabled={submitting}>{submitting ? "Assessing…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">The backend recomputes its heuristic score. Displayed scores always carry the governance caveat.</p>
          <div className="grid grid-cols-3 gap-2">
            <BrutalSelect id="ml-ra-severity" label="Severity" value={draft.risk_severity} onChange={(e) => setDraft((d) => ({ ...d, risk_severity: e.target.value }))} options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => ({ label: s, value: s }))} />
            <BrutalSelect id="ml-ra-likelihood" label="Likelihood" value={draft.risk_likelihood} onChange={(e) => setDraft((d) => ({ ...d, risk_likelihood: e.target.value }))} options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => ({ label: s, value: s }))} />
            <BrutalSelect id="ml-ra-impact" label="Impact" value={draft.risk_impact} onChange={(e) => setDraft((d) => ({ ...d, risk_impact: e.target.value }))} options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => ({ label: s, value: s }))} />
          </div>
          <BrutalInput id="ml-ra-status" label="Status" value={draft.risk_status} onChange={(e) => setDraft((d) => ({ ...d, risk_status: e.target.value }))} placeholder="optional, e.g. MITIGATED" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "model-card"} title="Record model card" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleModelCardCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <StatRow label="Model" value={selectedModelId ?? "—"} />
          <BrutalInput label="Purpose" value={draft.card_purpose} onChange={(e) => setDraft((d) => ({ ...d, card_purpose: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Risk" value={draft.card_risk} onChange={(e) => setDraft((d) => ({ ...d, card_risk: e.target.value }))} />
            <BrutalInput label="Version" value={draft.card_version} onChange={(e) => setDraft((d) => ({ ...d, card_version: e.target.value }))} />
          </div>
          <BrutalInput label="Approved envs (comma-separated)" value={draft.card_environments} onChange={(e) => setDraft((d) => ({ ...d, card_environments: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "system-card"} title="Record system card" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleSystemCardCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="System" value={draft.card_system} onChange={(e) => setDraft((d) => ({ ...d, card_system: e.target.value }))} />
          <BrutalInput label="Purpose" value={draft.card_purpose} onChange={(e) => setDraft((d) => ({ ...d, card_purpose: e.target.value }))} />
          <BrutalInput label="Models (comma-separated)" value={draft.models} onChange={(e) => setDraft((d) => ({ ...d, models: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "approval-create"} title="Request approval" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleApprovalCreate()} disabled={submitting}>{submitting ? "Requesting…" : "Request"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Request type" value={draft.approval_type} onChange={(e) => setDraft((d) => ({ ...d, approval_type: e.target.value }))} placeholder="deploy, publish…" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Model ID" value={draft.approval_model_id} onChange={(e) => setDraft((d) => ({ ...d, approval_model_id: e.target.value }))} placeholder="optional uuid" />
            <BrutalInput label="Provider" value={draft.approval_provider} onChange={(e) => setDraft((d) => ({ ...d, approval_provider: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Version" value={draft.approval_version} onChange={(e) => setDraft((d) => ({ ...d, approval_version: e.target.value }))} />
            <BrutalInput label="Reason" value={draft.approval_reason} onChange={(e) => setDraft((d) => ({ ...d, approval_reason: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "approval-decide"} title="Decide approval?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleApprovalDecide()} disabled={submitting}>{submitting ? "Deciding…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Approval ID" value={draft.approval_id} onChange={(e) => setDraft((d) => ({ ...d, approval_id: e.target.value }))} placeholder="uuid from a request response" />
          <BrutalInput label="Approver" value={draft.approver} onChange={(e) => setDraft((d) => ({ ...d, approver: e.target.value }))} placeholder="your identity" />
          <BrutalSelect label="Decision" value={draft.decision} onChange={(e) => setDraft((d) => ({ ...d, decision: e.target.value }))} options={["approved", "rejected", "approve", "reject", "allow", "deny"].map((s) => ({ label: s, value: s }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "monitoring-snapshot"} title="Record monitoring snapshot" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleMonitoringSnapshot()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Snapshots record reported measurements — the backend computes nothing from them here.</p>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Latency ms" value={draft.snapshot_latency} onChange={(e) => setDraft((d) => ({ ...d, snapshot_latency: e.target.value }))} />
            <BrutalInput label="Error rate" value={draft.snapshot_error_rate} onChange={(e) => setDraft((d) => ({ ...d, snapshot_error_rate: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Tokens" value={draft.snapshot_tokens} onChange={(e) => setDraft((d) => ({ ...d, snapshot_tokens: e.target.value }))} />
            <BrutalInput label="Cost" value={draft.snapshot_cost} onChange={(e) => setDraft((d) => ({ ...d, snapshot_cost: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Quality" value={draft.snapshot_quality} onChange={(e) => setDraft((d) => ({ ...d, snapshot_quality: e.target.value }))} />
            <BrutalInput label="Safety" value={draft.snapshot_safety} onChange={(e) => setDraft((d) => ({ ...d, snapshot_safety: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "monitoring-drift"} title="Check drift" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleDriftCheck()} disabled={submitting}>{submitting ? "Checking…" : "Check"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Model ID (empty = tenant-wide)" value={draft.drift_model_id} onChange={(e) => setDraft((d) => ({ ...d, drift_model_id: e.target.value }))} />
          <BrutalInput label="Window" value={draft.drift_window} onChange={(e) => setDraft((d) => ({ ...d, drift_window: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "deploy-create"} title="Deploy model?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleDeployCreate()} disabled={submitting}>{submitting ? "Deploying…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">The backend only deploys APPROVED or ACTIVE models with an AVAILABLE provider — anything else is rejected with 403.</p>
          <StatRow label="Model" value={selectedModelId ?? "—"} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Version" value={draft.deploy_version} onChange={(e) => setDraft((d) => ({ ...d, deploy_version: e.target.value }))} />
            <BrutalInput label="Environment" value={draft.deploy_environment} onChange={(e) => setDraft((d) => ({ ...d, deploy_environment: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider" value={draft.deploy_provider} onChange={(e) => setDraft((d) => ({ ...d, deploy_provider: e.target.value }))} />
            <BrutalInput label="Approved by" value={draft.deploy_approved_by} onChange={(e) => setDraft((d) => ({ ...d, deploy_approved_by: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "deploy-rollback"} title="Roll back deployment?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleDeployRollback()} disabled={submitting}>{submitting ? "Rolling back…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Rollback deprecates the deployed model. Already-rolled-back deployments are rejected with 409.</p>
          <BrutalInput label="Deployment ID" value={draft.rollback_id} onChange={(e) => setDraft((d) => ({ ...d, rollback_id: e.target.value }))} placeholder="uuid from a create response" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal === "gateway-invoke"} title="Invoke model?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleGatewayInvoke()} disabled={executing}>{executing ? "Invoking…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">
            AI GATEWAY INVOKE · SERVER-SIDE PROVIDER CALL · Provider implementation: MOCKED / NON-PRODUCTION. Only APPROVED or ACTIVE models with an AVAILABLE provider are served.
          </p>
          <BrutalInput label="Model ID" value={draft.gateway_model_id} onChange={(e) => setDraft((d) => ({ ...d, gateway_model_id: e.target.value }))} placeholder="uuid" />
          <BrutalInput label="Prompt" value={draft.gateway_prompt} onChange={(e) => setDraft((d) => ({ ...d, gateway_prompt: e.target.value }))} placeholder="input text (max 200000 chars)" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Classification" value={draft.gateway_classification} onChange={(e) => setDraft((d) => ({ ...d, gateway_classification: e.target.value }))} />
            <BrutalInput label="Purpose" value={draft.gateway_purpose} onChange={(e) => setDraft((d) => ({ ...d, gateway_purpose: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>
    </div>
  );
}