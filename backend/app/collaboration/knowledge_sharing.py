"""Knowledge Sharing — team knowledge base, repository wiki, architecture notes, engineering decisions, meeting notes, AI summaries, best practices, coding standards, decision records."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class KnowledgeType(Enum):
    WIKI = "wiki"
    ARCHITECTURE_NOTE = "architecture_note"
    ENGINEERING_DECISION = "engineering_decision"
    MEETING_NOTE = "meeting_note"
    AI_SUMMARY = "ai_summary"
    BEST_PRACTICE = "best_practice"
    CODING_STANDARD = "coding_standard"
    DECISION_RECORD = "decision_record"


@dataclass
class KnowledgePage:
    id: str
    org_id: str
    workspace_id: str
    knowledge_type: KnowledgeType
    title: str
    content: str = ""
    tags: list = field(default_factory=list)
    authors: list = field(default_factory=list)
    references: list = field(default_factory=list)
    version: int = 1
    is_published: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["knowledge_type"] = self.knowledge_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgePage":
        data = data.copy()
        data["knowledge_type"] = KnowledgeType(data.get("knowledge_type", "wiki"))
        return cls(**data)


class KnowledgeSharing:
    def __init__(self, storage_dir: str = "collab_data/knowledge_sharing"):
        self.storage_dir = storage_dir
        self._pages: dict[str, KnowledgePage] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "pages.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._pages[k] = KnowledgePage.from_dict(v)
                    except Exception as e: logger.warning("Skipping page %s: %s", k, e)
            except Exception as e: logger.error("Failed to load knowledge pages: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._pages.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save knowledge pages: %s", e)

    def create_page(self, org_id: str, workspace_id: str, knowledge_type: KnowledgeType, title: str, content: str = "", tags: list = None, authors: list = None) -> KnowledgePage:
        page = KnowledgePage(id=str(uuid.uuid4()), org_id=org_id, workspace_id=workspace_id, knowledge_type=knowledge_type, title=title, content=content, tags=tags or [], authors=authors or [])
        self._pages[page.id] = page
        self._save()
        return page

    def get_page(self, page_id: str) -> Optional[KnowledgePage]: return self._pages.get(page_id)

    def update_page(self, page_id: str, updates: dict) -> Optional[KnowledgePage]:
        page = self._pages.get(page_id)
        if not page: return None
        for k, v in updates.items():
            if hasattr(page, k) and k not in ("id", "created_at"):
                if k == "knowledge_type": setattr(page, k, KnowledgeType(v) if isinstance(v, str) else v)
                else: setattr(page, k, v)
        page.version += 1
        page.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return page

    def search(self, query: str, workspace_id: str = "", knowledge_type: Optional[KnowledgeType] = None) -> list[KnowledgePage]:
        q = query.lower()
        results = []
        for p in self._pages.values():
            if not p.is_published: continue
            if workspace_id and p.workspace_id != workspace_id: continue
            if knowledge_type and p.knowledge_type != knowledge_type: continue
            if q in p.title.lower() or q in p.content.lower() or any(q in t.lower() for t in p.tags):
                results.append(p)
        return results

    def list_by_workspace(self, workspace_id: str) -> list[KnowledgePage]:
        return sorted([p for p in self._pages.values() if p.workspace_id == workspace_id and p.is_published], key=lambda p: p.updated_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
