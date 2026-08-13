"""Volume 31 service - Enterprise Data Lakehouse & Analytics Platform."""
import logging, asyncio
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage

from .event_model import Event, EventStore
from .ingestion import IngestionPipeline, SourceAdapter
from .stream_processing import StreamProcessor
from .batch_processing import BatchScheduler, AggregationEngine
from .data_lake import DataLake, LocalObjectStore
from .lakehouse import Lakehouse, Schema, ColumnSpec
from .olap import WarehouseEngineFactory
from .query_service import AnalyticsQueryService, QuerySpec, TenantGuard
from .analytics_cache import AnalyticsCache
from .transformation import TransformEngine
from .schema_registry import SchemaRegistry
from .metadata_catalog import MetadataCatalog
from .data_quality import DataQualityEngine
from .data_lineage import LineageGraph
from .metric_registry import MetricRegistry, SemanticLayer
from .reporting import ReportingEngine
from .exports import ExportService
from .retention import RetentionEngine
from .archival import ArchivalEngine
from .privacy import PrivacyEngine, PIIInspector
from .governance import GovernanceEngine
from .data_observability import DataObservability
from .anomaly_detection import AnomalyEngine
from .forecasting import ForecastEngine
from .ecommerce_analytics import EcommerceAnalytics
from .ai_analytics import AIAnalytics
from .rag_analytics import RAGAnalytics
from .agent_analytics import AgentAnalytics
from .engineering_analytics import EngineeringAnalytics
from .repository_analytics import RepositoryAnalytics
from .org_analytics import OrgAnalytics
from .finops import FinOpsAnalytics
from .ai_roi import AIROIService

logger = logging.getLogger(__name__)


class LakehouseService(AsyncService):
    """Unified entry point for the Enterprise Data Lakehouse & Analytics Platform."""

    def __init__(self):
        super().__init__("lakehouse", JsonFileStorage("data/lakehouse/service.json"))
        self.event_store = EventStore()
        self.pipeline = IngestionPipeline(store=self.event_store)
        self.adapters = SourceAdapter(self.pipeline)
        self.stream = StreamProcessor()
        self.batch = BatchScheduler()
        self.aggregator = AggregationEngine()
        self.store = LocalObjectStore("data/lakehouse/lake")
        self.datalake = DataLake(self.store)
        self.lakehouse = Lakehouse("data/lakehouse")
        self.olap = WarehouseEngineFactory.create("in_memory")
        self.cache = AnalyticsCache()
        self.guard = TenantGuard()
        self.queries = AnalyticsQueryService(self.olap, cache=self.cache, guard=self.guard)
        self.transform = TransformEngine(self.olap)
        self.schemas = SchemaRegistry("data/lakehouse/schemas")
        self.catalog = MetadataCatalog("data/lakehouse/catalog")
        self.quality = DataQualityEngine("data/lakehouse/quality")
        self.lineage = LineageGraph()
        self.metrics = MetricRegistry()
        self.semantics = SemanticLayer(self.metrics)
        self.reporting = ReportingEngine("data/lakehouse/reports")
        self.exports = ExportService(self.guard)
        self.retention = RetentionEngine()
        self.archival = ArchivalEngine()
        self.privacy = PrivacyEngine()
        self.gov = GovernanceEngine()
        self.obs = DataObservability()
        self.anomaly = AnomalyEngine()
        self.forecast = ForecastEngine()
        self.ecom = EcommerceAnalytics()
        self.ai = AIAnalytics()
        self.rag = RAGAnalytics()
        self.agents = AgentAnalytics()
        self.engineering = EngineeringAnalytics()
        self.repository = RepositoryAnalytics()
        self.org = OrgAnalytics()
        self.finops = FinOpsAnalytics()
        self.roi = AIROIService()

    # ── Ingestion ──
    async def ingest_event(self, organization_id: str, event_type: str, payload: dict = None):
        Validator.non_empty(organization_id, "organization_id")
        Validator.non_empty(event_type, "event_type")
        raw = {"organization_id": organization_id, "event_type": event_type,
               **({"payload": payload} if payload else {})}
        result = self.adapters.from_rest(raw)
        self.pipeline.drain_queue()
        event = Event.from_dict(raw)
        self.datalake.write_event(event.to_dict())
        self.telemetry.increment("events_ingested")
        return result.__dict__

    async def ingest_batch(self, organization_id: str, events: list[dict]):
        Validator.non_empty(organization_id, "organization_id")
        bounded = list(events)[:10000]
        for raw in bounded:
            raw.setdefault("organization_id", organization_id)
        results = self.adapters.from_batch(bounded, check_tenant=True)
        self.pipeline.drain_queue()
        for raw in bounded:
            self.datalake.write_event(Event.from_dict(raw).to_dict())
        self.telemetry.increment("batch_events", len(bounded))
        return {"accepted": sum(1 for r in results if r.accepted),
                "duplicates": sum(1 for r in results if r.duplicate),
                "failed": sum(1 for r in results if not r.accepted and not r.duplicate)}

    async def replay_events(self, organization_id: str, from_offset: int = 0):
        return self.pipeline.replay(from_offset)

    # ── Stream / Batch ──
    async def push_metric(self, organization_id: str, name: str, value: float):
        Validator.non_empty(organization_id, "organization_id")
        self.stream.push({"organization_id": organization_id, "event_type": "metric",
                          "name": name, "value": value})
        return {"ok": True, "metric": name, "value": value}

    async def run_batch(self, organization_id: str, job: str = "daily"):
        self.batch.register("daily", "daily", lambda: self._aggregate("daily"))
        self.batch.register("weekly", "weekly", lambda: self._aggregate("weekly"))
        self.batch.register("monthly", "monthly", lambda: self._aggregate("monthly"))
        result = self.batch.run_job(job)
        self.telemetry.increment("batch_runs")
        return {"organization_id": organization_id, "job": job, **result}

    def _aggregate(self, period: str) -> dict:
        events = self.event_store.replay(0)
        summary = self.aggregator.aggregate(events, period=period,
                                            metric_fns={"count": len})
        return {"processed": len(events), "summary": summary}

    # ── Lake / Lakehouse ──
    async def lake_manifest(self, organization_id: str = ""):
        return self.datalake.manifest(organization_id)

    async def create_table(self, organization_id: str, name: str, columns: list[dict],
                           partition_cols: list[str] = None):
        schema = Schema(name, [ColumnSpec(c["name"], c["type"], bool(c.get("nullable", True)))
                               for c in columns])
        self.lakehouse.create_table(f"{organization_id}__{name}", schema,
                                    tuple(partition_cols or ()))
        self.olap.register_table(f"{organization_id}__{name}", [])
        return {"table": name, "columns": len(columns)}

    async def write_rows(self, organization_id: str, table: str, rows: list[dict]):
        table_obj = self.lakehouse.table(f"{organization_id}__{table}")
        if not table_obj:
            raise ValueError(f"table not found: {table}")
        bounded = list(rows)[:10000]
        for row in bounded:
            row.setdefault("organization_id", organization_id)
        result = table_obj.write_batch(bounded)
        self.olap.append(f"{organization_id}__{table}", bounded)
        return result

    async def query(self, organization_id: str, table: str, group_by: str = "",
                    agg: str = "count", filters: dict = None, limit: int = 100):
        spec = QuerySpec(table=f"{organization_id}__{table}", organization_id=organization_id,
                         groups=[group_by] if group_by else None,
                         aggregations={"value": agg} if agg != "count" else {},
                         filters=filters or {}, limit=limit)
        return self.queries.run(spec)

    # ── Governance / Privacy ──
    async def mask_data(self, organization_id: str, rows: list[dict], policy: str = "mask"):
        self.guard.check(organization_id)
        return self.privacy.mask(rows, policy=policy)

    async def governance_decision(self, organization_id: str, resource: str, action: str = "read"):
        return self.gov.decide(resource, "analyst" if organization_id else "anon", action).__dict__

    async def retention_report(self):
        return self.retention.status()

    # ── Analytics ──
    async def metrics_for_org(self, organization_id: str):
        self.guard.check(organization_id)
        return {"metrics": self.metrics.list(), "semantic": self.semantics.metrics()}

    async def ecommerce(self, organization_id: str):
        self.guard.check(organization_id)
        return self.ecom.revenue_totals()

    async def ai_usage(self, organization_id: str):
        self.guard.check(organization_id)
        return self.ai.usage(organization_id)

    async def rag_metrics(self, organization_id: str):
        self.guard.check(organization_id)
        return self.rag.metrics(organization_id)

    async def agent_performance(self, organization_id: str):
        self.guard.check(organization_id)
        return self.agents.overview(organization_id)

    async def finops_overview(self, organization_id: str):
        self.guard.check(organization_id)
        return self.finops.total_spend(organization_id)

    def health_check(self) -> dict:
        return self.health()


svc = LakehouseService()
registry.register(svc)