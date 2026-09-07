export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface MfaChallengeRequired {
  mfa_required: true;
  challenge_token: string;
  mfa_methods: string[];
  expires_in: number;
}

export type LoginResponse = AuthTokens | MfaChallengeRequired;

export function isMfaChallenge(res: LoginResponse): res is MfaChallengeRequired {
  return (res as MfaChallengeRequired).mfa_required === true;
}

export interface ApiUser {
  id: string;
  email: string;
  username: string;
  full_name?: string | null;
  is_active: boolean;
  created_at?: string;
  avatar_url?: string | null;
}

export interface WhoAmI {
  user_id: string;
  email: string;
  username: string;
  full_name?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  mfa_enabled: boolean;
  auth_method: string;
  organizations: Array<{ organization_id: string; role: string }>;
  permissions: string[];
}

export interface MfaSetup {
  secret: string;
  uri: string;
  backup_codes: string[];
  recovery_code: string;
}

export interface MfaStatus {
  enabled: boolean;
  setup_required: boolean;
}

export interface SessionOut {
  id: string;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface ApiKeyOut {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  last_used_at?: string | null;
  expires_at?: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKeyOut {
  full_key: string;
}

export interface FinOpsSummary {
  tenant: string;
  spend_cents: number;
  cost_records: number;
  total_tokens: number;
  ai_executions: number;
  ai_tokens: number;
  ai_cost_cents: number;
}

export interface CostRecord {
  id: string;
  provider: string;
  model: string;
  amount_cents: number;
  cost_basis: string;
  occurred_at: string | null;
}

export interface CostsPage {
  items: Array<CostRecord>;
  total: number;
  limit: number;
  offset: number;
  spend_cents: number;
}

export interface KnowledgeHit {
  document_id?: string;
  chunk_id?: string;
  title?: string;
  snippet?: string;
  citation?: string;
  score?: number;
}

export interface KnowledgePage {
  items: Array<KnowledgeHit>;
  total: number;
}

export interface Paginated<T> {
  items: T[];
  total?: number;
}

export interface HealthDependencies {
  status: string;
  checks: Record<string, { status: string; latency_ms?: number; detail?: string }>;
  measured_at?: number;
}

export interface WorkflowHealth {
  tenant?: string;
  total: number;
  success: number;
  failed: number;
  success_rate?: number;
}

export interface WorkflowRun {
  run_id?: string;
  id?: string;
  status: string;
  execution_id?: string;
  workflow_version_id?: string;
  workflow_id?: string;
  created_at?: string;
}

export interface AiUsageItem {
  id: string;
  action: string;
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_cents?: number;
  created_at?: string;
}

export interface AiUsagePage {
  items: AiUsageItem[];
  count: number;
  totals?: Record<string, unknown>;
}

export interface SecurityDashboard {
  tenant?: string;
  total_scans?: number;
  open_findings?: number;
  risk?: unknown;
  [key: string]: unknown;
}

export interface GovernancePosture {
  scope_type?: string;
  scope_value?: string;
  domain?: string;
  violations?: unknown[];
  posture_score?: number;
  compliance?: unknown;
  controls_passing?: number;
  [key: string]: unknown;
}

export interface IntegrationItem {
  id: string;
  name?: string;
  provider?: string;
  status?: string;
  health?: string;
}

export interface ObservabilityDashboard {
  tenant?: string;
  services?: number;
  health?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RecentActivityItem {
  id: string;
  tenant?: string;
  event_type: string;
  source?: string;
  payload?: unknown;
  created_at?: string;
}
