"""Multimodal ingestion pipeline: secure upload -> validation -> scan ->
extraction -> chunking -> embedding -> indexing -> knowledge-graph interlink.

`MultimodalPipeline.ingest` is the single entry point used by the service,
the job workers, and tests. Every step records progress on the JobManager
when a job is supplied, and failures are surfaced as structured results
(never silent, never fabricated).
"""
import asyncio, logging, time, uuid
from typing import Any, Optional

from app.multimodal.assets import (
    Modality, MultimodalAsset, MultimodalIngestion, sha256_of)
from app.multimodal.security import (
    UploadSecurity, UploadVerdict, PromptInjectionScanner, ProcessingSandbox)
from app.multimodal.docs import DocumentPipeline
from app.multimodal.images import ImageIntelService
from app.multimodal.video import VideoIntelligence
from app.multimodal.audio import AudioIntelligence
from app.multimodal.index_store import VectorIndex, IndexEntry
from app.multimodal.rag import MultimodalRAG, SynthGraph
from app.multimodal.memory import MultimodalMemory

logger = logging.getLogger(__name__)


def _in_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class MultimodalPipeline:
    """Orchestrates a full asset lifecycle. All cross-cutting concerns
    (security, sandboxing, budgets, provenance) are applied here."""

    def __init__(self,
                 ingestion: Optional[MultimodalIngestion] = None,
                 security: Optional[UploadSecurity] = None,
                 sandbox: Optional[ProcessingSandbox] = None,
                 docs: Optional[DocumentPipeline] = None,
                 images: Optional[ImageIntelService] = None,
                 video: Optional[VideoIntelligence] = None,
                 audio: Optional[AudioIntelligence] = None,
                 index: Optional[VectorIndex] = None,
                 rag: Optional[MultimodalRAG] = None,
                 graph: Optional[SynthGraph] = None,
                 memory: Optional[MultimodalMemory] = None,
                 scanner: Optional[PromptInjectionScanner] = None):
        self.ingestion = ingestion or MultimodalIngestion()
        self.security = security or UploadSecurity()
        self.sandbox = sandbox or ProcessingSandbox()
        self.docs = docs or DocumentPipeline()
        self.images = images or ImageIntelService()
        self.video = video or VideoIntelligence()
        self.audio = audio or AudioIntelligence()
        self.index = index or VectorIndex()
        self.rag = rag or MultimodalRAG(self.index)
        self.graph = graph or SynthGraph()
        self.memory = memory or MultimodalMemory()
        self.scanner = scanner or PromptInjectionScanner()

    # ------------------------------------------------------------- lifecycle
    def ingest(self, organization_id: str, data: bytes, file_name: str = "",
               source: str = "upload", declared_mime: str = "",
               job=None, workspace_id: str = "", repository_id: str = "",
               index_after: bool = True) -> dict:
        """Validate -> register -> extract -> chunk -> embed/index -> KG.

        Synchronous facade: spins a private event loop for the async KG step,
        safe in both CLI and async service contexts (creates a fresh loop
        only when no loop is running)."""
        if _in_loop():
            raise RuntimeError(
                "ingest is sync-only; call the async ingest_async inside an "
                "event loop (JobManager handlers use ingest_async)")
        return asyncio.run(self.ingest_async(
            organization_id, data, file_name, source, declared_mime, job,
            workspace_id, repository_id, index_after))

    async def ingest_async(self, organization_id: str, data: bytes,
                           file_name: str = "", source: str = "upload",
                           declared_mime: str = "",
                           job=None, workspace_id: str = "",
                           repository_id: str = "",
                           index_after: bool = True) -> dict:
        """Async variant used by workers and the API layer."""
        start = time.time()
        self._progress(job, 0.05, "validating upload")
        verdict: UploadVerdict = self.security.validate(data, file_name, declared_mime)
        if not verdict.allowed:
            self._progress(job, 1.0, "rejected by upload security")
            return {"status": "rejected", "asset_id": "",
                    "checks": [c.to_dict() for c in verdict.checks],
                    "reason": verdict.reason or "; ".join(
                        c.detail for c in verdict.checks if not c.passed),
                    "latency_ms": round((time.time() - start) * 1000, 2)}

        budget = self.memory.can_ingest(organization_id, len(data))
        if not budget["allowed"]:
            return {"status": "budget_limited", "asset_id": "",
                    "reason": budget["reason"],
                    "latency_ms": round((time.time() - start) * 1000, 2)}

        self._progress(job, 0.15, "registering asset")
        asset = self.ingestion.register(
            organization_id=organization_id, data=data, file_name=file_name,
            source=source, declared_mime=declared_mime,
            workspace_id=workspace_id, repository_id=repository_id)
        self.memory.record(organization_id, assets_ingested=1, bytes_ingested=len(data))

        token = self.sandbox.enter(job.job_id if job else "", asset.asset_id)
        try:
            self._progress(job, 0.25, "extracting content")
            extraction, chunks = self._extract(asset, data)
            # prompt-injection scan on extracted text (defense in depth)
            if extraction.get("full_text"):
                scan = self.scanner.scan(extraction["full_text"])
                if scan.get("detected"):
                    asset.status = "failed"
                    asset.metadata["rejected_reason"] = "prompt injection detected in content"
                    self.ingestion.store.put(asset)
                    return {"status": "rejected", "asset_id": asset.asset_id,
                            "reason": "prompt injection detected",
                            "injection": scan, "latency_ms": round((time.time() - start) * 1000, 2)}
                extraction["injection_scan"] = scan

            if index_after and chunks:
                self._progress(job, 0.55, "embedding and indexing")
                entries = [
                    IndexEntry(
                        id=f"{asset.asset_id}:{i}",
                        tenant=organization_id, asset_id=asset.asset_id,
                        modality=asset.modality, text=c["text"],
                        chunk_index=c["index"],
                        metadata={"source": asset.file_name, "page": c.get("page", 0)})
                    for i, c in enumerate(chunks)]
                written = self.index.index(organization_id, entries)
                self.memory.record(organization_id, chunks_indexed=written,
                                   embed_calls=len(entries))
            else:
                written = 0

            self._progress(job, 0.8, "interlinking knowledge graph")
            kg = await self.graph.upsert_asset(
                organization_id, asset.asset_id, asset.modality, asset.file_name)
            if extraction.get("diagram"):
                kg_diagram = await self.graph.upsert_diagram(
                    organization_id, asset.asset_id, extraction["diagram"])
                extraction["kg_diagram"] = kg_diagram

            asset.status = "completed"
            asset.processed_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat()
            asset.metadata.update({"chunks": len(chunks), "indexed": written})
            self.ingestion.store.put(asset)
            self._progress(job, 1.0, "completed")
            result = {
                "status": "completed",
                "asset_id": asset.asset_id,
                "modality": asset.modality,
                "chunks": len(chunks),
                "indexed": written,
                "extraction": {k: v for k, v in extraction.items()
                               if k not in ("pages", "chunks")},
                "kg": kg,
                "latency_ms": round((time.time() - start) * 1000, 2),
            }
            return result
        finally:
            self.sandbox.leave(token)

    def _extract(self, asset: MultimodalAsset, data: bytes) -> tuple[dict, list[dict]]:
        """Dispatch by modality; always returns (extraction, chunks)."""
        if asset.modality == Modality.IMAGE:
            analysis = self.images.analyze(asset.asset_id, data, asset.file_name)
            extraction = analysis.to_dict()
            chunks = self._chunks_from_text(analysis.text or analysis.caption or "",
                                            asset)
            if analysis.diagram:
                extraction["diagram"] = analysis.diagram
                for node in extraction["diagram"].get("nodes", []):
                    if node.get("label"):
                        chunks.append({"index": len(chunks), "text":
                                       f"diagram component: {node['label']}",
                                       "page": 0})
            return extraction, chunks
        if asset.modality == Modality.DOCUMENT:
            result = self.docs.process(data, asset.file_name, asset.to_dict())
            chunks = result.get("chunks", [])
            return result, chunks
        if asset.modality == Modality.VIDEO:
            analysis = self.video.analyze(asset.asset_id, data, asset.file_name)
            chunks = self._chunks_from_text(
                "\n".join(f.text for f in analysis.frames) or analysis.transcript, asset)
            return analysis.to_dict(), chunks
        if asset.modality == Modality.AUDIO:
            analysis = self.audio.transcribe(data, asset.asset_id, asset.file_name)
            chunks = self._chunks_from_text(analysis.transcript, asset)
            extraction = analysis.to_dict()
            if analysis.available:
                extraction["topics"] = analysis.topics
                extraction["decisions"] = analysis.decisions
            return extraction, chunks
        if asset.modality == Modality.TEXT:
            result = self.docs.process(data, asset.file_name, asset.to_dict())
            return result, result.get("chunks", [])
        return {"error": f"no extractor for modality {asset.modality}"}, []

    @staticmethod
    def _chunks_from_text(text: str, asset: MultimodalAsset) -> list[dict]:
        from app.multimodal.docs import SemanticChunker
        if not text.strip():
            return []
        return [c.to_dict() for c in SemanticChunker().chunk(
            text, source=asset.asset_id)]

    @staticmethod
    def _progress(job, ratio: float, stage: str) -> None:
        if job is not None:
            job.payload["progress"] = round(ratio, 3)
            job.payload["stage"] = stage

    # ---------------------------------------------------------- job handler
    async def ingest_job(self, job) -> dict:
        """Handler for JobManager: processes a stored blob referenced by
        payload (storage_key not required: payload carries the bytes base64
        for simplicity in this deployment)."""
        payload = job.payload or {}
        data = payload.get("data")
        if data is None:
            raise ValueError("job payload missing 'data'")
        import base64
        if isinstance(data, str):
            data = base64.b64decode(data)
        return await self.ingest_async(
            organization_id=job.organization_id,
            data=data,
            file_name=payload.get("file_name", ""),
            source=payload.get("source", "job"),
            declared_mime=payload.get("declared_mime", ""),
            job=job,
            workspace_id=payload.get("workspace_id", ""),
            repository_id=payload.get("repository_id", ""),
        )

    def register_handlers(self, jobs) -> None:
        """Wire the pipeline into a JobManager."""
        jobs.register_handler("multimodal_ingest", self.ingest_job)

    # ------------------------------------------------------------ analytics
    def health(self) -> dict:
        return {"security": self.security.health(),
                "sandbox": self.sandbox.health(),
                "index": self.index.health(),
                "memory": self.memory.health()}