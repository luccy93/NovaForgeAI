"""Indexing strategy for all databases.

Defines indexes, key naming, and query optimization patterns.
"""

# ═══════════════════════════════════════════════════════════════════════
# POSTGRESQL INDEXING STRATEGY
# ═══════════════════════════════════════════════════════════════════════

POSTGRES_INDEXES = {
    "users": [
        "idx_users_email ON users (email)",
        "idx_users_username ON users (username)",
        "idx_users_email_lower ON users (LOWER(email))",
        "idx_users_created_at ON users (created_at)",
    ],
    "organizations": [
        "idx_orgs_slug ON organizations (slug)",
        "idx_orgs_created_at ON organizations (created_at)",
    ],
    "user_organizations": [
        "idx_user_orgs_user_id ON user_organizations (user_id)",
        "idx_user_orgs_org_id ON user_organizations (organization_id)",
    ],
    "repositories": [
        "idx_repos_org_id ON repositories (organization_id)",
        "idx_repos_full_name ON repositories (full_name)",
        "idx_repos_language ON repositories (language)",
        "idx_repos_updated_at ON repositories (updated_at)",
        "idx_repos_org_lang ON repositories (organization_id, language)",
    ],
    "messages": [
        "idx_messages_conversation_id ON messages (conversation_id)",
        "idx_messages_role ON messages (role)",
        "idx_messages_created_at ON messages (created_at)",
    ],
    "conversations": [
        "idx_conversations_user_id ON conversations (user_id)",
        "idx_conversations_session_id ON conversations (session_id)",
        "idx_conversations_org_id ON conversations (organization_id)",
        "idx_conversations_updated_at ON conversations (updated_at)",
    ],
    "commits": [
        "idx_commits_repo_id ON commits (repository_id)",
        "idx_commits_sha ON commits (sha)",
        "idx_commits_authored_at ON commits (authored_at)",
        "idx_commits_repo_author ON commits (repository_id, author_email)",
    ],
    "branches": [
        "idx_branches_repo_id ON branches (repository_id)",
        "idx_branches_repo_name ON branches (repository_id, name)",
    ],
    "audit_logs": [
        "idx_audit_org_id ON audit_logs (organization_id)",
        "idx_audit_action ON audit_logs (action)",
        "idx_audit_created_at ON audit_logs (created_at)",
        "idx_audit_user_action ON audit_logs (user_id, action)",
    ],
    "agent_runs": [
        "idx_agent_runs_org_id ON agent_runs (organization_id)",
        "idx_agent_runs_status ON agent_runs (status)",
        "idx_agent_runs_agent ON agent_runs (agent_name)",
        "idx_agent_runs_created_at ON agent_runs (created_at)",
    ],
    "usage_records": [
        "idx_usage_org_id ON usage_records (organization_id)",
        "idx_usage_metric ON usage_records (metric)",
        "idx_usage_recorded_at ON usage_records (recorded_at)",
        "idx_usage_org_metric ON usage_records (organization_id, metric)",
    ],
    "analytics_events": [
        "idx_analytics_org_id ON analytics_events (organization_id)",
        "idx_analytics_type ON analytics_events (event_type)",
        "idx_analytics_created_at ON analytics_events (created_at)",
    ],
    "security_reports": [
        "idx_security_repo_id ON security_reports (repository_id)",
        "idx_security_status ON security_reports (status)",
    ],
    "api_keys": [
        "idx_api_keys_user_id ON api_keys (user_id)",
        "idx_api_keys_prefix ON api_keys (key_prefix)",
    ],
    "notifications": [
        "idx_notifications_user_id ON notifications (user_id)",
        "idx_notifications_read ON notifications (user_id, is_read)",
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# NEO4J INDEXING STRATEGY
# ═══════════════════════════════════════════════════════════════════════

NEO4J_INDEXES = [
    "CREATE INDEX neo_repo_id IF NOT EXISTS FOR (n:Repository) ON (n.id)",
    "CREATE INDEX neo_file_path IF NOT EXISTS FOR (n:File) ON (n.path)",
    "CREATE INDEX neo_func_name IF NOT EXISTS FOR (n:Function) ON (n.name)",
    "CREATE INDEX neo_class_name IF NOT EXISTS FOR (n:Class) ON (n.name)",
    "CREATE INDEX neo_commit_sha IF NOT EXISTS FOR (n:Commit) ON (n.sha)",
    "CREATE VECTOR INDEX neo_code_embeddings IF NOT EXISTS FOR (n:Function) ON (n.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
]

# ═══════════════════════════════════════════════════════════════════════
# QDRANT PAYLOAD INDEXES
# ═══════════════════════════════════════════════════════════════════════

# See app/core/qdrant_schema.py for per-collection payload indexes
# Summary:
# - repository_chunks: repository_id, file_path, language, chunk_type, branch, hash
# - documentation_chunks: repository_id, doc_type, language
# - conversation_memory: conversation_id, user_id, role
# - architecture_chunks: repository_id, node_type
# - security_chunks: repository_id, severity, scan_type

# ═══════════════════════════════════════════════════════════════════════
# REDIS KEY NAMESPACES & TTL
# ═══════════════════════════════════════════════════════════════════════

REDIS_TTL = {
    # Cache
    "cache:repo:*": 300,           # 5 min
    "cache:user:*": 600,           # 10 min
    "cache:org:*": 300,            # 5 min
    "cache:search:*": 60,          # 1 min
    "cache:prompt:*": 3600,        # 1 hour
    "cache:embedding:*": 86400,    # 24 hours

    # Rate Limiting
    "ratelimit:*": 60,             # 1 min window

    # Sessions
    "session:*": 3600,             # 1 hour

    # Blacklist
    "blacklist:*": 3600,           # 1 hour

    # Locks
    "lock:*": 30,                  # 30 seconds

    # Queues
    "queue:*": 86400,              # 24 hours
}

# ═══════════════════════════════════════════════════════════════════════
# QUERY OPTIMIZATION PATTERNS
# ═══════════════════════════════════════════════════════════════════════

QUERY_PATTERNS = {
    "pagination": "Always use LIMIT/OFFSET or cursor-based pagination. Never SELECT without limit.",
    "n_plus_1": "Use eager loading (selectinload, joinedload) to avoid N+1 queries.",
    "batch_insert": "Use bulk_insert_mappings for batch operations. Never insert in loops.",
    "async": "Use async session for all database operations. Never block the event loop.",
    "connection_pool": "Pool size=20, max_overflow=10, pool_recycle=3600s.",
    "read_replicas": "Route read-only queries to replicas when available.",
    "prepared_statements": "SQLAlchemy uses prepared statements by default. Keep it enabled.",
}
