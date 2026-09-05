"use client";

import { apiRequest } from "@/lib/api-client";
import type {
  ApiUser,
  AuthTokens,
  CostsPage,
  FinOpsSummary,
  KnowledgePage,
} from "@/types/api";

export type { AuthTokens, CostsPage, FinOpsSummary, KnowledgeHit, KnowledgePage, ApiUser, CostRecord } from "@/types/api";
export { ApiError, type ApiErrorKind } from "@/lib/api-client";

const TOKEN_KEY = "nf_token";

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

export const api = {
  register: (email: string, username: string, password: string) =>
    apiRequest<AuthTokens>("/auth/register", {
      method: "POST",
      body: { email, username, password },
    }),

  login: (email: string, password: string) =>
    apiRequest<AuthTokens>("/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  me: (token: string) => apiRequest<ApiUser>("/auth/me", { token }),

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
};
