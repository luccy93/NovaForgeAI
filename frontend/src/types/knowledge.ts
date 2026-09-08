"use client";

/**
 * Knowledge (Volume 68) API types. Shape mirrors the exact payloads returned
 * by /api/v1/knowledge/* — never invent extra fields.
 */

export interface KnowledgeCitation {
  source_name?: string;
  doc_type?: string | null;
  version?: string | null;
  url?: string | null;
}

export interface KnowledgeSearchItem {
  document_id?: string;
  chunk_id?: string;
  title?: string | null;
  snippet?: string;
  score: number;
  source_type?: string | null;
  classification?: string;
  freshness_score?: number | null;
  citations: KnowledgeCitation[];
  retrieval_method?: string;
}

export interface KnowledgeSearchResponse {
  items: KnowledgeSearchItem[];
  total: number;
  query_id: string;
  latency_ms: number;
  filters_applied: {
    source_type?: string | null;
    doc_type?: string | null;
    classification?: string | null;
  };
}

export interface KnowledgeSource {
  source_id: string;
  name: string;
  source_type: string;
  status: string;
  classification?: string;
  owner?: string | null;
  region?: string | null;
  last_ingested_at?: string | null;
  created_at?: string | null;
}

export interface KnowledgeSourcesResponse {
  items: KnowledgeSource[];
  total: number;
}

export interface KnowledgeSourceCreated {
  source_id: string;
  name: string;
  source_type: string;
  status: string;
}

export interface KnowledgeDocument {
  document_id: string;
  title: string;
  content?: string;
  summary?: string | null;
  doc_type: string;
  version: string;
  classification: string;
  source_id?: string | null;
  freshness_score?: number | null;
  chunk_count?: number;
  status?: string;
  tags?: string[];
  attribution?: Record<string, unknown>;
  language?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface KnowledgeDocumentCreated {
  document_id: string;
  status: string;
}

export interface KnowledgeIngestionJob {
  job_id: string;
  source_id?: string | null;
  job_type: string;
  status: string;
  documents_processed: number;
  chunks_created: number;
  error?: string | null;
  created_at?: string | null;
}

export interface KnowledgeIngestionJobsResponse {
  items: KnowledgeIngestionJob[];
  total: number;
}

export interface KnowledgeIngestionJobDetail extends KnowledgeIngestionJob {
  documents_total?: number;
  documents_failed?: number;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface KnowledgeIngestionJobCreated {
  job_id: string;
  status: string;
  job_type: string;
}

export interface KnowledgeEntityLink {
  link_id: string;
  source_entity_id: string;
  target_entity_id: string;
  link_type: string;
  weight: number;
}

export interface KnowledgeEntity {
  entity_id: string;
  entity_type: string;
  name: string;
  canonical_id?: string | null;
  description?: string | null;
  classification?: string;
  confidence?: number;
  status?: string;
  created_at?: string | null;
}

export interface KnowledgeEntityDetail extends KnowledgeEntity {
  properties?: Record<string, unknown>;
  links: KnowledgeEntityLink[];
}

export interface KnowledgeEntitiesResponse {
  items: KnowledgeEntity[];
  total: number;
}

export interface KnowledgeEntityCreated {
  entity_id: string;
  entity_type: string;
  name: string;
}

export interface KnowledgeLinkCreated {
  link_id: string;
  source_entity_id: string;
  target_entity_id: string;
  link_type: string;
}

export interface KnowledgeFreshnessStats {
  total: number;
  fresh: number;
  aging: number;
  stale: number;
}

export interface KnowledgeUsageStats {
  total_queries: number;
  by_type: Record<string, number>;
  avg_latency_ms: number;
  unique_users: number;
  top_terms: string[];
}

export interface KnowledgeAuditEntry {
  query_id: string;
  query_text: string;
  query_type: string;
  results_count: number;
  latency_ms: number;
  user_id?: string | null;
  created_at?: string | null;
}

export interface KnowledgeAuditHistoryResponse {
  items: KnowledgeAuditEntry[];
  total: number;
}

export interface KnowledgeSearchFilterState {
  source_type?: string;
  doc_type?: string;
  classification?: string;
}