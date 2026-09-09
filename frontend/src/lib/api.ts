"use client";

import { apiRequest } from "@/lib/api-client";
import type {
  ApiKeyCreated,
  ApiKeyOut,
  ApiUser,
  AuthTokens,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  CostsPage,
  FinOpsSummary,
  LoginResponse,
  MfaSetup,
  MfaStatus,
  SessionOut,
  WhoAmI,
} from "@/types/api";
import type { CatalogSearchResponse } from "@/types/universal";
import type { Organization, OrganizationMember, InviteResult, Workspace, Role } from "@/types/org";
import type {
  KnowledgeAuditHistoryResponse,
  KnowledgeDocument,
  KnowledgeEntitiesResponse,
  KnowledgeEntityDetail,
  KnowledgeFreshnessStats,
  KnowledgeIngestionJobDetail,
  KnowledgeIngestionJobsResponse,
  KnowledgeSearchResponse,
  KnowledgeSource,
  KnowledgeSourcesResponse,
  KnowledgeUsageStats,
} from "@/types/knowledge";
import type {
  AiopsStatus,
  AlertFatigueReport,
  AlertMutationResult,
  IncidentTransitionBody,
  ObservabilityAlertsResponse,
  ObservabilityQuality,
  SreAnalytics,
  SreIncident,
  SreIncidentTimeline,
  SreIncidentsResponse,
  SreService,
  SreServiceDependencies,
  SreServicesResponse,
  SreStatusComponentsResponse,
  SreStatusSummary,
} from "@/types/observability";
import type {
  AccessApproveResult,
  AccessRequestsResponse,
  AlertStatusResult,
  PrivilegedAccessResponse,
  SecOpsAlertsResponse,
  SecOpsCoverage,
  SecOpsDashboard,
  SecOpsEventsResponse,
  SecOpsFindingsResponse,
  SecOpsPosture,
  SecOpsResponsesResponse,
  SecOpsRiskSnapshot,
  SecOpsSlo,
  ZeroTrustPosture,
} from "@/types/security";

export type { AuthTokens, CostsPage, FinOpsSummary, KnowledgeHit, KnowledgePage, ApiUser, CostRecord, MfaSetup, MfaStatus, SessionOut, ApiKeyOut, ApiKeyCreated, WhoAmI, LoginResponse } from "@/types/api";
export type { ChatMessage, ChatResponse, ChatSource, ConversationSummary, ConversationDetail, StreamEvent, AiModel } from "@/types/api";
export type {
  RepositoryOut,
  CodeIndexOut,
  IndexVersionOut,
  IndexDiffOut,
  IndexHealthOut,
  CodeFileOut,
  FileContentOut,
  CodeMetricsOut,
  SymbolOut,
  SymbolDetailOut,
  SymbolSearchOut,
  GraphOut,
  GraphNodeOut,
  GraphEdgeOut,
  ModuleInfo,
  CyclesOut,
  CodeSmellOut,
  SmellScanOut,
  QualitySummary,
  SecurityVulnerabilityOut,
  SecurityScanOut,
  SecretOut,
  SecretScanOut,
  ImpactAnalysisOut,
  DownstreamOut,
  DependencyOut,
  SearchResultItem,
  SearchOut,
  RAGContextOut,
  TestCoverageOut,
  TestQualityOut,
  TestGapOut,
  OwnershipSummaryOut,
  ContributorStatsOut,
  BusRiskOut,
  OwnerOut,
  HotspotOut,
  ChurnMetricsOut,
  AuthorActivityOut,
  ChangeSummaryOut,
  RepositoryProfileOut,
  LanguageOut,
  ArchitectureOverviewOut,
  DependencyGraphOut,
  DevCapabilities,
  AiDevContextItem,
  AiDevContextOut,
  ExplainIn,
  ExplainOut,
  ReviewFinding,
  AiReviewOut,
  AiReviewDetail,
  PatchFileEdit,
  PatchOut,
  PatchListOut,
  ChangeSummaryIn,
  ChangeSummaryOut2,
  AgentOut,
  AgentListOut,
  AgentPlanOut,
  AgentPlanListOut,
  AgentCheckpointOut,
  AgentCheckpointListOut,
  SecurityBlock,
  SecurityGateOut,
} from "@/types/code";
export { ApiError, type ApiErrorKind } from "@/lib/api-client";
export { streamChatResponse, type StreamChatEvent } from "@/lib/api-client";
export { isMfaChallenge } from "@/types/api";
export type {
  KnowledgeCitation,
  KnowledgeSearchItem,
  KnowledgeSearchResponse,
  KnowledgeSource,
  KnowledgeSourcesResponse,
  KnowledgeSourceCreated,
  KnowledgeDocument,
  KnowledgeDocumentCreated,
  KnowledgeIngestionJob,
  KnowledgeIngestionJobsResponse,
  KnowledgeIngestionJobDetail,
  KnowledgeIngestionJobCreated,
  KnowledgeEntity,
  KnowledgeEntityDetail,
  KnowledgeEntityLink,
  KnowledgeEntitiesResponse,
  KnowledgeEntityCreated,
  KnowledgeLinkCreated,
  KnowledgeFreshnessStats,
  KnowledgeUsageStats,
  KnowledgeAuditEntry,
  KnowledgeAuditHistoryResponse,
  KnowledgeSearchFilterState,
} from "@/types/knowledge";

const TOKEN_KEY = "nf_token";
const REFRESH_KEY = "nf_refresh";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setRefreshToken(token: string): void {
  if (token) localStorage.setItem(REFRESH_KEY, token);
}

export function clearRefreshToken(): void {
  localStorage.removeItem(REFRESH_KEY);
}

export function clearAllTokens(): void {
  clearToken();
  clearRefreshToken();
}

export const api = {
  register: (email: string, username: string, password: string) =>
    apiRequest<AuthTokens>("/auth/register", {
      method: "POST",
      body: { email, username, password },
    }),

  login: (email: string, password: string) =>
    apiRequest<LoginResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  mfaChallenge: (challenge_token: string, code: string) =>
    apiRequest<AuthTokens>("/auth/mfa/challenge", {
      method: "POST",
      body: { challenge_token, code },
    }),

  refresh: (refresh_token: string) =>
    apiRequest<AuthTokens>("/auth/refresh", {
      method: "POST",
      body: { refresh_token },
    }),

  me: (token: string) => apiRequest<ApiUser>("/auth/me", { token }),

  whoami: (token: string) => apiRequest<WhoAmI>("/auth/whoami", { token }),

  // Password recovery
  requestPasswordReset: (email: string) =>
    apiRequest<{ status: string }>("/auth/password/reset", {
      method: "POST",
      body: { email },
    }),

  confirmPasswordReset: (token: string, new_password: string) =>
    apiRequest<{ status: string }>("/auth/password/reset/confirm", {
      method: "POST",
      body: { token, new_password },
    }),

  changePassword: (token: string, current_password: string, new_password: string) =>
    apiRequest<{ status: string }>("/auth/password/change", {
      method: "POST",
      token,
      body: { current_password, new_password },
    }),

  // Email verification
  verifyEmail: (token: string) =>
    apiRequest<{ status: string }>(`/auth/email/verify?token=${encodeURIComponent(token)}`, {
      method: "POST",
    }),

  resendVerification: (token: string) =>
    apiRequest<{ status: string }>("/auth/email/resend-verification", {
      method: "POST",
      token,
    }),

  // MFA
  setupMfa: (token: string) => apiRequest<MfaSetup>("/auth/mfa/setup", { token }),

  verifyMfa: (token: string, code: string) =>
    apiRequest<MfaStatus>("/auth/mfa/verify", {
      method: "POST",
      token,
      body: { code },
    }),

  disableMfa: (token: string, code: string) =>
    apiRequest<MfaStatus>("/auth/mfa/disable", {
      method: "POST",
      token,
      body: { code },
    }),

  verifyBackupCode: (token: string, code: string) =>
    apiRequest<{ status: string; remaining: number }>(
      `/auth/mfa/verify-backup?code=${encodeURIComponent(code)}`,
      { method: "POST", token },
    ),

  // Sessions
  listSessions: (token: string) =>
    apiRequest<SessionOut[]>("/auth/sessions", { token }),

  revokeSession: (token: string, sessionId: string) =>
    apiRequest<void>(`/auth/sessions/${sessionId}`, { method: "DELETE", token }),

  revokeAllOtherSessions: (token: string) =>
    apiRequest<void>("/auth/sessions", { method: "DELETE", token }),

  // API Keys
  listApiKeys: (token: string) =>
    apiRequest<ApiKeyOut[]>("/auth/api-keys", { token }),

  createApiKey: (token: string, name: string, scopes: string[] = []) =>
    apiRequest<ApiKeyCreated>("/auth/api-keys", {
      method: "POST",
      token,
      body: { name, scopes },
    }),

  deleteApiKey: (token: string, keyId: string) =>
    apiRequest<void>(`/auth/api-keys/${keyId}`, { method: "DELETE", token }),

  // Existing domain APIs
  finopsSummary: (token: string, start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const suffix = params.size > 0 ? `?${params.toString()}` : "";
    return apiRequest<FinOpsSummary>(`/finops/usage/summary${suffix}`, { token });
  },

  finopsCosts: (token: string, limit = 10) =>
    apiRequest<CostsPage>(`/finops/costs?limit=${limit}`, { token }),

  knowledgeSearch: (token: string, query: string, opts?: {
    source_type?: string;
    doc_type?: string;
    classification?: string;
    limit?: number;
    offset?: number;
    signal?: AbortSignal;
  }) => {
    const params = new URLSearchParams({ query });
    if (opts?.source_type) params.set("source_type", opts.source_type);
    if (opts?.doc_type) params.set("doc_type", opts.doc_type);
    if (opts?.classification) params.set("classification", opts.classification);
    params.set("limit", String(opts?.limit ?? 20));
    params.set("offset", String(opts?.offset ?? 0));
    return apiRequest<KnowledgeSearchResponse>(`/knowledge/search?${params.toString()}`, {
      token,
      signal: opts?.signal,
    });
  },

  // ─── Knowledge: sources ─────────────────────────────────────────────────
  knowledgeListSources: (token: string, opts?: { status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    params.set("limit", String(opts?.limit ?? 100));
    return apiRequest<KnowledgeSourcesResponse>(`/knowledge/sources?${params.toString()}`, { token });
  },
  knowledgeGetSource: (token: string, sourceId: string) =>
    apiRequest<KnowledgeSource>(`/knowledge/sources/${sourceId}`, { token }),

  // ─── Knowledge: documents ───────────────────────────────────────────────
  knowledgeGetDocument: (token: string, documentId: string) =>
    apiRequest<KnowledgeDocument>(`/knowledge/documents/${documentId}`, { token }),

  // ─── Knowledge: ingestion ───────────────────────────────────────────────
  knowledgeListIngestionJobs: (token: string, opts?: { source_id?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.source_id) params.set("source_id", opts.source_id);
    params.set("limit", String(opts?.limit ?? 100));
    return apiRequest<KnowledgeIngestionJobsResponse>(`/knowledge/ingestion/jobs?${params.toString()}`, { token });
  },
  knowledgeGetIngestionJob: (token: string, jobId: string) =>
    apiRequest<KnowledgeIngestionJobDetail>(`/knowledge/ingestion/jobs/${jobId}`, { token }),

  // ─── Knowledge: entities ────────────────────────────────────────────────
  knowledgeListEntities: (token: string, opts?: { entity_type?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.entity_type) params.set("entity_type", opts.entity_type);
    params.set("limit", String(opts?.limit ?? 100));
    return apiRequest<KnowledgeEntitiesResponse>(`/knowledge/entities?${params.toString()}`, { token });
  },
  knowledgeGetEntity: (token: string, entityId: string) =>
    apiRequest<KnowledgeEntityDetail>(`/knowledge/entities/${entityId}`, { token }),

  // ─── Knowledge: freshness / audit ───────────────────────────────────────
  knowledgeFreshnessStats: (token: string) =>
    apiRequest<KnowledgeFreshnessStats>("/knowledge/freshness/stats", { token }),
  knowledgeUsageStats: (token: string, opts?: { since_hours?: number }) => {
    const params = new URLSearchParams();
    if (opts?.since_hours) params.set("since_hours", String(opts.since_hours));
    return apiRequest<KnowledgeUsageStats>(`/knowledge/audit/usage?${params.toString()}`, { token });
  },

  // Dashboard — real backend signals
  healthDependencies: () =>
    apiRequest<import("@/types/api").HealthDependencies>("/health/dependencies", { retryGet: false }),
  healthReady: () =>
    apiRequest<{ status: string; checks: Record<string, boolean> }>("/health/ready"),
  workflowHealth: (token: string) =>
    apiRequest<import("@/types/api").WorkflowHealth>("/workflows/health", { token }),
  listWorkflowRuns: (token: string, limit = 5) =>
    apiRequest<{ items: import("@/types/api").WorkflowRun[] }>("/workflows/runs?limit=" + limit, { token }),
  // Fallback: list workflows then runs per workflow if needed
  aiUsage: (token: string, limit = 10) =>
    apiRequest<import("@/types/api").AiUsagePage>(`/ai-dev/usage?limit=${limit}`, { token }),
  securityDashboard: (token: string) =>
    apiRequest<import("@/types/api").SecurityDashboard>("/security/dashboard", { token }),
  secOpsDashboard: (token: string) =>
    apiRequest<SecOpsDashboard>("/secops/dashboard", { token }),
  governancePosture: (token: string) =>
    apiRequest<import("@/types/api").GovernancePosture>("/governance/posture", { token }),
  governanceDecisions: (token: string, limit = 5) =>
    apiRequest<{ items: unknown[]; total: number }>(`/governance/decisions?limit=${limit}`, { token }),
  integrationsList: (token: string) =>
    apiRequest<{ items: import("@/types/api").IntegrationItem[]; total: number }>("/integrations", { token }),
  observabilityDashboard: (token: string) =>
    apiRequest<import("@/types/api").ObservabilityDashboard>("/observability/dashboard", { token }),

  // ─── Observability & SRE (Operations) ───────────────────────────────────
  observabilityAlerts: (token: string, opts?: { status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    params.set("limit", String(opts?.limit ?? 100));
    return apiRequest<ObservabilityAlertsResponse>(`/observability/alerts?${params.toString()}`, { token });
  },
  observabilityQuality: (token: string, opts?: { service?: string }) => {
    const params = new URLSearchParams();
    if (opts?.service) params.set("service", opts.service);
    const qs = params.toString();
    return apiRequest<ObservabilityQuality>(
      `/observability/observability-quality${qs ? `?${qs}` : ""}`,
      { token },
    );
  },
  observabilityAiopsStatus: (token: string) =>
    apiRequest<AiopsStatus>("/observability/aiops/status", { token }),
  observabilityAlertFatigue: (token: string) =>
    apiRequest<AlertFatigueReport>("/observability/alerts/fatigue/report", { token }),
  sreStatusSummary: (token: string) =>
    apiRequest<SreStatusSummary>("/sre/status/summary", { token }),
  sreStatusComponents: (token: string, opts?: { limit?: number }) =>
    apiRequest<SreStatusComponentsResponse>(`/sre/status/components?limit=${opts?.limit ?? 100}`, { token }),
  sreAnalytics: (token: string, days = 30) =>
    apiRequest<SreAnalytics>(`/sre/analytics?days=${days}`, { token }),
  sreListIncidents: (token: string, opts?: { status?: string; offset?: number; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    params.set("offset", String(opts?.offset ?? 0));
    params.set("limit", String(opts?.limit ?? 50));
    return apiRequest<SreIncidentsResponse>(`/sre/incidents?${params.toString()}`, { token });
  },
  sreGetIncident: (token: string, incidentId: string) =>
    apiRequest<SreIncident>(`/sre/incidents/${encodeURIComponent(incidentId)}`, { token }),
  sreIncidentTimeline: (token: string, incidentId: string) =>
    apiRequest<SreIncidentTimeline>(`/sre/incidents/${encodeURIComponent(incidentId)}/timeline`, { token }),
  sreListServices: (token: string, opts?: { limit?: number }) =>
    apiRequest<SreServicesResponse>(`/sre/services?limit=${opts?.limit ?? 100}`, { token }),
  sreGetService: (token: string, serviceId: string) =>
    apiRequest<SreService>(`/sre/services/${encodeURIComponent(serviceId)}`, { token }),
  sreServiceDependencies: (token: string, serviceId: string) =>
    apiRequest<SreServiceDependencies>(`/sre/services/${encodeURIComponent(serviceId)}/dependencies`, { token }),
  acknowledgeAlert: (token: string, alertId: string) =>
    apiRequest<AlertMutationResult>(`/observability/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
      method: "POST",
      token,
      body: {},
    }),
  resolveAlert: (token: string, alertId: string) =>
    apiRequest<AlertMutationResult>(`/observability/alerts/${encodeURIComponent(alertId)}/resolve`, {
      method: "POST",
      token,
      body: {},
    }),
  incidentTransition: (token: string, incidentId: string, body: IncidentTransitionBody) =>
    apiRequest<SreIncident>(`/sre/incidents/${encodeURIComponent(incidentId)}/transition`, {
      method: "POST",
      token,
      body: { target: body.target, note: body.note ?? "" },
    }),

  // ─── Security Operations (secops) ─────────────────────────────────────
  secOpsPosture: (token: string) =>
    apiRequest<SecOpsPosture>("/secops/posture", { token }),
  secOpsCoverage: (token: string) =>
    apiRequest<SecOpsCoverage>("/secops/coverage", { token }),
  secOpsSlo: (token: string) =>
    apiRequest<SecOpsSlo>("/secops/slo", { token }),
  secOpsRisk: (token: string) =>
    apiRequest<SecOpsRiskSnapshot>("/secops/risk", { token }),
  secOpsEvents: (token: string, opts?: { category?: string; severity?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.category) params.set("category", opts.category);
    if (opts?.severity) params.set("severity", opts.severity);
    params.set("limit", String(opts?.limit ?? 50));
    return apiRequest<SecOpsEventsResponse>(`/secops/security-events?${params.toString()}`, { token });
  },
  secOpsAlerts: (token: string, opts?: { status?: string; severity?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.severity) params.set("severity", opts.severity);
    params.set("limit", String(opts?.limit ?? 50));
    return apiRequest<SecOpsAlertsResponse>(`/secops/security-alerts?${params.toString()}`, { token });
  },
  secOpsFindings: (token: string, opts?: { status?: string; severity?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.severity) params.set("severity", opts.severity);
    params.set("limit", String(opts?.limit ?? 50));
    return apiRequest<SecOpsFindingsResponse>(`/secops/findings?${params.toString()}`, { token });
  },
  secOpsResponses: (token: string, opts?: { limit?: number }) => {
    const params = new URLSearchParams();
    params.set("limit", String(opts?.limit ?? 20));
    return apiRequest<SecOpsResponsesResponse>(`/secops/responses?${params.toString()}`, { token });
  },
  secOpsUpdateAlertStatus: (token: string, alertId: string, status: string, reason?: string) =>
    apiRequest<AlertStatusResult>(`/secops/security-alerts/${encodeURIComponent(alertId)}/status`, {
      method: "POST",
      token,
      body: { status, reason },
    }),
  secOpsUpdateFindingStatus: (token: string, findingId: string, status: string) =>
    apiRequest<AlertStatusResult>(`/secops/findings/${encodeURIComponent(findingId)}/status`, {
      method: "POST",
      token,
      body: { status },
    }),
  secOpsApproveResponse: (token: string, responseId: string) =>
    apiRequest<Record<string, unknown>>(`/secops/responses/${encodeURIComponent(responseId)}/approve`, {
      method: "POST",
      token,
      body: {},
    }),
  secOpsExecuteResponse: (token: string, responseId: string) =>
    apiRequest<Record<string, unknown>>(`/secops/responses/${encodeURIComponent(responseId)}/execute`, {
      method: "POST",
      token,
      body: {},
    }),
  secOpsVerifyResponse: (token: string, responseId: string) =>
    apiRequest<Record<string, unknown>>(`/secops/responses/${encodeURIComponent(responseId)}/verify`, {
      method: "POST",
      token,
      body: {},
    }),

  // ─── Zero Trust (zero-trust) ──────────────────────────────────────────
  zeroTrustPosture: (token: string) =>
    apiRequest<ZeroTrustPosture>("/zero-trust/posture", { token }),
  zeroTrustPrivilegedAccess: (token: string, opts?: { limit?: number }) => {
    const params = new URLSearchParams();
    params.set("limit", String(opts?.limit ?? 20));
    return apiRequest<PrivilegedAccessResponse>(`/zero-trust/privileged-access?${params.toString()}`, { token });
  },
  zeroTrustAccessRequests: (token: string, opts?: { status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    params.set("limit", String(opts?.limit ?? 20));
    return apiRequest<AccessRequestsResponse>(`/zero-trust/access-requests?${params.toString()}`, { token });
  },
  zeroTrustApproveAccessRequest: (token: string, requestId: string, bindingHash?: string) =>
    apiRequest<AccessApproveResult>(
      `/zero-trust/access-requests/${encodeURIComponent(requestId)}/approve`,
      {
        method: "POST",
        token,
        body: bindingHash ? { binding_hash: bindingHash } : {},
      },
    ),

  recentActivity: (
    token: string,
    limit = 20,
    filters?: { eventType?: string; source?: string; startTime?: string; endTime?: string },
  ) => {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    if (filters?.eventType) params.set("event_type", filters.eventType);
    if (filters?.source) params.set("source", filters.source);
    if (filters?.startTime) params.set("start_time", filters.startTime);
    if (filters?.endTime) params.set("end_time", filters.endTime);
    return apiRequest<{ events: import("@/types/api").RecentActivityItem[]; count: number }>(
      `/analytics/events?${params.toString()}`,
      { token },
    );
  },
  knowledgeHistory: (token: string, limit = 5) =>
    apiRequest<KnowledgeAuditHistoryResponse>(`/knowledge/audit/history?limit=${limit}`, { token }),

  dataCatalogSearch: (token: string, query: string, opts?: { limit?: number }) => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return apiRequest<CatalogSearchResponse>(
      `/data-platform/catalog/search${qs ? `?${qs}` : ""}`,
      { token },
    );
  },

  // Organizations
  listOrganizations: (token: string) =>
    apiRequest<Organization[]>("/organizations", { token }),
  listMyOrganizations: (token: string) =>
    apiRequest<Organization[]>("/organizations/my", { token }),
  getOrganization: (token: string, id: string) =>
    apiRequest<Organization>(`/organizations/${id}`, { token }),
  createOrganization: (token: string, name: string, slug: string, description?: string) =>
    apiRequest<Organization>("/organizations", {
      method: "POST",
      token,
      body: { name, slug, description },
    }),
  updateOrganization: (token: string, id: string, name?: string, description?: string) => {
    const params = new URLSearchParams();
    if (name) params.set("name", name);
    if (description !== undefined) params.set("description", description || "");
    const qs = params.toString() ? `?${params.toString()}` : "";
    return apiRequest<Organization>(`/organizations/${id}${qs}`, { method: "PATCH", token });
  },
  deleteOrganization: (token: string, id: string) =>
    apiRequest<void>(`/organizations/${id}`, { method: "DELETE", token }),

  // Members & invitations
  listMembers: (token: string, orgId: string) =>
    apiRequest<OrganizationMember[]>(`/organizations/${orgId}/members`, { token }),
  inviteMember: (token: string, orgId: string, email: string, role: string = "member") =>
    apiRequest<InviteResult>(`/organizations/${orgId}/members`, {
      method: "POST",
      token,
      body: { email, role },
    }),
  removeMember: (token: string, orgId: string, userId: string) =>
    apiRequest<void>(`/organizations/${orgId}/members/${userId}`, { method: "DELETE", token }),
  updateMemberRole: (token: string, orgId: string, userId: string, role: string) =>
    apiRequest<{ status: string }>(`/organizations/${orgId}/members/${userId}/role?role=${encodeURIComponent(role)}`, {
      method: "PUT",
      token,
    }),

  // Workspaces (IAM)
  listWorkspaces: (token: string, orgId: string) =>
    apiRequest<Workspace[]>(`/iam/workspaces?org_id=${encodeURIComponent(orgId)}`, { token }),
  createWorkspace: (token: string, orgId: string, name: string, slug: string) =>
    apiRequest<Workspace>("/iam/workspaces", {
      method: "POST",
      token,
      body: { org_id: orgId, name, slug },
    }),
  getWorkspace: (token: string, id: string) =>
    apiRequest<Workspace>(`/iam/workspaces/${id}`, { token }),
  deleteWorkspace: (token: string, id: string) =>
    apiRequest<{ deleted: boolean }>(`/iam/workspaces/${id}`, { method: "DELETE", token }),

  // Roles & permissions
  listRoles: (token: string, orgId: string) =>
    apiRequest<Role[]>(`/iam/roles?org_id=${encodeURIComponent(orgId)}`, { token }),
  authorize: (token: string, orgId: string, permission: string) =>
    apiRequest<{ allowed: boolean; decision: string }>(`/iam/authorization/authorize`, {
      method: "POST",
      token,
      body: { org_id: orgId, permission },
    }),

  // Chat & Conversations
  chat: (token: string, body: { message: string; conversation_id?: string; repo_id?: string }) =>
    apiRequest<ChatResponse>("/chat", {
      method: "POST",
      body,
    }),

  listConversations: (token: string, limit = 20, offset = 0) =>
    apiRequest<ConversationSummary[]>(`/chat/conversations?limit=${limit}&offset=${offset}`),

  getConversation: (token: string, conversationId: string) =>
    apiRequest<ConversationDetail>(`/chat/conversations/${conversationId}`),

  deleteConversation: (token: string, conversationId: string) =>
    apiRequest<void>(`/chat/conversations/${conversationId}`, { method: "DELETE" }),

  // ─── Repositories ────────────────────────────────────────────────────────
  listRepositories: (token: string, limit = 50, offset = 0, language?: string) => {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    if (language) params.set("language", language);
    return apiRequest<import("@/types/code").RepositoryOut[]>(`/repositories?${params.toString()}`, { token });
  },
  getRepository: (token: string, repositoryId: string) =>
    apiRequest<import("@/types/code").RepositoryOut>(`/repositories/${repositoryId}`, { token }),

  // ─── Code Intelligence: Index ────────────────────────────────────────────
  ciGetIndex: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").CodeIndexOut>(`/code-intelligence/${repoId}/index`, { token }),
  ciCreateIndex: (token: string, repoId: string, branch = "main", forceRebuild = false) =>
    apiRequest<import("@/types/code").CodeIndexOut>(`/code-intelligence/${repoId}/index`, {
      method: "POST",
      token,
      body: { branch, force_rebuild: forceRebuild },
    }),
  ciIndexHealth: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").IndexHealthOut>(`/code-intelligence/${repoId}/index/health`, { token }),
  ciIndexVersions: (token: string, repoId: string, limit = 20, offset = 0) =>
    apiRequest<import("@/types/code").IndexVersionOut[]>(
      `/code-intelligence/${repoId}/index/versions?limit=${limit}&offset=${offset}`,
      { token },
    ),
  ciRebuildIndex: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").CodeIndexOut>(`/code-intelligence/${repoId}/index/rebuild`, {
      method: "POST",
      token,
    }),

  // ─── Code Intelligence: Files ────────────────────────────────────────────
  ciFiles: (token: string, repoId: string, opts?: { language?: string; pathPrefix?: string; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (opts?.language) params.set("language", opts.language);
    if (opts?.pathPrefix) params.set("path_prefix", opts.pathPrefix);
    params.set("limit", String(opts?.limit ?? 50));
    params.set("offset", String(opts?.offset ?? 0));
    return apiRequest<import("@/types/code").CodeFileOut[]>(
      `/code-intelligence/${repoId}/files?${params.toString()}`,
      { token },
    );
  },
  ciFileDetail: (token: string, repoId: string, fileId: string) =>
    apiRequest<import("@/types/code").FileContentOut>(
      `/code-intelligence/${repoId}/files/${fileId}?include_symbols=true&include_references=true`,
      { token },
    ),
  ciFileMetrics: (token: string, repoId: string, fileId: string) =>
    apiRequest<import("@/types/code").CodeMetricsOut>(`/code-intelligence/${repoId}/files/${fileId}/metrics`, { token }),

  // ─── Code Intelligence: Symbols ──────────────────────────────────────────
  ciSymbols: (token: string, repoId: string, opts?: { symbolType?: string; fileId?: string; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (opts?.symbolType) params.set("symbol_type", opts.symbolType);
    if (opts?.fileId) params.set("file_id", opts.fileId);
    params.set("limit", String(opts?.limit ?? 50));
    params.set("offset", String(opts?.offset ?? 0));
    return apiRequest<import("@/types/code").SymbolOut[]>(
      `/code-intelligence/${repoId}/symbols?${params.toString()}`,
      { token },
    );
  },
  ciSymbolDetail: (token: string, repoId: string, symbolId: string) =>
    apiRequest<import("@/types/code").SymbolDetailOut>(`/code-intelligence/${repoId}/symbols/${symbolId}`, { token }),
  ciSymbolSearch: (token: string, repoId: string, name: string, symbolTypes?: string[]) =>
    apiRequest<import("@/types/code").SymbolSearchOut>(`/code-intelligence/${repoId}/search/symbols`, {
      method: "POST",
      token,
      body: { name, symbol_types: symbolTypes ?? [], fuzzy: true },
    }),

  // ─── Code Intelligence: Search ───────────────────────────────────────────
  ciSearch: (token: string, repoId: string, query: string, opts?: { fileTypes?: string[]; symbolTypes?: string[]; maxResults?: number }) =>
    apiRequest<import("@/types/code").SearchOut>(`/code-intelligence/${repoId}/search`, {
      method: "POST",
      token,
      body: {
        query,
        file_types: opts?.fileTypes ?? [],
        symbol_types: opts?.symbolTypes ?? [],
        max_results: opts?.maxResults ?? 20,
        include_context: true,
      },
    }),

  // ─── Code Intelligence: Graph ────────────────────────────────────────────
  ciGraph: (token: string, repoId: string, limit = 200) =>
    apiRequest<import("@/types/code").GraphOut>(`/code-intelligence/${repoId}/graph?limit=${limit}`, { token }),
  ciGraphTraverse: (token: string, repoId: string, symbolId: string, direction = "both", maxDepth = 3) =>
    apiRequest<import("@/types/code").GraphOut>(`/code-intelligence/${repoId}/graph/traverse`, {
      method: "POST",
      token,
      body: { symbol_id: symbolId, direction, max_depth: maxDepth, edge_types: [] },
    }),
  ciGraphModules: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").ModuleInfo[]>(`/code-intelligence/${repoId}/graph/modules`, { token }),
  ciGraphCycles: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").CyclesOut>(`/code-intelligence/${repoId}/graph/cycles`, { token }),

  // ─── Code Intelligence: Impact / Quality / Security ──────────────────────
  ciImpactAnalyze: (token: string, repoId: string, body: { symbol_id?: string; file_path?: string; change_type?: string }) =>
    apiRequest<import("@/types/code").ImpactAnalysisOut>(`/code-intelligence/${repoId}/impact/analyze`, {
      method: "POST",
      token,
      body: { symbol_id: body.symbol_id, file_path: body.file_path, change_type: body.change_type ?? "modify" },
    }),
  ciDownstream: (token: string, repoId: string, symbolId: string, maxDepth = 5) =>
    apiRequest<import("@/types/code").DownstreamOut>(`/code-intelligence/${repoId}/impact/downstream`, {
      method: "POST",
      token,
      body: { symbol_id: symbolId, max_depth: maxDepth },
    }),
  ciUnused: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").UnusedItemOut[]>(`/code-intelligence/${repoId}/impact/unused`, {
      method: "POST",
      token,
    }),
  ciSmellsScan: (token: string, repoId: string, body?: { file_paths?: string[]; smell_types?: string[] }) =>
    apiRequest<import("@/types/code").SmellScanOut>(`/code-intelligence/${repoId}/quality/smells`, {
      method: "POST",
      token,
      body: { file_paths: body?.file_paths ?? [], smell_types: body?.smell_types ?? [] },
    }),
  ciQualitySummary: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").QualitySummary>(`/code-intelligence/${repoId}/quality/summary`, { token }),
  ciSecurityScan: (token: string, repoId: string, body?: { file_paths?: string[]; vulnerability_types?: string[] }) =>
    apiRequest<import("@/types/code").SecurityScanOut>(`/code-intelligence/${repoId}/security/scan`, {
      method: "POST",
      token,
      body: { file_paths: body?.file_paths ?? [], vulnerability_types: body?.vulnerability_types ?? [] },
    }),
  ciSecretsScan: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").SecretScanOut>(`/code-intelligence/${repoId}/security/secrets`, {
      method: "POST",
      token,
    }),

  // ─── Code Intelligence: Tests ────────────────────────────────────────────
  ciTests: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").TestCoverageOut>(`/code-intelligence/${repoId}/tests`, { token }),
  ciTestQuality: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").TestQualityOut[]>(`/code-intelligence/${repoId}/tests/quality`, { token }),
  ciTestGaps: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").TestGapOut[]>(`/code-intelligence/${repoId}/tests/gaps`, { token }),

  // ─── Code Intelligence: Ownership / History / Summary ────────────────────
  ciOwnership: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").OwnershipSummaryOut>(`/code-intelligence/${repoId}/ownership`, { token }),
  ciContributors: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").ContributorStatsOut[]>(`/code-intelligence/${repoId}/ownership/contributors`, { token }),
  ciBusRisk: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").BusRiskOut[]>(`/code-intelligence/${repoId}/ownership/bus-risk`, { token }),
  ciHotspots: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").HotspotOut[]>(`/code-intelligence/${repoId}/history/hotspots?top_n=20`, { token }),
  ciChurn: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").ChurnMetricsOut>(`/code-intelligence/${repoId}/history/churn`, { token }),
  ciAuthors: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").AuthorActivityOut[]>(`/code-intelligence/${repoId}/history/authors`, { token }),
  ciChangeSummary: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").ChangeSummaryOut>(`/code-intelligence/${repoId}/history/summary`, { token }),
  ciRepoSummary: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").RepositoryProfileOut>(`/code-intelligence/${repoId}/summary`, { token }),
  ciLanguages: (token: string, repoId: string) =>
    apiRequest<import("@/types/code").LanguageOut[]>(`/code-intelligence/${repoId}/summary/languages`, { token }),
  ciRagContext: (token: string, repoId: string, query: string, opts?: { maxTokens?: number }) =>
    apiRequest<import("@/types/code").RAGContextOut>(`/code-intelligence/${repoId}/rag/context`, {
      method: "POST",
      token,
      body: { query, max_tokens: opts?.maxTokens ?? 4096, include_graph: true },
    }),

  // ─── DevTools capabilities (C2 gate) ─────────────────────────────────────
  devCapabilities: (token: string, clientType = "browser") =>
    apiRequest<import("@/types/code").DevCapabilities>(`/devtools/capabilities?client_type=${clientType}`, { token }),

  // ─── AI Developer (C2) ───────────────────────────────────────────────────
  aiDevContext: (token: string, repoId: string, query: string, tokenBudget = 4000) =>
    apiRequest<import("@/types/code").AiDevContextOut>(
      `/ai-dev/repositories/${repoId}/context?q=${encodeURIComponent(query)}&token_budget=${tokenBudget}`,
      { token },
    ),
  aiDevExplain: (token: string, body: import("@/types/code").ExplainIn) =>
    apiRequest<import("@/types/code").ExplainOut>("/ai-dev/explain", { method: "POST", token, body }),
  aiDevReviewCreate: (token: string, body: { repository_id: string; files: Array<{ path: string; content: string }>; branch?: string | null; commit_sha?: string | null; rules_version?: string }) =>
    apiRequest<import("@/types/code").AiReviewOut>("/ai-dev/review", { method: "POST", token, body }),
  aiDevGetReview: (token: string, reviewId: string) =>
    apiRequest<import("@/types/code").AiReviewDetail>(`/ai-dev/reviews/${reviewId}`, { token }),
  aiDevListPatches: (token: string, repositoryId?: string, status?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (repositoryId) params.set("repository_id", repositoryId);
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    return apiRequest<import("@/types/code").PatchListOut>(`/ai-dev/patches?${params.toString()}`, { token });
  },
  aiDevGetPatch: (token: string, patchId: string) =>
    apiRequest<import("@/types/code").PatchOut>(`/ai-dev/patches/${patchId}`, { token }),
  aiDevChangesSummary: (token: string, body: import("@/types/code").ChangeSummaryIn) =>
    apiRequest<import("@/types/code").ChangeSummaryOut2>("/ai-dev/changes/summary", { method: "POST", token, body }),
  aiDevListAgents: (token: string, opts?: { repositoryId?: string; status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.repositoryId) params.set("repository_id", opts.repositoryId);
    if (opts?.status) params.set("status", opts.status);
    params.set("limit", String(opts?.limit ?? 50));
    return apiRequest<import("@/types/code").AgentListOut>(`/ai-dev/agents?${params.toString()}`, { token });
  },
  aiDevGetAgent: (token: string, runId: string) =>
    apiRequest<import("@/types/code").AgentOut>(`/ai-dev/agents/${runId}`, { token }),
  aiDevAgentPlans: (token: string, runId: string) =>
    apiRequest<import("@/types/code").AgentPlanListOut>(`/ai-dev/agents/${runId}/plans`, { token }),
  aiDevAgentCheckpoints: (token: string, runId: string) =>
    apiRequest<import("@/types/code").AgentCheckpointListOut>(`/ai-dev/agents/${runId}/checkpoints`, { token }),
  aiDevSecurityGate: (token: string, body: { repository_id?: string | null; review_id?: string | null; files?: Array<{ path: string; content: string }> | null; findings?: Array<Record<string, unknown>> | null; branch?: string }) =>
    apiRequest<import("@/types/code").SecurityGateOut>("/ai-dev/security-gate", { method: "POST", token, body }),
  aiDevTestGenerate: (token: string, body: import("@/types/code").TestGenerateIn) =>
    apiRequest<import("@/types/code").AiDevTestRunOut>("/ai-dev/tests/generate", { method: "POST", token, body }),
  aiDevAgentCancel: (token: string, runId: string, reason?: string) =>
    apiRequest<import("@/types/code").AgentOut>(`/ai-dev/agents/${runId}/cancel`, { method: "POST", token, body: { reason } }),
  aiDevAgentApprovePlan: (token: string, runId: string, planId: string, body: { approved: boolean; approved_by: string; reason?: string }) =>
    apiRequest<import("@/types/code").AgentPlanOut>(`/ai-dev/agents/${runId}/plans/${planId}/approve`, { method: "POST", token, body }),
};
