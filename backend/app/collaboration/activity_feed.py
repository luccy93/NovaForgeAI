"""Activity Feed — aggregate and display cross-entity activities across the collaboration platform."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class FeedCategory(Enum):
    WORKSPACE = "workspace"
    REPOSITORY = "repository"
    TEAM = "team"
    PROJECT = "project"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    AI = "ai"
    AGENT = "agent"
    DOCUMENTATION = "documentation"
    REVIEW = "review"
    DISCUSSION = "discussion"


@dataclass
class FeedItem:
    id: str
    org_id: str
    user_id: str
    category: FeedCategory
    title: str
    description: str = ""
    source: str = ""
    source_id: str = ""
    source_type: str = ""
    metadata: dict = field(default_factory=dict)
    priority: int = 0
    is_pinned: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FeedItem":
        data = data.copy()
        data["category"] = FeedCategory(data.get("category", "workspace"))
        return cls(**data)


class ActivityFeed:
    def __init__(self, storage_dir: str = "collab_data/feed"):
        self.storage_dir = storage_dir
        self._items: dict[str, FeedItem] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "feed.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._items[k] = FeedItem.from_dict(v)
                    except Exception as e: logger.warning("Skipping feed item %s: %s", k, e)
            except Exception as e: logger.error("Failed to load activity feed: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._items.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save activity feed: %s", e)

    def publish(self, org_id: str, user_id: str, category: FeedCategory, title: str, description: str = "", source: str = "", source_id: str = "", source_type: str = "", metadata: dict = None, priority: int = 0) -> FeedItem:
        item = FeedItem(id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, category=category, title=title, description=description, source=source, source_id=source_id, source_type=source_type, metadata=metadata or {}, priority=priority)
        self._items[item.id] = item
        self._save()
        return item

    def get_feed(self, org_id: str = "", user_id: str = "", category: Optional[FeedCategory] = None, limit: int = 100) -> list[FeedItem]:
        results = list(self._items.values())
        if org_id: results = [i for i in results if i.org_id == org_id]
        if user_id: results = [i for i in results if i.user_id == user_id]
        if category: results = [i for i in results if i.category == category]
        return sorted(results, key=lambda i: (i.priority, i.created_at), reverse=True)[:limit]

    def pin_item(self, item_id: str) -> bool:
        item = self._items.get(item_id)
        if not item: return False
        item.is_pinned = True
        self._save()
        return True

    def unpin_item(self, item_id: str) -> bool:
        item = self._items.get(item_id)
        if not item: return False
        item.is_pinned = False
        self._save()
        return True

    def get_pinned(self, org_id: str = "") -> list[FeedItem]:
        results = [i for i in self._items.values() if i.is_pinned]
        if org_id: results = [i for i in results if i.org_id == org_id]
        return sorted(results, key=lambda i: i.created_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
