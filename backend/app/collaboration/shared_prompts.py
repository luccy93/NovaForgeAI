"""Shared Prompts — organization/team/repo prompt library, favorites, collections, versioning, sharing."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PromptScope(Enum):
    ORGANIZATION = "organization"
    TEAM = "team"
    REPOSITORY = "repository"
    PERSONAL = "personal"


@dataclass
class SharedPrompt:
    id: str
    org_id: str
    name: str
    prompt_template: str
    scope: PromptScope = PromptScope.TEAM
    description: str = ""
    tags: list = field(default_factory=list)
    variables: list = field(default_factory=list)
    version: int = 1
    author_id: str = ""
    collection_id: str = ""
    is_favorite: bool = False
    usage_count: int = 0
    avg_score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope"] = self.scope.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SharedPrompt":
        data = data.copy()
        data["scope"] = PromptScope(data.get("scope", "team"))
        return cls(**data)


@dataclass
class PromptCollection:
    id: str
    org_id: str
    name: str
    description: str = ""
    prompt_ids: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "PromptCollection": return cls(**data)


class SharedPrompts:
    def __init__(self, storage_dir: str = "collab_data/prompts"):
        self.storage_dir = storage_dir
        self._prompts: dict[str, SharedPrompt] = {}
        self._collections: dict[str, PromptCollection] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _prompts_path(self) -> str: return os.path.join(self.storage_dir, "prompts.json")
    def _cols_path(self) -> str: return os.path.join(self.storage_dir, "collections.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._prompts_path(), self._prompts, SharedPrompt),
            (self._cols_path(), self._collections, PromptCollection),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load prompt data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._prompts_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._prompts.items()}, f, indent=2, default=str)
            with open(self._cols_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._collections.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save prompt data: %s", e)

    def create_prompt(self, org_id: str, name: str, prompt_template: str, scope: PromptScope = PromptScope.TEAM, author_id: str = "", description: str = "", tags: list = None, variables: list = None) -> SharedPrompt:
        p = SharedPrompt(id=str(uuid.uuid4()), org_id=org_id, name=name, prompt_template=prompt_template, scope=scope, author_id=author_id, description=description, tags=tags or [], variables=variables or [])
        self._prompts[p.id] = p
        self._save()
        return p

    def get_prompt(self, prompt_id: str) -> Optional[SharedPrompt]: return self._prompts.get(prompt_id)

    def update_prompt(self, prompt_id: str, updates: dict) -> Optional[SharedPrompt]:
        p = self._prompts.get(prompt_id)
        if not p: return None
        for k, v in updates.items():
            if hasattr(p, k) and k not in ("id", "created_at"):
                if k == "scope": setattr(p, k, PromptScope(v) if isinstance(v, str) else v)
                else: setattr(p, k, v)
        p.version += 1
        p.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return p

    def list_prompts(self, org_id: str = "", scope: Optional[PromptScope] = None, tag: str = "") -> list[SharedPrompt]:
        results = list(self._prompts.values())
        if org_id: results = [p for p in results if p.org_id == org_id]
        if scope: results = [p for p in results if p.scope == scope]
        if tag: results = [p for p in results if tag in p.tags]
        return sorted(results, key=lambda p: p.usage_count, reverse=True)

    def record_usage(self, prompt_id: str, score: float = 0.0) -> bool:
        p = self._prompts.get(prompt_id)
        if not p: return False
        p.usage_count += 1
        p.avg_score = round((p.avg_score * (p.usage_count - 1) + score) / p.usage_count, 4) if score else p.avg_score
        self._save()
        return True

    def create_collection(self, org_id: str, name: str, description: str = "") -> PromptCollection:
        col = PromptCollection(id=str(uuid.uuid4()), org_id=org_id, name=name, description=description)
        self._collections[col.id] = col
        self._save()
        return col

    def add_to_collection(self, collection_id: str, prompt_id: str) -> bool:
        col = self._collections.get(collection_id)
        if not col: return False
        if prompt_id not in col.prompt_ids: col.prompt_ids.append(prompt_id)
        self._save()
        return True

    def list_collections(self, org_id: str = "") -> list[PromptCollection]:
        results = list(self._collections.values())
        if org_id: results = [c for c in results if c.org_id == org_id]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
