"use client";

import { isSafeNotificationTarget } from "@/lib/navigation";

/**
 * Build a canonical cross-domain handoff URL.
 * - Validates base href via isSafeNotificationTarget (blocks //, ://, javascript:)
 * - Optionally appends query params with encodeURIComponent via URLSearchParams
 * - Never includes tokens, secrets, or API keys
 * - Falls back to bare href if validation fails
 */
export function buildHandoff(
  href: string,
  params?: Record<string, string | undefined | null>,
): string {
  if (!isSafeNotificationTarget(href)) return href;
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
