"use client";

import { apiRequest } from "@/lib/api-client";
import type {
  ApiKeyCreated,
  ApiKeyOut,
  ApiUser,
  AuthTokens,
  CostsPage,
  FinOpsSummary,
  KnowledgePage,
  LoginResponse,
  MfaSetup,
  MfaStatus,
  SessionOut,
  WhoAmI,
} from "@/types/api";
import type { Organization, OrganizationMember, InviteResult, Workspace, Role } from "@/types/org";

export type { AuthTokens, CostsPage, FinOpsSummary, KnowledgeHit, KnowledgePage, ApiUser, CostRecord, MfaSetup, MfaStatus, SessionOut, ApiKeyOut, ApiKeyCreated, WhoAmI, LoginResponse } from "@/types/api";
export { ApiError, type ApiErrorKind } from "@/lib/api-client";
export { isMfaChallenge } from "@/types/api";

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

  knowledgeSearch: (token: string, query: string, limit = 5) =>
    apiRequest<KnowledgePage>(
      `/knowledge/search?query=${encodeURIComponent(query)}&limit=${limit}`,
      { token },
    ),

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
    apiRequest<Record<string, unknown>>("/secops/dashboard", { token }),
  governancePosture: (token: string) =>
    apiRequest<import("@/types/api").GovernancePosture>("/governance/posture", { token }),
  governanceDecisions: (token: string, limit = 5) =>
    apiRequest<{ items: unknown[]; total: number }>(`/governance/decisions?limit=${limit}`, { token }),
  integrationsList: (token: string) =>
    apiRequest<{ items: import("@/types/api").IntegrationItem[]; total: number }>("/integrations", { token }),
  observabilityDashboard: (token: string) =>
    apiRequest<import("@/types/api").ObservabilityDashboard>("/observability/dashboard", { token }),
  recentActivity: (token: string, limit = 20) =>
    apiRequest<{ events: import("@/types/api").RecentActivityItem[]; count: number }>(
      `/analytics/events?limit=${limit}`,
      { token },
    ),
  knowledgeHistory: (token: string, limit = 5) =>
    apiRequest<{ items: unknown[]; total: number }>(`/knowledge/audit/history?limit=${limit}`, { token }),

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
};
