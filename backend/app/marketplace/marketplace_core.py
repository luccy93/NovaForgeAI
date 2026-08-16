"""Marketplace Core — catalog, categories, items, discovery, ratings, search."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MarketplaceItem:
    id: str; org_id: str; name: str; description: str = ""
    category: str = "extension"; item_type: str = "plugin"  # plugin, agent, prompt, theme, workflow, template, connector, model
    publisher: str = ""; version: str = "1.0.0"; price: float = 0.0
    is_free: bool = True; is_verified: bool = False
    downloads: int = 0; rating: float = 0.0; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "MarketplaceItem": return cls(**data)

class MarketplaceCore:
    def __init__(self, storage_dir: str = "marketplace_data"):
        self.storage_dir = storage_dir; self._items: dict[str, MarketplaceItem] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "items.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._items[k] = MarketplaceItem.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._items.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, category: str = "extension", item_type: str = "plugin", publisher: str = "", price: float = 0.0) -> MarketplaceItem:
        item = MarketplaceItem(id=str(uuid.uuid4()), org_id=org_id, name=name, category=category, item_type=item_type, publisher=publisher, price=price, is_free=price == 0)
        self._items[item.id] = item; self._save(); return item

    def search(self, query: str, category: str = "", item_type: str = "") -> list[MarketplaceItem]:
        q = query.lower()
        results = [i for i in self._items.values() if q in i.name.lower() or q in i.description.lower()]
        if category: results = [i for i in results if i.category == category]
        if item_type: results = [i for i in results if i.item_type == item_type]
        return sorted(results, key=lambda i: i.downloads, reverse=True)

    def get_by_category(self, category: str) -> list[MarketplaceItem]:
        return sorted([i for i in self._items.values() if i.category == category], key=lambda i: i.rating, reverse=True)

    def record_download(self, item_id: str) -> bool:
        item = self._items.get(item_id)
        if not item: return False
        item.downloads += 1; self._save(); return True

    def rate(self, item_id: str, rating: float) -> bool:
        item = self._items.get(item_id)
        if not item: return False
        item.rating = (item.rating + rating) / 2 if item.rating > 0 else rating; self._save(); return True

    def get_telemetry(self) -> dict: return {"items": len(self._items)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Plugin:
    id: str; item_id: str; org_id: str; name: str; version: str = "1.0.0"
    entry_point: str = ""; permissions: list = field(default_factory=list)
    dependencies: list = field(default_factory=list); is_signed: bool = False
    status: str = "published"; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PluginRegistry:
    def __init__(self, storage_dir: str = "marketplace_data/plugins"):
        self.storage_dir = storage_dir; self._plugins: dict[str, Plugin] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "plugins.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._plugins[k] = Plugin(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._plugins.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, item_id: str, org_id: str, name: str, entry_point: str = "", permissions: list = None) -> Plugin:
        p = Plugin(id=str(uuid.uuid4()), item_id=item_id, org_id=org_id, name=name, entry_point=entry_point, permissions=permissions or [])
        self._plugins[p.id] = p; self._save(); return p

    def get_by_org(self, org_id: str) -> list[Plugin]:
        return [p for p in self._plugins.values() if p.org_id == org_id]

    def get_telemetry(self) -> dict: return {"plugins": len(self._plugins)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Package:
    id: str; org_id: str; name: str; version: str = "1.0.0"
    package_type: str = "plugin"; dependencies: list = field(default_factory=list)
    license_info: str = ""; security_score: float = 1.0
    downloads: int = 0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PackageRegistry:
    def __init__(self, storage_dir: str = "marketplace_data/packages"):
        self.storage_dir = storage_dir; self._packages: dict[str, Package] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "packages.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._packages[k] = Package(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._packages.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, package_type: str = "plugin", dependencies: list = None) -> Package:
        p = Package(id=str(uuid.uuid4()), org_id=org_id, name=name, package_type=package_type, dependencies=dependencies or [])
        self._packages[p.id] = p; self._save(); return p

    def search(self, query: str) -> list[Package]:
        q = query.lower()
        return [p for p in self._packages.values() if q in p.name.lower()]

    def get_telemetry(self) -> dict: return {"packages": len(self._packages)}
