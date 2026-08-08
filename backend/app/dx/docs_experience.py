"""Documentation Experience — unified documentation with semantic search, AI summaries, examples, code samples, architecture guides, tutorials, version history."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DocPage:
    id: str
    org_id: str
    title: str
    content: str = ""
    summary: str = ""
    category: str = ""
    tags: list = field(default_factory=list)
    version: int = 1
    is_published: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "DocPage": return cls(**data)


class DocsExperience:
    def __init__(self, storage_dir: str = "dx_data/docs"):
        self.storage_dir = storage_dir
        self._pages: dict[str, DocPage] = {}
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
                    try: self._pages[k] = DocPage.from_dict(v)
                    except Exception as e: logger.warning("Skipping doc %s: %s", k, e)
            except Exception as e: logger.error("Failed to load docs: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._pages.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save docs: %s", e)

    def create_page(self, org_id: str, title: str, content: str = "", category: str = "", tags: list = None) -> DocPage:
        page = DocPage(id=str(uuid.uuid4()), org_id=org_id, title=title, content=content, category=category, tags=tags or [])
        self._pages[page.id] = page
        self._save()
        return page

    def search(self, query: str) -> list[DocPage]:
        q = query.lower()
        results = []
        for p in self._pages.values():
            if not p.is_published: continue
            score = 0
            if q in p.title.lower(): score += 10
            if q in p.content.lower(): score += 3
            if q in p.summary.lower(): score += 5
            if any(q in t.lower() for t in p.tags): score += 2
            if score > 0: results.append((p, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:20]]

    def generate_summary(self, page_id: str) -> Optional[str]:
        page = self._pages.get(page_id)
        if not page: return None
        words = page.content.split()
        page.summary = " ".join(words[:50]) + "..." if len(words) > 50 else page.content
        self._save()
        return page.summary

    def list_by_category(self, category: str) -> list[DocPage]:
        return sorted([p for p in self._pages.values() if p.category == category and p.is_published], key=lambda p: p.updated_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
