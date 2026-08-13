# Volume 31 — Enterprise Data Lakehouse & Analytics Platform

## Overview
Layered, tenant-isolated data infrastructure for NovaForge:
event ingestion → stream/batch processing → data lake/lakehouse → OLAP →
warehouse → semantic layer → analytics services → reporting/export, with
privacy, governance, retention, observability, anomaly detection and
forecasting built in.

## Module map (`backend/app/lakehouse/`)

| Module | Purpose |
|---|---|
| `event_model.py` | Standardized event envelope (Event, EventType, EventStore) with idempotency, dedup, replay |
| `ingestion.py` | IngestionPipeline: backpressure, retry, DLQ, checkpointing; SourceAdapter for REST/webhook/Kafka/CDC/batch |
| `stream_processing.py` | StreamProcessor: per-second metrics and rate tracking |
| `batch_processing.py` | BatchScheduler + AggregationEngine (daily/weekly/monthly) |
| `data_lake.py` | ObjectStore abstraction, partitioning (org/year/month/day), manifests, checksums |
| `lakehouse.py` | LakeTable: columnar JSON batches, partition pruning, compaction, snapshots, schema evolution |
| `olap.py` | AnalyticsEngine interface; in-memory/duckdb/postgres backends; QueryOptimizer |
| `warehouse.py` | Star-schema dimensions/facts definitions |
| `query_service.py` | AnalyticsQueryService: injection-safe QuerySpec, tenant guard, caching, pagination |
| `analytics_cache.py` | TTL cache + materialized views |
| `transformation.py` | Idempotent transforms (filter/map/aggregate) |
| `schema_registry.py`, `metadata_catalog.py` | Schema versioning and catalog entries |
| `data_quality.py`, `data_lineage.py` | Quality checks and lineage graph |
| `metric_registry.py` | MetricRegistry + SemanticLayer |
| `reporting.py`, `exports.py` | Report definitions; CSV/JSON/XLSX/Parquet/PDF export |
| `retention.py`, `archival.py` | Retention policies + archive ledger |
| `privacy.py`, `governance.py` | PII masking/RTBF; role-based access + audit trail |
| `data_observability.py` | Pipeline health, freshness, volume drift |
| `anomaly_detection.py`, `forecasting.py` | Statistical anomaly detection; naive/EMA/trend/seasonal forecasts |
| `ecommerce_analytics.py`, `ai_analytics.py`, `rag_analytics.py`, `agent_analytics.py`, `engineering_analytics.py`, `repository_analytics.py`, `org_analytics.py`, `finops.py`, `ai_roi.py` | Domain analytics services |
| `service.py` | `LakehouseService` — registered in the global registry under `lakehouse` |

## Wiring
- **CLI**: `python -m app.novaforge_cli health` — shows all 8 volumes (lakehouse included).
  Commands: `ingest <org> <event_type> [json]`, `query <org> <table> [group_by] [agg]`,
  `analytics <org> <kind>` (kinds: ecommerce, ai, rag, agents, finops).
- **API** (`app/api.py`): `/api/v1/lakehouse/events`, `/events/batch`, `/metrics`, `/batch`,
  `/tables`, `/query`, `/analytics/{kind}`, `/retention`.

## Tenant isolation
Every ingestion path and query runs through `TenantGuard`; events carry
`organization_id` and cross-tenant writes/reads are rejected. Table names in the
lakehouse are namespaced `{organization_id}__{table}`.

## Verification
```bash
cd backend
python -m app.novaforge_cli health                       # all_healthy (8 volumes)
python -m pytest ../tests/backend/test_lakehouse.py --confcutdir=../tests/backend -q
```

## Notes / design decisions
- No fabricated metrics: all analytics operate on recorded events or explicitly
  provided data; ROI requires an honest baseline or is flagged "not measurable".
- Default OLAP backend is in-memory (`WarehouseEngineFactory.create`); swap to
  duckdb/postgres by engine name.
- Retention defaults: raw_events 90d, aggregated 730d, ai_logs 180d,
  security_events 365d, audit 730d, analytics 1825d; configurable per dataset.
