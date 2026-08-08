"""Collaboration Search — messages, meetings, knowledge, repos, projects, tasks, architecture."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SearchIndex:
    id: str; org_id: str; resource_type: str; resource_id: str
    title: str = ""; content: str = ""; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "SearchIndex": return cls(**data)

class CollaborationSearch:
    def __init__(self, storage_dir: str = "rtc_data/search"):
        self.storage_dir = storage_dir; self._index: dict[str, SearchIndex] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "index.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._index[k] = SearchIndex.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._index.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def index_resource(self, org_id: str, resource_type: str, resource_id: str, title: str = "", content: str = "") -> SearchIndex:
        si = SearchIndex(id=str(uuid.uuid4()), org_id=org_id, resource_type=resource_type, resource_id=resource_id, title=title, content=content)
        self._index[si.id] = si; self._save(); return si

    def search(self, org_id: str, query: str, resource_type: str = "") -> list[SearchIndex]:
        q = query.lower()
        results = [i for i in self._index.values() if i.org_id == org_id]
        if resource_type: results = [i for i in results if i.resource_type == resource_type]
        return [i for i in results if q in i.title.lower() or q in i.content.lower()]

    def get_telemetry(self) -> dict: return {"indexed": len(self._index)}
