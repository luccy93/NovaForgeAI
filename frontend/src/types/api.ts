export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface ApiUser {
  id: string;
  email: string;
  username: string;
  full_name?: string | null;
  is_active: boolean;
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
