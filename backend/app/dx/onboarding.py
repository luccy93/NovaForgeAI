"""Onboarding — interactive onboarding with workspace setup, repo import wizard, AI tutorial, command guide, documentation tour, architecture tour, organization setup."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class OnboardingStep(Enum):
    WELCOME = "welcome"
    WORKSPACE_SETUP = "workspace_setup"
    REPO_IMPORT = "repo_import"
    AI_TUTORIAL = "ai_tutorial"
    COMMAND_GUIDE = "command_guide"
    DOCS_TOUR = "docs_tour"
    ARCHITECTURE_TOUR = "architecture_tour"
    ORG_SETUP = "org_setup"
    COMPLETE = "complete"


@dataclass
class OnboardingProgress:
    id: str
    user_id: str
    org_id: str
    current_step: OnboardingStep = OnboardingStep.WELCOME
    completed_steps: list = field(default_factory=list)
    skipped_steps: list = field(default_factory=list)
    is_completed: bool = False
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["current_step"] = self.current_step.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OnboardingProgress":
        data = data.copy()
        data["current_step"] = OnboardingStep(data.get("current_step", "welcome"))
        return cls(**data)


class OnboardingService:
    def __init__(self, storage_dir: str = "dx_data/onboarding"):
        self.storage_dir = storage_dir
        self._progress: dict[str, OnboardingProgress] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "progress.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._progress[k] = OnboardingProgress.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load onboarding: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._progress.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save onboarding: %s", e)

    def start(self, user_id: str, org_id: str) -> OnboardingProgress:
        prog = OnboardingProgress(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id)
        self._progress[prog.id] = prog
        self._save()
        return prog

    def advance(self, user_id: str, step: OnboardingStep) -> Optional[OnboardingProgress]:
        for p in self._progress.values():
            if p.user_id == user_id and not p.is_completed:
                if step not in p.completed_steps: p.completed_steps.append(step.value)
                steps = list(OnboardingStep)
                current_idx = steps.index(p.current_step)
                next_idx = min(current_idx + 1, len(steps) - 1)
                p.current_step = steps[next_idx]
                if p.current_step == OnboardingStep.COMPLETE:
                    p.is_completed = True
                    p.completed_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return p
        return None

    def skip(self, user_id: str, step: OnboardingStep) -> Optional[OnboardingProgress]:
        for p in self._progress.values():
            if p.user_id == user_id:
                if step.value not in p.skipped_steps: p.skipped_steps.append(step.value)
                self._save()
                return p
        return None

    def get_progress(self, user_id: str) -> Optional[OnboardingProgress]:
        for p in self._progress.values():
            if p.user_id == user_id: return p
        return None

    def get_telemetry(self) -> dict: return dict(self._telemetry)
