#!/usr/bin/env bash
# NovaForge AI — Automated Backup Script
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "${BACKUP_PATH}"
echo "Starting backup to ${BACKUP_PATH}"

# PostgreSQL
echo "[1/4] Backing up PostgreSQL..."
PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" pg_dump \
    -h "${POSTGRES_HOST:-localhost}" \
    -U "${POSTGRES_USER:-postgres}" \
    -d "${POSTGRES_DB:-novaforge}" \
    -F c \
    -f "${BACKUP_PATH}/postgres.dump" \
    -v

# Redis
echo "[2/4] Backing up Redis..."
redis-cli -h "${REDIS_HOST:-localhost}" SAVE
cp /data/redis/dump.rdb "${BACKUP_PATH}/redis.rdb" 2>/dev/null || true

# Neo4j
echo "[3/4] Backing up Neo4j..."
neo4j-admin database dump neo4j --to-path="${BACKUP_PATH}/neo4j" 2>/dev/null || \
    echo "WARNING: Neo4j dump skipped (admin tool not available)"

# Qdrant
echo "[4/4] Backing up Qdrant snapshots..."
curl -X POST "http://${QDRANT_HOST:-localhost}:6333/collections/repository_chunks/snapshots" 2>/dev/null || \
    echo "WARNING: Qdrant snapshot skipped"

# Compress
echo "Compressing backup..."
tar -czf "${BACKUP_PATH}.tar.gz" -C "${BACKUP_DIR}" "${TIMESTAMP}"
rm -rf "${BACKUP_PATH}"

# Cleanup old backups
echo "Cleaning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "*.tar.gz" -type f -mtime +"${RETENTION_DAYS}" -delete

echo "Backup complete: ${BACKUP_PATH}.tar.gz"
