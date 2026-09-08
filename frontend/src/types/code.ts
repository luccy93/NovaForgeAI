// Code Intelligence + AI Developer API types.
// These mirror the backend REST contracts exactly. No fabricated data.

// ─── Repositories (/api/v1/repositories) ────────────────────────────────────

export interface RepositoryOut {
  id: string;
  name: string;
  full_name: string;
  description?: string | null;
  private: boolean;
  git_url?: string | null;
  default_branch: string;
  language?: string | null;
  size?: number | null;
  last_indexed_at?: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Index (/api/v1/code-intelligence/{repo}/index) ────────────────────────

export type CodeIndexStatus = "indexing" | "ready" | "queued" | "failed" | string;

export interface CodeIndexOut {
  id: string;
  repository_id: string;
  status: string;
  branch: string;
  file_count: number;
  symbol_count: number;
  index_size_bytes: number;
  created_at: string;
  updated_at: string;
}

export interface IndexVersionOut {
  id: string;
  index_id: string;
  version: number;
  status: string;
  commit_sha?: string | null;
  files_changed: number;
  created_at: string;
}

export interface IndexDiffOut {
  files_added: string[];
  files_removed: string[];
  files_modified: string[];
  symbols_added: number;
  symbols_removed: number;
  symbols_modified: number;
}

export interface IndexHealthOut {
  index_id: string;
  status: string;
  last_updated?: string | null;
  file_count: number;
  symbol_count: number;
  chunk_count: number;
  index_size_bytes: number;
  health_score: number;
  issues: string[];
}

// ─── Files (/api/v1/code-intelligence/{repo}/files) ─────────────────────────

export interface CodeFileOut {
  id: string;
  index_id: string;
  path: string;
  language?: string | null;
  size_bytes: number;
  line_count: number;
  symbol_count: number;
  status: string;
  indexed_at?: string | null;
}

export interface FileSymbol {
  id: string;
  name: string;
  symbol_type: string;
  line_start: number;
  line_end: number;
  signature?: string | null;
}

export interface FileReference {
  id: string;
  reference_type?: string | null;
  target_file_id?: string | null;
  line?: number | null;
}

export interface FileImport {
  id: string;
  module_path: string;
  names?: string[] | null;
  line?: number | null;
}

/**
 * IMPORTANT: The backend does NOT expose raw file source text. `FileContentOut`
 * carries file metadata + symbols + references + imports only. Code preview is
 * derived from search snippets/content_preview, never fabricated.
 */
export interface FileContentOut {
  file: CodeFileOut;
  symbols: FileSymbol[];
  references: FileReference[];
  imports: FileImport[];
}

export interface CodeMetricsOut {
  file_id: string;
  path: string;
  line_count: number;
  code_lines: number;
  comment_lines: number;
  blank_lines: number;
  cyclomatic_complexity: number;
  cognitive_complexity: number;
  maintainability_index: number;
}

// ─── Symbols (/api/v1/code-intelligence/{repo}/symbols) ─────────────────────

export interface SymbolOut {
  id: string;
  file_id: string;
  name: string;
  symbol_type: string;
  qualified_name?: string | null;
  line_start: number;
  line_end: number;
  column_start: number;
  column_end: number;
  docstring?: string | null;
  signature?: string | null;
  complexity: number;
}

export interface SymbolDetailOut extends SymbolOut {
  calls: Array<Record<string, unknown>>;
  called_by: Array<Record<string, unknown>>;
  references: Array<Record<string, unknown>>;
  children: Array<Record<string, unknown>>;
}

export interface SymbolSearchOut {
  results: SymbolOut[];
  total: number;
}

// ─── Graph (/api/v1/code-intelligence/{repo}/graph) ─────────────────────────

export interface GraphNodeOut {
  id: string;
  label: string;
  type: string;
  file_path?: string | null;
}

export interface GraphEdgeOut {
  source: string;
  target: string;
  edge_type: string;
  weight?: number;
}

export interface GraphOut {
  nodes: GraphNodeOut[];
  edges: GraphEdgeOut[];
  stats: Record<string, unknown>;
}

export interface ModuleInfo {
  module: string;
  file_count: number;
}

export interface CyclesOut {
  cycles: string[][];
  total_cycles: number;
}

// ─── Quality (/api/v1/code-intelligence/{repo}/quality) ─────────────────────

export interface CodeSmellOut {
  id: string;
  file_id: string;
  symbol_id?: string | null;
  smell_type: string;
  severity: string;
  message: string;
  line_start: number;
  line_end: number;
  suggestion?: string | null;
  effort_estimate?: string | null;
}

export interface SmellScanOut {
  total_smells: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  smells: CodeSmellOut[];
}

export interface QualitySummary {
  total_files: number;
  avg_complexity: number;
  avg_maintainability: number;
  total_code_lines: number;
  total_smells: number;
  smells_by_severity: Record<string, number>;
}

// ─── Security (/api/v1/code-intelligence/{repo}/security) ───────────────────

export interface SecurityVulnerabilityOut {
  id: string;
  file_id: string;
  symbol_id?: string | null;
  vulnerability_type: string;
  severity: string;
  message: string;
  line_start: number;
  line_end: number;
  recommendation?: string | null;
}

export interface SecurityScanOut {
  total_vulnerabilities: number;
  by_severity: Record<string, number>;
  vulnerabilities: SecurityVulnerabilityOut[];
}

export interface SecretOut {
  file_id: string;
  file_path: string;
  line: number;
  secret_type: string;
  severity: string;
}

export interface SecretScanOut {
  total_secrets: number;
  secrets: SecretOut[];
}

// ─── Impact (/api/v1/code-intelligence/{repo}/impact) ───────────────────────

export interface BreakingChangeOut {
  symbol_name: string;
  symbol_type: string;
  file_path: string;
  line: number;
  reason: string;
  severity: string;
}

export interface UnusedItemOut {
  symbol_name: string;
  symbol_type: string;
  file_path: string;
  line: number;
  confidence: number;
}

export interface ImpactAnalysisOut {
  affected_files: number;
  affected_symbols: number;
  breaking_changes: BreakingChangeOut[];
  unused_items: UnusedItemOut[];
  impact_score: number;
  risk_level: string;
}

export interface DownstreamOut {
  direct_dependencies: Array<Record<string, unknown>>;
  transitive_dependencies: Array<Record<string, unknown>>;
  total_affected: number;
}

export interface DependencyOut {
  direct_upstreams: Array<Record<string, unknown>>;
  transitive_upstreams: Array<Record<string, unknown>>;
  total_dependencies: number;
}

// ─── Search (/api/v1/code-intelligence/{repo}/search) ───────────────────────

export interface SearchResultItem {
  id: string;
  name: string;
  result_type: string;
  file_path?: string | null;
  line?: number | null;
  score: number;
  /** Backend-provided indexed code snippet. Never fabricated. */
  snippet?: string | null;
  context?: Record<string, unknown> | null;
}

export interface SearchOut {
  query: string;
  total_results: number;
  results: SearchResultItem[];
  search_time_ms: number;
}

// ─── RAG context (/api/v1/code-intelligence/{repo}/rag/context) ─────────────

export interface RAGContextOut {
  query: string;
  context_chunks: Array<Record<string, unknown>>;
  relevant_symbols: Array<Record<string, unknown>>;
  graph_context?: Record<string, unknown> | null;
  metrics_summary?: Record<string, unknown> | null;
  total_tokens_estimate: number;
}

// ─── Tests (/api/v1/code-intelligence/{repo}/tests) ─────────────────────────

export interface TestCoverageOut {
  total_test_files: number;
  total_test_functions: number;
  frameworks_used: string[];
  coverage_summary: Record<string, unknown>;
}

export interface TestQualityOut {
  file_path: string;
  test_count: number;
  assert_density: number;
  mock_ratio: number;
  quality_score: number;
}

export interface TestGapOut {
  symbol_name: string;
  symbol_type: string;
  file_path: string;
  has_tests: boolean;
}

// ─── Ownership (/api/v1/code-intelligence/{repo}/ownership) ─────────────────

export interface OwnershipSummaryOut {
  total_files: number;
  owned_files: number;
  ownership_coverage: number;
  total_contributors: number;
  bus_risk_files: number;
  unowned_files: number;
}

export interface ContributorStatsOut {
  email: string;
  name?: string | null;
  commits: number;
  files_changed: number;
  lines_added: number;
  lines_deleted: number;
}

export interface BusRiskOut {
  file_path: string;
  owner_count: number;
  risk_level: string;
  primary_owner?: string | null;
}

export interface OwnerOut {
  owner_email: string;
  owner_name?: string | null;
  ownership_score: number;
  commits_count: number;
  lines_changed: number;
  role?: string | null;
}

// ─── History (/api/v1/code-intelligence/{repo}/history) ─────────────────────

export interface HotspotOut {
  file_path: string;
  change_count: number;
  contributor_count: number;
  risk_score: number;
}

export interface ChurnMetricsOut {
  total_lines_added: number;
  total_lines_deleted: number;
  churn_ratio: number;
  avg_daily_changes: number;
}

export interface AuthorActivityOut {
  author_name: string;
  author_email: string;
  commits: number;
  files_changed: number;
  active_days: number;
}

export interface ChangeSummaryOut {
  total_commits: number;
  total_files_changed: number;
  total_authors: number;
  date_range_days: number;
  avg_commits_per_day: number;
}

// ─── Repository summary (/api/v1/code-intelligence/{repo}/summary) ──────────

export interface RepositoryProfileOut {
  total_files: number;
  total_symbols: number;
  total_lines: number;
  languages_count: number;
  frameworks: string[];
  architecture_type: string;
  maturity_indicator: string;
}

export interface LanguageOut {
  language: string;
  file_count: number;
  line_count: number;
  percentage: number;
}

// ─── Architecture (/api/v1/code-intelligence/{repo}/architecture) ───────────

export interface ArchitectureOverviewOut {
  layers: Array<Record<string, unknown>>;
  modules: Array<Record<string, unknown>>;
  dependencies: Array<Record<string, unknown>>;
  summary?: Record<string, unknown> | null;
}

export interface DependencyGraphOut {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  circular_dependencies: string[][];
}

// ─── DevTools capabilities (/api/v1/devtools/capabilities) ──────────────────

export interface DevCapabilities {
  streaming: boolean;
  cancellation: boolean;
  diff_preview: boolean;
  code_actions: boolean;
  review: boolean;
  search: boolean;
  agent_execution: boolean;
  workflow_execution: boolean;
  git_integration: boolean;
  offline_mode: boolean;
  [key: string]: unknown;
}

// ─── AI Developer (/api/v1/ai-dev) ──────────────────────────────────────────

export interface AiDevContextItem {
  kind: string;
  text: string;
  citation: {
    file?: string | null;
    line_start?: number | null;
    line_end?: number | null;
  };
}

export interface AiDevContextOut {
  repository_id: string;
  query: string;
  tokens_used: number;
  token_budget: number;
  truncated: boolean;
  items: AiDevContextItem[];
  recent_changes: Array<Record<string, unknown>>;
  test_mapping: Record<string, Array<Record<string, unknown>>>;
}

export interface ExplainIn {
  repository_id: string;
  kind: string;
  target: string;
  top?: number;
}

export interface ExplainOut {
  kind: string;
  [key: string]: unknown;
}

export interface ReviewFinding {
  id: string;
  file_path: string;
  line_start?: number | null;
  line_end?: number | null;
  category: string;
  severity: string;
  message: string;
  reason?: string | null;
  confidence: number;
  status: string;
  suggested_fix?: string | null;
  evidence?: string;
}

export interface AiReviewOut {
  review: Record<string, unknown>;
  review_id: string;
}

export interface AiReviewDetail {
  review: Record<string, unknown>;
  findings: ReviewFinding[];
}

export interface PatchFileEdit {
  path: string;
  old_content: string | null;
  old_hash?: string | null;
  new_content: string;
}

export interface PatchOut {
  id: string;
  repository_id: string;
  title: string;
  branch: string;
  status: string;
  files: Array<{ path: string; old_hash?: string | null; new_hash?: string | null; old_content: string; new_content: string }>;
  diffs: Record<string, string>;
  rollback_diffs: Record<string, string>;
  model?: string | null;
  source: string;
  base_commit_sha?: string | null;
  applied_at?: string | null;
  rolled_back_at?: string | null;
  error?: string | null;
}

export interface PatchListOut {
  items: PatchOut[];
  count: number;
}

export interface ChangeSummaryIn {
  repository_id: string;
  commit_sha?: string | null;
  files?: Array<Record<string, unknown>> | null;
}

export interface ChangeSummaryOut2 {
  repository_id: string;
  commit_sha?: string | null;
  commit_message?: string | null;
  author?: string | null;
  stats: { files: number; additions: number; deletions: number };
  notes: string[];
}

export interface TestGenerateIn {
  repository_id: string;
  patch_id?: string | null;
  commit_sha?: string | null;
  branch?: string | null;
  framework?: string | null;
}

export interface AiDevTestRunOut {
  id: string;
  repository_id?: string | null;
  branch?: string | null;
  commit_sha?: string | null;
  patch_id?: string | null;
  status: string;
  framework?: string | null;
  command?: string | null;
  test_plan?: unknown;
  test_results?: unknown;
  failures_analysis?: string | null;
  duration_ms?: number | null;
  ci_pipeline_run_id?: string | null;
  [key: string]: unknown;
}

export interface AgentOut {
  id: string;
  repository_id: string;
  agent_type: string;
  name: string;
  goal: string;
  status: string;
  model?: string | null;
  result?: string | null;
  last_error?: string | null;
  created_at: string;
  start_time?: string | null;
  end_time?: string | null;
  [key: string]: unknown;
}

export interface AgentListOut {
  items: AgentOut[];
  count: number;
}

export interface AgentPlanOut {
  id: string;
  agent_run_id: string;
  plan_type: string;
  name: string;
  steps: unknown[];
  rationale?: string | null;
  approved: boolean;
  approved_by?: string | null;
  rejected: boolean;
}

export interface AgentPlanListOut {
  items: AgentPlanOut[];
  count: number;
}

export interface AgentCheckpointOut {
  id: string;
  sequence: number;
  summary: string;
  state: Record<string, unknown>;
  is_final: boolean;
}

export interface AgentCheckpointListOut {
  items: AgentCheckpointOut[];
  count: number;
}

export interface SecurityBlock {
  category: string;
  severity: string;
  message: string;
  reason?: string | null;
  file_path?: string | null;
  line_start?: number | null;
  confidence?: number;
}

export interface SecurityGateOut {
  decision: string;
  passed: boolean;
  blockers: SecurityBlock[];
  warnings: SecurityBlock[];
  blocker_count: number;
  warning_count: number;
  repository_id?: string | null;
  review_id?: string | null;
  commit_sha?: string | null;
  ran_by: string;
  eligible: boolean;
}
