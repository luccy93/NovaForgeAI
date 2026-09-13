export interface AdminOverview {
  total_organizations: number;
  total_users: number;
  total_repositories: number;
  active_subscriptions: number;
  total_agent_runs: number;
  mrr_cents?: number | null;
}

export interface AdminOrganization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  is_active: boolean;
  member_count: number;
  repository_count: number;
  created_at: string;
}

export interface AdminUser {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface AdminAuditLog {
  id: string;
  organization_id?: string | null;
  user_id?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  details?: unknown;
  ip_address?: string | null;
  created_at: string;
}

export interface AdminAnalyticsEvent {
  id: string;
  organization_id?: string | null;
  user_id?: string | null;
  event_type?: string | null;
  event_name?: string | null;
  properties?: unknown;
  created_at: string;
}

export interface AdminFeatureFlag {
  name: string;
  default: boolean;
  overridden: boolean;
  enabled: boolean;
}

export interface FeatureFlag {
  id: string;
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  organization_id?: string | null;
}
