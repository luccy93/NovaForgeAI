"use client";

/**
 * Browser-safe environment boundaries. Only NEXT_PUBLIC_* values may
 * appear here — never secrets, never server-only configuration.
 *
 * Resolution is lazy (per call, never at module import) so static
 * prerendering without a configured URL cannot crash the build.
 */
const DEV_FALLBACK_API = "http://127.0.0.1:8000/api/v1";

export function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured && configured.trim() !== "") return configured.replace(/\/$/, "");
  if (typeof window !== "undefined" && process.env.NODE_ENV === "production") {
    // Fail visibly at runtime rather than silently pointing at a dev host.
    throw new Error("NEXT_PUBLIC_API_URL is required in production");
  }
  return DEV_FALLBACK_API;
}

export const env = {
  isProduction: process.env.NODE_ENV === "production",
} as const;
