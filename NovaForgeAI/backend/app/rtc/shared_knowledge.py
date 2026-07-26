"""Shared Knowledge — knowledge base, architecture decisions, standards, playbooks, runbooks."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class KnowledgeArticle:
    id: str; org_id: str; title: str; content: str; category: str = "engineering"
    author_id: str = ""; tags: list = field(default_factory=list); is_published: bool = True
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeArticle": return cls(**data)

class SharedKnowledge:
    def __init__(self, storage_dir: str = "rtc_data/knowledge"):
        self.storage_dir = storage_dir; self._articles: dict[str, KnowledgeArticle] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "articles.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._articles[k] = KnowledgeArticle.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._articles.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, title: str, content: str, category: str = "engineering", author_id: str = "") -> KnowledgeArticle:
        a = KnowledgeArticle(id=str(uuid.uuid4()), org_id=org_id, title=title, content=content, category=category, author_id=author_id)
        self._articles[a.id] = a; self._save(); return a

    def search(self, org_id: str, query: str) -> list[KnowledgeArticle]:
        q = query.lower()
        return [a for a in self._articles.values() if a.org_id == org_id and (q in a.title.lower() or q in a.content.lower())]

    def get_telemetry(self) -> dict: return {"articles": len(self._articles)}
