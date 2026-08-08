"""Multimodal Research — support repository diagrams, architecture images, flowcharts, screenshots, videos, audio, PDF, Word, PowerPoint, code images, repository visualization."""
import json, uuid, os, logging, base64
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class MediaType(Enum):
    REPO_DIAGRAM = "repo_diagram"
    ARCHITECTURE_IMAGE = "architecture_image"
    FLOWCHART = "flowchart"
    SCREENSHOT = "screenshot"
    VIDEO = "video"
    AUDIO = "audio"
    PDF = "pdf"
    WORD = "word"
    POWERPOINT = "powerpoint"
    CODE_IMAGE = "code_image"
    REPO_VISUALIZATION = "repo_visualization"


@dataclass
class MultimodalArtifact:
    id: str
    name: str
    media_type: MediaType
    format: str = ""
    size_bytes: int = 0
    description: str = ""
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    content_ref: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["media_type"] = self.media_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MultimodalArtifact":
        data = data.copy()
        data["media_type"] = MediaType(data.get("media_type", "pdf"))
        return cls(**data)


@dataclass
class MultimodalAnalysis:
    id: str
    artifact_id: str
    analysis_type: str
    content: str = ""
    confidence: float = 0.0
    model_used: str = ""
    tokens_used: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "MultimodalAnalysis": return cls(**data)


@dataclass
class RepositoryVisualization:
    id: str
    org_id: str
    repo_name: str
    visualization_type: str
    elements: dict = field(default_factory=dict)
    layout: str = "hierarchical"
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "RepositoryVisualization": return cls(**data)


class MultimodalResearch:
    def __init__(self, storage_dir: str = "research_data/multimodal"):
        self.storage_dir = storage_dir
        self._artifacts: dict[str, MultimodalArtifact] = {}
        self._analyses: dict[str, MultimodalAnalysis] = {}
        self._visualizations: dict[str, RepositoryVisualization] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _artifacts_path(self) -> str: return os.path.join(self.storage_dir, "artifacts.json")
    def _analyses_path(self) -> str: return os.path.join(self.storage_dir, "analyses.json")
    def _viz_path(self) -> str: return os.path.join(self.storage_dir, "visualizations.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._artifacts_path(), self._artifacts, MultimodalArtifact),
            (self._analyses_path(), self._analyses, MultimodalAnalysis),
            (self._viz_path(), self._visualizations, RepositoryVisualization),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load %s: %s", path, e)

    def _save(self) -> None:
        try:
            for path, store in [
                (self._artifacts_path(), self._artifacts),
                (self._analyses_path(), self._analyses),
                (self._viz_path(), self._visualizations),
            ]:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({k: v.to_dict() for k, v in store.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save multimodal data: %s", e)

    def register_artifact(self, name: str, media_type: MediaType, format: str = "", description: str = "", content_ref: str = "", metadata: dict = None) -> MultimodalArtifact:
        artifact = MultimodalArtifact(id=str(uuid.uuid4()), name=name, media_type=media_type, format=format, description=description, content_ref=content_ref, metadata=metadata or {})
        self._artifacts[artifact.id] = artifact
        self._save()
        return artifact

    def get_artifact(self, artifact_id: str) -> Optional[MultimodalArtifact]: return self._artifacts.get(artifact_id)

    def analyze_artifact(self, artifact_id: str, analysis_type: str, content: str, confidence: float = 0.0, model_used: str = "", tokens_used: int = 0) -> MultimodalAnalysis:
        analysis = MultimodalAnalysis(id=str(uuid.uuid4()), artifact_id=artifact_id, analysis_type=analysis_type, content=content, confidence=confidence, model_used=model_used, tokens_used=tokens_used)
        self._analyses[analysis.id] = analysis
        self._save()
        return analysis

    def create_visualization(self, org_id: str, repo_name: str, visualization_type: str, elements: dict = None, layout: str = "hierarchical") -> RepositoryVisualization:
        viz = RepositoryVisualization(id=str(uuid.uuid4()), org_id=org_id, repo_name=repo_name, visualization_type=visualization_type, elements=elements or {}, layout=layout)
        self._visualizations[viz.id] = viz
        self._save()
        return viz

    def list_artifacts(self, media_type: Optional[MediaType] = None) -> list[MultimodalArtifact]:
        results = list(self._artifacts.values())
        if media_type: results = [a for a in results if a.media_type == media_type]
        return sorted(results, key=lambda a: a.created_at, reverse=True)

    def list_visualizations(self, org_id: str = "") -> list[RepositoryVisualization]:
        results = list(self._visualizations.values())
        if org_id: results = [v for v in results if v.org_id == org_id]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
