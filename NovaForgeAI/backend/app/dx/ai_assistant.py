"""AI Assistant — context-aware assistant with repo awareness, workspace awareness, conversation memory, architecture awareness, prompt suggestions, next action suggestions, error recovery."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AssistantContextType(Enum):
    REPOSITORY = "repository"
    WORKSPACE = "workspace"
    FILE = "file"
    ARCHITECTURE = "architecture"
    CONVERSATION = "conversation"
    ERROR = "error"


@dataclass
class AssistantContext:
    id: str
    user_id: str
    context_type: AssistantContextType
    data: dict = field(default_factory=dict)
    relevance: float = 1.0
    expires_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["context_type"] = self.context_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AssistantContext":
        data = data.copy()
        data["context_type"] = AssistantContextType(data.get("context_type", "workspace"))
        return cls(**data)


@dataclass
class AssistantSuggestion:
    id: str
    user_id: str
    suggestion_type: str
    title: str
    description: str = ""
    action: str = ""
    confidence: float = 0.0
    is_actioned: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AssistantSuggestion": return cls(**data)


@dataclass
class AssistantMemory:
    id: str
    user_id: str
    key: str
    value: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AssistantMemory": return cls(**data)


class AIAssistant:
    def __init__(self, storage_dir: str = "dx_data/assistant"):
        self.storage_dir = storage_dir
        self._contexts: dict[str, AssistantContext] = {}
        self._suggestions: dict[str, AssistantSuggestion] = {}
        self._memory: dict[str, AssistantMemory] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _ctx_path(self) -> str: return os.path.join(self.storage_dir, "contexts.json")
    def _sug_path(self) -> str: return os.path.join(self.storage_dir, "suggestions.json")
    def _mem_path(self) -> str: return os.path.join(self.storage_dir, "memory.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._ctx_path(), self._contexts, AssistantContext),
            (self._sug_path(), self._suggestions, AssistantSuggestion),
            (self._mem_path(), self._memory, AssistantMemory),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load assistant data: %s", e)

    def _save(self) -> None:
        try:
            for path, store in [
                (self._ctx_path(), self._contexts),
                (self._sug_path(), self._suggestions),
                (self._mem_path(), self._memory),
            ]:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({k: v.to_dict() for k, v in store.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save assistant data: %s", e)

    def set_context(self, user_id: str, context_type: AssistantContextType, data: dict) -> AssistantContext:
        ctx = AssistantContext(id=str(uuid.uuid4()), user_id=user_id, context_type=context_type, data=data)
        self._contexts[ctx.id] = ctx
        self._save()
        return ctx

    def get_context(self, user_id: str, context_type: Optional[AssistantContextType] = None) -> list[AssistantContext]:
        results = [c for c in self._contexts.values() if c.user_id == user_id]
        if context_type: results = [c for c in results if c.context_type == context_type]
        return sorted(results, key=lambda c: c.relevance, reverse=True)[:10]

    def suggest(self, user_id: str, suggestion_type: str, title: str, description: str = "", action: str = "", confidence: float = 0.0) -> AssistantSuggestion:
        sug = AssistantSuggestion(id=str(uuid.uuid4()), user_id=user_id, suggestion_type=suggestion_type, title=title, description=description, action=action, confidence=confidence)
        self._suggestions[sug.id] = sug
        self._save()
        return sug

    def get_suggestions(self, user_id: str, suggestion_type: str = "") -> list[AssistantSuggestion]:
        results = [s for s in self._suggestions.values() if s.user_id == user_id and not s.is_actioned]
        if suggestion_type: results = [s for s in results if s.suggestion_type == suggestion_type]
        return sorted(results, key=lambda s: s.confidence, reverse=True)[:10]

    def mark_suggestion_actioned(self, sug_id: str) -> bool:
        sug = self._suggestions.get(sug_id)
        if not sug: return False
        sug.is_actioned = True
        self._save()
        return True

    def remember(self, user_id: str, key: str, value: str) -> AssistantMemory:
        mem = AssistantMemory(id=str(uuid.uuid4()), user_id=user_id, key=key, value=value)
        self._memory[mem.id] = mem
        self._save()
        return mem

    def recall(self, user_id: str, key: str) -> Optional[AssistantMemory]:
        for m in self._memory.values():
            if m.user_id == user_id and m.key == key: return m
        return None

    def get_conversation_memory(self, user_id: str, limit: int = 20) -> list[AssistantMemory]:
        results = [m for m in self._memory.values() if m.user_id == user_id]
        return sorted(results, key=lambda m: m.timestamp, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
