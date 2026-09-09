"use client";

/** Security Operations (secops) dashboard — verbatim response shapes. */
export interface SecOpsAlertsSummary {
  total: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface SecOpsDashboard {
  tenant: string;
  alerts: SecOpsAlertsSummary;
  findings: { total: number };
  cases: { total: number };
  indicators: { total: number };
}

/** Posture/coverage/SLO payloads are heterogeneous; only primitive values are rendered. */
export interface SecOpsPosture {
  [key: string]: unknown;
}

export interface SecOpsCoverage {
  [key: string]: unknown;
}

export interface SecOpsSlo {
  [key: string]: unknown;
}

export interface SecOpsRiskSnapshot {
  id?: string;
  risk_score?: number;
  severity?: string;
  calculated_at?: string | null;
  inputs?: unknown;
  tenant?: string;
}

export interface SecOpsEvent {
  event_id: string;
  source?: string;
  category?: string;
  severity?: string;
  action?: string;
  actor?: string;
  resource?: string;
  region?: string;
  tenant?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface SecOpsEventsResponse {
  items: SecOpsEvent[];
  total: number;
  tenant: string;
}

export interface SecOpsAlert {
  id: string;
  rule_name?: string;
  severity?: string;
  status?: string;
  confidence?: number;
  fingerprint?: string;
  events?: unknown[];
}

export interface SecOpsAlertsResponse {
  items: SecOpsAlert[];
  total: number;
}

export interface SecOpsFinding {
  id: string;
  finding?: string;
  resource?: string;
  severity?: string;
  status?: string;
}

export interface SecOpsFindingsResponse {
  items: SecOpsFinding[];
}

export interface SecOpsResponseRecord {
  id?: string;
  status?: string;
  action?: string;
  policy?: string;
  requested_by?: string;
  approved_by?: string;
  [key: string]: unknown;
}

export interface SecOpsResponsesResponse {
  items: SecOpsResponseRecord[];
  total: number;
}

export interface AlertStatusResult {
  id: string;
  status: string;
}

/** Zero Trust (zero-trust module) — verbatim response shapes. */
export interface ZeroTrustPosture {
  identity?: unknown;
  access?: unknown;
  machine?: unknown;
  [key: string]: unknown;
}

export interface PrivilegedAccessItem {
  id: string;
  identity?: string;
  resource?: string;
  status?: string;
  privilege_level?: string;
}

export interface PrivilegedAccessResponse {
  items: PrivilegedAccessItem[];
}

export interface AccessRequestItem {
  id: string;
  identity?: string;
  resource?: string;
  action?: string;
  status?: string;
  binding_hash?: string;
}

export interface AccessRequestsResponse {
  items: AccessRequestItem[];
}

export interface AccessApproveResult {
  id: string;
  status: string;
  expires_at?: string | null;
}

/** Alert lifecycle statuses accepted by the secops alert status endpoint. */
export const SECOPS_ALERT_STATUSES = [
  "ACKNOWLEDGED",
  "INVESTIGATING",
  "CONTAINED",
  "RESOLVED",
  "FALSE_POSITIVE",
] as const;

/** Finding statuses surfaced for the findings status mutation. */
export const SECOPS_FINDING_STATUSES = ["OPEN", "RESOLVED", "FALSE_POSITIVE"] as const;