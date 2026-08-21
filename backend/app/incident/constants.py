"""Incident Response Platform -- Constants (Volume 49).

Single source of truth for incident lifecycle, severities, roles, source
types, incident types, and detection thresholds.
"""

# ---------------------------------------------------------------------------
# Incident states
# ---------------------------------------------------------------------------
INCIDENT_DETECTED = "detected"
INCIDENT_TRIAGED = "triaged"
INCIDENT_INVESTIGATING = "investigating"
INCIDENT_MITIGATING = "mitigating"
INCIDENT_MONITORING = "monitoring"
INCIDENT_RESOLVED = "resolved"
INCIDENT_POSTMORTEM = "postmortem"
INCIDENT_CLOSED = "closed"

INCIDENT_STATUSES = (
    INCIDENT_DETECTED,
    INCIDENT_TRIAGED,
    INCIDENT_INVESTIGATING,
    INCIDENT_MITIGATING,
    INCIDENT_MONITORING,
    INCIDENT_RESOLVED,
    INCIDENT_POSTMORTEM,
    INCIDENT_CLOSED,
)

INCIDENT_TRANSITIONS = {
    INCIDENT_DETECTED: (INCIDENT_TRIAGED, INCIDENT_INVESTIGATING, INCIDENT_MITIGATING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_TRIAGED: (INCIDENT_INVESTIGATING, INCIDENT_MITIGATING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_INVESTIGATING: (INCIDENT_MITIGATING, INCIDENT_MONITORING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_MITIGATING: (INCIDENT_MONITORING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_MONITORING: (INCIDENT_RESOLVED, INCIDENT_MITIGATING, INCIDENT_CLOSED),
    INCIDENT_RESOLVED: (INCIDENT_POSTMORTEM, INCIDENT_CLOSED, INCIDENT_MONITORING),
    INCIDENT_POSTMORTEM: (INCIDENT_CLOSED,),
    INCIDENT_CLOSED: (),
}

INCIDENT_ACTIVE_STATUSES = (
    INCIDENT_DETECTED,
    INCIDENT_TRIAGED,
    INCIDENT_INVESTIGATING,
    INCIDENT_MITIGATING,
    INCIDENT_MONITORING,
)

# ---------------------------------------------------------------------------
# Severities
# ---------------------------------------------------------------------------
SEV0 = "SEV0"
SEV1 = "SEV1"
SEV2 = "SEV2"
SEV3 = "SEV3"
SEV4 = "SEV4"

SEVERITIES = (SEV0, SEV1, SEV2, SEV3, SEV4)

SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

SEVERITY_DESCRIPTIONS = {
    SEV0: "Total platform outage - immediate response required",
    SEV1: "Major outage affecting many customers - respond within minutes",
    SEV2: "Partial outage or degraded service - respond within 30 minutes",
    SEV3: "Minor impact - respond during business hours",
    SEV4: "Informational - no action required",
}

SEVERITY_TARGET_MINUTES = {SEV0: 5, SEV1: 15, SEV2: 30, SEV3: 240, SEV4: 1440}

# ---------------------------------------------------------------------------
# Incident types
# ---------------------------------------------------------------------------
INCIDENT_TYPE_AVAILABILITY = "availability"
INCIDENT_TYPE_PERFORMANCE = "performance"
INCIDENT_TYPE_DEPLOYMENT = "deployment"
INCIDENT_TYPE_SECURITY = "security"
INCIDENT_TYPE_DATA = "data"
INCIDENT_TYPE_DEPENDENCY = "dependency"
INCIDENT_TYPE_INFRASTRUCTURE = "infrastructure"
INCIDENT_TYPE_AI_RUNTIME = "ai_runtime"

INCIDENT_TYPES = (
    INCIDENT_TYPE_AVAILABILITY,
    INCIDENT_TYPE_PERFORMANCE,
    INCIDENT_TYPE_DEPLOYMENT,
    INCIDENT_TYPE_SECURITY,
    INCIDENT_TYPE_DATA,
    INCIDENT_TYPE_DEPENDENCY,
    INCIDENT_TYPE_INFRASTRUCTURE,
    INCIDENT_TYPE_AI_RUNTIME,
)

# ---------------------------------------------------------------------------
# Detection sources
# ---------------------------------------------------------------------------
SOURCE_ALERT = "alert"
SOURCE_METRIC = "metric"
SOURCE_LOG = "log"
SOURCE_TRACE = "trace"
SOURCE_DEPLOYMENT = "deployment"
SOURCE_SECURITY = "security"
SOURCE_CI_CD = "ci_cd"
SOURCE_CODE_INTEL = "code_intelligence"
SOURCE_AI_AGENT = "ai_agent"
SOURCE_EVENT_BUS = "event_bus"
SOURCE_EXTERNAL = "external"
SOURCE_MANUAL = "manual"
SOURCE_ANOMALY = "anomaly"
SOURCE_SCHEDULED = "scheduled"

SOURCES = (
    SOURCE_ALERT, SOURCE_METRIC, SOURCE_LOG, SOURCE_TRACE,
    SOURCE_DEPLOYMENT, SOURCE_SECURITY, SOURCE_CI_CD, SOURCE_CODE_INTEL,
    SOURCE_AI_AGENT, SOURCE_EVENT_BUS, SOURCE_EXTERNAL, SOURCE_MANUAL,
    SOURCE_ANOMALY, SOURCE_SCHEDULED,
)

# ---------------------------------------------------------------------------
# Incident command roles
# ---------------------------------------------------------------------------
ROLE_INCIDENT_COMMANDER = "incident_commander"
ROLE_TECHNICAL_LEAD = "technical_lead"
ROLE_COMMUNICATIONS = "communications"
ROLE_SECURITY_LEAD = "security_lead"
ROLE_SCRIBE = "scribe"

INCIDENT_ROLES = (
    ROLE_INCIDENT_COMMANDER,
    ROLE_TECHNICAL_LEAD,
    ROLE_COMMUNICATIONS,
    ROLE_SECURITY_LEAD,
    ROLE_SCRIBE,
)

# ---------------------------------------------------------------------------
# Hypothesis statuses
# ---------------------------------------------------------------------------
HYPOTHESIS_PROPOSED = "proposed"
HYPOTHESIS_ACCEPTED = "accepted"
HYPOTHESIS_REJECTED = "rejected"
HYPOTHESIS_VERIFIED = "verified"

HYPOTHESIS_STATUSES = (HYPOTHESIS_PROPOSED, HYPOTHESIS_ACCEPTED, HYPOTHESIS_REJECTED, HYPOTHESIS_VERIFIED)

# ---------------------------------------------------------------------------
# Action statuses
# ---------------------------------------------------------------------------
ACTION_PROPOSED = "proposed"
ACTION_APPROVED = "approved"
ACTION_EXECUTING = "executing"
ACTION_SUCCEEDED = "succeeded"
ACTION_FAILED = "failed"
ACTION_ROLLED_BACK = "rolled_back"
ACTION_REJECTED = "rejected"

ACTION_STATUSES = (
    ACTION_PROPOSED, ACTION_APPROVED, ACTION_EXECUTING,
    ACTION_SUCCEEDED, ACTION_FAILED, ACTION_ROLLED_BACK, ACTION_REJECTED,
)

ACTION_TRANSITIONS = {
    ACTION_PROPOSED: (ACTION_APPROVED, ACTION_REJECTED),
    ACTION_APPROVED: (ACTION_EXECUTING, ACTION_REJECTED),
    ACTION_EXECUTING: (ACTION_SUCCEEDED, ACTION_FAILED),
    ACTION_FAILED: (ACTION_ROLLED_BACK,),
    ACTION_SUCCEEDED: (),
    ACTION_ROLLED_BACK: (),
    ACTION_REJECTED: (),
}

# ---------------------------------------------------------------------------
# Risk levels for actions
# ---------------------------------------------------------------------------
RISK_SAFE = "safe"
RISK_MODERATE = "moderate"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"

RISK_LEVELS = (RISK_SAFE, RISK_MODERATE, RISK_HIGH, RISK_CRITICAL)

AUTO_EXECUTABLE_RISKS = (RISK_SAFE,)

# ---------------------------------------------------------------------------
# Alert statuses
# ---------------------------------------------------------------------------
ALERT_FIRING = "firing"
ALERT_ACKNOWLEDGED = "acknowledged"
ALERT_RESOLVED = "resolved"

ALERT_STATUSES = (ALERT_FIRING, ALERT_ACKNOWLEDGED, ALERT_RESOLVED)

# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------
ENV_PRODUCTION = "production"
ENV_STAGING = "staging"
ENV_DEVELOPMENT = "development"

ENVIRONMENTS = (ENV_PRODUCTION, ENV_STAGING, ENV_DEVELOPMENT)

# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------
ESCALATION_TIMEOUT_DEFAULT_MINUTES = 30

# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
DEDUP_WINDOW_SECONDS = 300

# ---------------------------------------------------------------------------
# Runbook
# ---------------------------------------------------------------------------
RUNBOOK_VERSION_INITIAL = "1.0"
