export interface GovernancePolicy {
  id: string;
  tenant: string;
  name: string;
  domain: string;
  description: string;
  owner: string;
  status: string;
  active_version_id: string | null;
}

export interface GovernancePoliciesResponse {
  items: GovernancePolicy[];
  total: number;
}

export interface GovernanceBinding {
  id: string;
  tenant: string;
  policy_id: string;
  version_id: string;
  scope_type: string;
  scope_value: string;
  mandatory: boolean;
  enabled: boolean;
}

export interface GovernanceBindingsResponse {
  items: GovernanceBinding[];
  total: number;
}

export interface GovernanceDecision {
  id: string;
  evaluation_id: string;
  tenant: string;
  policy_id: string | null;
  version_id: string | null;
  binding_id: string | null;
  rule_index: number;
  decision: string;
  scope_type: string;
  scope_value: string;
  priority: number;
  reason: string;
  obligations: readonly unknown[];
  approval_id: string;
  actor: string;
}

export interface GovernanceDecisionsResponse {
  items: GovernanceDecision[];
  total: number;
}

export interface GovernanceException {
  id: string;
  tenant: string;
  policy_id: string;
  scope_type: string;
  scope_value: string;
  justification: string;
  requester: string;
  approver: string;
  start_at: string | null;
  end_at: string | null;
  max_duration_hours: number;
  high_risk: boolean;
  status: string;
}

export interface GovernanceExceptionsResponse {
  items: GovernanceException[];
  total: number;
}

export interface GovernancePosture {
  [key: string]: unknown;
  snapshot_id: string;
  total_policies: number;
  active_policies: number;
  violations_24h: number;
  open_exceptions: number;
  verified_controls: number;
  failing_controls: number;
  computed_at: string | null;
}

export interface GovernanceEvidence {
  id: string;
  tenant: string;
  control_key: string;
  source_system: string;
  source_ref: string;
  source_version: string;
  collected_at: string | null;
  valid_until: string | null;
  integrity_hash: string;
  result: string;
  expired: boolean;
}

export interface GovernanceEvidenceResponse {
  items: GovernanceEvidence[];
  total: number;
}

export interface GovernanceEvidenceCoverage {
  total: number;
  expired: number;
  valid: number;
}

export interface GovernanceDriftFinding {
  id: string;
  finding_type: string;
  severity: string;
  resource_type: string;
  resource_id: string;
  description: string;
  status: string;
}

export interface GovernanceDriftResponse {
  items: GovernanceDriftFinding[];
  total: number;
}

export interface GovernanceTrendPoint {
  computed_at: string | null;
  domain: string;
  active_policies: number;
  violations_24h: number;
  open_exceptions: number;
  verified_controls: number;
  failing_controls: number;
}

export interface GovernanceTrendsResponse {
  items: GovernanceTrendPoint[];
  total: number;
}

export interface GovernanceDriftResolveResult {
  id: string;
  status: string;
}

export const GOVERNANCE_POLICY_STATUSES = ["DRAFT", "VALIDATING", "ACTIVE", "SUPERSEDED", "RETIRED"] as const;
export const GOVERNANCE_DECISIONS = ["ALLOW", "DENY", "REQUIRE_APPROVAL"] as const;
export const GOVERNANCE_EXCEPTION_STATUSES = ["PENDING", "APPROVED", "DENIED", "EXPIRED", "REVOKED"] as const;
export const GOVERNANCE_DRIFT_STATUSES = ["OPEN", "RESOLVED"] as const;
export const GOVERNANCE_DRIFT_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export const GOVERNANCE_SCOPE_TYPES = ["organization", "tenant", "workspace", "resource"] as const;
export const GOVERNANCE_REPORT_TYPES = ["posture", "violations", "compliance"] as const;
export const GOVERNANCE_VERSION_STATUSES = ["DRAFT", "VALIDATING", "ACTIVE", "SUPERSEDED", "RETIRED"] as const;
export const GOVERNANCE_EFFECTS = ["allow", "deny", "require_approval"] as const;

/** Immutable policy version — plane_policies._serialize_version. */
export interface GovernancePolicyVersion {
  id: string;
  tenant: string;
  policy_id: string;
  version: number;
  status: string;
  effective_from: string | null;
  effective_until: string | null;
  rules: Array<Record<string, unknown>>;
  default_effect: string;
  checksum: string;
  reason: string;
  created_by: string;
}

export interface GovernancePolicyVersionsResponse {
  items: GovernancePolicyVersion[];
  total: number;
}

/** POST /governance/evaluate result (enforce=false). enforce=true adds allowed/zero_trust/approval_id. */
export interface GovernanceEvaluateResult {
  decision: string;
  reason: string;
  policy_id: string | null;
  version_id: string | null;
  binding_id: string | null;
  rule_index: number | null;
  priority: number;
  obligations: unknown[];
  exception_id: string | null;
  scope_type: string;
  scope_value: string;
  effective_at: string;
  latency_ms: number;
  id?: string;
  evaluation_id?: string;
  allowed?: boolean;
  approval_id?: string;
  zero_trust?: {
    decision: string;
    allowed: boolean;
    reason: string;
  };
}

/** POST /governance/simulate single-request result. Simulation never has side effects. */
export interface GovernanceSimulateResult {
  decision: string;
  reason: string;
  policy_id: string | null;
  version_id: string | null;
  binding_id: string | null;
  rule_index: number | null;
  priority: number;
  obligations: unknown[];
  scope_type: string;
  scope_value: string;
  simulated_at: string;
  side_effects: false;
}

export interface GovernanceSimulateBatchResponse {
  items: GovernanceSimulateResult[];
  total: number;
  summary: Record<string, number>;
}

/** GET /governance/decisions/{id}/explain — the `why` string is backend-composed. */
export interface GovernanceDecisionExplanation {
  decision: string;
  reason: string;
  scope: { scope_type: string; scope_value: string };
  priority: number;
  obligations: unknown[];
  approval_id: string;
  actor: string;
  policy?: { id: string; name: string; domain: string; status: string };
  version?: { id: string; version: number; status: string; checksum: string };
  rule?: { index: number; name?: string; effect?: string; priority?: number; obligations?: unknown[] };
  binding?: { id: string; scope_type: string; scope_value: string; mandatory: boolean };
  evaluation_id?: string;
  exception_id?: string;
  why: string;
}

export interface GovernanceExplainResponse {
  id: string;
  tenant: string;
  explanation: GovernanceDecisionExplanation;
}

/** Posture snapshot row (GET /governance/posture/history). Raw counts only. */
export interface GovernancePostureSnapshot {
  id: string;
  scope_type: string;
  scope_value: string;
  domain: string;
  total_policies: number;
  active_policies: number;
  violations_24h: number;
  open_exceptions: number;
  verified_controls: number;
  failing_controls: number;
  computed_at: string | null;
  metadata: Record<string, unknown>;
}

export interface GovernancePostureHistoryResponse {
  items: GovernancePostureSnapshot[];
  total: number;
}

export interface GovernanceTopRisk {
  area: string;
  severity: string;
  resource: string;
}

/** Persisted governance report — plane_reports._serialize. */
export interface GovernanceReport {
  id: string;
  tenant: string;
  report_type: string;
  scope_type: string;
  scope_value: string;
  period_start: string | null;
  period_end: string | null;
  summary: {
    posture?: Record<string, unknown>;
    violations?: number;
    open_exceptions?: number;
    open_drift?: number;
    evidence?: Record<string, unknown>;
    top_risks?: GovernanceTopRisk[];
  };
  sections: Array<{ name: string; items: Array<Record<string, unknown>> }>;
}

export interface GovernanceReportsResponse {
  items: GovernanceReport[];
  total: number;
}

/** POST /governance/govern/{ai,data,security,spend,integration,workflow,agent}.
 * Central evaluation result plus the domain layer verdict. No scores —
 * only decision/allowed/layer/reason and the domain's own detail fields. */
export interface DomainGovernResult {
  decision: string;
  reason: string;
  allowed: boolean;
  layer: string;
  policy_id?: string | null;
  version_id?: string | null;
  binding_id?: string | null;
  rule_index?: number | null;
  priority?: number;
  obligations?: unknown[];
  exception_id?: string | null;
  scope_type?: string;
  scope_value?: string;
  approval_id?: string;
  finops_gate?: string;
  zero_trust?: {
    decision: string;
    allowed: boolean;
    reason: string;
  };
}

export const GOVERN_ACTION_CLASSES = ["read", "write", "execute", "approve", "share", "export"] as const;
export const GOVERN_CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] as const;