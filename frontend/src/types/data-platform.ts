"use client";

/**
 * Data Platform (V65) domain types. Shapes mirror the exact backend
 * serializers in backend/app/api/data_platform.py and
 * backend/app/data_platform/ — never invent fields.
 *
 * Notes:
 * - Most list endpoints return `{items}` with NO `total`; counts derived
 *   client-side are labeled "listed", never presented as totals.
 * - Source credentials are write-only: the backend stores a hash ref and
 *   never returns credential material, so no credential field exists here.
 * - Lakehouse `row_count` values are backend-reported (the raw tier count
 *   is a backend placeholder) and must be labeled as reported, never
 *   treated as measured truth.
 */

export interface PaginatedItems<T> {
  items: T[];
  total?: number;
}

/** POST /data-platform/datasets response + GET /datasets list row. */
export interface DatasetListItem {
  id: string;
  name: string;
  status: string;
  classification: string;
  owner?: string | null;
  region?: string | null;
}

/** GET /data-platform/datasets/{id} response. */
export interface DatasetDetail extends DatasetListItem {
  description?: string | null;
  storage_location?: string | null;
}

/** POST /data-platform/datasets/{id}/versions response. */
export interface DatasetVersion {
  id: string;
  version: string;
  schema_version: string;
}

/** POST /data-platform/sources response. */
export interface DataSourceCreated {
  id: string;
  name: string;
  connector: string;
  status: string;
}

/** GET /data-platform/sources row (no status, no detail endpoint). */
export interface DataSourceListItem {
  id: string;
  name: string;
  connector: string;
  region?: string | null;
}

/** Schema field shape per the DataSchema model: {name, type, nullable, classification}. */
export interface SchemaField {
  name: string;
  type: string;
  nullable?: boolean;
  classification?: string;
}

/** POST /data-platform/schemas response. */
export interface DataSchema {
  id: string;
  version: string;
  fields: SchemaField[];
}

/** GET /data-platform/schemas row. */
export interface DataSchemaListItem {
  id: string;
  dataset_id: string;
  version: string;
  is_published: boolean;
}

/** POST /data-platform/pipelines response. */
export interface DataPipelineCreated {
  id: string;
  name: string;
  status: string;
  dag_hash?: string | null;
}

/** GET /data-platform/pipelines row. */
export interface DataPipelineListItem {
  id: string;
  name: string;
  status: string;
  priority?: string | null;
}

/** POST /data-platform/pipelines/{id}/runs response. */
export interface PipelineRunStarted {
  run_id: string;
  status: string;
  idempotency_key?: string | null;
}

/** POST /data-platform/pipelines/runs/{run_id}/complete response. */
export interface PipelineRunCompleted {
  run_id: string;
  status: string;
  duration_ms?: number | null;
}

/** POST /data-platform/pipelines/{id}/backfill response. */
export interface PipelineBackfill {
  run_id: string;
  status: string;
  scope?: Record<string, unknown>;
  time_range?: Record<string, unknown>;
}

/** GET /data-platform/data-jobs row (run history source). */
export interface DataJobRow {
  run_id: string;
  status: string;
  records?: number | null;
}

/** POST /data-platform/quality/rules response. */
export interface QualityRuleCreated {
  id: string;
  name: string;
  version: string;
}

/** Quality job per-rule counters (POST /quality/jobs + GET /quality/results). */
export interface QualityResultRow {
  rule_id: string;
  passed: number;
  failed: number;
  timestamp?: string;
}

/** POST /data-platform/quality/profile response. */
export interface QualityProfile {
  row_count: number;
  null_rate: Record<string, number>;
  distinct_count: Record<string, number>;
  min_max: Record<string, unknown>;
  distribution?: Record<string, unknown>;
}

/** POST /data-platform/lineage response. */
export interface LineageEdgeCreated {
  id: string;
  source: string;
  target: string;
}

export interface LineageEdge {
  source: string;
  target: string;
  transformation?: string | null;
}

/** GET /data-platform/lineage/{node}/graph response. */
export interface LineageGraph {
  node: string;
  upstream: LineageEdge[];
  downstream: LineageEdge[];
  provenance: unknown[];
}

/** POST /data-platform/streams response. */
export interface DataStreamCreated {
  id: string;
  topic: string;
  partition: number;
}

/** POST /data-platform/streams/{topic}/ingest response. */
export interface StreamEventReceipt {
  event_id: string;
  topic: string;
  partition: number;
  idempotency_key?: string | null;
}

/** GET /data-platform/streams/{topic}/lag response (computed server-side). */
export interface StreamLag {
  topic: string;
  consumer: string;
  lag: number;
}

/** Stream event returned by POST /streams/{topic}/consume. */
export interface StreamEvent {
  event_id?: string;
  topic?: string;
  partition?: number;
  offset?: number;
  payload?: Record<string, unknown>;
}

/** GET /data-platform/lakehouse/{id}/stats response. */
export interface LakehouseTierStat {
  exists: boolean;
  row_count: number;
}

export interface LakehouseStats {
  stats: Record<string, LakehouseTierStat>;
  optimizations: Array<Record<string, unknown>>;
}

/** POST /data-platform/lakehouse/{id}/tier response. */
export interface LakehouseTierWrite {
  tier: string;
  records: number;
  format: string;
  dataset_id: string;
}

export const DATA_CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] as const;
export const DATA_CONNECTORS = [
  "postgresql",
  "object_storage",
  "api",
  "git",
  "csv",
  "json",
  "parquet",
  "event_stream",
] as const;
export const LAKEHOUSE_TIERS = ["raw", "validated", "curated", "serving"] as const;
export const QUALITY_RULE_TYPES = ["required", "range", "regex", "uniqueness", "referential"] as const;
export const SCHEMA_COMPATIBILITY = ["backward", "forward", "full"] as const;
