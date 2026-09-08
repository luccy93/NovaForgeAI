"use client";

/** Alert lifecycle statuses as returned by the observability platform. */
export type ObservabilityAlertStatus =
  | "FIRING"
  | "ACKNOWLEDGED"
  | "SUPPRESSED"
  | "RESOLVED";

export interface ObservabilityAlert {
  id: string;
  resource: string;
  status: ObservabilityAlertStatus;
  severity: string;
  fingerprint: string;
}

export interface ObservabilityAlertsResponse {
  items: ObservabilityAlert[];
}

export interface ObservabilityDashboard {
  tenant: string;
  services: number;
  health: Record<string, string>;
}

export interface ObservabilityQualityBreakdownItem {
  score?: number;
  weight?: number;
  note?: string;
  services?: number;
  age_seconds?: number | null;
  unique_fingerprints?: number;
  total_alerts?: number;
  slos?: number;
  synthetic_checks?: number;
  error?: string;
}

export interface ObservabilityQuality {
  tenant: string;
  service: string;
  overall_score: number;
  grade: "excellent" | "good" | "fair" | "poor";
  breakdown: Record<string, ObservabilityQualityBreakdownItem>;
  recommendations: Array<string | null>;
  scored_at: string;
}

export interface AiopsStatus {
  tenant: string;
  /** Never rendered raw; only the typed `stages` list and disclaimer are shown. */
  pipeline: unknown;
  quality: ObservabilityQuality | { error: string };
  capacity: unknown;
  stages: string[];
  disclaimer: string;
}

export interface AlertMutationResult {
  id: string;
  status: ObservabilityAlertStatus;
}

export interface AlertFatigueRecommendation {
  type: string;
  action?: string;
  evidence: Record<string, unknown>;
}

export interface AlertFatigueReport {
  window_hours: number;
  total: number;
  duplicates: Record<string, number>;
  high_frequency: string[];
  flapping: string[];
  recommendations: AlertFatigueRecommendation[];
}

export type SreOverallStatus = "operational" | "degraded" | "major_outage";

export interface SreStatusSummary {
  overall: SreOverallStatus;
  components: number;
  by_status: Record<string, number>;
}

export interface SreStatusComponent {
  id: string;
  component_id: string;
  service_id: string;
  name: string;
  description: string;
  status: string;
  region: string;
  public: boolean;
  history: unknown[];
}

export interface SreStatusComponentsResponse {
  total: number;
  items: SreStatusComponent[];
}

export interface SreAnalyticsIncidents {
  total: number;
  mttd_hours: number | null;
  mtta_hours: number | null;
  mttm_hours: number | null;
  mttr_hours: number | null;
  open: number;
}

export interface SreAnalytics {
  period_days: number;
  incidents: SreAnalyticsIncidents;
  deployments: {
    total: number;
    failed: number;
    change_failure_rate: number;
  };
  alerts: {
    total: number;
    firing: number;
  };
}

export type SreIncidentStatus =
  | "detected"
  | "investigating"
  | "identified"
  | "mitigating"
  | "monitoring"
  | "resolved"
  | "closed";

export interface SreIncident {
  id: string;
  incident_id: string;
  organization_id: string;
  title: string;
  description: string;
  severity: string;
  status: SreIncidentStatus;
  service_id: string;
  region: string;
  commander: string;
  /** Never rendered. */
  impact: unknown;
  root_cause: string;
  detection: string;
  related_deployments: string[];
  related_changes: string[];
  related_alerts: string[];
  postmortem_id: string;
  detected_at: string | null;
  acknowledged_at: string | null;
  mitigated_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  created_at: string | null;
}

export interface SreIncidentsResponse {
  total: number;
  items: SreIncident[];
}

export interface SreIncidentTimelineEvent {
  event_type: string;
  actor: string;
  message: string;
  occurred_at: string;
  /** Never rendered. */
  metadata?: unknown;
}

export interface SreIncidentTimeline {
  incident_id: string;
  events: SreIncidentTimelineEvent[];
}

export interface SreService {
  id: string;
  service_id: string;
  name: string;
  description: string;
  owner: string;
  team: string;
  tier: string;
  criticality: string;
  deployment_strategy: string;
  scaling_strategy: string;
  backup_strategy: string;
  rto_minutes: number;
  rpo_minutes: number;
  runbook_id: string;
  on_call: string;
  status: string;
  /** Never rendered. */
  metadata?: unknown;
  created_at: string | null;
  updated_at: string | null;
}

export interface SreServicesResponse {
  total: number;
  items: SreService[];
}

export interface SreServiceDependency {
  depends_on: string;
  kind: string;
  critical: boolean;
}

export interface SreServiceDependencies {
  service_id: string;
  dependencies: SreServiceDependency[];
  edges: Record<string, unknown>;
}

export interface IncidentTransitionBody {
  target: string;
  note?: string;
}

export const INCIDENT_STATUSES: readonly SreIncidentStatus[] = [
  "detected",
  "investigating",
  "identified",
  "mitigating",
  "monitoring",
  "resolved",
  "closed",
] as const;

/** UX copy of the backend state machine; the backend remains authoritative. */
export const INCIDENT_TRANSITIONS: Record<SreIncidentStatus, SreIncidentStatus[]> = {
  detected: ["investigating", "identified", "mitigating", "resolved", "closed"],
  investigating: ["identified", "mitigating", "resolved", "closed"],
  identified: ["mitigating", "monitoring", "resolved", "closed"],
  mitigating: ["monitoring", "resolved", "closed"],
  monitoring: ["resolved", "mitigating", "closed"],
  resolved: ["closed", "monitoring"],
  closed: [],
};