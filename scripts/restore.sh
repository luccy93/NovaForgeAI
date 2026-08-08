#!/usr/bin/env bash
# NovaForge AI — Automated Restore Script
set -euo pipefail

BACKUP_FILE="${1:-}"
if [ -z "${BACKUP_FILE}" ]; then
    echo "Usage: $0 <backup-file.tar.gz>"
    exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

RESTORE_DIR=$(mktemp -d)
echo "Restoring from ${BACKUP_FILE}"

tar -xzf "${BACKUP_FILE}" -C "${RESTORE_DIR}"
BACKUP_CONTENT=$(find "${RESTORE_DIR}" -type f)

# PostgreSQL
PG_BACKUP=$(find "${RESTORE_DIR}" -name "postgres.dump")
if [ -n "${PG_BACKUP}" ]; then
    echo "[1/4] Restoring PostgreSQL..."
    PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" pg_restore \
        -h "${POSTGRES_HOST:-localhost}" \
        -U "${POSTGRES_USER:-postgres}" \
        -d "${POSTGRES_DB:-novaforge}" \
        --clean \
        --if-exists \
        "${PG_BACKUP}"
fi

# Redis
REDIS_BACKUP=$(find "${RESTORE_DIR}" -name "redis.rdb")
if [ -n "${REDIS_BACKUP}" ]; then
    echo "[2/4] Restoring Redis..."
    cp "${REDIS_BACKUP}" /data/redis/dump.rdb
    redis-cli -h "${REDIS_HOST:-localhost}" FLUSHALL
    redis-cli -h "${REDIS_HOST:-localhost}" SAVE
fi

# Neo4j
NEO4J_BACKUP=$(find "${RESTORE_DIR}" -name "neo4j.dump" -o -path "*/neo4j/*")
if [ -n "${NEO4J_BACKUP}" ]; then
    echo "[3/4] Restoring Neo4j..."
    neo4j-admin database load neo4j --from-path="${NEO4J_BACKUP}" 2>/dev/null || \
        echo "WARNING: Neo4j restore skipped"
fi

echo "Restore complete. Restart services."
rm -rf "${RESTORE_DIR}"
