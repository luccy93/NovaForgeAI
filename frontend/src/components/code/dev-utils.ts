"use client";

import { ApiError } from "@/lib/api-client";

export function sessionExpired() {
  window.location.href = "/auth/login";
}

// Returns a friendly error message, or "" when the session expired (the caller
// should then stop and not update UI state).
export function devErrorMessage(e: unknown, label: string): string {
  if (e instanceof ApiError && e.kind === "unauthorized") {
    sessionExpired();
    return "";
  }
  return e instanceof Error ? e.message : `Failed to load ${label}`;
}

export function asString(v: unknown): string | null {
  return typeof v === "string" ? v : v == null ? null : String(v);
}

export function asStringList(v: unknown): string[] {
  return Array.isArray(v) ? v.map((item) => asString(item) ?? "").filter(Boolean) : [];
}

export function asNumber(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

export function asRecordList(v: unknown): Array<Record<string, unknown>> {
  return Array.isArray(v) ? v.filter((item): item is Record<string, unknown> => !!item && typeof item === "object") : [];
}