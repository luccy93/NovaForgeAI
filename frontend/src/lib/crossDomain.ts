"use client";

import { isSafeNotificationTarget } from "@/lib/navigation";

/**
 * Fail-closed allowlist for backend-provided EXTERNAL URLs (e.g. OAuth
 * provider authorize URLs, knowledge citations). Only absolute http/https
 * URLs pass; javascript:, data:, vbscript:, protocol-relative and malformed
 * values return null so callers render inert text instead of an anchor.
 */
export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

/**
 * Build a canonical cross-domain handoff URL.
 * - Validates base href via isSafeNotificationTarget (blocks //, ://, javascript:)
 * - Optionally appends query params with encodeURIComponent via URLSearchParams
 * - Never includes tokens, secrets, or API keys
 * - Fail-closed: unsafe base href falls back to /dashboard
 */
export function buildHandoff(
  href: string,
  params?: Record<string, string | undefined | null>,
): string {
  if (!isSafeNotificationTarget(href)) return "/dashboard";
  if (!params) return href;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== "") search.set(key, value);
  }
  const qs = search.toString();
  return qs ? `${href}?${qs}` : href;
}

/**
 * Safe helper for knowledge document deep links.
 * Uses canonical /knowledge/document/:id with encodeURIComponent.
 */
export function buildKnowledgeDocumentHref(documentId: string): string {
  const base = `/knowledge/document/${encodeURIComponent(documentId)}`;
  // Validate base prefix is allowed via isSafeNotificationTarget or startsWith /knowledge/document
  if (base.startsWith("/knowledge/document/")) return base;
  return "/knowledge";
}
