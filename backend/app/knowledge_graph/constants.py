"""Knowledge Graph constants (Volume 51)."""
from __future__ import annotations

from enum import Enum


class EntityType(str, Enum):
    """Node types in the unified organizational knowledge graph."""

    ORGANIZATION = "organization"
    WORKSPACE = "workspace"
    PROJECT = "project"
    TEAM = "team"
    USER = "user"
    REPOSITORY = "repository"
    BRANCH = "branch"
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    FILE = "file"
    SYMBOL = "symbol"
    PACKAGE = "package"
    DEPENDENCY = "dependency"
    SERVICE = "service"
    API_ENDPOINT = "api_endpoint"
    DATABASE = "database"
    QUEUE = "queue"
    ENVIRONMENT = "environment"
    DEPLOYMENT = "deployment"
    ARTIFACT = "artifact"
    PIPELINE = "pipeline"
    INCIDENT = "incident"
    SLO = "slo"
    SECURITY_FINDING = "security_finding"
    DOCUMENT = "document"
    AGENT = "agent"
    TOOL = "tool"
    WORKFLOW = "workflow"
    MODEL = "model"
    PROVIDER = "provider"
    MARKETPLACE_PACKAGE = "marketplace_package"
    RUNBOOK = "runbook"


class RelationshipType(str, Enum):
    """Edge types in the unified organizational knowledge graph."""

    OWNS = "OWNS"
    MAINTAINS = "MAINTAINS"
    CONTAINS = "CONTAINS"
    DEPENDS_ON = "DEPENDS_ON"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    IMPLEMENTS = "IMPLEMENTS"
    TESTS = "TESTS"
    DOCUMENTS = "DOCUMENTS"
    DEPLOYS = "DEPLOYS"
    BUILDS = "BUILDS"
    AFFECTS = "AFFECTS"
    CAUSED_BY = "CAUSED_BY"
    FIXES = "FIXES"
    USES = "USES"
    RUNS_ON = "RUNS_ON"
    TRIGGERS = "TRIGGERS"
    REQUIRES = "REQUIRES"
    APPROVES = "APPROVES"
    MEMBER_OF = "MEMBER_OF"
    RELATED_TO = "RELATED_TO"
    EXPOSES = "EXPOSES"
    PRODUCES = "PRODUCES"
    CONSUMES = "CONSUMES"
    GOVERNS = "GOVERNS"


class Confidence(str, Enum):
    """Confidence level assigned to entities and relationships."""

    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    POSSIBLE = "POSSIBLE"
    UNKNOWN = "UNKNOWN"


class OwnershipType(str, Enum):
    """How ownership of a graph entity was established."""

    CODEOWNER = "CODEOWNER"
    MAINTAINER = "MAINTAINER"
    TEAM_OWNER = "TEAM_OWNER"
    SERVICE_OWNER = "SERVICE_OWNER"
    PROJECT_OWNER = "PROJECT_OWNER"


class EvidenceSource(str, Enum):
    """Origin of evidence supporting an entity or relationship."""

    GIT = "git"
    CONFIGURATION = "configuration"
    API_METADATA = "api_metadata"
    DEPLOYMENT_METADATA = "deployment_metadata"
    OWNERSHIP_METADATA = "ownership_metadata"
    DOCUMENT_REFERENCE = "document_reference"
    EVENT_BUS = "event_bus"
    ADMINISTRATOR_ASSIGNMENT = "administrator_assignment"
    CODE_ANALYSIS = "code_analysis"
    SECURITY_SCAN = "security_scan"
    INCIDENT_DATA = "incident_data"
    ANALYTICS_DATA = "analytics_data"


class GraphTraversalType(str, Enum):
    """Supported graph traversal algorithms."""

    BFS = "BFS"
    DFS = "DFS"
    SHORTEST_PATH = "SHORTEST_PATH"
    ALL_PATHS = "ALL_PATHS"
    IMPACT_PATH = "IMPACT_PATH"
    DEPENDENCY_PATH = "DEPENDENCY_PATH"


class EntityStatus(str, Enum):
    """Lifecycle status of a graph entity."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class TemporalMode(str, Enum):
    """Temporal view mode for graph queries."""

    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"


class SyncStatus(str, Enum):
    """Status of a graph synchronization run."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class QualityIssueType(str, Enum):
    """Categories of data quality issues in the graph."""

    ORPHAN_NODE = "ORPHAN_NODE"
    DUPLICATE_ENTITY = "DUPLICATE_ENTITY"
    INVALID_EDGE = "INVALID_EDGE"
    STALE_RELATIONSHIP = "STALE_RELATIONSHIP"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    CONFLICTING_OWNERSHIP = "CONFLICTING_OWNERSHIP"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"


class IngestionSource(str, Enum):
    """Upstream sources that feed the knowledge graph."""

    GIT_EVENTS = "git_events"
    REPOSITORY_INDEXING = "repository_indexing"
    RAG_INGESTION = "rag_ingestion"
    DEPLOYMENT_EVENTS = "deployment_events"
    CICD_EVENTS = "cicd_events"
    SECURITY_EVENTS = "security_events"
    INCIDENT_EVENTS = "incident_events"
    MARKETPLACE_EVENTS = "marketplace_events"
    IDENTITY_EVENTS = "identity_events"
    ANALYTICS_EVENTS = "analytics_events"
    MANUAL_ASSIGNMENT = "manual_assignment"
    CONFIGURATION_FILE = "configuration_file"


DEFAULT_TENANT = "default"
MAXTraversalDepth = 10
DEFAULTTraversalDepth = 3
MAXResultLimit = 1000
DEFAULTResultLimit = 100
MAXPathLength = 20
MAXBlastRadiusDepth = 5
STALE_THRESHOLD_DAYS = 90
SNAPSHOT_RETENTION_DAYS = 365
ENTITY_SEARCH_MIN_SCORE = 0.3
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500
