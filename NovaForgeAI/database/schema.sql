-- NovaForge AI - PostgreSQL 16 Schema
-- All tables use UUID primary keys, proper foreign keys with cascading deletes,
-- indexes on foreign keys and frequently queried columns, and automatic timestamps.

-- Enable uuid-ossp extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE users (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) NOT NULL,
    username        VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    avatar_url      VARCHAR(500),
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    is_verified     BOOLEAN     NOT NULL DEFAULT FALSE,
    is_superuser    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_users_email ON users (email);
CREATE UNIQUE INDEX uq_users_username ON users (username);
CREATE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_username ON users (username);

-- ============================================================
-- ORGANIZATIONS
-- ============================================================

CREATE TABLE organizations (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(100) NOT NULL,
    description VARCHAR(1000),
    avatar_url  VARCHAR(500),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_organizations_slug ON organizations (slug);
CREATE INDEX ix_organizations_slug ON organizations (slug);

-- ============================================================
-- USER_ORGANIZATIONS (junction table)
-- ============================================================

CREATE TABLE user_organizations (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, organization_id)
);

CREATE INDEX ix_user_organizations_user_id ON user_organizations (user_id);
CREATE INDEX ix_user_organizations_organization_id ON user_organizations (organization_id);

-- ============================================================
-- REPOSITORIES
-- ============================================================

CREATE TABLE repositories (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    full_name       VARCHAR(500) NOT NULL,
    description     VARCHAR(2000),
    private         BOOLEAN     NOT NULL DEFAULT TRUE,
    git_url         VARCHAR(500),
    default_branch  VARCHAR(100) NOT NULL DEFAULT 'main',
    language        VARCHAR(100),
    size            INTEGER,
    organization_id UUID        REFERENCES organizations(id) ON DELETE CASCADE,
    owner_id        UUID        REFERENCES users(id) ON DELETE SET NULL,
    last_indexed_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_repositories_organization_id ON repositories (organization_id);
CREATE INDEX ix_repositories_owner_id ON repositories (owner_id);

-- ============================================================
-- CONVERSATIONS
-- ============================================================

CREATE TABLE conversations (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    title       VARCHAR(500) NOT NULL DEFAULT 'New Conversation',
    session_id  VARCHAR(255) NOT NULL,
    user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_conversations_session_id ON conversations (session_id);
CREATE INDEX ix_conversations_user_id ON conversations (user_id);

-- ============================================================
-- MESSAGES
-- ============================================================

CREATE TABLE messages (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    role            message_role NOT NULL,
    content         TEXT        NOT NULL,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    metadata        JSONB,
    tokens_used     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);
CREATE INDEX ix_messages_role ON messages (role);

-- ============================================================
-- UPDATED_AT TRIGGER FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to tables with updated_at

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_repositories_updated_at
    BEFORE UPDATE ON repositories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
