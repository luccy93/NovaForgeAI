"""Integration Marketplace — discover, install, and manage connector marketplace entries."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class MarketplaceStatus(Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


@dataclass
class MarketplaceEntry:
    id: str
    name: str
    provider: str
    category: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    icon_url: str = ""
    docs_url: str = ""
    config_schema: dict = field(default_factory=dict)
    status: MarketplaceStatus = MarketplaceStatus.DRAFT
    install_count: int = 0
    rating: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MarketplaceEntry":
        data = data.copy()
        data["status"] = MarketplaceStatus(data.get("status", "draft"))
        return cls(**data)


class Marketplace:
    def __init__(self, storage_dir: str = "integration_data/marketplace"):
        self.storage_dir = storage_dir
        self._entries: dict[str, MarketplaceEntry] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "entries.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._entries[k] = MarketplaceEntry.from_dict(v)
                    except Exception as e: logger.warning("Skipping entry %s: %s", k, e)
            except Exception as e: logger.error("Failed to load marketplace: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._entries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save marketplace: %s", e)

    def publish(self, name: str, provider: str, category: str, description: str = "", author: str = "", config_schema: dict = None) -> MarketplaceEntry:
        entry = MarketplaceEntry(id=str(uuid.uuid4()), name=name, provider=provider, category=category, description=description, author=author, config_schema=config_schema or {}, status=MarketplaceStatus.PUBLISHED)
        self._entries[entry.id] = entry
        self._save()
        return entry

    def get(self, entry_id: str) -> Optional[MarketplaceEntry]: return self._entries.get(entry_id)

    def search(self, query: str, category: str = "") -> list[MarketplaceEntry]:
        q = query.lower()
        results = [e for e in self._entries.values() if e.status == MarketplaceStatus.PUBLISHED]
        if category: results = [e for e in results if e.category == category]
        return [e for e in results if q in e.name.lower() or q in e.provider.lower() or q in e.description.lower()]

    def list_by_category(self, category: str) -> list[MarketplaceEntry]:
        return [e for e in self._entries.values() if e.category == category and e.status == MarketplaceStatus.PUBLISHED]

    def record_install(self, entry_id: str) -> bool:
        entry = self._entries.get(entry_id)
        if not entry: return False
        entry.install_count += 1
        self._save()
        return True

    def rate(self, entry_id: str, rating: float) -> bool:
        entry = self._entries.get(entry_id)
        if not entry: return False
        entry.rating = (entry.rating + rating) / 2 if entry.rating else rating
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
