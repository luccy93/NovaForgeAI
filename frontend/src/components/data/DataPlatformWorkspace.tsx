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
  AccessAnomaly,
  DataJobRow,
  DataPipelineListItem,
  DataProductListItem,
  DataSchemaListItem,
  DataSourceListItem,
  DatasetDetail,
  DatasetListItem,
  DriftCheckResult,
  FreshnessDetail,
  IngestJob,
  LakehouseStats,
  LineageGraph,
  QualityProfile,
  QualityResultRow,
  ReconciliationResult,
  StreamCheckpoint,
  StreamEvent,
} from "@/types/data-platform";
import {
  DATA_CLASSIFICATIONS,
  DATA_CONNECTORS,
  LAKEHOUSE_TIERS,
  QUALITY_RULE_TYPES,
  SCHEMA_COMPATIBILITY,
} from "@/types/data-platform";
import type { CatalogHit } from "@/types/universal";

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
  if (status === "ACTIVE" || status === "SUCCESS" || status === "COMPLETED" || status === "FRESH") return "yellow";
  if (status === "FAILED" || status === "STALE" || status === "MISSING") return "error";
  if (status === "DRAFT" || status === "PENDING" || status === "UNKNOWN" || status === "ARCHIVED") return "muted";
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

type TabId =
  | "overview"
  | "datasets"
  | "sources"
  | "schemas"
  | "pipelines"
  | "quality"
  | "lineage"
  | "streams"
  | "catalog"
  | "lakehouse"
  | "operations"
  | "intelligence";

type PendingModal =
  | { kind: "dataset-create" }
  | { kind: "dataset-version"; dataset: DatasetListItem }
  | { kind: "dataset-archive"; dataset: DatasetListItem }
  | { kind: "source-create" }
  | { kind: "schema-create" }
  | { kind: "schema-evolve"; schema: DataSchemaListItem }
  | { kind: "pipeline-create" }
  | { kind: "pipeline-run"; pipeline: DataPipelineListItem }
  | { kind: "pipeline-complete" }
  | { kind: "pipeline-backfill"; pipeline: DataPipelineListItem }
  | { kind: "quality-rule" }
  | { kind: "lineage-create" }
  | { kind: "lakehouse-write" }
  | { kind: "product-create" }
  | { kind: "domain-create" }
  | { kind: "replay-create" }
  | { kind: "export-create" }
  | null;

export function DataPlatformWorkspace() {
  const pushToast = useToastStore((s) => s.push);
  const [active, setActive] = useState<TabId>("overview");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [datasets, setDatasets] = useState<DatasetListItem[] | null>(null);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [datasetFilters, setDatasetFilters] = useState({ status: "ALL", classification: "ALL", owner: "" });
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [datasetDetail, setDatasetDetail] = useState<DatasetDetail | null>(null);
  const [datasetDetailError, setDatasetDetailError] = useState<string | null>(null);
  const [datasetDetailLoading, setDatasetDetailLoading] = useState(false);
  const [lastVersion, setLastVersion] = useState<{ id: string; version: string; schema_version: string } | null>(null);

  const [sources, setSources] = useState<DataSourceListItem[] | null>(null);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [sourceConnector, setSourceConnector] = useState("ALL");

  const [schemas, setSchemas] = useState<DataSchemaListItem[] | null>(null);
  const [schemasError, setSchemasError] = useState<string | null>(null);
  const [schemaDatasetId, setSchemaDatasetId] = useState("");

  const [pipelines, setPipelines] = useState<DataPipelineListItem[] | null>(null);
  const [pipelinesError, setPipelinesError] = useState<string | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState("ALL");
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<DataJobRow[] | null>(null);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [lastRun, setLastRun] = useState<{ run_id: string; status: string } | null>(null);

  const [qualityDatasetId, setQualityDatasetId] = useState("");
  const [qualityResults, setQualityResults] = useState<QualityResultRow[] | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityProfile, setQualityProfile] = useState<QualityProfile | null>(null);
  const [lastRule, setLastRule] = useState<{ id: string; name: string; version: string } | null>(null);

  const [lineageNode, setLineageNode] = useState("");
  const [lineageDepth, setLineageDepth] = useState("3");
  const [lineageGraph, setLineageGraph] = useState<LineageGraph | null>(null);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);

  const [catalogQuery, setCatalogQuery] = useState("");
  const [catalogOwner, setCatalogOwner] = useState("");
  const [catalogClassification, setCatalogClassification] = useState("ALL");
  const [catalogSemantic, setCatalogSemantic] = useState(false);
  const [catalogOffline, setCatalogOffline] = useState(false);
  const [catalogHits, setCatalogHits] = useState<CatalogHit[] | null>(null);
  const [catalogMeta, setCatalogMeta] = useState<{ total?: number; source?: string | null; stale?: boolean; warning?: string | null } | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);

  const [streamTopic, setStreamTopic] = useState("");
  const [streamResult, setStreamResult] = useState<Record<string, unknown> | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamRunning, setStreamRunning] = useState(false);
  const [streamDraft, setStreamDraft] = useState({ partition: "0", consumer_group: "", schema_id: "", region: "", consumer: "", limit: "10", payload: "" });

  const [lakehouseStats, setLakehouseStats] = useState<LakehouseStats | null>(null);
  const [lakehouseError, setLakehouseError] = useState<string | null>(null);
  const [lakehouseLoading, setLakehouseLoading] = useState(false);

  const [ingestJob, setIngestJob] = useState<IngestJob | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [ingestRunning, setIngestRunning] = useState(false);
  const [ingestDraft, setIngestDraft] = useState({ dataset_id: "", source_id: "", mode: "batch", records: "", bytes: "", error: "", changes: "" });
  const [checkpoint, setCheckpoint] = useState<StreamCheckpoint | null>(null);
  const [checkpointError, setCheckpointError] = useState<string | null>(null);
  const [checkpointDraft, setCheckpointDraft] = useState({ consumer: "", topic: "", partition: "0" });

  const [products, setProducts] = useState<DataProductListItem[] | null>(null);
  const [productsError, setProductsError] = useState<string | null>(null);
  const [productStatus, setProductStatus] = useState("ALL");

  const [freshness, setFreshness] = useState<FreshnessDetail | null>(null);
  const [freshnessError, setFreshnessError] = useState<string | null>(null);
  const [freshnessLoading, setFreshnessLoading] = useState(false);
  const [freshnessInterval, setFreshnessInterval] = useState("24");
  const [driftResult, setDriftResult] = useState<DriftCheckResult | null>(null);
  const [driftCheckError, setDriftCheckError] = useState<string | null>(null);
  const [driftCheckRunning, setDriftCheckRunning] = useState(false);
  const [driftSchemas, setDriftSchemas] = useState({ current: "", previous: "" });

  const [reconciliation, setReconciliation] = useState<ReconciliationResult | null>(null);
  const [reconciliationError, setReconciliationError] = useState<string | null>(null);
  const [reconciliationRunning, setReconciliationRunning] = useState(false);
  const [reconciliationDraft, setReconciliationDraft] = useState({ source_count: "", processed_count: "", output_count: "" });

  const [anomalies, setAnomalies] = useState<AccessAnomaly[] | null>(null);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<{ export_id: string; dataset_id: string; status: string } | null>(null);
  const [replayResult, setReplayResult] = useState<{ id: string; topic: string; status: string } | null>(null);

  const [modal, setModal] = useState<PendingModal>(null);
  const [submitting, setSubmitting] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    description: "",
    workspace: "",
    project: "",
    owner: "",
    team: "",
    classification: "INTERNAL",
    schema_version: "1.0",
    storage_location: "",
    region: "",
    status: "DRAFT",
    retention_days: "",
    version_payload: "",
    connector: "postgresql",
    credentials: "",
    config: "",
    schema_dataset_id: "",
    new_schema_version: "1.0",
    schema_fields: "",
    schema_classification: "INTERNAL",
    evolve_fields: "",
    compatibility: "backward",
    pipeline_description: "",
    pipeline_steps: "",
    pipeline_dependencies: "",
    pipeline_schedule: "",
    pipeline_owner: "",
    pipeline_region: "",
    pipeline_priority: "NORMAL",
    pipeline_status: "DRAFT",
    run_payload: "",
    complete_status: "SUCCESS",
    complete_records: "",
    complete_error: "",
    backfill_payload: "",
    rule_name: "",
    rule_type: "required",
    rule_params: "",
    rule_version: "1.0",
    quality_records: "",
    lineage_source: "",
    lineage_target: "",
    lineage_transformation: "",
    lineage_pipeline_id: "",
    lakehouse_tier: "raw",
    lakehouse_format: "json",
    lakehouse_records: "",
    product_description: "",
    product_contract: "",
    product_domain: "",
    product_slo: "",
    product_status: "DRAFT",
    domain_owner: "",
    domain_description: "",
    replay_topic: "",
    replay_scope: "",
    replay_requires_approval: false,
    replay_approved: false,
    export_purpose: "",
    export_destination: "",
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
      if (e instanceof ApiError && (e.kind === "rate_limited" || e.status === 429)) {
        pushToast("warning", "Rate limited — retry shortly");
        return;
      }
      pushToast("error", e instanceof Error ? e.message : fallback);
    },
    [pushToast],
  );

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
    setDatasetsError(null);
    setSourcesError(null);
    setSchemasError(null);
    setPipelinesError(null);
    setJobsError(null);

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
          api.dataDatasets(token, {
            status: datasetFilters.status !== "ALL" ? datasetFilters.status : undefined,
            classification: datasetFilters.classification !== "ALL" ? datasetFilters.classification : undefined,
            owner: datasetFilters.owner.trim() || undefined,
            limit: 50,
          }),
        (value) => setDatasets(value?.items ?? []),
        setDatasetsError,
      ),
      settle(
        () => api.dataSources(token, { connector: sourceConnector !== "ALL" ? sourceConnector : undefined, limit: 50 }),
        (value) => setSources(value?.items ?? []),
        setSourcesError,
      ),
      settle(
        () => api.dataSchemas(token, { dataset_id: schemaDatasetId.trim() || undefined, limit: 50 }),
        (value) => setSchemas(value?.items ?? []),
        setSchemasError,
      ),
      settle(
        () => api.dataPipelines(token, { status: pipelineStatus !== "ALL" ? pipelineStatus : undefined, limit: 50 }),
        (value) => setPipelines(value?.items ?? []),
        setPipelinesError,
      ),
      settle(() => api.dataJobs(token, { limit: 20 }), (value) => setJobs(value?.items ?? []), setJobsError),
    ]);

    if (!controller.signal.aborted && seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, [datasetFilters, sourceConnector, schemaDatasetId, pipelineStatus]);

  const loadDatasetDetail = useCallback(async (datasetId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setDatasetDetailLoading(true);
    setDatasetDetailError(null);
    try {
      const detail = await api.dataDataset(token, datasetId);
      setDatasetDetail(detail);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setDatasetDetailError(e instanceof Error ? e.message : "Dataset unavailable");
    } finally {
      setDatasetDetailLoading(false);
    }
  }, []);

  const loadJobs = useCallback(async (pipelineId: string | null) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setJobsLoading(true);
    setJobsError(null);
    try {
      const res = await api.dataJobs(token, { pipeline_id: pipelineId ?? undefined, limit: 20 });
      setJobs(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setJobsError(e instanceof Error ? e.message : "Runs unavailable");
    } finally {
      setJobsLoading(false);
    }
  }, []);

  const loadQualityResults = useCallback(async () => {
    const datasetId = qualityDatasetId.trim();
    if (!datasetId) {
      pushToast("warning", "Enter a dataset ID first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setQualityLoading(true);
    setQualityError(null);
    try {
      const res = await api.dataQualityResults(token, datasetId);
      setQualityResults(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setQualityError(e instanceof Error ? e.message : "Quality results unavailable");
    } finally {
      setQualityLoading(false);
    }
  }, [qualityDatasetId, pushToast]);

  const loadLineage = useCallback(async () => {
    const node = lineageNode.trim();
    if (!node) {
      pushToast("warning", "Enter a lineage node (type:id) first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const depth = Math.min(Math.max(Number(lineageDepth) || 3, 1), 10);
    setLineageLoading(true);
    setLineageError(null);
    try {
      const graph = await api.dataLineageGraph(token, node, depth);
      setLineageGraph(graph);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setLineageError(e instanceof Error ? e.message : "Lineage unavailable");
    } finally {
      setLineageLoading(false);
    }
  }, [lineageNode, lineageDepth, pushToast]);

  const runCatalogSearch = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setCatalogLoading(true);
    setCatalogError(null);
    try {
      const res = await api.dataCatalogSearchFull(token, {
        q: catalogQuery.trim() || undefined,
        owner: catalogOwner.trim() || undefined,
        classification: catalogClassification !== "ALL" ? catalogClassification : undefined,
        limit: 20,
        semantic: catalogSemantic,
        offline: catalogOffline,
      });
      setCatalogHits(res.items ?? []);
      setCatalogMeta({ total: res.total, source: res.source, stale: res.stale, warning: res.warning ?? res.error ?? null });
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setCatalogError(e instanceof Error ? e.message : "Catalog search unavailable");
    } finally {
      setCatalogLoading(false);
    }
  }, [catalogQuery, catalogOwner, catalogClassification, catalogSemantic, catalogOffline]);

  const loadLakehouseStats = useCallback(async () => {
    const datasetId = selectedDatasetId;
    if (!datasetId) {
      pushToast("warning", "Select a dataset first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setLakehouseLoading(true);
    setLakehouseError(null);
    try {
      const res = await api.dataLakehouseStats(token, datasetId);
      setLakehouseStats(res);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setLakehouseError(e instanceof Error ? e.message : "Lakehouse stats unavailable");
    } finally {
      setLakehouseLoading(false);
    }
  }, [selectedDatasetId, pushToast]);

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
      setDatasets(null);
      setSources(null);
      setSchemas(null);
      setPipelines(null);
      setJobs(null);
      setDatasetDetail(null);
      setQualityResults(null);
      setQualityProfile(null);
      setLineageGraph(null);
      setCatalogHits(null);
      setCatalogMeta(null);
      setLakehouseStats(null);
      setLastRun(null);
      setLastVersion(null);
      setLastRule(null);
      setStreamResult(null);
      setIngestJob(null);
      setCheckpoint(null);
      setProducts(null);
      setFreshness(null);
      setDriftResult(null);
      setReconciliation(null);
      setAnomalies(null);
      setExportResult(null);
      setReplayResult(null);
      setSelectedDatasetId(null);
      setSelectedPipelineId(null);
      setDatasetsError(null);
      setSourcesError(null);
      setSchemasError(null);
      setPipelinesError(null);
      setJobsError(null);
      setQualityError(null);
      setLineageError(null);
      setCatalogError(null);
      setLakehouseError(null);
      setStreamError(null);
      setIngestError(null);
      setCheckpointError(null);
      setProductsError(null);
      setFreshnessError(null);
      setDriftCheckError(null);
      setReconciliationError(null);
      setAnomaliesError(null);
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
    if (selectedDatasetId) {
      void loadDatasetDetail(selectedDatasetId);
    } else {
      setDatasetDetail(null);
      setDatasetDetailError(null);
    }
  }, [selectedDatasetId, loadDatasetDetail]);

  const canDataWrite = hasPermission(permissions, PERMISSIONS.dataWrite);

  function resetDraft() {
    setDraft({
      name: "",
      description: "",
      workspace: "",
      project: "",
      owner: "",
      team: "",
      classification: "INTERNAL",
      schema_version: "1.0",
      storage_location: "",
      region: "",
      status: "DRAFT",
      retention_days: "",
      version_payload: "",
      connector: "postgresql",
      credentials: "",
      config: "",
      schema_dataset_id: "",
      new_schema_version: "1.0",
      schema_fields: "",
      schema_classification: "INTERNAL",
      evolve_fields: "",
      compatibility: "backward",
      pipeline_description: "",
      pipeline_steps: "",
      pipeline_dependencies: "",
      pipeline_schedule: "",
      pipeline_owner: "",
      pipeline_region: "",
      pipeline_priority: "NORMAL",
      pipeline_status: "DRAFT",
      run_payload: "",
      complete_status: "SUCCESS",
      complete_records: "",
      complete_error: "",
      backfill_payload: "",
      rule_name: "",
      rule_type: "required",
      rule_params: "",
      rule_version: "1.0",
      quality_records: "",
      lineage_source: "",
      lineage_target: "",
      lineage_transformation: "",
      lineage_pipeline_id: "",
      lakehouse_tier: "raw",
      lakehouse_format: "json",
      lakehouse_records: "",
      product_description: "",
      product_contract: "",
      product_domain: "",
      product_slo: "",
      product_status: "DRAFT",
      domain_owner: "",
      domain_description: "",
      replay_topic: "",
      replay_scope: "",
      replay_requires_approval: false,
      replay_approved: false,
      export_purpose: "",
      export_destination: "",
    });
  }

  async function authedToken(): Promise<string | null> {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return null;
    }
    return token;
  }

  async function handleDatasetCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.name.trim()) {
      pushToast("warning", "Dataset name is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataDatasetCreate(token, {
        name: draft.name.trim(),
        description: draft.description.trim() || undefined,
        workspace: draft.workspace.trim() || undefined,
        project: draft.project.trim() || undefined,
        owner: draft.owner.trim() || undefined,
        team: draft.team.trim() || undefined,
        classification: draft.classification,
        schema_version: draft.schema_version.trim() || "1.0",
        storage_location: draft.storage_location.trim() || undefined,
        region: draft.region.trim() || undefined,
        status: draft.status,
        retention_days: draft.retention_days.trim() ? Number(draft.retention_days) : undefined,
      });
      setModal(null);
      pushToast("success", `Dataset ${result.name} registered`);
      setSelectedDatasetId(result.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create dataset", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDatasetVersion() {
    if (!modal || modal.kind !== "dataset-version") return;
    const token = await authedToken();
    if (!token) return;
    let payload: Record<string, unknown>;
    try {
      payload = parseJsonObject(draft.version_payload, "Version payload");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid payload");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataDatasetVersion(token, modal.dataset.id, payload);
      setLastVersion(result);
      setModal(null);
      pushToast("success", `Version ${result.version} recorded`);
      void loadDatasetDetail(modal.dataset.id);
    } catch (e) {
      notifyError(e, "Failed to record version");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDatasetArchive() {
    if (!modal || modal.kind !== "dataset-archive") return;
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      await api.dataDatasetArchive(token, modal.dataset.id);
      setModal(null);
      pushToast("success", `Dataset ${modal.dataset.name} archived`);
      setSelectedDatasetId(null);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to archive dataset", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSourceCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.name.trim() || !draft.connector.trim()) {
      pushToast("warning", "Source name and connector are required");
      return;
    }
    let config: Record<string, unknown> = {};
    try {
      config = parseJsonObject(draft.config, "Config");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid config");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataSourceCreate(token, {
        name: draft.name.trim(),
        connector: draft.connector,
        credentials: draft.credentials || undefined,
        region: draft.region.trim() || undefined,
        classification: draft.classification,
        owner: draft.owner.trim() || undefined,
        config,
      });
      setModal(null);
      pushToast("success", `Source ${result.name} registered — credentials stored as a hash ref, never returned`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register source", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSchemaCreate() {
    const token = await authedToken();
    if (!token) return;
    const datasetId = (draft.schema_dataset_id.trim() || selectedDatasetId || "");
    if (!datasetId) {
      pushToast("warning", "A dataset ID is required");
      return;
    }
    let fields: Array<Record<string, unknown>>;
    try {
      fields = parseJsonArray(draft.schema_fields, "Fields");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid fields");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataSchemaCreate(token, datasetId, {
        version: draft.new_schema_version.trim() || "1.0",
        fields,
        classification: draft.schema_classification,
      });
      setModal(null);
      pushToast("success", `Schema v${result.version} published`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to publish schema", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSchemaEvolve() {
    if (!modal || modal.kind !== "schema-evolve") return;
    const token = await authedToken();
    if (!token) return;
    let fields: Array<Record<string, unknown>>;
    try {
      fields = parseJsonArray(draft.evolve_fields, "Fields");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid fields");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataSchemaEvolve(token, modal.schema.id, {
        fields,
        compatibility: draft.compatibility,
      });
      setModal(null);
      pushToast("success", `Schema evolved to v${result.version}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to evolve schema", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePipelineCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.name.trim()) {
      pushToast("warning", "Pipeline name is required");
      return;
    }
    let steps: unknown[] = [];
    let dependencies: string[] = [];
    try {
      steps = parseJsonArray(draft.pipeline_steps, "Steps");
      const depsRaw = draft.pipeline_dependencies.trim();
      dependencies = depsRaw ? (JSON.parse(depsRaw) as string[]) : [];
      if (!Array.isArray(dependencies)) throw new Error("Dependencies must be a JSON array");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid pipeline definition");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataPipelineCreate(token, {
        name: draft.name.trim(),
        description: draft.pipeline_description.trim() || undefined,
        steps,
        dependencies,
        schedule: draft.pipeline_schedule.trim() || undefined,
        owner: draft.pipeline_owner.trim() || undefined,
        region: draft.pipeline_region.trim() || undefined,
        priority: draft.pipeline_priority,
        status: draft.pipeline_status,
      });
      setModal(null);
      pushToast("success", `Pipeline ${result.name} created`);
      setSelectedPipelineId(result.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create pipeline", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePipelineRun() {
    if (!modal || modal.kind !== "pipeline-run") return;
    const token = await authedToken();
    if (!token) return;
    let payload: Record<string, unknown> = {};
    try {
      payload = parseJsonObject(draft.run_payload, "Run payload");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid payload");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataPipelineRun(token, modal.pipeline.id, payload);
      setLastRun({ run_id: result.run_id, status: result.status });
      setModal(null);
      pushToast("success", `Run ${result.run_id.slice(0, 8)} started`);
      void loadJobs(modal.pipeline.id);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to start run", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePipelineComplete() {
    const token = await authedToken();
    if (!token) return;
    const runId = lastRun?.run_id ?? "";
    if (!runId) {
      pushToast("warning", "Start a run first — completion reports the worker outcome");
      setModal(null);
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataPipelineRunComplete(token, runId, {
        status: draft.complete_status,
        records: draft.complete_records.trim() ? Number(draft.complete_records) : 0,
        error: draft.complete_error.trim() || undefined,
      });
      setLastRun({ run_id: result.run_id, status: result.status });
      setModal(null);
      pushToast("success", `Run reported as ${result.status}`);
      void loadJobs(selectedPipelineId);
    } catch (e) {
      notifyError(e, "Failed to report run completion");
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePipelineBackfill() {
    if (!modal || modal.kind !== "pipeline-backfill") return;
    const token = await authedToken();
    if (!token) return;
    let payload: Record<string, unknown>;
    try {
      payload = parseJsonObject(draft.backfill_payload, "Backfill payload");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid payload");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataPipelineBackfill(token, modal.pipeline.id, payload);
      setModal(null);
      pushToast("success", `Backfill run ${String(result.run_id).slice(0, 8)} requested`);
      void loadJobs(modal.pipeline.id);
    } catch (e) {
      notifyError(e, "Failed to request backfill");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleQualityRuleCreate() {
    const token = await authedToken();
    if (!token) return;
    const datasetId = qualityDatasetId.trim() || selectedDatasetId || "";
    if (!datasetId || !draft.rule_name.trim()) {
      pushToast("warning", "A dataset and a rule name are required");
      return;
    }
    let params: Record<string, unknown> = {};
    try {
      params = parseJsonObject(draft.rule_params, "Rule params");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid params");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataQualityRuleCreate(token, datasetId, {
        name: draft.rule_name.trim(),
        rule_type: draft.rule_type,
        params,
        version: draft.rule_version.trim() || "1.0",
      });
      setLastRule(result);
      setModal(null);
      pushToast("success", `Quality rule ${result.name} created`);
    } catch (e) {
      notifyError(e, "Failed to create quality rule");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleQualityJobRun() {
    const token = await authedToken();
    if (!token) return;
    const datasetId = qualityDatasetId.trim() || selectedDatasetId || "";
    if (!datasetId) {
      pushToast("warning", "A dataset is required");
      return;
    }
    let records: Array<Record<string, unknown>>;
    try {
      records = parseJsonArray(draft.quality_records, "Records");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid records");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataQualityJobRun(token, { dataset_id: datasetId, records });
      setModal(null);
      const failed = result.results.reduce((n, r) => n + r.failed, 0);
      pushToast(failed > 0 ? "warning" : "success", `Quality job finished · ${failed} failed checks`);
      setQualityDatasetId(datasetId);
      void loadQualityResults();
    } catch (e) {
      notifyError(e, "Failed to run quality job");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleQualityProfile() {
    const token = await authedToken();
    if (!token) return;
    const datasetId = qualityDatasetId.trim() || selectedDatasetId || "";
    if (!datasetId) {
      pushToast("warning", "A dataset is required");
      return;
    }
    let records: Array<Record<string, unknown>>;
    try {
      records = parseJsonArray(draft.quality_records, "Records");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid records");
      return;
    }
    setSubmitting(true);
    try {
      const profile = await api.dataQualityProfile(token, { dataset_id: datasetId, records });
      setQualityProfile(profile);
      setModal(null);
      pushToast("success", `Profile computed over ${profile.row_count} rows`);
    } catch (e) {
      notifyError(e, "Failed to profile dataset");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLineageCreate() {
    const token = await authedToken();
    if (!token) return;
    if (!draft.lineage_source.trim() || !draft.lineage_target.trim()) {
      pushToast("warning", "Source and target nodes are required (type:id)");
      return;
    }
    setSubmitting(true);
    try {
      await api.dataLineageCreate(token, {
        source: draft.lineage_source.trim(),
        target: draft.lineage_target.trim(),
        transformation: draft.lineage_transformation.trim() || undefined,
        pipeline_id: draft.lineage_pipeline_id.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Lineage edge recorded");
      if (lineageNode.trim()) void loadLineage();
    } catch (e) {
      notifyError(e, "Failed to record lineage edge");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStreamOp(kind: "create" | "ingest" | "lag" | "consume") {
    const token = await authedToken();
    if (!token) return;
    const topic = streamTopic.trim();
    if (!topic && kind !== "create") {
      pushToast("warning", "Enter a topic first");
      return;
    }
    setStreamRunning(true);
    setStreamError(null);
    try {
      if (kind === "create") {
        if (!topic) {
          pushToast("warning", "Enter a topic first");
          setStreamRunning(false);
          return;
        }
        const res = await api.dataStreamCreate(token, {
          topic,
          partition: Number(streamDraft.partition) || 0,
          consumer_group: streamDraft.consumer_group.trim() || undefined,
          schema_id: streamDraft.schema_id.trim() || undefined,
          region: streamDraft.region.trim() || undefined,
        });
        setStreamResult(res as unknown as Record<string, unknown>);
        pushToast("success", `Stream ${res.topic} registered`);
      } else if (kind === "ingest") {
        const payload = parseJsonObject(streamDraft.payload, "Event payload");
        const res = await api.dataStreamIngest(token, topic, payload);
        setStreamResult(res as unknown as Record<string, unknown>);
        pushToast("success", "Event ingested — idempotent on content key");
      } else if (kind === "lag") {
        if (!streamDraft.consumer.trim()) {
          pushToast("warning", "Enter a consumer first");
          setStreamRunning(false);
          return;
        }
        const res = await api.dataStreamLag(token, topic, streamDraft.consumer.trim());
        setStreamResult(res as unknown as Record<string, unknown>);
      } else {
        if (!streamDraft.consumer.trim()) {
          pushToast("warning", "Enter a consumer first");
          setStreamRunning(false);
          return;
        }
        const res = await api.dataStreamConsume(token, topic, {
          consumer: streamDraft.consumer.trim(),
          partition: Number(streamDraft.partition) || 0,
          limit: Number(streamDraft.limit) || 10,
        });
        setStreamResult({ items: res.items, count: res.items.length } as unknown as Record<string, unknown>);
      }
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setStreamError(e instanceof Error ? e.message : "Stream operation failed");
    } finally {
      setStreamRunning(false);
    }
  }

  async function handleLakehouseWrite() {
    if (!modal || modal.kind !== "lakehouse-write") return;
    const token = await authedToken();
    if (!token) return;
    const datasetId = selectedDatasetId;
    if (!datasetId) {
      pushToast("warning", "Select a dataset first");
      setModal(null);
      return;
    }
    let records: Array<Record<string, unknown>>;
    try {
      records = parseJsonArray(draft.lakehouse_records, "Records");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid records");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataLakehouseTierWrite(token, datasetId, {
        tier: draft.lakehouse_tier,
        records,
        format: draft.lakehouse_format.trim() || "json",
      });
      setModal(null);
      pushToast("success", `Wrote ${result.records} records to the ${result.tier} tier`);
      void loadLakehouseStats();
    } catch (e) {
      notifyError(e, "Failed to write tier");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCatalogSnapshot() {
    const token = await authedToken();
    if (!token) return;
    setSubmitting(true);
    try {
      const result = await api.dataCatalogSnapshot(token);
      pushToast("success", `Catalog snapshot stored for tenant ${String(result.tenant).slice(0, 8)}`);
    } catch (e) {
      notifyError(e, "Failed to generate snapshot");
    } finally {
      setSubmitting(false);
    }
  }

  const selectedDataset = datasets?.find((d) => d.id === selectedDatasetId) ?? null;
  const selectedPipeline = pipelines?.find((p) => p.id === selectedPipelineId) ?? null;
  const canDataExport = hasPermission(permissions, PERMISSIONS.dataExport);

  const loadProducts = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setProductsError(null);
    try {
      const res = await api.dataProducts(token, {
        status: productStatus !== "ALL" ? productStatus : undefined,
        limit: 20,
      });
      setProducts(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setProductsError(e instanceof Error ? e.message : "Products unavailable");
    }
  }, [productStatus]);

  useEffect(() => {
    if (active === "intelligence") {
      void loadProducts();
      void loadAnomalies();
    }
  }, [active, loadProducts]);

  async function loadAnomalies() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setAnomaliesError(null);
    try {
      const res = await api.dataAccessAnomalies(token, 20);
      setAnomalies(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setAnomaliesError(e instanceof Error ? e.message : "Anomalies unavailable");
    }
  }

  async function handleIngestStart() {
    const token = await authedToken();
    if (!token) return;
    const datasetId = ingestDraft.dataset_id.trim() || selectedDatasetId || "";
    if (!datasetId || !ingestDraft.source_id.trim()) {
      pushToast("warning", "Dataset and source are required");
      return;
    }
    setIngestRunning(true);
    setIngestError(null);
    try {
      const job = await api.dataIngestStart(token, {
        dataset_id: datasetId,
        source_id: ingestDraft.source_id.trim(),
        mode: ingestDraft.mode.trim() || "batch",
      });
      setIngestJob(job);
      pushToast("success", `Ingestion job ${job.job_id.slice(0, 8)} started`);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setIngestError(e instanceof Error ? e.message : "Failed to start ingestion");
    } finally {
      setIngestRunning(false);
    }
  }

  async function handleIngestComplete() {
    const token = await authedToken();
    if (!token) return;
    if (!ingestJob) {
      pushToast("warning", "Start an ingestion job first");
      return;
    }
    setIngestRunning(true);
    setIngestError(null);
    try {
      const job = await api.dataIngestComplete(token, ingestJob.job_id, {
        records: ingestDraft.records.trim() ? Number(ingestDraft.records) : 0,
        bytes: ingestDraft.bytes.trim() ? Number(ingestDraft.bytes) : 0,
        error: ingestDraft.error.trim() || undefined,
      });
      setIngestJob(job);
      pushToast("success", `Ingestion job reported as ${job.status}`);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setIngestError(e instanceof Error ? e.message : "Failed to complete ingestion");
    } finally {
      setIngestRunning(false);
    }
  }

  async function handleIngestCdc() {
    const token = await authedToken();
    if (!token) return;
    const datasetId = ingestDraft.dataset_id.trim() || selectedDatasetId || "";
    let changes: Array<Record<string, unknown>>;
    try {
      changes = parseJsonArray(ingestDraft.changes, "Changes");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid changes");
      return;
    }
    if (!datasetId || changes.length === 0) {
      pushToast("warning", "Dataset and at least one change are required");
      return;
    }
    setIngestRunning(true);
    setIngestError(null);
    try {
      const res = await api.dataIngestCdc(token, { dataset_id: datasetId, changes });
      setIngestJob(null);
      pushToast("success", `CDC applied: ${JSON.stringify(res).slice(0, 80)}`);
      void loadAll();
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setIngestError(e instanceof Error ? e.message : "Failed to apply CDC");
    } finally {
      setIngestRunning(false);
    }
  }

  async function handleCheckpointLookup() {
    const token = await authedToken();
    if (!token) return;
    if (!checkpointDraft.consumer.trim() || !checkpointDraft.topic.trim()) {
      pushToast("warning", "Consumer and topic are required");
      return;
    }
    setCheckpointError(null);
    try {
      const res = await api.dataCheckpoints(token, {
        consumer: checkpointDraft.consumer.trim(),
        topic: checkpointDraft.topic.trim(),
        partition: Number(checkpointDraft.partition) || 0,
      });
      setCheckpoint(res);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setCheckpointError(e instanceof Error ? e.message : "Checkpoint unavailable");
    }
  }

  async function handleFreshnessUpdate() {
    const token = await authedToken();
    if (!token) return;
    if (!selectedDatasetId) {
      pushToast("warning", "Select a dataset first");
      return;
    }
    setFreshnessLoading(true);
    setFreshnessError(null);
    try {
      await api.dataFreshnessUpdate(token, selectedDatasetId, Number(freshnessInterval) || 24);
      const detail = await api.dataFreshness(token, selectedDatasetId);
      setFreshness(detail);
      pushToast("success", `Freshness is ${detail.status}`);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setFreshnessError(e instanceof Error ? e.message : "Freshness unavailable");
    } finally {
      setFreshnessLoading(false);
    }
  }

  async function handleDriftCheckRun() {
    const token = await authedToken();
    if (!token) return;
    if (!selectedDatasetId) {
      pushToast("warning", "Select a dataset first");
      return;
    }
    let current: unknown[];
    try {
      current = parseJsonArray(driftSchemas.current, "Current schema");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid schema");
      return;
    }
    let previous: unknown[] | undefined;
    if (driftSchemas.previous.trim()) {
      try {
        previous = parseJsonArray(driftSchemas.previous, "Previous schema");
      } catch (e) {
        pushToast("warning", e instanceof Error ? e.message : "Invalid schema");
        return;
      }
    }
    setDriftCheckRunning(true);
    setDriftCheckError(null);
    try {
      const res = await api.dataDriftCheck(token, selectedDatasetId, { current_schema: current, previous_schema: previous });
      setDriftResult(res);
      pushToast(res.drift ? "warning" : "success", res.drift ? "Schema drift detected" : "No schema drift");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setDriftCheckError(e instanceof Error ? e.message : "Drift check failed");
    } finally {
      setDriftCheckRunning(false);
    }
  }

  async function handleProductCreate() {
    if (!modal || modal.kind !== "product-create") return;
    const token = await authedToken();
    if (!token) return;
    if (!draft.name.trim() || !draft.owner.trim()) {
      pushToast("warning", "Product name and owner are required");
      return;
    }
    let contract: Record<string, unknown> = {};
    let slo: Record<string, unknown> = {};
    try {
      contract = parseJsonObject(draft.product_contract, "Contract");
      slo = parseJsonObject(draft.product_slo, "SLO");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataProductCreate(token, {
        name: draft.name.trim(),
        description: draft.product_description.trim() || undefined,
        owner: draft.owner.trim(),
        contract,
        classification: draft.classification,
        domain: draft.product_domain.trim() || undefined,
        slo,
        status: draft.product_status,
      });
      setModal(null);
      pushToast("success", `Data product ${result.name} created`);
      void loadProducts();
    } catch (e) {
      notifyError(e, "Failed to create data product", () => void loadProducts());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDomainCreate() {
    if (!modal || modal.kind !== "domain-create") return;
    const token = await authedToken();
    if (!token) return;
    if (!draft.name.trim() || !draft.domain_owner.trim()) {
      pushToast("warning", "Domain name and owner are required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataDomainCreate(token, {
        name: draft.name.trim(),
        owner: draft.domain_owner.trim(),
        description: draft.domain_description.trim() || undefined,
      });
      setModal(null);
      pushToast("success", `Data domain ${result.name} created`);
    } catch (e) {
      notifyError(e, "Failed to create data domain", () => void loadProducts());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReplayCreate() {
    if (!modal || modal.kind !== "replay-create") return;
    const token = await authedToken();
    if (!token) return;
    if (!draft.replay_topic.trim()) {
      pushToast("warning", "Topic is required");
      return;
    }
    let scope: Record<string, unknown> = {};
    try {
      scope = parseJsonObject(draft.replay_scope, "Scope");
    } catch (e) {
      pushToast("warning", e instanceof Error ? e.message : "Invalid scope");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataReplay(token, {
        topic: draft.replay_topic.trim(),
        scope,
        requires_approval: draft.replay_requires_approval || undefined,
        approved: draft.replay_approved || undefined,
      });
      setReplayResult(result);
      setModal(null);
      pushToast("success", `Replay job ${result.id.slice(0, 8)} is ${result.status}`);
    } catch (e) {
      notifyError(e, "Failed to create replay job");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReconciliationRun() {
    const token = await authedToken();
    if (!token) return;
    setReconciliationRunning(true);
    setReconciliationError(null);
    try {
      const res = await api.dataReconciliation(token, {
        source_count: reconciliationDraft.source_count.trim() ? Number(reconciliationDraft.source_count) : 0,
        processed_count: reconciliationDraft.processed_count.trim() ? Number(reconciliationDraft.processed_count) : 0,
        output_count: reconciliationDraft.output_count.trim() ? Number(reconciliationDraft.output_count) : 0,
      });
      setReconciliation(res);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setReconciliationError(e instanceof Error ? e.message : "Reconciliation failed");
    } finally {
      setReconciliationRunning(false);
    }
  }

  async function handleExportCreate() {
    if (!modal || modal.kind !== "export-create") return;
    const token = await authedToken();
    if (!token) return;
    const datasetId = selectedDatasetId;
    if (!datasetId) {
      pushToast("warning", "Select a dataset first");
      setModal(null);
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.dataExport(token, {
        dataset_id: datasetId,
        purpose: draft.export_purpose.trim() || undefined,
        destination: draft.export_destination.trim() || undefined,
      });
      setExportResult(result);
      setModal(null);
      pushToast("success", `Export ${result.export_id.slice(0, 8)} requested — audited server-side`);
    } catch (e) {
      notifyError(e, "Failed to request export");
    } finally {
      setSubmitting(false);
    }
  }

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "datasets", label: "Datasets" },
    { id: "sources", label: "Sources" },
    { id: "schemas", label: "Schemas" },
    { id: "pipelines", label: "Pipelines" },
    { id: "quality", label: "Quality" },
    { id: "lineage", label: "Lineage" },
    { id: "streams", label: "Streams" },
    { id: "catalog", label: "Catalog" },
    { id: "lakehouse", label: "Lakehouse" },
    { id: "operations", label: "Operations" },
    { id: "intelligence", label: "Intelligence" },
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
          {!canDataWrite ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Read-only view · no data:write
            </span>
          ) : (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Mutation actions enabled
            </span>
          )}
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div role="tablist" aria-label="Data platform sections" className="flex flex-wrap gap-2">
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
          <BrutalCard eyebrow="Dataset" title="Datasets listed">
            <PanelBody loading={loading} error={datasetsError} onRetry={() => void loadAll()} emptyTitle="No datasets" emptyDescription="Register a dataset to start tracking platform assets.">
              {datasets ? (
                <div className="space-y-1">
                  <StatRow label="Datasets listed" value={String(datasets.length)} />
                  {["DRAFT", "ACTIVE", "ARCHIVED"].map((s) => (
                    <StatRow key={s} label={s} value={String(datasets.filter((d) => d.status === s).length)} />
                  ))}
                  <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Listed count only — the backend reports no totals.</p>
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Source" title="Sources listed">
            <PanelBody loading={loading} error={sourcesError} onRetry={() => void loadAll()} emptyTitle="No sources" emptyDescription="Register a source to connect an upstream system.">
              {sources ? (
                <div className="space-y-1">
                  <StatRow label="Sources listed" value={String(sources.length)} />
                  {Array.from(new Set(sources.map((s) => s.connector))).slice(0, 6).map((c) => (
                    <StatRow key={c} label={c} value={String(sources.filter((s) => s.connector === c).length)} />
                  ))}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Pipeline" title="Pipelines & recent runs">
            <PanelBody loading={loading} error={pipelinesError || jobsError} onRetry={() => void loadAll()} emptyTitle="No pipelines" emptyDescription="Create a pipeline to orchestrate ingestion and transforms.">
              {pipelines ? (
                <div className="space-y-1">
                  <StatRow label="Pipelines listed" value={String(pipelines.length)} />
                  {(jobs ?? []).slice(0, 4).map((j) => (
                    <div key={j.run_id} className="flex items-center justify-between gap-2 border-b border-outline py-1.5 last:border-b-0">
                      <span className="truncate font-mono text-xs text-on-surface">{j.run_id.slice(0, 12)}…</span>
                      <BrutalBadge tone={statusTone(j.status)}>{j.status}</BrutalBadge>
                    </div>
                  ))}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "datasets" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Dataset" title="Datasets">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-24 flex-1">
                <BrutalSelect label="Status" value={datasetFilters.status} onChange={(e) => setDatasetFilters((f) => ({ ...f, status: e.target.value }))} options={["ALL", "DRAFT", "ACTIVE", "ARCHIVED"].map((s) => ({ label: s, value: s }))} />
              </div>
              <div className="min-w-24 flex-1">
                <BrutalSelect label="Classification" value={datasetFilters.classification} onChange={(e) => setDatasetFilters((f) => ({ ...f, classification: e.target.value }))} options={["ALL", ...DATA_CLASSIFICATIONS].map((s) => ({ label: s, value: s }))} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              {canDataWrite ? (
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal({ kind: "dataset-create" }); }}>New dataset</BrutalButton>
              ) : null}
            </div>
            <PanelBody loading={loading} error={datasetsError} onRetry={() => void loadAll()} emptyTitle="No datasets" emptyDescription="No datasets match the current filters.">
              {datasets && datasets.length > 0 ? (
                <ul className="space-y-2">
                  {datasets.map((ds) => (
                    <li key={ds.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedDatasetId(ds.id)}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${ds.id === selectedDatasetId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{ds.name}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {ds.classification} · {ds.owner || "unassigned"} · {ds.region || "no region"}
                          </p>
                        </div>
                        <BrutalBadge tone={statusTone(ds.status)}>{ds.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Dataset" title="Dataset detail">
            <PanelBody loading={datasetDetailLoading} error={datasetDetailError} onRetry={() => selectedDatasetId && void loadDatasetDetail(selectedDatasetId)} emptyTitle="Nothing selected" emptyDescription="Select a dataset to inspect its metadata.">
              {datasetDetail ? (
                <div className="space-y-1">
                  <StatRow label="Name" value={datasetDetail.name} />
                  <StatRow label="Description" value={datasetDetail.description || "—"} />
                  <StatRow label="Status" value={datasetDetail.status} />
                  <StatRow label="Classification" value={datasetDetail.classification} />
                  <StatRow label="Owner" value={datasetDetail.owner || "—"} />
                  <StatRow label="Region" value={datasetDetail.region || "—"} />
                  <StatRow label="Storage" value={datasetDetail.storage_location || "—"} />
                  {canDataWrite && selectedDataset ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <BrutalButton size="sm" variant="ghost" aria-label="Record version" onClick={() => { resetDraft(); setModal({ kind: "dataset-version", dataset: selectedDataset }); }}>Version</BrutalButton>
                      <BrutalButton size="sm" variant="ghost" aria-label="Archive dataset" onClick={() => setModal({ kind: "dataset-archive", dataset: selectedDataset })}>Archive</BrutalButton>
                    </div>
                  ) : null}
                  {lastVersion ? (
                    <div className="mt-2 border-t border-outline pt-2">
                      <StatRow label="Last version" value={`${lastVersion.version} (schema ${lastVersion.schema_version})`} />
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Dataset" title="Related schemas">
            <PanelBody loading={loading} error={schemasError} onRetry={() => void loadAll()} emptyTitle="No schemas" emptyDescription="Schemas published for the selected dataset appear here.">
              {schemas && selectedDatasetId ? (
                schemas.filter((s) => s.dataset_id === selectedDatasetId).length > 0 ? (
                  <ul className="space-y-2">
                    {schemas.filter((s) => s.dataset_id === selectedDatasetId).map((s) => (
                      <li key={s.id} className="flex items-center justify-between gap-2 border border-outline bg-surface p-3">
                        <span className="font-mono text-xs text-on-surface">v{s.version}</span>
                        <BrutalBadge tone={s.is_published ? "yellow" : "muted"}>{s.is_published ? "published" : "draft"}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <BrutalEmptyState title="No schemas" description="No schemas published for this dataset yet." />
                )
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "sources" ? (
        <BrutalCard eyebrow="Source" title="Sources">
          <div className="mb-3 flex max-w-xl flex-wrap items-end gap-2">
            <div className="min-w-32 flex-1">
              <BrutalSelect label="Connector" value={sourceConnector} onChange={(e) => setSourceConnector(e.target.value)} options={["ALL", ...DATA_CONNECTORS].map((c) => ({ label: c, value: c }))} />
            </div>
            <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
            {canDataWrite ? (
              <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal({ kind: "source-create" }); }}>Register source</BrutalButton>
            ) : null}
          </div>
          <p className="mb-2 font-mono text-xs text-on-surface-variant">Credentials are write-only at registration and never returned by any endpoint.</p>
          <PanelBody loading={loading} error={sourcesError} onRetry={() => void loadAll()} emptyTitle="No sources" emptyDescription="No sources match the current filter.">
            {sources && sources.length > 0 ? (
              <ul className="grid gap-2 md:grid-cols-2">
                {sources.map((src) => (
                  <li key={src.id} className="border border-outline bg-surface p-3">
                    <p className="truncate text-sm text-on-surface">{src.name}</p>
                    <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      {src.connector} · {src.region || "no region"}
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      ) : null}

      {active === "schemas" ? (
        <BrutalCard eyebrow="Source" title="Schemas">
          <div className="mb-3 flex max-w-2xl flex-wrap items-end gap-2">
            <div className="min-w-48 flex-1">
              <BrutalInput label="Dataset ID filter" value={schemaDatasetId} onChange={(e) => setSchemaDatasetId(e.target.value)} placeholder="optional uuid" />
            </div>
            <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
            {canDataWrite ? (
              <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setDraft((d) => ({ ...d, schema_dataset_id: selectedDatasetId ?? "" })); setModal({ kind: "schema-create" }); }}>Publish schema</BrutalButton>
            ) : null}
          </div>
          <PanelBody loading={loading} error={schemasError} onRetry={() => void loadAll()} emptyTitle="No schemas" emptyDescription="Published schema versions appear here with their field counts.">
            {schemas && schemas.length > 0 ? (
              <ul className="space-y-2">
                {schemas.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs text-on-surface">v{s.version} · {s.id.slice(0, 8)}</p>
                      <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        dataset {s.dataset_id.slice(0, 8)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <BrutalBadge tone={s.is_published ? "yellow" : "muted"}>{s.is_published ? "published" : "draft"}</BrutalBadge>
                      {canDataWrite ? (
                        <BrutalButton size="sm" variant="ghost" aria-label="Evolve schema" onClick={() => { resetDraft(); setModal({ kind: "schema-evolve", schema: s }); }}>Evolve</BrutalButton>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      ) : null}

      {active === "pipelines" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Pipeline" title="Pipelines">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="min-w-28 flex-1">
                <BrutalSelect label="Status" value={pipelineStatus} onChange={(e) => setPipelineStatus(e.target.value)} options={["ALL", "DRAFT", "ACTIVE", "PAUSED", "ARCHIVED"].map((s) => ({ label: s, value: s }))} />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
              {canDataWrite ? (
                <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal({ kind: "pipeline-create" }); }}>New pipeline</BrutalButton>
              ) : null}
            </div>
            <p className="mb-2 font-mono text-xs text-on-surface-variant">Supported operations are run, report completion and backfill — nothing else exists server-side.</p>
            <PanelBody loading={loading} error={pipelinesError} onRetry={() => void loadAll()} emptyTitle="No pipelines" emptyDescription="Create a pipeline to orchestrate ingestion and transforms.">
              {pipelines && pipelines.length > 0 ? (
                <ul className="space-y-2">
                  {pipelines.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => { setSelectedPipelineId(p.id); void loadJobs(p.id); }}
                        className={`flex w-full flex-wrap items-center justify-between gap-3 border p-3 text-left ${p.id === selectedPipelineId ? "border-primary-container bg-surface" : "border-outline bg-surface hover:border-on-surface"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{p.name}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {p.priority || "NORMAL"}
                          </p>
                        </div>
                        <BrutalBadge tone={statusTone(p.status)}>{p.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Pipeline" title="Run history">
            <PanelBody loading={jobsLoading} error={jobsError} onRetry={() => void loadJobs(selectedPipelineId)} emptyTitle="No runs" emptyDescription="Runs are reported by workers; select a pipeline to scope the history.">
              {jobs && jobs.length > 0 ? (
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {jobs.map((j) => (
                    <li key={j.run_id} className="border border-outline bg-surface p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-xs text-on-surface">{j.run_id.slice(0, 12)}…</span>
                        <BrutalBadge tone={statusTone(j.status)}>{j.status}</BrutalBadge>
                      </div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {j.records ?? 0} records
                      </p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
            {lastRun ? (
              <div className="mt-3 border-t border-outline pt-2">
                <StatRow label="Last run" value={`${lastRun.run_id.slice(0, 12)}… · ${lastRun.status}`} />
                {canDataWrite ? (
                  <div className="pt-2">
                    <BrutalButton size="sm" variant="ghost" aria-label="Report run completion" onClick={() => { resetDraft(); setModal({ kind: "pipeline-complete" }); }}>Report completion</BrutalButton>
                  </div>
                ) : null}
              </div>
            ) : null}
          </BrutalCard>

          <BrutalCard eyebrow="Pipeline" title="Operations">
            {!selectedPipeline ? (
              <BrutalEmptyState title="Nothing selected" description="Select a pipeline to run it or request a backfill." />
            ) : (
              <div className="space-y-3">
                <StatRow label="Pipeline" value={selectedPipeline.name} />
                <StatRow label="Status" value={selectedPipeline.status} />
                {canDataWrite ? (
                  <div className="flex flex-wrap gap-2">
                    <BrutalButton size="sm" variant="ghost" onClick={() => { resetDraft(); setModal({ kind: "pipeline-run", pipeline: selectedPipeline }); }}>Start run</BrutalButton>
                    <BrutalButton size="sm" variant="ghost" onClick={() => { resetDraft(); setModal({ kind: "pipeline-backfill", pipeline: selectedPipeline }); }}>Backfill</BrutalButton>
                  </div>
                ) : (
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Run operations require data:write</p>
                )}
              </div>
            )}
          </BrutalCard>
        </div>
      ) : null}

      {active === "quality" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Quality" title="Checks">
            <div className="mb-3 space-y-2">
              <BrutalInput label="Dataset ID" value={qualityDatasetId} onChange={(e) => setQualityDatasetId(e.target.value)} placeholder="uuid (or select a dataset)" />
              <div className="flex flex-wrap gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadQualityResults()}>Load results</BrutalButton>
                {canDataWrite ? (
                  <>
                    <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal({ kind: "quality-rule" }); }}>New rule</BrutalButton>
                  </>
                ) : null}
              </div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Rule types: required, range, regex, uniqueness, referential. No rule inventory endpoint exists — rules are managed per dataset.</p>
            </div>
            <PanelBody loading={qualityLoading} error={qualityError} onRetry={() => void loadQualityResults()} emptyTitle="No results" emptyDescription="Run a quality job, then load results for the dataset.">
              {qualityResults && qualityResults.length > 0 ? (
                <ul className="max-h-72 space-y-2 overflow-y-auto">
                  {qualityResults.map((r, index) => (
                    <li key={`${r.rule_id}-${index}`} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-xs text-on-surface">rule {r.rule_id.slice(0, 8)}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          passed {r.passed} · failed {r.failed}{r.timestamp ? ` · ${formatDateTime(r.timestamp)}` : ""}
                        </p>
                      </div>
                      <BrutalBadge tone={r.failed > 0 ? "error" : "yellow"}>{r.failed > 0 ? "failing" : "passing"}</BrutalBadge>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
            {lastRule ? (
              <div className="mt-3 border-t border-outline pt-2">
                <StatRow label="Last rule" value={`${lastRule.name} v${lastRule.version}`} />
              </div>
            ) : null}
          </BrutalCard>

          <BrutalCard eyebrow="Quality" title="Profile">
            <p className="mb-2 text-xs text-on-surface-variant">Profiles are computed server-side from records you submit — row counts, null rates, distinct counts and min/max. No scores are derived.</p>
            {qualityProfile ? (
              <div className="space-y-1">
                <StatRow label="Rows" value={String(qualityProfile.row_count)} />
                {Object.entries(qualityProfile.null_rate).slice(0, 8).map(([k, v]) => (
                  <StatRow key={k} label={`null ${k}`} value={String(v)} />
                ))}
                {Object.entries(qualityProfile.distinct_count).slice(0, 8).map(([k, v]) => (
                  <StatRow key={k} label={`distinct ${k}`} value={String(v)} />
                ))}
              </div>
            ) : (
              <BrutalEmptyState title="No profile" description="Submit records through a job or profile run to compute column statistics." />
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Quality" title="Run job / profile">
            <p className="mb-2 text-xs text-on-surface-variant">Provide records as a JSON array. Execution happens on the backend.</p>
            <BrutalInput label="Records (JSON array)" value={draft.quality_records} onChange={(e) => setDraft({ ...draft, quality_records: e.target.value })} placeholder='[{"email": "a@x.io"}]' />
            {canDataWrite ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <BrutalButton size="sm" variant="ghost" onClick={() => void handleQualityJobRun()} disabled={submitting}>{submitting ? "Running…" : "Run job"}</BrutalButton>
                <BrutalButton size="sm" variant="ghost" onClick={() => void handleQualityProfile()} disabled={submitting}>{submitting ? "Profiling…" : "Profile"}</BrutalButton>
              </div>
            ) : (
              <p className="mt-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Job runs require data:write</p>
            )}
          </BrutalCard>
        </div>
      ) : null}

      {active === "lineage" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Lineage" title="Traverse">
            <p className="mb-2 text-xs text-on-surface-variant">Nodes are <span className="font-mono">type:id</span> strings. Depth is bounded 1–10 by the backend.</p>
            <div className="space-y-2">
              <BrutalInput label="Node" value={lineageNode} onChange={(e) => setLineageNode(e.target.value)} placeholder="dataset:uuid" />
              <BrutalInput label="Depth (1–10)" value={lineageDepth} onChange={(e) => setLineageDepth(e.target.value)} placeholder="3" />
              <div className="flex flex-wrap gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadLineage()}>Traverse</BrutalButton>
                {canDataWrite ? (
                  <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal({ kind: "lineage-create" }); }}>Record edge</BrutalButton>
                ) : null}
              </div>
            </div>
            {lineageLoading ? (
              <div className="mt-3"><LoadingPanel rows={2} /></div>
            ) : lineageError ? (
              <p className="mt-3 text-xs text-error">{lineageError}</p>
            ) : lineageGraph ? (
              <div className="mt-3 grid grid-cols-3 gap-2">
                <div>
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Upstream · {lineageGraph.upstream.length}</p>
                  {lineageGraph.upstream.slice(0, 8).map((e, i) => (
                    <p key={i} className="truncate font-mono text-[10px] text-on-surface" title={`${e.source} → ${e.target}`}>{e.source}</p>
                  ))}
                </div>
                <div className="border border-primary-container bg-surface p-2">
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-primary-container">Node</p>
                  <p className="break-all font-mono text-[10px] text-on-surface">{lineageGraph.node}</p>
                </div>
                <div>
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Downstream · {lineageGraph.downstream.length}</p>
                  {lineageGraph.downstream.slice(0, 8).map((e, i) => (
                    <p key={i} className="truncate font-mono text-[10px] text-on-surface" title={`${e.source} → ${e.target}`}>{e.target}</p>
                  ))}
                </div>
              </div>
            ) : null}
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Lineage" title="Edges">
              {!lineageGraph || (lineageGraph.upstream.length === 0 && lineageGraph.downstream.length === 0) ? (
                <BrutalEmptyState title="No edges" description="Traverse a node to list its upstream and downstream edges." />
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Upstream</p>
                    <ul className="max-h-80 space-y-1 overflow-y-auto">
                      {lineageGraph.upstream.map((e, i) => (
                        <li key={i} className="border border-outline bg-surface px-2 py-1">
                          <p className="truncate font-mono text-xs text-on-surface">{e.source} → {e.target}</p>
                          {e.transformation ? <p className="truncate font-mono text-[10px] text-on-surface-variant">{e.transformation}</p> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Downstream</p>
                    <ul className="max-h-80 space-y-1 overflow-y-auto">
                      {lineageGraph.downstream.map((e, i) => (
                        <li key={i} className="border border-outline bg-surface px-2 py-1">
                          <p className="truncate font-mono text-xs text-on-surface">{e.source} → {e.target}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
              {lineageGraph && lineageGraph.provenance.length > 0 ? (
                <p className="mt-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                  Provenance records: {lineageGraph.provenance.length}
                </p>
              ) : null}
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "streams" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Stream" title="Topic operations">
            <p className="mb-2 text-xs text-on-surface-variant">Streams are topic-keyed — no inventory endpoint exists. Operate directly on a known topic.</p>
            <div className="space-y-2">
              <BrutalInput label="Topic" value={streamTopic} onChange={(e) => setStreamTopic(e.target.value)} placeholder="events" />
              <BrutalInput label="Partition" value={streamDraft.partition} onChange={(e) => setStreamDraft({ ...streamDraft, partition: e.target.value })} placeholder="0" />
              <BrutalInput label="Consumer" value={streamDraft.consumer} onChange={(e) => setStreamDraft({ ...streamDraft, consumer: e.target.value })} placeholder="consumer-group id" />
              <BrutalInput label="Event payload (JSON)" value={streamDraft.payload} onChange={(e) => setStreamDraft({ ...streamDraft, payload: e.target.value })} placeholder='{"id": 1}' />
              <BrutalInput label="Consume limit" value={streamDraft.limit} onChange={(e) => setStreamDraft({ ...streamDraft, limit: e.target.value })} placeholder="10" />
              <div className="flex flex-wrap gap-2">
                {canDataWrite ? (
                  <BrutalButton size="sm" variant="ghost" onClick={() => void handleStreamOp("create")} disabled={streamRunning}>Register</BrutalButton>
                ) : null}
                <BrutalButton size="sm" variant="ghost" onClick={() => void handleStreamOp("ingest")} disabled={streamRunning}>Ingest</BrutalButton>
                <BrutalButton size="sm" variant="ghost" onClick={() => void handleStreamOp("lag")} disabled={streamRunning}>Lag</BrutalButton>
                <BrutalButton size="sm" variant="ghost" onClick={() => void handleStreamOp("consume")} disabled={streamRunning}>Consume</BrutalButton>
              </div>
              {!canDataWrite ? (
                <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Stream registration requires data:write</p>
              ) : null}
            </div>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Stream" title="Result">
              {streamRunning ? (
                <LoadingPanel rows={2} />
              ) : streamError ? (
                <BrutalErrorState title="Stream operation failed" description={streamError} onRetry={() => void handleStreamOp("lag")} />
              ) : streamResult ? (
                <div className="space-y-1">
                  {Object.entries(streamResult).map(([k, v]) => (
                    <StatRow key={k} label={k.replace(/_/g, " ")} value={typeof v === "object" ? JSON.stringify(v).slice(0, 120) : String(v)} />
                  ))}
                  {Array.isArray((streamResult as { items?: unknown[] }).items) ? (
                    <div className="mt-2">
                      <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Events</p>
                      <ul className="max-h-64 space-y-1 overflow-y-auto">
                        {((streamResult as { items: StreamEvent[] }).items).slice(0, 20).map((ev, i) => (
                          <li key={i} className="border border-outline bg-surface px-2 py-1 font-mono text-xs text-on-surface">
                            {ev.event_id ?? `#${i}`} · {ev.topic ?? streamTopic} · offset {ev.offset ?? "—"}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : (
                <BrutalEmptyState title="No operation yet" description="Run a topic operation to see the backend-reported result. Lag is computed server-side per consumer." />
              )}
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "catalog" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Catalog" title="Search">
            <div className="space-y-2">
              <BrutalInput label="Query" value={catalogQuery} onChange={(e) => setCatalogQuery(e.target.value)} placeholder="dataset name or description" />
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Owner" value={catalogOwner} onChange={(e) => setCatalogOwner(e.target.value)} />
                <BrutalSelect label="Classification" value={catalogClassification} onChange={(e) => setCatalogClassification(e.target.value)} options={["ALL", ...DATA_CLASSIFICATIONS].map((c) => ({ label: c, value: c }))} />
              </div>
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                  <input type="checkbox" checked={catalogSemantic} onChange={(e) => setCatalogSemantic(e.target.checked)} />
                  Semantic (Qdrant)
                </label>
                <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                  <input type="checkbox" checked={catalogOffline} onChange={(e) => setCatalogOffline(e.target.checked)} />
                  Offline snapshot
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <BrutalButton variant="primary" size="sm" onClick={() => void runCatalogSearch()} disabled={catalogLoading}>{catalogLoading ? "Searching…" : "Search"}</BrutalButton>
                {canDataWrite ? (
                  <BrutalButton variant="ghost" size="sm" onClick={() => void handleCatalogSnapshot()} disabled={submitting}>Snapshot</BrutalButton>
                ) : null}
              </div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Lexical: PostgreSQL · Semantic: existing Qdrant collection · Offline: local snapshot, read-only.</p>
            </div>
          </BrutalCard>

          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Catalog" title="Results">
              {catalogLoading ? (
                <LoadingPanel />
              ) : catalogError ? (
                <BrutalErrorState title="Search unavailable" description={catalogError} onRetry={() => void runCatalogSearch()} />
              ) : catalogHits ? (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <BrutalBadge tone={catalogMeta?.stale ? "error" : "default"}>{catalogMeta?.source ?? "unknown source"}</BrutalBadge>
                    {catalogMeta?.total !== undefined ? <span className="font-mono text-xs text-on-surface-variant">{catalogMeta.total} hits</span> : null}
                    {catalogMeta?.stale ? <span className="font-mono text-xs uppercase tracking-widest text-error">READ-ONLY stale — no privileged actions</span> : null}
                  </div>
                  {catalogMeta?.warning ? <p className="text-xs text-error">{catalogMeta.warning}</p> : null}
                  {catalogHits.length > 0 ? (
                    <ul className="max-h-96 space-y-2 overflow-y-auto">
                      {catalogHits.map((hit) => (
                        <li key={hit.id} className="border border-outline bg-surface p-3">
                          <div className="flex items-center justify-between gap-2">
                            <p className="truncate text-sm text-on-surface">{hit.name ?? hit.id}</p>
                            {hit.score !== undefined && hit.score !== null ? (
                              <span className="font-mono text-xs text-on-surface-variant">score {Number(hit.score).toFixed(3)}</span>
                            ) : null}
                          </div>
                          {hit.description ? <p className="truncate text-xs text-on-surface-variant">{hit.description}</p> : null}
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {hit.owner || "no owner"} · {hit.classification || "unclassified"} · {hit.source || "unknown"}
                          </p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <BrutalEmptyState title="No hits" description="No catalog assets match the query." />
                  )}
                </div>
              ) : (
                <BrutalEmptyState title="No search yet" description="Run a catalog search to see provenance-rich results." />
              )}
            </BrutalCard>
          </div>
        </div>
      ) : null}

      {active === "lakehouse" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Lakehouse" title="Tier stats">
            <p className="mb-2 text-xs text-on-surface-variant">Tiers: raw, validated, curated, serving. Row counts are backend-reported, not measured here — nothing is derived client-side.</p>
            <div className="mb-3">
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadLakehouseStats()} disabled={!selectedDatasetId || lakehouseLoading}>
                {lakehouseLoading ? "Loading…" : "Load stats"}
              </BrutalButton>
              {!selectedDatasetId ? (
                <p className="mt-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Select a dataset in the Datasets tab first.</p>
              ) : null}
            </div>
            {lakehouseLoading ? (
              <LoadingPanel />
            ) : lakehouseError ? (
              <BrutalErrorState title="Stats unavailable" description={lakehouseError} onRetry={() => void loadLakehouseStats()} />
            ) : lakehouseStats ? (
              <div className="space-y-3">
                {Object.entries(lakehouseStats.stats).map(([tier, stat]) => (
                  <div key={tier} className="flex items-center justify-between gap-2 border border-outline bg-surface px-3 py-2">
                    <span className="font-mono text-xs uppercase tracking-widest text-on-surface">{tier}</span>
                    <span className="font-mono text-xs text-on-surface-variant">
                      {stat.exists ? `present · ${stat.row_count} rows (reported)` : "absent"}
                    </span>
                  </div>
                ))}
                {lakehouseStats.optimizations.length > 0 ? (
                  <div>
                    <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Storage recommendations</p>
                    {lakehouseStats.optimizations.slice(0, 5).map((opt, i) => (
                      <p key={i} className="truncate font-mono text-xs text-on-surface" title={JSON.stringify(opt)}>
                        {String(opt.action ?? "recommendation")}: {String(opt.reason ?? "")}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <BrutalEmptyState title="No stats loaded" description="Load tier stats for the selected dataset." />
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Lakehouse" title="Write tier">
            <p className="mb-2 text-xs text-on-surface-variant">Writes records into a tier for the selected dataset. Consequential — confirmed before sending.</p>
            {canDataWrite ? (
              <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setDraft((d) => ({ ...d, lakehouse_tier: "raw", lakehouse_format: "json", lakehouse_records: "" })); setModal({ kind: "lakehouse-write" }); }} disabled={!selectedDatasetId}>
                Write records
              </BrutalButton>
            ) : (
              <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Tier writes require data:write</p>
            )}
          </BrutalCard>
        </div>
      ) : null}

      {active === "operations" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Operations" title="Ingestion lifecycle">
            <p className="mb-2 text-xs text-on-surface-variant">Jobs start RUNNING and are completed explicitly with observed counts — progress is never simulated.</p>
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Dataset ID" value={ingestDraft.dataset_id} onChange={(e) => setIngestDraft({ ...ingestDraft, dataset_id: e.target.value })} placeholder="or select a dataset" />
                <BrutalInput label="Source ID" value={ingestDraft.source_id} onChange={(e) => setIngestDraft({ ...ingestDraft, source_id: e.target.value })} placeholder="uuid" />
              </div>
              <BrutalSelect label="Mode" value={ingestDraft.mode} onChange={(e) => setIngestDraft({ ...ingestDraft, mode: e.target.value })} options={["batch", "streaming", "cdc"].map((m) => ({ label: m, value: m }))} />
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Records" value={ingestDraft.records} onChange={(e) => setIngestDraft({ ...ingestDraft, records: e.target.value })} placeholder="0" />
                <BrutalInput label="Bytes" value={ingestDraft.bytes} onChange={(e) => setIngestDraft({ ...ingestDraft, bytes: e.target.value })} placeholder="0" />
              </div>
              <BrutalInput label="Error (for failure reports)" value={ingestDraft.error} onChange={(e) => setIngestDraft({ ...ingestDraft, error: e.target.value })} placeholder="optional" />
              {canDataWrite ? (
                <div className="flex flex-wrap gap-2">
                  <BrutalButton size="sm" variant="ghost" onClick={() => void handleIngestStart()} disabled={ingestRunning}>{ingestRunning ? "Working…" : "Start"}</BrutalButton>
                  <BrutalButton size="sm" variant="ghost" onClick={() => void handleIngestComplete()} disabled={ingestRunning || !ingestJob}>Complete</BrutalButton>
                </div>
              ) : (
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Ingestion requires data:write</p>
              )}
            </div>
            {ingestError ? <p className="mt-3 text-xs text-error">{ingestError}</p> : null}
            {ingestJob ? (
              <div className="mt-3 border-t border-outline pt-2">
                <StatRow label="Job" value={ingestJob.job_id} />
                <div className="flex items-center gap-2 pt-1">
                  <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Status</span>
                  <BrutalBadge tone={statusTone(ingestJob.status)}>{ingestJob.status}</BrutalBadge>
                </div>
              </div>
            ) : null}
          </BrutalCard>

          <BrutalCard eyebrow="Operations" title="CDC & checkpoints">
            <div className="space-y-2">
              <BrutalInput label="Changes (JSON array)" value={ingestDraft.changes} onChange={(e) => setIngestDraft({ ...ingestDraft, changes: e.target.value })} placeholder='[{"op": "insert", "row": {}}]' />
              {canDataWrite ? (
                <BrutalButton size="sm" variant="ghost" onClick={() => void handleIngestCdc()} disabled={ingestRunning}>Apply CDC</BrutalButton>
              ) : null}
            </div>
            <div className="mt-4 space-y-2 border-t border-outline pt-3">
              <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Consumer checkpoint</p>
              <BrutalInput label="Consumer" value={checkpointDraft.consumer} onChange={(e) => setCheckpointDraft({ ...checkpointDraft, consumer: e.target.value })} />
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Topic" value={checkpointDraft.topic} onChange={(e) => setCheckpointDraft({ ...checkpointDraft, topic: e.target.value })} />
                <BrutalInput label="Partition" value={checkpointDraft.partition} onChange={(e) => setCheckpointDraft({ ...checkpointDraft, partition: e.target.value })} />
              </div>
              <BrutalButton size="sm" variant="ghost" onClick={() => void handleCheckpointLookup()}>Look up</BrutalButton>
              {checkpointError ? <p className="text-xs text-error">{checkpointError}</p> : null}
              {checkpoint ? (
                <div className="border-t border-outline pt-2">
                  <StatRow label="Offset" value={String(checkpoint.offset)} />
                  <StatRow label="Watermark" value={formatDateTime(checkpoint.watermark)} />
                </div>
              ) : null}
            </div>
          </BrutalCard>

          <BrutalCard eyebrow="Operations" title="Replay & export">
            <p className="mb-2 text-xs text-on-surface-variant">Replay reprocesses a topic scope. Exports are audited server-side and need data:export.</p>
            <div className="flex flex-wrap gap-2">
              {canDataWrite ? (
                <BrutalButton size="sm" variant="ghost" onClick={() => { resetDraft(); setModal({ kind: "replay-create" }); }}>Replay topic</BrutalButton>
              ) : null}
              {canDataExport ? (
                <BrutalButton size="sm" variant="ghost" onClick={() => { resetDraft(); setModal({ kind: "export-create" }); }} disabled={!selectedDatasetId}>Request export</BrutalButton>
              ) : (
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Exports require data:export</p>
              )}
            </div>
            {replayResult ? (
              <div className="mt-3 border-t border-outline pt-2">
                <StatRow label="Replay" value={`${replayResult.id.slice(0, 8)} · ${replayResult.topic}`} />
                <BrutalBadge tone={statusTone(replayResult.status)}>{replayResult.status}</BrutalBadge>
              </div>
            ) : null}
            {exportResult ? (
              <div className="mt-3 border-t border-outline pt-2">
                <StatRow label="Export" value={exportResult.export_id.slice(0, 12)} />
                <BrutalBadge tone={statusTone(exportResult.status)}>{exportResult.status}</BrutalBadge>
              </div>
            ) : null}
          </BrutalCard>
        </div>
      ) : null}

      {active === "intelligence" ? (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            <BrutalCard eyebrow="Intelligence" title="Data products">
              <div className="mb-3 flex flex-wrap items-end gap-2">
                <div className="min-w-28 flex-1">
                  <BrutalSelect label="Status" value={productStatus} onChange={(e) => setProductStatus(e.target.value)} options={["ALL", "DRAFT", "ACTIVE", "ARCHIVED"].map((s) => ({ label: s, value: s }))} />
                </div>
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadProducts()}>Apply</BrutalButton>
                {canDataWrite ? (
                  <>
                    <BrutalButton variant="primary" size="sm" onClick={() => { resetDraft(); setModal({ kind: "product-create" }); }}>New product</BrutalButton>
                    <BrutalButton variant="ghost" size="sm" onClick={() => { resetDraft(); setModal({ kind: "domain-create" }); }}>New domain</BrutalButton>
                  </>
                ) : null}
              </div>
              {productsError ? (
                <BrutalErrorState title="Products unavailable" description={productsError} onRetry={() => void loadProducts()} />
              ) : products && products.length > 0 ? (
                <ul className="space-y-2">
                  {products.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{p.name}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{p.owner || "unassigned"}</p>
                      </div>
                      <BrutalBadge tone={statusTone(p.status)}>{p.status}</BrutalBadge>
                    </li>
                  ))}
                </ul>
              ) : products ? (
                <BrutalEmptyState title="No products" description="Publish a data product with an owner and contract." />
              ) : (
                <LoadingPanel rows={2} />
              )}
            </BrutalCard>

            <BrutalCard eyebrow="Intelligence" title="Freshness & schema drift">
              <p className="mb-2 text-xs text-on-surface-variant">Freshness states come from the backend: FRESH, STALE, MISSING or UNKNOWN. Applies to the selected dataset.</p>
              {!selectedDatasetId ? (
                <BrutalEmptyState title="No dataset selected" description="Select a dataset in the Datasets tab first." />
              ) : (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-end gap-2">
                    <div className="w-36">
                      <BrutalInput label="Expected hours" value={freshnessInterval} onChange={(e) => setFreshnessInterval(e.target.value)} />
                    </div>
                    <BrutalButton variant="ghost" size="sm" onClick={() => void handleFreshnessUpdate()} disabled={freshnessLoading}>
                      {freshnessLoading ? "Checking…" : "Refresh freshness"}
                    </BrutalButton>
                  </div>
                  {freshnessError ? <p className="text-xs text-error">{freshnessError}</p> : null}
                  {freshness ? (
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Status</span>
                        <BrutalBadge tone={statusTone(freshness.status)}>{freshness.status}</BrutalBadge>
                      </div>
                      <StatRow label="Last update" value={formatDateTime(freshness.last_update)} />
                      <StatRow label="SLO" value={JSON.stringify(freshness.slo).slice(0, 96)} />
                    </div>
                  ) : null}
                  <div className="space-y-2 border-t border-outline pt-3">
                    <BrutalInput label="Current schema (JSON array)" value={driftSchemas.current} onChange={(e) => setDriftSchemas({ ...driftSchemas, current: e.target.value })} placeholder='[{"name": "email"}]' />
                    <BrutalInput label="Previous schema (JSON array)" value={driftSchemas.previous} onChange={(e) => setDriftSchemas({ ...driftSchemas, previous: e.target.value })} placeholder="optional" />
                    <BrutalButton variant="ghost" size="sm" onClick={() => void handleDriftCheckRun()} disabled={driftCheckRunning}>
                      {driftCheckRunning ? "Checking…" : "Check drift"}
                    </BrutalButton>
                    {driftCheckError ? <p className="text-xs text-error">{driftCheckError}</p> : null}
                    {driftResult ? (
                      <div className="flex items-center gap-2">
                        <BrutalBadge tone={driftResult.drift ? "error" : "yellow"}>{driftResult.drift ? "drift detected" : "no drift"}</BrutalBadge>
                      </div>
                    ) : null}
                  </div>
                </div>
              )}
            </BrutalCard>

            <BrutalCard eyebrow="Intelligence" title="Reconciliation">
              <p className="mb-2 text-xs text-on-surface-variant">Compares submitted stage counts server-side: missing, duplicate and mismatched rows.</p>
              <div className="space-y-2">
                <BrutalInput label="Source count" value={reconciliationDraft.source_count} onChange={(e) => setReconciliationDraft({ ...reconciliationDraft, source_count: e.target.value })} placeholder="0" />
                <BrutalInput label="Processed count" value={reconciliationDraft.processed_count} onChange={(e) => setReconciliationDraft({ ...reconciliationDraft, processed_count: e.target.value })} placeholder="0" />
                <BrutalInput label="Output count" value={reconciliationDraft.output_count} onChange={(e) => setReconciliationDraft({ ...reconciliationDraft, output_count: e.target.value })} placeholder="0" />
                <BrutalButton variant="ghost" size="sm" onClick={() => void handleReconciliationRun()} disabled={reconciliationRunning}>
                  {reconciliationRunning ? "Comparing…" : "Reconcile"}
                </BrutalButton>
              </div>
              {reconciliationError ? <p className="mt-2 text-xs text-error">{reconciliationError}</p> : null}
              {reconciliation ? (
                <div className="mt-3 space-y-1 border-t border-outline pt-2">
                  <StatRow label="Missing" value={String(reconciliation.missing)} />
                  <StatRow label="Duplicate" value={String(reconciliation.duplicate)} />
                  <StatRow label="Mismatched" value={String(reconciliation.mismatched)} />
                </div>
              ) : null}
            </BrutalCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <BrutalCard eyebrow="Intelligence" title="Access anomalies">
              <p className="mb-2 text-xs text-on-surface-variant">Backend heuristic over identity audit logs (high-volume actors). Displayed verbatim — not a client-side detector.</p>
              {anomaliesError ? (
                <BrutalErrorState title="Anomalies unavailable" description={anomaliesError} onRetry={() => void loadAnomalies()} />
              ) : anomalies && anomalies.length > 0 ? (
                <ul className="space-y-2">
                  {anomalies.map((a, i) => (
                    <li key={`${a.actor}-${i}`} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-xs text-on-surface">{a.actor}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{a.count} actions</p>
                      </div>
                      <BrutalBadge tone="error">{a.type}</BrutalBadge>
                    </li>
                  ))}
                </ul>
              ) : anomalies ? (
                <BrutalEmptyState title="No anomalies" description="No high-volume actors detected in the window." />
              ) : (
                <LoadingPanel rows={2} />
              )}
            </BrutalCard>

            <BrutalCard eyebrow="Intelligence" title="Knowledge & AI">
              <p className="mb-3 text-xs text-on-surface-variant">Cross-link platform assets into the existing Knowledge search by canonical name — no duplicated embeddings or retrieval. No asset payloads leave this page except what you quote yourself.</p>
              <div className="flex flex-wrap gap-2">
                <BrutalButton variant="ghost" size="sm" href="/knowledge">Open Knowledge search</BrutalButton>
                <BrutalButton variant="yellow" size="sm" href="/ai">Ask AI about data</BrutalButton>
              </div>
              {selectedDataset ? (
                <div className="mt-3 border-t border-outline pt-2">
                  <StatRow label="Selected" value={selectedDataset.name} />
                  <div className="pt-2">
                    <BrutalButton variant="ghost" size="sm" href="/knowledge">Analyze dataset in Knowledge</BrutalButton>
                  </div>
                </div>
              ) : null}
            </BrutalCard>
          </div>
        </div>
      ) : null}

      <BrutalModal open={modal?.kind === "dataset-create"} title="New dataset" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleDatasetCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} placeholder="events" />
          <BrutalInput label="Description" value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.workspace} onChange={(e) => setDraft((d) => ({ ...d, workspace: e.target.value }))} />
            <BrutalInput label="Project" value={draft.project} onChange={(e) => setDraft((d) => ({ ...d, project: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
            <BrutalInput label="Team" value={draft.team} onChange={(e) => setDraft((d) => ({ ...d, team: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Classification" value={draft.classification} onChange={(e) => setDraft((d) => ({ ...d, classification: e.target.value }))} options={DATA_CLASSIFICATIONS.map((c) => ({ label: c, value: c }))} />
            <BrutalSelect label="Status" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))} options={["DRAFT", "ACTIVE", "ARCHIVED"].map((s) => ({ label: s, value: s }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Storage location" value={draft.storage_location} onChange={(e) => setDraft((d) => ({ ...d, storage_location: e.target.value }))} />
            <BrutalInput label="Region" value={draft.region} onChange={(e) => setDraft((d) => ({ ...d, region: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "dataset-version"} title="Record dataset version" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleDatasetVersion()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <BrutalInput label="Version payload (JSON object)" value={draft.version_payload} onChange={(e) => setDraft((d) => ({ ...d, version_payload: e.target.value }))} placeholder='{"version": "2.0", "schema_version": "1.1"}' />
      </BrutalModal>

      <BrutalModal open={modal?.kind === "dataset-archive"} title="Archive dataset?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleDatasetArchive()} disabled={submitting}>{submitting ? "Archiving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">Archiving moves the dataset out of active use. The backend reports the archival result.</p>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "source-create"} title="Register source" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleSourceCreate()} disabled={submitting}>{submitting ? "Registering…" : "Register"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">One-time secret: credentials are stored as a hash reference and <span className="font-bold text-on-surface">never returned</span> by any endpoint.</p>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
            <BrutalSelect label="Connector" value={draft.connector} onChange={(e) => setDraft((d) => ({ ...d, connector: e.target.value }))} options={DATA_CONNECTORS.map((c) => ({ label: c, value: c }))} />
          </div>
          <BrutalInput label="Credentials (one-time)" type="password" autoComplete="new-password" value={draft.credentials} onChange={(e) => setDraft((d) => ({ ...d, credentials: e.target.value }))} placeholder="••••••••" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Region" value={draft.region} onChange={(e) => setDraft((d) => ({ ...d, region: e.target.value }))} />
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
          </div>
          <BrutalSelect label="Classification" value={draft.classification} onChange={(e) => setDraft((d) => ({ ...d, classification: e.target.value }))} options={DATA_CLASSIFICATIONS.map((c) => ({ label: c, value: c }))} />
          <BrutalInput label="Config (JSON object)" value={draft.config} onChange={(e) => setDraft((d) => ({ ...d, config: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "schema-create"} title="Publish schema" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleSchemaCreate()} disabled={submitting}>{submitting ? "Publishing…" : "Publish"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Dataset ID" value={draft.schema_dataset_id} onChange={(e) => setDraft((d) => ({ ...d, schema_dataset_id: e.target.value }))} placeholder="uuid" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Version" value={draft.new_schema_version} onChange={(e) => setDraft((d) => ({ ...d, new_schema_version: e.target.value }))} />
            <BrutalSelect label="Classification" value={draft.schema_classification} onChange={(e) => setDraft((d) => ({ ...d, schema_classification: e.target.value }))} options={DATA_CLASSIFICATIONS.map((c) => ({ label: c, value: c }))} />
          </div>
          <BrutalInput label="Fields (JSON array)" value={draft.schema_fields} onChange={(e) => setDraft((d) => ({ ...d, schema_fields: e.target.value }))} placeholder='[{"name": "email", "type": "string", "nullable": false}]' />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "schema-evolve"} title="Evolve schema" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleSchemaEvolve()} disabled={submitting}>{submitting ? "Evolving…" : "Evolve"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Fields (JSON array)" value={draft.evolve_fields} onChange={(e) => setDraft((d) => ({ ...d, evolve_fields: e.target.value }))} placeholder='[{"name": "email", "type": "string"}]' />
          <BrutalSelect label="Compatibility" value={draft.compatibility} onChange={(e) => setDraft((d) => ({ ...d, compatibility: e.target.value }))} options={SCHEMA_COMPATIBILITY.map((c) => ({ label: c, value: c }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "pipeline-create"} title="New pipeline" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePipelineCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          <BrutalInput label="Description" value={draft.pipeline_description} onChange={(e) => setDraft((d) => ({ ...d, pipeline_description: e.target.value }))} />
          <BrutalInput label="Steps (JSON array)" value={draft.pipeline_steps} onChange={(e) => setDraft((d) => ({ ...d, pipeline_steps: e.target.value }))} placeholder="[]" />
          <BrutalInput label="Dependencies (JSON array)" value={draft.pipeline_dependencies} onChange={(e) => setDraft((d) => ({ ...d, pipeline_dependencies: e.target.value }))} placeholder="[]" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Schedule (cron)" value={draft.pipeline_schedule} onChange={(e) => setDraft((d) => ({ ...d, pipeline_schedule: e.target.value }))} />
            <BrutalInput label="Owner" value={draft.pipeline_owner} onChange={(e) => setDraft((d) => ({ ...d, pipeline_owner: e.target.value }))} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <BrutalInput label="Region" value={draft.pipeline_region} onChange={(e) => setDraft((d) => ({ ...d, pipeline_region: e.target.value }))} />
            <BrutalInput label="Priority" value={draft.pipeline_priority} onChange={(e) => setDraft((d) => ({ ...d, pipeline_priority: e.target.value }))} />
            <BrutalSelect label="Status" value={draft.pipeline_status} onChange={(e) => setDraft((d) => ({ ...d, pipeline_status: e.target.value }))} options={["DRAFT", "ACTIVE", "PAUSED", "ARCHIVED"].map((s) => ({ label: s, value: s }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "pipeline-run"} title="Start pipeline run" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePipelineRun()} disabled={submitting}>{submitting ? "Starting…" : "Start"}</BrutalButton>
        </>
      }>
        <BrutalInput label="Run payload (JSON object)" value={draft.run_payload} onChange={(e) => setDraft((d) => ({ ...d, run_payload: e.target.value }))} placeholder="{}" />
      </BrutalModal>

      <BrutalModal open={modal?.kind === "pipeline-complete"} title="Report run completion" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePipelineComplete()} disabled={submitting}>{submitting ? "Reporting…" : "Report"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Reports the worker-observed outcome for the last started run. Statuses come from the backend, never simulated.</p>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Status" value={draft.complete_status} onChange={(e) => setDraft((d) => ({ ...d, complete_status: e.target.value }))} options={["SUCCESS", "FAILED", "CANCELLED"].map((s) => ({ label: s, value: s }))} />
            <BrutalInput label="Records" value={draft.complete_records} onChange={(e) => setDraft((d) => ({ ...d, complete_records: e.target.value }))} placeholder="0" />
          </div>
          <BrutalInput label="Error" value={draft.complete_error} onChange={(e) => setDraft((d) => ({ ...d, complete_error: e.target.value }))} placeholder="optional" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "pipeline-backfill"} title="Request backfill?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePipelineBackfill()} disabled={submitting}>{submitting ? "Requesting…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Backfills reprocess a scope and time range through the pipeline.</p>
          <BrutalInput label="Backfill payload (JSON object)" value={draft.backfill_payload} onChange={(e) => setDraft((d) => ({ ...d, backfill_payload: e.target.value }))} placeholder='{"scope": {}, "time_range": {}}' />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "quality-rule"} title="New quality rule" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleQualityRuleCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.rule_name} onChange={(e) => setDraft((d) => ({ ...d, rule_name: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Rule type" value={draft.rule_type} onChange={(e) => setDraft((d) => ({ ...d, rule_type: e.target.value }))} options={QUALITY_RULE_TYPES.map((t) => ({ label: t, value: t }))} />
            <BrutalInput label="Version" value={draft.rule_version} onChange={(e) => setDraft((d) => ({ ...d, rule_version: e.target.value }))} />
          </div>
          <BrutalInput label="Params (JSON object)" value={draft.rule_params} onChange={(e) => setDraft((d) => ({ ...d, rule_params: e.target.value }))} placeholder='{"field": "email"}' />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "lineage-create"} title="Record lineage edge" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleLineageCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Source (type:id)" value={draft.lineage_source} onChange={(e) => setDraft((d) => ({ ...d, lineage_source: e.target.value }))} />
            <BrutalInput label="Target (type:id)" value={draft.lineage_target} onChange={(e) => setDraft((d) => ({ ...d, lineage_target: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Transformation" value={draft.lineage_transformation} onChange={(e) => setDraft((d) => ({ ...d, lineage_transformation: e.target.value }))} />
            <BrutalInput label="Pipeline ID" value={draft.lineage_pipeline_id} onChange={(e) => setDraft((d) => ({ ...d, lineage_pipeline_id: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "lakehouse-write"} title="Write tier records?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleLakehouseWrite()} disabled={submitting}>{submitting ? "Writing…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Tier" value={draft.lakehouse_tier} onChange={(e) => setDraft((d) => ({ ...d, lakehouse_tier: e.target.value }))} options={LAKEHOUSE_TIERS.map((t) => ({ label: t, value: t }))} />
            <BrutalInput label="Format" value={draft.lakehouse_format} onChange={(e) => setDraft((d) => ({ ...d, lakehouse_format: e.target.value }))} />
          </div>
          <BrutalInput label="Records (JSON array)" value={draft.lakehouse_records} onChange={(e) => setDraft((d) => ({ ...d, lakehouse_records: e.target.value }))} placeholder='[{"id": 1}]' />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "product-create"} title="New data product" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleProductCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
          </div>
          <BrutalInput label="Description" value={draft.product_description} onChange={(e) => setDraft((d) => ({ ...d, product_description: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Domain" value={draft.product_domain} onChange={(e) => setDraft((d) => ({ ...d, product_domain: e.target.value }))} />
            <BrutalSelect label="Status" value={draft.product_status} onChange={(e) => setDraft((d) => ({ ...d, product_status: e.target.value }))} options={["DRAFT", "ACTIVE", "ARCHIVED"].map((s) => ({ label: s, value: s }))} />
          </div>
          <BrutalSelect label="Classification" value={draft.classification} onChange={(e) => setDraft((d) => ({ ...d, classification: e.target.value }))} options={DATA_CLASSIFICATIONS.map((c) => ({ label: c, value: c }))} />
          <BrutalInput label="Contract (JSON object)" value={draft.product_contract} onChange={(e) => setDraft((d) => ({ ...d, product_contract: e.target.value }))} placeholder="{}" />
          <BrutalInput label="SLO (JSON object)" value={draft.product_slo} onChange={(e) => setDraft((d) => ({ ...d, product_slo: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "domain-create"} title="New data domain" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleDomainCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          <BrutalInput label="Owner" value={draft.domain_owner} onChange={(e) => setDraft((d) => ({ ...d, domain_owner: e.target.value }))} />
          <BrutalInput label="Description" value={draft.domain_description} onChange={(e) => setDraft((d) => ({ ...d, domain_description: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "replay-create"} title="Replay topic?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleReplayCreate()} disabled={submitting}>{submitting ? "Requesting…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Replay reprocesses a topic scope as a new PENDING job. If approval is required, the backend rejects unapproved requests with 403.</p>
          <BrutalInput label="Topic" value={draft.replay_topic} onChange={(e) => setDraft((d) => ({ ...d, replay_topic: e.target.value }))} />
          <BrutalInput label="Scope (JSON object)" value={draft.replay_scope} onChange={(e) => setDraft((d) => ({ ...d, replay_scope: e.target.value }))} placeholder="{}" />
          <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            <input type="checkbox" checked={draft.replay_requires_approval} onChange={(e) => setDraft((d) => ({ ...d, replay_requires_approval: e.target.checked }))} />
            Requires approval
          </label>
          <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            <input type="checkbox" checked={draft.replay_approved} onChange={(e) => setDraft((d) => ({ ...d, replay_approved: e.target.checked }))} />
            Approved (only check with a real approval)
          </label>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "export-create"} title="Request export?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleExportCreate()} disabled={submitting}>{submitting ? "Requesting…" : "Confirm"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">Exports are audited server-side with your identity, purpose and destination. The dataset is taken from the current selection.</p>
          <StatRow label="Dataset" value={selectedDatasetId ?? "—"} />
          <BrutalInput label="Purpose" value={draft.export_purpose} onChange={(e) => setDraft((d) => ({ ...d, export_purpose: e.target.value }))} placeholder="why this export is needed" />
          <BrutalInput label="Destination" value={draft.export_destination} onChange={(e) => setDraft((d) => ({ ...d, export_destination: e.target.value }))} placeholder="where the data goes" />
        </div>
      </BrutalModal>
    </div>
  );
}
