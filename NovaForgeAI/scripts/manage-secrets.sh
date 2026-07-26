#!/usr/bin/env bash
# NovaForge AI — Secret Management
set -euo pipefail

SECRETS_FILE="${SECRETS_FILE:-.secrets.env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

generate_secret() {
    openssl rand -hex 32
}

generate_password() {
    openssl rand -base64 24
}

validate_secrets() {
    local errors=0
    
    if [ -z "${JWT_SECRET:-}" ]; then
        echo "ERROR: JWT_SECRET is not set"
        errors=$((errors + 1))
    elif [ "${#JWT_SECRET}" -lt 32 ]; then
        echo "ERROR: JWT_SECRET must be at least 32 characters"
        errors=$((errors + 1))
    fi
    
    if [ -z "${POSTGRES_PASSWORD:-}" ]; then
        echo "ERROR: POSTGRES_PASSWORD is not set"
        errors=$((errors + 1))
    fi
    
    return "${errors}"
}

init_secrets() {
    if [ -f "${SECRETS_FILE}" ]; then
        echo "ERROR: ${SECRETS_FILE} already exists. Remove it first to regenerate."
        exit 1
    fi
    
    cat > "${SECRETS_FILE}" << EOF
# NovaForge AI — Secrets
# WARNING: Keep this file secure. Never commit to git.

# JWT
JWT_SECRET=$(generate_secret)

# PostgreSQL
POSTGRES_PASSWORD=$(generate_password)

# Redis
REDIS_PASSWORD=$(generate_password)

# Neo4j
NEO4J_PASSWORD=$(generate_password)

# Qdrant (no auth by default)

# Encryption
ENCRYPTION_KEY=$(generate_secret)
EOF
    
    chmod 600 "${SECRETS_FILE}"
    echo "Secrets written to ${SECRETS_FILE}"
}

load_secrets() {
    if [ -f "${SECRETS_FILE}" ]; then
        set -a
        source "${SECRETS_FILE}"
        set +a
        echo "Secrets loaded from ${SECRETS_FILE}"
    else
        echo "WARNING: ${SECRETS_FILE} not found"
    fi
}

case "${1:-}" in
    init)
        init_secrets
        ;;
    validate)
        validate_secrets
        ;;
    load)
        load_secrets
        ;;
    *)
        echo "Usage: $0 {init|validate|load}"
        exit 1
        ;;
esac
