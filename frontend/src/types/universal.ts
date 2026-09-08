"use client";

/**
 * Universal search (Volume 68 C2) types. Shapes mirror the exact authorized
 * endpoints they come from — never invent fields or pretend a domain exposes
 * search when it does not.
 */

export interface CatalogHit {
  id: string;
  name?: string | null;
  owner?: string | null;
  classification?: string | null;
  description?: string | null;
  score?: number | null;
  source?: string | null;
}

export interface CatalogSearchResponse {
  items: CatalogHit[];
  total?: number;
  source?: string | null;
  stale?: boolean;
  warning?: string | null;
  error?: string | null;
}

export type UniversalDomainId =
  | "knowledge"
  | "dataCatalog"
  | "code"
  | "incidents"
  | "security"
  | "workflows"
  | "integrations";

export interface UniversalDomain {
  id: UniversalDomainId;
  label: string;
  reason: string;
}