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