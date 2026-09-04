"use client";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("nf_token");
}

export function setToken(token: string): void {
  localStorage.setItem("nf_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("nf_token");
}

async function req<T>(path: string, token?: string | null, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return (await resp.json()) as T;
}

export interface AuthResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export const api = {
  register: (email: string, username: string, password: string) =>
    req<AuthResponse>("/auth/register", null, {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    }),

  login: (email: string, password: string) =>
    req<AuthResponse>("/auth/login", null, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: (token: string) => req<Record<string, unknown>>("/auth/me", token),

  finopsSummary: (token: string) =>
    req<Record<string, unknown>>("/finops/usage/summary", token),

  finopsCosts: (token: string, limit = 10) =>
    req<{ items: unknown[]; total: number; spend_cents: number }>(
      `/finops/costs?limit=${limit}`,
      token,
    ),

  knowledgeSearch: (token: string, query: string, limit = 5) =>
    req<{ items: Array<Record<string, unknown>>; total: number }>(
      `/knowledge/search?query=${encodeURIComponent(query)}&limit=${limit}`,
      token,
    ),
};
