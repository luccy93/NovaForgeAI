"""Data Warehouse models - star-schema dimensions, facts, and PostgreSQL DDL for the OLAP store."""
from typing import Optional


class Dimensions:
    """Dimension keys used across all facts (star schema)."""
    ORG = "dim_organization"
    WORKSPACE = "dim_workspace"
    PROJECT = "dim_project"
    REPOSITORY = "dim_repository"
    USER = "dim_user"
    TEAM = "dim_team"
    MODEL = "dim_model"
    PROVIDER = "dim_provider"
    AGENT = "dim_agent"
    ENVIRONMENT = "dim_environment"
    DEPLOYMENT = "dim_deployment"
    DATE = "dim_date"
    TIME = "dim_time"
    REGION = "dim_region"
    PLUGIN = "dim_plugin"
    ALL = [ORG, WORKSPACE, PROJECT, REPOSITORY, USER, TEAM, MODEL, PROVIDER,
           AGENT, ENVIRONMENT, DEPLOYMENT, DATE, TIME, REGION, PLUGIN]


class FactTable:
    """Fac table definitions (names registered in the warehouse)."""
    AI_USAGE = "fact_ai_usage"
    AGENT_EXECUTION = "fact_agent_execution"
    REPOSITORY_ACTIVITY = "fact_repository_activity"
    PULL_REQUEST = "fact_pull_request"
    DEPLOYMENT = "fact_deployment"
    SECURITY = "fact_security"
    TESTING = "fact_testing"
    INCIDENT = "fact_incident"
    INFRASTRUCTURE = "fact_infrastructure"
    SEARCH = "fact_search"
    EMBEDDING = "fact_embedding"
    BILLING = "fact_billing"
    COLLABORATION = "fact_collaboration"
    MARKETPLACE = "fact_marketplace"

    ALL = [AI_USAGE, AGENT_EXECUTION, REPOSITORY_ACTIVITY, PULL_REQUEST, DEPLOYMENT,
           SECURITY, TESTING, INCIDENT, INFRASTRUCTURE, SEARCH, EMBEDDING,
           BILLING, COLLABORATION, MARKETPLACE]


FACTS = {
    FactTable.AI_USAGE: ["organization_id", "date", "user_id", "model_id", "provider_id",
                         "request_type", "prompt_tokens", "completion_tokens", "embedding_tokens",
                         "cost", "latency_ms", "streaming", "context_size", "rag_used",
                         "citation_count", "failed"],
    FactTable.AGENT_EXECUTION: ["organization_id", "date", "agent_id", "workflow_id", "user_id",
                                "task", "duration_ms", "success", "retries", "tools_used",
                                "tokens", "cost", "model_id", "confidence", "approved",
                                "overridden"],
    FactTable.REPOSITORY_ACTIVITY: ["organization_id", "date", "repository_id", "event_type",
                                    "commits", "files_touched", "authors", "lines_added",
                                    "lines_removed"],
    FactTable.PULL_REQUEST: ["organization_id", "date", "repository_id", "user_id",
                             "state", "cycle_days", "review_hours", "reviewers",
                             "comments", "reviews", "additions", "deletions"],
    FactTable.DEPLOYMENT: ["organization_id", "date", "repository_id", "environment_id",
                           "deployment_id", "status", "duration_sec", "success",
                           "rollback", "strategy"],
    FactTable.SECURITY: ["organization_id", "date", "repository_id", "finding_id",
                         "category", "severity", "status", "time_to_remediate_days"],
    FactTable.TESTING: ["organization_id", "date", "repository_id", "suite", "tests",
                        "passed", "failed", "skipped", "flaky", "coverage", "duration_ms"],
    FactTable.INCIDENT: ["organization_id", "date", "service", "severity", "status",
                         "sealed_minutes", "detection_minutes", "open", "affected_users"],
    FactTable.INFRASTRUCTURE: ["organization_id", "date", "resource_type", "provider_id",
                               "region_id", "cpu", "memory", "gpu", "storage", "network",
                               "cost", "workers_used"],
    FactTable.SEARCH: ["organization_id", "date", "query_id", "query_type", "user_id",
                       "vector_msec", "bm25_msec", "hybrid", "reranked", "results",
                       "latency_ms", "top_k", "relevant_in_top10", "precision_at_k",
                       "mrr", "ndcg"],
    FactTable.EMBEDDING: ["organization_id", "date", "model_id", "operation", "count",
                          "tokens", "dimensions", "cost", "latency_ms", "cached"],
    FactTable.BILLING: ["organization_id", "date", "workspace_id", "project_id",
                        "repository_id", "user_id", "category", "amount", "currency",
                        "quantity", "unit_price"],
    FactTable.COLLABORATION: ["organization_id", "date", "workspace_id", "user_id",
                              "channel", "kind", "count", "participants"],
    FactTable.MARKETPLACE: ["organization_id", "date", "plugin_id", "item_kind",
                            "action", "quantity", "revenue", "organization_admin"],
}

DIM_NAMES = ["dim_organization", "dim_workspace", "dim_project", "dim_repository",
             "dim_user", "dim_team", "dim_model", "dim_provider", "dim_agent",
             "dim_environment", "dim_deployment", "dim_date", "dim_time",
             "dim_region", "dim_plugin"]

warehouse_tables = DIM_NAMES + FactTable.ALL


class WarehouseDDL:
    """PostgreSQL DDL for the star-schema warehouse (dimensions + facts)."""

    DIMS: dict[str, list[str]] = {
        "dim_organization": ["id varchar primary key", "name varchar", "plan varchar", "created_date varchar"],
        "dim_workspace": ["id varchar primary key", "organization_id varchar", "name varchar"],
        "dim_project": ["id varchar primary key", "organization_id varchar", "name varchar"],
        "dim_repository": ["id varchar primary key", "organization_id varchar",
                           "name varchar", "language varchar", "is_archived boolean"],
        "dim_user": ["id varchar primary key", "organization_id varchar", "email varchar", "role varchar"],
        "dim_team": ["id varchar primary key", "organization_id varchar", "name varchar"],
        "dim_model": ["id varchar primary key", "name varchar", "provider_id varchar", "params varchar"],
        "dim_provider": ["id varchar primary key", "name varchar"],
        "dim_agent": ["id varchar primary key", "organization_id varchar", "name varchar", "kind varchar"],
        "dim_environment": ["id varchar primary key", "name varchar", "type varchar"],
        "dim_deployment": ["id varchar primary key", "organization_id varchar", "name varchar"],
        "dim_date": ["date varchar primary key", "year int", "month int", "day int", "iso_week int"],
        "dim_time": ["time_id varchar primary key", "hour int", "minute int"],
        "dim_region": ["id varchar primary key", "name varchar", "cloud varchar"],
        "dim_plugin": ["id varchar primary key", "name varchar", "kind varchar"],
    }

    @staticmethod
    def build_ddl() -> dict[str, str]:
        """Renders idempotent CREATE TABLE IF NOT EXISTS statements for the warehouse."""
        statements = {}
        for name, cols in WarehouseDDL.DIMS.items():
            statements[name] = f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(cols)});"
        for name, cols in FACTS.items():
            col_sql = ", ".join([f"{c} varchar" for c in cols])
            statements[name] = f"CREATE TABLE IF NOT EXISTS {name} ({col_sql});"
        return statements


class DimensionScaffold:
    """Scaffolds SCD-0 dimensions in the OLAP engine with tenant isolation."""

    @staticmethod
    def row(dim: str, values: dict[str, object]) -> dict:
        base = {"dim_kind": dim, "organization_id": values.get("organization_id", ""),
                "ref_id": values.get("id", ""), "created_at": values.get("created_at", "")}
        for k in ("name", "email", "role", "plan", "language"):
            if k in values:
                base[k] = values[k]
        return base


class FactScaffold:
    """Builds fact rows from events in a deterministic way per tenant."""

    @staticmethod
    def from_event(event: dict) -> list[dict]:
        """Routes an event to its fact rows deterministically from its payload."""
        cat = event.get("category", "")
        payload = event.get("payload") or {}
        org = event.get("organization_id", "")
        date = (event.get("timestamp", "") or "")[:10]
        common = {"organization_id": org, "date": date,
                  "repository_id": event.get("repository_id", ""),
                  "user_id": event.get("user_id", "")}
        rows: list[dict] = []
        if cat == "ai_request" or cat == "ai_response":
            rows.append(dict(**common, **payload))
        elif cat == "agent":
            rows.append(dict(**common, **payload))
        elif cat == "repository":
            rows.append(dict(**common, **payload))
        elif cat == "pull_request":
            rows.append(dict(**common, **payload))
        elif cat == "deployment":
            rows.append(dict(**common, **payload))
        elif cat == "security":
            rows.append(dict(**common, **payload))
        elif cat == "test":
            rows.append(dict(**common, **payload))
        elif cat == "incident":
            rows.append(dict(**common, **payload))
        elif cat == "infrastructure":
            rows.append(dict(**common, **payload))
        elif cat == "rag_search":
            rows.append(dict(**common, **payload))
        elif cat == "embedding":
            rows.append(dict(**common, **payload))
        elif cat == "billing":
            rows.append(dict(**common, **payload))
        elif cat == "collaboration" or cat == "workspace":
            rows.append(dict(**common, **payload))
        elif cat == "marketplace":
            rows.append(dict(**common, **payload))
        return rows