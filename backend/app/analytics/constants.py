"""Unified Analytics Platform -- Constants (Volume 50)."""

ANALYTICS_SCHEMA_VERSION = "1.0"
ANALYTICS_EVENT_VERSION = 1
ANALYTICS_METRIC_VERSION = 1

# ── Data Categories ────────────────────────────────────────────────────
CAT_PLATFORM = "platform"
CAT_AI = "ai"
CAT_ENGINEERING = "engineering"
CAT_SECURITY = "security"
CAT_INCIDENTS = "incidents"
CAT_MARKETPLACE = "marketplace"
CAT_CICD = "cicd"
CAT_COST = "cost"
CAT_QUALITY = "quality"
CAT_RELIABILITY = "reliability"

CATEGORIES = (CAT_PLATFORM, CAT_AI, CAT_ENGINEERING, CAT_SECURITY,
              CAT_INCIDENTS, CAT_MARKETPLACE, CAT_CICD, CAT_COST,
              CAT_QUALITY, CAT_RELIABILITY)

# ── Aggregation Types ──────────────────────────────────────────────────
AGG_SUM = "sum"
AGG_AVG = "avg"
AGG_MIN = "min"
AGG_MAX = "max"
AGG_COUNT = "count"
AGG_P50 = "p50"
AGG_P90 = "p90"
AGG_P95 = "p95"
AGG_P99 = "p99"
AGG_RATE = "rate"
AGG_UNIQUE = "unique"

AGGREGATION_TYPES = (AGG_SUM, AGG_AVG, AGG_MIN, AGG_MAX, AGG_COUNT,
                     AGG_P50, AGG_P90, AGG_P95, AGG_P99, AGG_RATE, AGG_UNIQUE)

# ── Granularity ────────────────────────────────────────────────────────
GRANULARITY_MINUTE = "minute"
GRANULARITY_HOUR = "hour"
GRANULARITY_DAY = "day"
GRANULARITY_WEEK = "week"
GRANULARITY_MONTH = "month"

GRANULARITIES = (GRANULARITY_MINUTE, GRANULARITY_HOUR, GRANULARITY_DAY,
                 GRANULARITY_WEEK, GRANULARITY_MONTH)

GRANULARITY_SECONDS = {
    GRANULARITY_MINUTE: 60,
    GRANULARITY_HOUR: 3600,
    GRANULARITY_DAY: 86400,
    GRANULARITY_WEEK: 604800,
    GRANULARITY_MONTH: 2592000,
}

# ── Cost Types ─────────────────────────────────────────────────────────
COST_MODEL = "model"
COST_COMPUTE = "compute"
COST_STORAGE = "storage"
COST_NETWORK = "network"
COST_CI_MINUTES = "ci_minutes"
COST_ARTIFACT = "artifact"
COST_EXTERNAL = "external"
COST_TOTAL = "total"

COST_TYPES = (COST_MODEL, COST_COMPUTE, COST_STORAGE, COST_NETWORK,
              COST_CI_MINUTES, COST_ARTIFACT, COST_EXTERNAL, COST_TOTAL)

CURRENCY_USD = "USD"

# ── Budget Status ──────────────────────────────────────────────────────
BUDGET_OK = "ok"
BUDGET_WARNING = "warning"
BUDGET_SOFT_LIMIT = "soft_limit"
BUDGET_HARD_LIMIT = "hard_limit"

BUDGET_STATUSES = (BUDGET_OK, BUDGET_WARNING, BUDGET_SOFT_LIMIT, BUDGET_HARD_LIMIT)

# ── Recommendation Priority ───────────────────────────────────────────
REC_LOW = "low"
REC_MEDIUM = "medium"
REC_HIGH = "high"
REC_CRITICAL = "critical"

# ── Report Types ───────────────────────────────────────────────────────
REPORT_EXECUTIVE = "executive"
REPORT_ENGINEERING = "engineering"
REPORT_AI_USAGE = "ai_usage"
REPORT_FINOPS = "finops"
REPORT_SECURITY = "security"
REPORT_SRE = "sre"
REPORT_CICD = "cicd"
REPORT_MARKETPLACE = "marketplace"

REPORT_TYPES = (REPORT_EXECUTIVE, REPORT_ENGINEERING, REPORT_AI_USAGE,
                REPORT_FINOPS, REPORT_SECURITY, REPORT_SRE,
                REPORT_CICD, REPORT_MARKETPLACE)

# ── Export Formats ─────────────────────────────────────────────────────
FORMAT_JSON = "json"
FORMAT_CSV = "csv"
FORMAT_PDF = "pdf"

EXPORT_FORMATS = (FORMAT_JSON, FORMAT_CSV, FORMAT_PDF)

# ── Anomaly Severity ──────────────────────────────────────────────────
ANOMALY_LOW = "low"
ANOMALY_MEDIUM = "medium"
ANOMALY_HIGH = "high"
ANOMALY_CRITICAL = "critical"

# ── Event Sources (normalized) ────────────────────────────────────────
SOURCE_PLATFORM = "platform"
SOURCE_AI = "ai"
SOURCE_RAG = "rag"
SOURCE_AGENT = "agent"
SOURCE_CODE_INTEL = "code_intelligence"
SOURCE_CICD = "cicd"
SOURCE_SECURITY = "security"
SOURCE_MARKETPLACE = "marketplace"
SOURCE_INCIDENT = "incident"
SOURCE_DEPLOYMENT = "deployment"
SOURCE_INFRA = "infrastructure"
SOURCE_API_GATEWAY = "api_gateway"
SOURCE_SDK = "sdk"
SOURCE_CLI = "cli"
SOURCE_MANUAL = "manual"

# ── Data Quality Issue Types ──────────────────────────────────────────
DQ_MISSING_EVENT = "missing_event"
DQ_DUPLICATE_EVENT = "duplicate_event"
DQ_INVALID_TIMESTAMP = "invalid_timestamp"
DQ_SCHEMA_MISMATCH = "schema_mismatch"
DQ_NEGATIVE_COST = "negative_cost"
DQ_IMPOSSIBLE_DURATION = "impossible_duration"
DQ_ORPHAN_RESOURCE = "orphan_resource"
DQ_MISSING_VALUE = "missing_value"

# ── DORA Metrics ──────────────────────────────────────────────────────
DORA_DEPLOYMENT_FREQUENCY = "deployment_frequency"
DORA_LEAD_TIME = "lead_time"
DORA_CHANGE_FAILURE_RATE = "change_failure_rate"
DORA_MTTR = "mttr"
