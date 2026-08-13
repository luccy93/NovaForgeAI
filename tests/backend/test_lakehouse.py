"""Volume 31 tests - Enterprise Data Lakehouse & Analytics Platform."""
import asyncio
import pytest


def _svc():
    from app.lakehouse.service import svc
    return svc


# ─── Event model & ingestion ───────────────────────────────────────────

class TestEventModel:
    def test_event_defaults(self):
        from app.lakehouse.event_model import Event
        e = Event(event_type="commit.pushed", organization_id="org-1")
        assert e.event_id
        assert e.correlation_id == e.event_id
        assert e.is_valid()

    def test_event_rejects_unknown_type(self):
        from app.lakehouse.event_model import Event
        e = Event(event_type="made_up.event", organization_id="org-1")
        assert not e.is_valid()

    def test_store_dedup(self):
        from app.lakehouse.event_model import Event, EventStore
        store = EventStore()
        e = Event(event_type="commit.pushed", organization_id="org-1")
        assert store.append(e) is True
        assert store.append(e) is False
        assert store.count() == 1
        assert store.duplicates_rejected == 1

    def test_store_replay(self):
        from app.lakehouse.event_model import Event, EventStore
        store = EventStore()
        for i in range(3):
            store.append(Event(event_type="commit.pushed", organization_id="org-1",
                               payload={"n": i}))
        replayed = store.replay(1)
        assert len(replayed) == 2
        assert replayed[0]["payload"]["n"] == 1


class TestIngestion:
    def test_pipeline_accepts_and_stores(self):
        from app.lakehouse.event_model import Event
        from app.lakehouse.ingestion import IngestionPipeline
        pipe = IngestionPipeline()
        result = pipe.ingest({"event_type": "commit.pushed", "organization_id": "org-1"})
        assert result.accepted is True
        assert pipe.drain_queue() == 1
        assert pipe.store.count() == 1

    def test_backpressure(self):
        from app.lakehouse.event_model import Event
        from app.lakehouse.ingestion import IngestionPipeline
        pipe = IngestionPipeline(max_queue=2)
        for _ in range(5):
            pipe.enqueue(Event(event_type="commit.pushed", organization_id="org-1"))
        assert pipe.overload_dropped == 3

    def test_dlq_catches_failures(self):
        from app.lakehouse.event_model import Event, EventStore
        from app.lakehouse.ingestion import IngestionPipeline

        class BrokenStore(EventStore):
            def append(self, event):
                raise RuntimeError("store down")

        pipe = IngestionPipeline(store=BrokenStore(), max_retries=1, retry_backoff=0)
        pipe.enqueue(Event(event_type="commit.pushed", organization_id="org-1"))
        pipe.drain_queue()
        assert len(pipe.dlq) == 1
        assert pipe.failed == 1

    def test_tenant_check_on_batch(self):
        from app.lakehouse.ingestion import IngestionPipeline, SourceAdapter
        pipe = IngestionPipeline()
        adapter = SourceAdapter(pipe)
        results = adapter.from_batch(
            [{"event_type": "commit.pushed", "organization_id": "org-1"}],
            check_tenant=True)
        assert results[0].accepted is True


# ─── Lakehouse tables ──────────────────────────────────────────────────

class TestLakehouse:
    def test_write_scan_compact(self, tmp_path):
        from app.lakehouse.lakehouse import Lakehouse, Schema, ColumnSpec
        lake = Lakehouse(str(tmp_path))
        schema = Schema("events", [ColumnSpec("organization_id", "string", nullable=False),
                                   ColumnSpec("amount", "float")])
        table = lake.create_table("org-1__sales", schema)
        result = table.write_batch([
            {"organization_id": "org-1", "amount": 10.5},
            {"organization_id": "org-1", "amount": 20.0},
            {"organization_id": "org-1"},  # rejected: amount null but nullable, so ok
        ])
        assert result["rows_written"] == 3
        assert table.scan() and len(table.scan()) == 3
        assert table.scan({"amount": 10.5}) == [{"organization_id": "org-1", "amount": 10.5}]
        table.compact()
        assert len(table.files) == 1
        assert len(table.scan()) == 3

    def test_schema_validation_rejects_bad_rows(self, tmp_path):
        from app.lakehouse.lakehouse import Lakehouse, Schema, ColumnSpec
        lake = Lakehouse(str(tmp_path))
        schema = Schema("t", [ColumnSpec("organization_id", "string", nullable=False),
                              ColumnSpec("amount", "float")])
        table = lake.create_table("t", schema)
        result = table.write_batch([{"organization_id": None, "amount": "x"}])
        assert result["rows_written"] == 0
        assert len(result["rejected"]) == 1

    def test_partition_pruning(self, tmp_path):
        from app.lakehouse.lakehouse import Lakehouse, Schema, ColumnSpec
        lake = Lakehouse(str(tmp_path))
        schema = Schema("e", [ColumnSpec("organization_id", "string", nullable=False),
                              ColumnSpec("region", "string")])
        table = lake.create_table("e", schema, partition_cols=("region",))
        table.write_batch([
            {"organization_id": "o", "region": "us"},
            {"organization_id": "o", "region": "eu"},
        ])
        assert len(table.scan(partition={"region": "us"})) == 1


# ─── OLAP + query service ──────────────────────────────────────────────

class TestOLAPQuery:
    def test_group_by_and_query(self):
        from app.lakehouse.olap import InMemoryAnalytics
        from app.lakehouse.query_service import AnalyticsQueryService, QuerySpec
        olap = InMemoryAnalytics()
        olap.register_table("sales", [
            {"organization_id": "o1", "region": "us", "amount": 10},
            {"organization_id": "o1", "region": "eu", "amount": 20},
            {"organization_id": "o2", "region": "us", "amount": 5},
        ])
        qs = AnalyticsQueryService(olap)
        result = qs.run(QuerySpec("sales", organization_id="o1",
                                  groups=["region"], aggregations={"total": "sum:amount"}))
        assert result["total"] == 2
        assert {r["region"] for r in result["rows"]} == {"us", "eu"}

    def test_tenant_guard(self):
        from app.lakehouse.query_service import TenantGuard, QuerySpec, AnalyticsQueryService
        from app.lakehouse.olap import InMemoryAnalytics
        olap = InMemoryAnalytics()
        olap.register_table("t", [{"organization_id": "o1", "v": 1}])
        guard = TenantGuard({"o1"})
        qs = AnalyticsQueryService(olap, guard=guard)
        with pytest.raises(PermissionError):
            qs.run(QuerySpec("t", organization_id="o2"))

    def test_cache_hit(self):
        from app.lakehouse.olap import InMemoryAnalytics
        from app.lakehouse.query_service import AnalyticsQueryService, QuerySpec
        from app.lakehouse.analytics_cache import AnalyticsCache
        olap = InMemoryAnalytics()
        olap.register_table("t", [{"organization_id": "o1", "v": 7}])
        qs = AnalyticsQueryService(olap, cache=AnalyticsCache())
        first = qs.run(QuerySpec("t", organization_id="o1"))
        second = qs.run(QuerySpec("t", organization_id="o1"))
        assert second["cached"] is True
        assert first["rows"] == second["rows"]


# ─── Anomaly / forecasting ─────────────────────────────────────────────

class TestAnomalyAndForecast:
    def test_anomaly_detected(self):
        from app.lakehouse.anomaly_detection import AnomalyEngine
        engine = AnomalyEngine()
        series = {"cpu": [30, 31, 29, 32, 30, 31, 30, 29, 31, 30, 95.0]}
        report = engine.run(series)
        assert report["anomaly_count"] >= 1

    def test_forecast_horizon(self):
        from app.lakehouse.forecasting import ForecastEngine
        engine = ForecastEngine()
        series = [10 + i % 5 for i in range(60)]
        result = engine.forecast("load", series, horizon=10)
        assert len(result["forecast"]) == 10
        assert result["metric"] == "load"


# ─── Privacy / governance / retention ──────────────────────────────────

class TestCompliance:
    def test_pii_mask(self):
        from app.lakehouse.privacy import PrivacyEngine
        engine = PrivacyEngine()
        masked = engine.mask([{"email": "dev@novaforge.ai", "name": "Dev"}])
        assert masked[0]["email"] != "dev@novaforge.ai"
        assert masked[0]["name"] == "Dev"

    def test_rtbf(self):
        from app.lakehouse.privacy import PrivacyEngine
        engine = PrivacyEngine()
        tables = {"users": [{"id": "u1", "x": 1}, {"id": "u2", "x": 2}]}
        removed = engine.right_to_be_forgotten("u1", tables)
        assert removed["users"] == 1
        assert len(tables["users"]) == 1

    def test_governance_defaults(self):
        from app.lakehouse.governance import GovernanceEngine, GovernanceRule
        gov = GovernanceEngine()
        assert gov.can("billing", "viewer", "read") is True
        assert gov.can("billing", "viewer", "export") is False
        gov.add_rule(GovernanceRule("billing", "viewer", allow_export=True))
        assert gov.can("billing", "viewer", "export") is True

    def test_retention_expired(self):
        from app.lakehouse.retention import RetentionEngine
        engine = RetentionEngine()
        engine.configure("raw_events", days=1)
        expired = engine.expired_items("raw_events", [("e1", "2020-01-01T00:00:00Z")])
        assert len(expired) == 1


# ─── Service end-to-end ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLakehouseService:
    async def test_ingest_and_query_flow(self):
        svc = _svc()
        await svc.ingest_event("org-svc", "commit.pushed", {"ref": "main"})
        assert svc.event_store.count() >= 1
        assert svc.datalake.manifest("org-svc")["object_count"] >= 1

    async def test_table_lifecycle(self):
        svc = _svc()
        await svc.create_table("org-svc", "sales", [
            {"name": "organization_id", "type": "string", "nullable": False},
            {"name": "amount", "type": "float"},
            {"name": "region", "type": "string"},
        ])
        await svc.write_rows("org-svc", "sales", [
            {"amount": 10, "region": "us"},
            {"amount": 20, "region": "eu"},
        ])
        result = await svc.query("org-svc", "sales", group_by="region")
        assert result["total"] == 2

    async def test_health(self):
        svc = _svc()
        assert svc.health_check()["status"] == "healthy"