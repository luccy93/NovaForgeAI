"""Innovation Pipeline — track ideas, prototypes, experiments through innovation lifecycle."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class InnovationStage(Enum):
    IDEA = "idea"
    RESEARCH = "research"
    PROTOTYPE = "prototype"
    EXPERIMENT = "experiment"
    VALIDATED = "validated"
    INTEGRATED = "integrated"
    SHIPPED = "shipped"
    DEPRECATED = "deprecated"


class InnovationImpact(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class InnovationIdea:
    id: str
    org_id: str
    title: str
    description: str = ""
    hypothesis: str = ""
    expected_impact: InnovationImpact = InnovationImpact.MEDIUM
    stage: InnovationStage = InnovationStage.IDEA
    owner: str = ""
    contributors: list = field(default_factory=list)
    references: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["expected_impact"] = self.expected_impact.value
        d["stage"] = self.stage.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InnovationIdea":
        data = data.copy()
        data["expected_impact"] = InnovationImpact(data.get("expected_impact", "medium"))
        data["stage"] = InnovationStage(data.get("stage", "idea"))
        return cls(**data)


class InnovationPipeline:
    def __init__(self, storage_dir: str = "research_data/innovation"):
        self.storage_dir = storage_dir
        self._ideas: dict[str, InnovationIdea] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "ideas.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._ideas[k] = InnovationIdea.from_dict(v)
                    except Exception as e: logger.warning("Skipping idea %s: %s", k, e)
            except Exception as e: logger.error("Failed to load ideas: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._ideas.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save ideas: %s", e)

    def submit_idea(self, title: str, org_id: str, description: str = "", hypothesis: str = "", expected_impact: InnovationImpact = InnovationImpact.MEDIUM) -> InnovationIdea:
        idea = InnovationIdea(id=str(uuid.uuid4()), org_id=org_id, title=title, description=description, hypothesis=hypothesis, expected_impact=expected_impact)
        self._ideas[idea.id] = idea
        self._save()
        return idea

    def get_idea(self, idea_id: str) -> Optional[InnovationIdea]: return self._ideas.get(idea_id)

    def update_idea(self, idea_id: str, updates: dict) -> Optional[InnovationIdea]:
        idea = self._ideas.get(idea_id)
        if not idea: return None
        for k, v in updates.items():
            if hasattr(idea, k) and k not in ("id", "created_at"):
                if k == "expected_impact": setattr(idea, k, InnovationImpact(v) if isinstance(v, str) else v)
                elif k == "stage": setattr(idea, k, InnovationStage(v) if isinstance(v, str) else v)
                else: setattr(idea, k, v)
        idea.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return idea

    def promote_stage(self, idea_id: str, new_stage: InnovationStage) -> Optional[InnovationIdea]:
        idea = self._ideas.get(idea_id)
        if not idea: return None
        stages = list(InnovationStage)
        current_idx = stages.index(idea.stage)
        new_idx = stages.index(new_stage)
        if new_idx > current_idx + 1:
            logger.warning("Cannot skip stages from %s to %s", idea.stage.value, new_stage.value)
            return None
        idea.stage = new_stage
        idea.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return idea

    def list_ideas(self, org_id: str = "", stage: Optional[InnovationStage] = None, impact: Optional[InnovationImpact] = None) -> list[InnovationIdea]:
        results = list(self._ideas.values())
        if org_id: results = [i for i in results if i.org_id == org_id]
        if stage: results = [i for i in results if i.stage == stage]
        if impact: results = [i for i in results if i.expected_impact == impact]
        return results

    def delete_idea(self, idea_id: str) -> bool:
        if idea_id not in self._ideas: return False
        del self._ideas[idea_id]
        self._save()
        return True

    def get_innovation_velocity(self, org_id: str) -> dict:
        ideas = self.list_ideas(org_id=org_id)
        return {
            "total_ideas": len(ideas),
            "by_stage": {s.value: len([i for i in ideas if i.stage == s]) for s in InnovationStage},
            "by_impact": {s.value: len([i for i in ideas if i.expected_impact == s]) for s in InnovationImpact},
            "shipped": len([i for i in ideas if i.stage == InnovationStage.SHIPPED]),
        }

    def get_telemetry(self) -> dict: return dict(self._telemetry)
