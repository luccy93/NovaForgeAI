"""Volume 32 service - Multimodal AI & Computer Vision Platform."""
import logging
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage

from .assets import AssetStore, MultimodalIngestion, sha256_of
from .jobs import JobManager
from .security import (
    UploadSecurity, SSRFGuard, ProcessingSandbox, PromptInjectionScanner)
from .vision_gateway import VisionModelGateway, VisionRequest
from .ocr import OCRDetector
from .docs import DocumentPipeline
from .images import ImageIntelService
from .video import VideoIntelligence
from .audio import AudioIntelligence
from .index_store import VectorIndex
from .rag import MultimodalRAG, SynthGraph
from .memory import MultimodalMemory
from .pipeline import MultimodalPipeline
from .screenshots import ScreenshotCapture, ScreenshotStore, ComparisonStore

logger = logging.getLogger(__name__)


class MultimodalService(AsyncService):
    """Unified entry point for the Multimodal AI & Computer Vision Platform."""

    def __init__(self):
        super().__init__("multimodal", JsonFileStorage("data/multimodal/service.json"))
        self.store = AssetStore()
        self.ingestion = MultimodalIngestion(self.store)
        self.gateway = VisionModelGateway()
        self.ocr = OCRDetector(gateway=self.gateway)
        self.security = UploadSecurity()
        self.ssrf = SSRFGuard()
        self.sandbox = ProcessingSandbox()
        self.scanner = PromptInjectionScanner()
        self.docs = DocumentPipeline(ocr=self.ocr)
        self.images = ImageIntelService(gateway=self.gateway, ocr=self.ocr)
        self.video = VideoIntelligence(ocr=self.ocr)
        self.audio = AudioIntelligence()
        self.index = VectorIndex(persist_path="data/multimodal/index.json")
        self.rag = MultimodalRAG(self.index)
        self.graph = SynthGraph()
        self.memory = MultimodalMemory(
            storage=JsonFileStorage("data/multimodal/cost_ledger.json"))
        self.screenshots = ScreenshotCapture(store=ScreenshotStore(),
                                             guard=self.ssrf)
        self.comparisons = ComparisonStore()
        self.pipeline = MultimodalPipeline(
            ingestion=self.ingestion, security=self.security, sandbox=self.sandbox,
            docs=self.docs, images=self.images, video=self.video,
            audio=self.audio, index=self.index, rag=self.rag,
            graph=self.graph, memory=self.memory, scanner=self.scanner)
        self.jobs = JobManager()
        self.pipeline.register_handlers(self.jobs)

    # ------------------------------------------------------------- ingestion
    async def ingest(self, organization_id: str, file_name: str, data: bytes,
                     declared_mime: str = "", source: str = "upload",
                     workspace_id: str = "", repository_id: str = "",
                     async_: bool = False) -> dict:
        Validator.non_empty(organization_id, "organization_id")
        if async_:
            job = self.jobs.enqueue(
                "multimodal_ingest", organization_id,
                payload={"data": data.hex(), "file_name": file_name,
                         "declared_mime": declared_mime, "source": source,
                         "workspace_id": workspace_id, "repository_id": repository_id})
            return {"status": "queued", "job_id": job.job_id}
        return await self.pipeline.ingest_async(
            organization_id, data, file_name=file_name, source=source,
            declared_mime=declared_mime, workspace_id=workspace_id,
            repository_id=repository_id)

    async def asset(self, organization_id: str, asset_id: str):
        Validator.non_empty(organization_id, "organization_id")
        asset = self.store.get(asset_id, organization_id)
        if asset is None:
            raise KeyError(f"asset not found: {asset_id}")
        return asset.to_dict()

    async def list_assets(self, organization_id: str, modality: str = "",
                          limit: int = 100) -> dict:
        Validator.non_empty(organization_id, "organization_id")
        return {"assets": [a.to_dict() for a in self.store.list(
            organization_id, modality=modality)[:limit]]}

    async def delete_asset(self, organization_id: str, asset_id: str) -> dict:
        Validator.non_empty(organization_id, "organization_id")
        deleted = self.store.delete(asset_id, organization_id)
        removed = self.index.delete_asset(organization_id, asset_id)
        return {"deleted": deleted, "index_entries_removed": removed}

    async def inspect(self, organization_id: str, file_name: str, data: bytes,
                      declared_mime: str = "") -> dict:
        Validator.non_empty(organization_id, "organization_id")
        verdict = self.security.validate(data, file_name, declared_mime)
        return {"verdict": verdict.to_dict(),
                "description": self.ingestion.describe(data, file_name, declared_mime)}

    # ---------------------------------------------------------------- vision
    async def vision(self, organization_id: str, prompt: str, image_data: bytes,
                     image_mime: str = "image/png", task: str = "default") -> dict:
        Validator.non_empty(organization_id, "organization_id")
        result = self.gateway.analyze(
            VisionRequest(prompt=prompt, image_data=image_data,
                          image_mime=image_mime), task=task, organization_id=organization_id)
        self.memory.record(organization_id, vision_calls=1, cost_usd=result.cost_usd)
        if result.cost_usd > 0:
            self.memory.record_cost(
                organization_id, "vision", cost_usd=result.cost_usd,
                provider=result.provider, model=result.model)
        return result.to_dict()

    async def ocr(self, organization_id: str, image_data: bytes,
                  asset_id: str = "") -> dict:
        Validator.non_empty(organization_id, "organization_id")
        result = self.ocr.ocr(image_data, organization_id, asset_id)
        self.memory.record(organization_id, ocr_calls=1)
        if getattr(result, "provider_cost_usd", 0.0) or getattr(result, "cost_usd", 0.0):
            self.memory.record_cost(
                organization_id, "ocr",
                cost_usd=getattr(result, "cost_usd", 0.0) or
                getattr(result, "provider_cost_usd", 0.0),
                provider=result.engine, model=result.engine)
        return result.to_dict()

    async def analyze_image(self, organization_id: str, asset_id: str) -> dict:
        """Re-analyze a stored image asset (stats, diagram, VRT helpers)."""
        asset = self.store.get(asset_id, organization_id)
        if asset is None:
            raise KeyError(f"asset not found: {asset_id}")
        # note: blob not persisted in this deployment; recompute on provided
        # bytes via /analyze in the API layer. Returns stored extraction.
        return {"asset": asset.to_dict(),
                "note": "stored metadata only; run ingest for full analysis"}

    async def compare_images(self, organization_id: str, baseline: bytes,
                             candidate: bytes) -> dict:
        Validator.non_empty(organization_id, "organization_id")
        baseline_id = f"inline:{sha256_of(baseline)[:16]}"
        candidate_id = f"inline:{sha256_of(candidate)[:16]}"
        verdict = self.images.compare(baseline, candidate)
        record = self.comparisons.record(
            organization_id, baseline_id, candidate_id, verdict)
        verdict["recorded"] = record
        return verdict

    # ------------------------------------------------------------ screenshots
    async def capture_screenshot(self, organization_id: str, url: str,
                                 viewport: str = "") -> dict:
        """Capture a URL screenshot for visual regression testing.

        Results are honest: no browser automation -> `available: False` with
        a reason. URLs pass the SSRF guard first.
        """
        Validator.non_empty(organization_id, "organization_id")
        vp = tuple(int(x) for x in viewport.split("x")) if viewport else (1280, 800)
        record = self.screenshots.capture(url, organization_id, vp)
        return record.to_dict()

    async def compare_screenshots(self, organization_id: str, baseline_id: str,
                                  candidate_id: str) -> dict:
        Validator.non_empty(organization_id, "organization_id")
        baseline = self.screenshots.store.get(baseline_id, organization_id)
        candidate = self.screenshots.store.get(candidate_id, organization_id)
        if baseline is None or not baseline.available:
            raise KeyError(f"screenshot not found: {baseline_id}")
        if candidate is None or not candidate.available:
            raise KeyError(f"screenshot not found: {candidate_id}")
        import os as _os
        for shot, other in ((baseline, candidate), (candidate, baseline)):
            if not shot.file_path or not _os.path.exists(shot.file_path):
                raise FileNotFoundError(f"screenshot bytes missing: {shot.id}")
        with open(baseline.file_path, "rb") as fh:
            baseline_bytes = fh.read()
        with open(candidate.file_path, "rb") as fh:
            candidate_bytes = fh.read()
        verdict = self.images.compare(baseline_bytes, candidate_bytes)
        record = self.comparisons.record(
            organization_id, baseline_id, candidate_id, verdict)
        return {**verdict, "recorded": record}

    # ------------------------------------------------------------------ rag
    async def search(self, organization_id: str, query: str, limit: int = 8,
                     modalities: str = "") -> dict:
        Validator.non_empty(organization_id, "organization_id")
        mods = [m.strip() for m in modalities.split(",") if m.strip()] or None
        sources = self.rag.search(organization_id, query, limit=limit,
                                  modalities=mods)
        self.memory.record(organization_id, rag_searches=1)
        return {"query": query, "results": [s.to_dict() for s in sources]}

    async def answer(self, organization_id: str, query: str, limit: int = 8,
                     modalities: str = "", generate: bool = True) -> dict:
        Validator.non_empty(organization_id, "organization_id")
        mods = [m.strip() for m in modalities.split(",") if m.strip()] or None
        result = self.rag.answer(organization_id, query, limit=limit,
                                 modalities=mods, generate=generate)
        self.memory.record(organization_id, rag_searches=1,
                           llm_calls=1 if result.synthesized else 0)
        if result.synthesized and result.latency_ms:
            self.memory.record_cost(
                organization_id, "answer", provider=result.model,
                model=result.model or "openai", cost_usd=getattr(result, "cost_usd", 0.0))
        return result.to_dict()

    # ---------------------------------------------------------------- jobs
    async def job(self, organization_id: str, job_id: str) -> dict:
        job = self.jobs.get(job_id, organization_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        return job.to_dict()

    async def list_jobs(self, organization_id: str, status: str = "",
                        limit: int = 100) -> dict:
        return {"jobs": self.jobs.list(organization_id, status=status, limit=limit)}

    # ------------------------------------------------------------ analytics
    async def usage(self, organization_id: str) -> dict:
        Validator.non_empty(organization_id, "organization_id")
        return self.memory.snapshot(organization_id)

    async def usage_totals(self) -> dict:
        return self.memory.totals()

    async def ledger(self, organization_id: str = "", limit: int = 100) -> dict:
        """Append-only cost ledger (mirrors multimodal_cost_ledger)."""
        return {"entries": self.memory.ledger(organization_id, limit),
                "totals": self.memory.cost_totals()}

    async def comparisons(self, organization_id: str = "", limit: int = 100) -> dict:
        return {"comparisons": self.comparisons.list(organization_id, limit)}

    async def health_check(self) -> dict:
        return self.health()

    def health(self) -> dict:
        h = super().health()
        h["gateway"] = self.gateway.health()
        h["ocr"] = self.ocr.health()
        h["video"] = self.video.probing
        h["index"] = self.index.health()
        h["jobs"] = self.jobs.health()
        h["memory"] = self.memory.health()
        h["screenshots"] = self.screenshots.health()
        h["comparisons"] = {"stored": self.comparisons.count()}
        return h


svc = MultimodalService()
registry.register(svc)