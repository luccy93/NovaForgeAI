"""SRE constants (Volume 35).

Single source of truth for SRE vocabulary: dependency statuses, health
states, circuit breaker states, incident lifecycle, SLO windows, SLI
types, burn-rate severity tiers and alert severities.

Every constant used across the SRE package lives here so definitions are
never duplicated or silently inconsistent.
"""

# ---------------------------------------------------------------------------
# Health states
# ---------------------------------------------------------------------------
HEALTH_HEALTHY = "healthy"
HEALTH_DEGRADED = "degraded"
HEALTH_UNHEALTHY = "unhealthy"
HEALTH_UNKNOWN = "unknown"

HEALTH_STATES = (HEALTH_HEALTHY, HEALTH_DEGRADED, HEALTH_UNHEALTHY, HEALTH_UNKNOWN)

# ---------------------------------------------------------------------------
# Dependency statuses
# ---------------------------------------------------------------------------
DEPENDENCY_STATUS_HEALTHY = "healthy"
DEPENDENCY_STATUS_DEGRADED = "degraded"
DEPENDENCY_STATUS_DOWN = "down"
DEPENDENCY_STATUS_UNKNOWN = "unknown"

DEPENDENCY_STATUSES = (
    DEPENDENCY_STATUS_HEALTHY,
    DEPENDENCY_STATUS_DEGRADED,
    DEPENDENCY_STATUS_DOWN,
    DEPENDENCY_STATUS_UNKNOWN,
)

# ---------------------------------------------------------------------------
# Circuit breaker states
# ---------------------------------------------------------------------------
CIRCUIT_CLOSED = "closed"
CIRCUIT_OPEN = "open"
CIRCUIT_HALF_OPEN = "half_open"

CIRCUIT_STATES = (CIRCUIT_CLOSED, CIRCUIT_OPEN, CIRCUIT_HALF_OPEN)

# ---------------------------------------------------------------------------
# Service tiers
# ---------------------------------------------------------------------------
TIER_0 = "tier0"
TIER_1 = "tier1"
TIER_2 = "tier2"
TIER_3 = "tier3"

SERVICE_TIERS = (TIER_0, TIER_1, TIER_2, TIER_3)

# Friendly aliases used across the SRE modules (criticality labels).
TIER_0_CRITICAL = TIER_0
TIER_1_HIGH = TIER_1
TIER_2_IMPORTANT = TIER_2
TIER_3_NON_CRITICAL = TIER_3

TIER_LABELS = {
    TIER_0: "Critical",
    TIER_1: "High",
    TIER_2: "Important",
    TIER_3: "Non-critical",
}

# Default recovery/availability posture per tier (used by catalog seeding).
TIER_DEFAULTS = {
    TIER_0: {"rto_minutes": 15, "rpo_minutes": 5, "availability_target": 0.9999},
    TIER_1: {"rto_minutes": 60, "rpo_minutes": 15, "availability_target": 0.9995},
    TIER_2: {"rto_minutes": 240, "rpo_minutes": 60, "availability_target": 0.999},
    TIER_3: {"rto_minutes": 1440, "rpo_minutes": 360, "availability_target": 0.99},
}

# Deployment strategies
DEPLOYMENT_ROLLING = "rolling"
DEPLOYMENT_CANARY = "canary"
DEPLOYMENT_BLUE_GREEN = "blue-green"

DEPLOYMENT_STRATEGIES = (DEPLOYMENT_ROLLING, DEPLOYMENT_CANARY, DEPLOYMENT_BLUE_GREEN)

# ---------------------------------------------------------------------------
# SLO windows
# ---------------------------------------------------------------------------
WINDOW_DAILY = "daily"
WINDOW_WEEKLY = "weekly"
WINDOW_MONTHLY = "monthly"
WINDOW_QUARTERLY = "quarterly"

SLO_WINDOWS = (WINDOW_DAILY, WINDOW_WEEKLY, WINDOW_MONTHLY, WINDOW_QUARTERLY)

WINDOW_SECONDS = {
    WINDOW_DAILY: 86400,
    WINDOW_WEEKLY: 7 * 86400,
    WINDOW_MONTHLY: 30 * 86400,
    WINDOW_QUARTERLY: 91 * 86400,
}

# ---------------------------------------------------------------------------
# SLI types
# ---------------------------------------------------------------------------
SLI_AVAILABILITY = "availability"
SLI_LATENCY = "latency"
SLI_THROUGHPUT = "throughput"
SLI_ERROR_RATE = "error_rate"
SLI_SUCCESS_RATE = "success_rate"
SLI_FRESHNESS = "freshness"
SLI_DURABILITY = "durability"
SLI_CORRECTNESS = "correctness"
SLI_QUEUE_DELAY = "queue_delay"
SLI_PROCESSING_TIME = "processing_time"
SLI_RECOVERY_TIME = "recovery_time"

SLI_TYPES = (
    SLI_AVAILABILITY,
    SLI_LATENCY,
    SLI_THROUGHPUT,
    SLI_ERROR_RATE,
    SLI_SUCCESS_RATE,
    SLI_FRESHNESS,
    SLI_DURABILITY,
    SLI_CORRECTNESS,
    SLI_QUEUE_DELAY,
    SLI_PROCESSING_TIME,
    SLI_RECOVERY_TIME,
)

# ---------------------------------------------------------------------------
# Error budget statuses
# ---------------------------------------------------------------------------
BUDGET_HEALTHY = "healthy"
BUDGET_AT_RISK = "at_risk"
BUDGET_EXHAUSTED = "exhausted"

BUDGET_STATUSES = (BUDGET_HEALTHY, BUDGET_AT_RISK, BUDGET_EXHAUSTED)

# ---------------------------------------------------------------------------
# Burn rate tiers (multi-window detection)
# ---------------------------------------------------------------------------
BURN_FAST = "fast"
BURN_MEDIUM = "medium"
BURN_SLOW = "slow"

BURN_TIERS = (BURN_FAST, BURN_MEDIUM, BURN_SLOW)

# Default burn-rate windows: (window_minutes, target_burn_rate) per tier.
# A tier fires when the observed error budget burn rate over the window
# exceeds the tier threshold.
BURN_RATE_CONFIG = {
    BURN_FAST: {"window_minutes": 5, "threshold": 14.4},
    BURN_MEDIUM: {"window_minutes": 30, "threshold": 6.0},
    BURN_SLOW: {"window_minutes": 360, "threshold": 1.0},
}

# ---------------------------------------------------------------------------
# Alert severities
# ---------------------------------------------------------------------------
SEV0 = "SEV0"
SEV1 = "SEV1"
SEV2 = "SEV2"
SEV3 = "SEV3"
SEV4 = "SEV4"

SEVERITIES = (SEV0, SEV1, SEV2, SEV3, SEV4)

SEVERITY_RANK = {severity: index for index, severity in enumerate(SEVERITIES)}

SEVERITY_DESCRIPTIONS = {
    SEV0: "Total platform outage - immediate response required",
    SEV1: "Major outage affecting many customers - respond within minutes",
    SEV2: "Partial outage or degraded service - respond within 30 minutes",
    SEV3: "Minor impact - respond during business hours",
    SEV4: "Informational - no action required",
}

# Target response time (minutes) per severity for incident response.
SEVERITY_DEFAULT_TARGET_MINUTES = {SEV0: 5, SEV1: 15, SEV2: 30, SEV3: 240, SEV4: 1440}

# ---------------------------------------------------------------------------
# Incident lifecycle
# ---------------------------------------------------------------------------
INCIDENT_DETECTED = "detected"
INCIDENT_INVESTIGATING = "investigating"
INCIDENT_IDENTIFIED = "identified"
INCIDENT_MITIGATING = "mitigating"
INCIDENT_MONITORING = "monitoring"
INCIDENT_RESOLVED = "resolved"
INCIDENT_CLOSED = "closed"

INCIDENT_STATUSES = (
    INCIDENT_DETECTED,
    INCIDENT_INVESTIGATING,
    INCIDENT_IDENTIFIED,
    INCIDENT_MITIGATING,
    INCIDENT_MONITORING,
    INCIDENT_RESOLVED,
    INCIDENT_CLOSED,
)

# Alias used by the incident lifecycle module.
INCIDENT_STATES = INCIDENT_STATUSES

# Command roles assignable during an incident.
INCIDENT_COMMAND_ROLES = (
    "incident_commander",
    "sme",
    "scribe",
    "communications_liaison",
    "on_call",
)

INCIDENT_DETECTION_SOURCES = (
    "slo_violation",
    "alert",
    "security",
    "deployment",
    "provider",
    "infrastructure",
    "database",
    "user",
    "anomaly",
    "manual",
)

INCIDENT_ACTIVE_STATUSES = (INCIDENT_DETECTED, INCIDENT_INVESTIGATING, INCIDENT_IDENTIFIED, INCIDENT_MITIGATING, INCIDENT_MONITORING)

# Valid transitions for the incident state machine.
INCIDENT_TRANSITIONS = {
    INCIDENT_DETECTED: (INCIDENT_INVESTIGATING, INCIDENT_IDENTIFIED, INCIDENT_MITIGATING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_INVESTIGATING: (INCIDENT_IDENTIFIED, INCIDENT_MITIGATING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_IDENTIFIED: (INCIDENT_MITIGATING, INCIDENT_MONITORING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_MITIGATING: (INCIDENT_MONITORING, INCIDENT_RESOLVED, INCIDENT_CLOSED),
    INCIDENT_MONITORING: (INCIDENT_RESOLVED, INCIDENT_MITIGATING, INCIDENT_CLOSED),
    INCIDENT_RESOLVED: (INCIDENT_CLOSED, INCIDENT_MONITORING),
    INCIDENT_CLOSED: (),
}

# ---------------------------------------------------------------------------
# Alert / incident correlation
# ---------------------------------------------------------------------------
ALERT_STATUS_FIRING = "firing"
ALERT_STATUS_ACKED = "acked"
ALERT_STATUS_RESOLVED = "resolved"

ALERT_STATUSES = (ALERT_STATUS_FIRING, ALERT_STATUS_ACKED, ALERT_STATUS_RESOLVED)

# ---------------------------------------------------------------------------
# Runbook scenarios
# ---------------------------------------------------------------------------
RUNBOOK_SCENARIOS = (
    "api_outage",
    "database_outage",
    "redis_outage",
    "qdrant_outage",
    "neo4j_outage",
    "ai_provider_outage",
    "deployment_failure",
    "authentication_outage",
    "queue_failure",
    "high_latency",
    "memory_exhaustion",
    "disk_exhaustion",
    "security_incident",
    "certificate_expiration",
    "dns_failure",
)

# ---------------------------------------------------------------------------
# Dependency kinds
# ---------------------------------------------------------------------------
DEPENDENCY_KIND_EXTERNAL = "external"
DEPENDENCY_KIND_SERVICE = "service"
DEPENDENCY_KIND_DATABASE = "database"
DEPENDENCY_KIND_QUEUE = "queue"
DEPENDENCY_KIND_STORAGE = "storage"
DEPENDENCY_KIND_AI = "ai_provider"
DEPENDENCY_KIND_INFRA = "infrastructure"

# ---------------------------------------------------------------------------
# Status page states
# ---------------------------------------------------------------------------
STATUS_OPERATIONAL = "operational"
STATUS_DEGRADED = "degraded"
STATUS_PARTIAL_OUTAGE = "partial_outage"
STATUS_MAJOR_OUTAGE = "major_outage"
STATUS_MAINTENANCE = "maintenance"
STATUS_UNKNOWN = "unknown"

STATUS_STATES = (
    STATUS_OPERATIONAL,
    STATUS_DEGRADED,
    STATUS_PARTIAL_OUTAGE,
    STATUS_MAJOR_OUTAGE,
    STATUS_MAINTENANCE,
    STATUS_UNKNOWN,
)

# ---------------------------------------------------------------------------
# Region modes
# ---------------------------------------------------------------------------
REGION_ACTIVE_ACTIVE = "active-active"
REGION_ACTIVE_PASSIVE = "active-passive"
REGION_WARM_STANDBY = "warm-standby"
REGION_COLD_STANDBY = "cold-standby"

REGION_MODES = (REGION_ACTIVE_ACTIVE, REGION_ACTIVE_PASSIVE, REGION_WARM_STANDBY, REGION_COLD_STANDBY)

# ---------------------------------------------------------------------------
# Reliability score components
# ---------------------------------------------------------------------------
SCORE_COMPONENTS = (
    "availability",
    "latency",
    "error_rate",
    "incident_frequency",
    "recovery_time",
    "slo_compliance",
    "dependency_health",
    "change_failure_rate",
)

SCORE_WEIGHTS = {
    "availability": 0.25,
    "latency": 0.10,
    "error_rate": 0.15,
    "incident_frequency": 0.10,
    "recovery_time": 0.10,
    "slo_compliance": 0.15,
    "dependency_health": 0.10,
    "change_failure_rate": 0.05,
}

# ---------------------------------------------------------------------------
# Operational maturity levels
# ---------------------------------------------------------------------------
MATURITY_UNKNOWN = 0
MATURITY_BASIC_MONITORING = 1
MATURITY_OBSERVABLE = 2
MATURITY_RELIABLE = 3
MATURITY_HIGHLY_RELIABLE = 4
MATURITY_AUTONOMOUS = 5

MATURITY_LEVELS = {
    MATURITY_UNKNOWN: "Level 0 - Unknown",
    MATURITY_BASIC_MONITORING: "Level 1 - Basic Monitoring",
    MATURITY_OBSERVABLE: "Level 2 - Observable",
    MATURITY_RELIABLE: "Level 3 - Reliable",
    MATURITY_HIGHLY_RELIABLE: "Level 4 - Highly Reliable",
    MATURITY_AUTONOMOUS: "Level 5 - Autonomous Operations",
}

# ---------------------------------------------------------------------------
# Operations / automation policy
# ---------------------------------------------------------------------------
ACTION_SAFE = "safe"
ACTION_UNSAFE = "unsafe"

AUTOMATED_ACTIONS = (
    "restart_worker",
    "scale_pool",
    "retry_job",
    "failover",
    "drain_instance",
    "queue_non_critical",
    "rotate_credential",
)

UNSAFE_ACTIONS = ("failover", "drain_instance", "rotate_credential")

REMEDIATION_RESULT_PENDING = "pending"
REMEDIATION_RESULT_SUCCESS = "success"
REMEDIATION_RESULT_FAILED = "failed"
REMEDIATION_RESULT_SKIPPED = "skipped"
REMEDIATION_RESULT_ROLLED_BACK = "rolled_back"

# ---------------------------------------------------------------------------
# Maintenance windows
# ---------------------------------------------------------------------------
MAINTENANCE_SCHEDULED = "scheduled"
MAINTENANCE_IN_PROGRESS = "in_progress"
MAINTENANCE_COMPLETED = "completed"
MAINTENANCE_CANCELLED = "cancelled"

MAINTENANCE_STATUSES = (
    MAINTENANCE_SCHEDULED,
    MAINTENANCE_IN_PROGRESS,
    MAINTENANCE_COMPLETED,
    MAINTENANCE_CANCELLED,
)

# ---------------------------------------------------------------------------
# Traffic routing modes
# ---------------------------------------------------------------------------
TRAFFIC_REGION = "region"
TRAFFIC_HEALTH_BASED = "health"
TRAFFIC_LATENCY_BASED = "latency"
TRAFFIC_MAINTENANCE = "maintenance"
TRAFFIC_DRAINING = "draining"

TRAFFIC_MODES = (
    TRAFFIC_HEALTH_BASED,
    TRAFFIC_LATENCY_BASED,
    TRAFFIC_REGION,
    TRAFFIC_MAINTENANCE,
    TRAFFIC_DRAINING,
)

# ---------------------------------------------------------------------------
# Chaos experiment scopes
# ---------------------------------------------------------------------------
CHAOS_SCOPE_TEST = "test"
CHAOS_SCOPE_STAGING = "staging"
CHAOS_SCOPE_PROD_LIMITED = "prod-limited"

CHAOS_SCOPES = (CHAOS_SCOPE_TEST, CHAOS_SCOPE_STAGING, CHAOS_SCOPE_PROD_LIMITED)

CHAOS_PENDING = "pending"
CHAOS_RUNNING = "running"
CHAOS_PASSED = "passed"
CHAOS_FAILED = "failed"
CHAOS_ABORTED = "aborted"

CHAOS_STATUSES = (CHAOS_PENDING, CHAOS_RUNNING, CHAOS_PASSED, CHAOS_FAILED, CHAOS_ABORTED)

# ---------------------------------------------------------------------------
# Certificate statuses
# ---------------------------------------------------------------------------
CERT_VALID = "valid"
CERT_EXPIRING = "expiring"
CERT_EXPIRED = "expired"
CERT_FAILED = "failed"

CERT_STATUSES = (CERT_VALID, CERT_EXPIRING, CERT_EXPIRED, CERT_FAILED)

# Default warning window before expiry (days).
CERT_EXPIRY_WARNING_DAYS = 30

# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------
CAPACITY_ALERT_THRESHOLD_PERCENT = 80.0  # warn at this utilization
CAPACITY_CRITICAL_THRESHOLD_PERCENT = 95.0

# ---------------------------------------------------------------------------
# Default SLO targets by tier (availability fraction)
# ---------------------------------------------------------------------------
DEFAULT_SLO_TARGETS = {
    TIER_0: 0.9999,
    TIER_1: 0.9995,
    TIER_2: 0.999,
    TIER_3: 0.99,
}

# Default RTO/RPO (minutes) by tier.
DEFAULT_RTO_MINUTES = {TIER_0: 15, TIER_1: 60, TIER_2: 4 * 60, TIER_3: 24 * 60}
DEFAULT_RPO_MINUTES = {TIER_0: 5, TIER_1: 15, TIER_2: 60, TIER_3: 6 * 60}
