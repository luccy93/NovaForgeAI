/** Governed integrations domain types (Phase 19).
 *
 * Mirrors the backend serializers in backend/app/integrations/ exactly.
 * Credential material, tokens and secrets are NEVER represented here —
 * the backend returns metadata references only (secret_ref, material_hint,
 * token_ref, expiry) and the UI must never attempt to render material.
 */

export type IntegrationType = "webhook" | "api" | "oauth" | "connector";

export type IntegrationStatus = "ACTIVE" | "DISABLED" | "DEGRADED" | "QUARANTINED" | "REVOKED";

export type HealthState = "UNKNOWN" | "HEALTHY" | "DEGRADED" | "UNHEALTHY";

export type CredentialKind = "api_key" | "bearer" | "basic" | "oauth" | "webhook_secret";

export type OAuthStatus = "PENDING" | "ACTIVE" | "NEEDS_REAUTH" | "REVOKED";

export type PolicyAction = "alert" | "warn" | "require_approval" | "block";

export interface Paginated<T> {
  items: T[];
  total: number;
}

export interface Integration {
  id: string;
  tenant: string;
  name: string;
  type: string;
  provider: string;
  version: string;
  workspace: string;
  environment: string;
  region: string;
  capabilities: string[];
  status: string;
  health: string;
  config: Record<string, unknown>;
  owner: string;
}

export interface IntegrationVersion {
  id: string;
  integration_id: string;
  version: string;
  contract: Record<string, unknown>;
  compatibility: string;
  deprecated: boolean;
  migration_notes: string;
}

export interface IntegrationConnection {
  id: string;
  tenant: string;
  integration_id: string;
  workspace: string;
  environment: string;
  endpoint_ref: string;
  credential_id: string | null;
  scopes: string[];
  status: string;
  health: string;
  last_success_at: string | null;
  last_failure_at: string | null;
  consecutive_failures: number;
}

/** Credential metadata only — material is never exposed by the backend. */
export interface IntegrationCredentialMeta {
  id: string;
  tenant: string;
  connection_id: string | null;
  kind: string;
  secret_ref: string;
  material_hint: string;
  scopes: string[];
  expires_at: string | null;
  status: string;
}

export interface ConnectorDefinition {
  key: string;
  provider: string;
  capabilities: string[];
  auth_kind: string;
}

/** One sync run record (backend list shape: sync_key/status/pages/records/error). */
export interface ConnectorSyncRecord {
  sync_key: string;
  status: string;
  pages: number;
  records: number;
  error: string;
  deduplicated?: boolean;
}

export interface OAuthConnection {
  id: string;
  tenant: string;
  integration_id: string;
  connection_id: string | null;
  provider: string;
  client_id: string;
  scopes: string[];
  redirect_uri: string;
  token_ref: string;
  expires_at: string | null;
  status: string;
}

export interface OAuthStartResult {
  id: string;
  status: string;
  authorize_url: string;
  state?: string;
}

export interface IntegrationWebhook {
  id: string;
  tenant: string;
  name: string;
  integration_id: string | null;
  url: string;
  events: string[];
  credential_id: string | null;
  status: string;
}

export interface WebhookDelivery {
  id: string;
  tenant: string;
  webhook_id: string;
  delivery_id: string;
  event_type: string;
  status: string;
  attempts: number;
  next_retry_at: string | null;
  response_code: number | null;
  response_bytes: number | null;
  error: string;
}

export interface InboundEvent {
  id: string;
  tenant: string;
  webhook_id: string;
  delivery_id: string;
  event_type: string;
  status: string;
  approval_id: string;
  deduplicated?: boolean;
}

export interface IntegrationPolicy {
  id: string;
  tenant: string;
  name: string;
  workspace: string;
  project: string;
  provider: string;
  operation: string;
  action: string;
  allowed_classifications: string[];
  allowed_regions: string[];
  allowed_fields: string[];
  max_estimated_cents: number | null;
  enabled: boolean;
  owner: string;
}

export interface TransferEvaluation {
  decision: string;
  reasons: string[];
  allowed: boolean;
  evaluation: {
    classification: string;
    region: string;
    fields: string[];
    estimated_cents: number;
  };
}

export interface HealthSummary {
  integration_id: string;
  tenant: string;
  current_health: string;
  current_status: string;
  window_days: number;
  checks: number;
  last_check: string | null;
  avg_latency_ms: number | null;
  executions: number;
  error_rate: number;
  authentication_failures: number;
  rate_limit_hits: number;
}

export interface ExecutionResult {
  id: string;
  tenant: string;
  connection_id: string;
  operation: string;
  method: string;
  endpoint_ref: string;
  status: string;
  attempts: number;
  latency_ms: number | null;
  request_bytes: number | null;
  response_bytes: number | null;
  idempotency_key: string;
  error: string;
}

export const INTEGRATION_TYPES: IntegrationType[] = ["webhook", "api", "oauth", "connector"];

export const INTEGRATION_STATUSES: IntegrationStatus[] = [
  "ACTIVE",
  "DISABLED",
  "DEGRADED",
  "QUARANTINED",
  "REVOKED",
];

export const POLICY_ACTIONS: PolicyAction[] = ["alert", "warn", "require_approval", "block"];

/** Capabilities enforced per integration type by the backend registry. */
export const CAPABILITIES_BY_TYPE: Record<IntegrationType, string[]> = {
  webhook: ["receive", "deliver", "sign", "verify"],
  api: ["execute", "sync", "health"],
  oauth: ["authorize", "refresh", "revoke"],
  connector: ["execute", "sync", "health", "discover"],
};
