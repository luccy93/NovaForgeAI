"""Knowledge Service — team knowledge base, repository wiki, architecture notes, engineering decisions, meeting notes, AI summaries, best practices, coding standards, decision records."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class KnowledgeCategory(Enum):
    KNOWLEDGE_BASE = "knowledge_base"
    WIKI = "wiki"
    ARCHITECTURE_NOTE = "architecture_note"
    ENGINEERING_DECISION = "engineering_decision"
    MEETING_NOTE = "meeting_note"
    AI_SUMMARY = "ai_summary"
    BEST_PRACTICE = "best_practice"
    CODING_STANDARD = "coding_standard"
    DECISION_RECORD = "decision_record"


@dataclass
class KnowledgeArticle:
    id: str
    org_id: str
    workspace_id: str
    category: KnowledgeCategory
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
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeArticle":
        data = data.copy()
        data["category"] = KnowledgeCategory(data.get("category", "knowledge_base"))
        return cls(**data)


class KnowledgeService:
    def __init__(self, storage_dir: str = "collab_data/knowledge"):
        self.storage_dir = storage_dir
        self._articles: dict[str, KnowledgeArticle] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "articles.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._articles[k] = KnowledgeArticle.from_dict(v)
                    except Exception as e: logger.warning("Skipping article %s: %s", k, e)
            except Exception as e: logger.error("Failed to load knowledge articles: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._articles.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save knowledge articles: %s", e)

    def create_article(self, org_id: str, workspace_id: str, category: KnowledgeCategory, title: str, content: str = "", tags: list = None, authors: list = None) -> KnowledgeArticle:
        art = KnowledgeArticle(id=str(uuid.uuid4()), org_id=org_id, workspace_id=workspace_id, category=category, title=title, content=content, tags=tags or [], authors=authors or [])
        self._articles[art.id] = art
        self._save()
        return art

    def get_article(self, article_id: str) -> Optional[KnowledgeArticle]: return self._articles.get(article_id)

    def update_article(self, article_id: str, updates: dict) -> Optional[KnowledgeArticle]:
        art = self._articles.get(article_id)
        if not art: return None
        for k, v in updates.items():
            if hasattr(art, k) and k not in ("id", "created_at"):
                if k == "category": setattr(art, k, KnowledgeCategory(v) if isinstance(v, str) else v)
                else: setattr(art, k, v)
        art.version += 1
        art.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return art

    def search(self, query: str, category: Optional[KnowledgeCategory] = None, workspace_id: str = "") -> list[KnowledgeArticle]:
        q = query.lower()
        results = []
        for art in self._articles.values():
            if not art.is_published: continue
            if category and art.category != category: continue
            if workspace_id and art.workspace_id != workspace_id: continue
            if q in art.title.lower() or q in art.content.lower() or any(q in t.lower() for t in art.tags):
                results.append(art)
        return results

    def list_by_workspace(self, workspace_id: str, category: Optional[KnowledgeCategory] = None) -> list[KnowledgeArticle]:
        results = [a for a in self._articles.values() if a.workspace_id == workspace_id and a.is_published]
        if category: results = [a for a in results if a.category == category]
        return sorted(results, key=lambda a: a.updated_at, reverse=True)

    def list_by_org(self, org_id: str) -> list[KnowledgeArticle]:
        return sorted([a for a in self._articles.values() if a.org_id == org_id and a.is_published], key=lambda a: a.updated_at, reverse=True)

    def delete_article(self, article_id: str) -> bool:
        if article_id not in self._articles: return False
        del self._articles[article_id]
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
