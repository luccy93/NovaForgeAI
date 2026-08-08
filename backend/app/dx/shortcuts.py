"""Shortcuts — keyboard shortcuts for navigation, search, chat, review, documentation, terminal, deploy, settings with custom shortcuts and profiles."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ShortcutCategory(Enum):
    NAVIGATION = "navigation"
    SEARCH = "search"
    CHAT = "chat"
    REVIEW = "review"
    DOCUMENTATION = "documentation"
    TERMINAL = "terminal"
    DEPLOY = "deploy"
    SETTINGS = "settings"
    WORKSPACE = "workspace"
    CUSTOM = "custom"


@dataclass
class Shortcut:
    id: str
    name: str
    category: ShortcutCategory
    keys: str
    description: str = ""
    action: str = ""
    is_custom: bool = False
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Shortcut":
        data = data.copy()
        data["category"] = ShortcutCategory(data.get("category", "navigation"))
        return cls(**data)


@dataclass
class ShortcutProfile:
    id: str
    user_id: str
    name: str
    shortcuts: dict = field(default_factory=dict)
    is_active: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ShortcutProfile": return cls(**data)


class ShortcutsService:
    def __init__(self, storage_dir: str = "dx_data/shortcuts"):
        self.storage_dir = storage_dir
        self._shortcuts: dict[str, Shortcut] = {}
        self._profiles: dict[str, ShortcutProfile] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _sc_path(self) -> str: return os.path.join(self.storage_dir, "shortcuts.json")
    def _prof_path(self) -> str: return os.path.join(self.storage_dir, "profiles.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._sc_path(), self._shortcuts, Shortcut),
            (self._prof_path(), self._profiles, ShortcutProfile),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load shortcuts: %s", e)

    def _save(self) -> None:
        try:
            with open(self._sc_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._shortcuts.items()}, f, indent=2, default=str)
            with open(self._prof_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._profiles.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save shortcuts: %s", e)

    def register_default(self, name: str, category: ShortcutCategory, keys: str, description: str = "", action: str = "") -> Shortcut:
        sc = Shortcut(id=str(uuid.uuid4()), name=name, category=category, keys=keys, description=description, action=action)
        self._shortcuts[sc.id] = sc
        self._save()
        return sc

    def register_custom(self, user_id: str, name: str, category: ShortcutCategory, keys: str, description: str = "", action: str = "") -> Shortcut:
        sc = Shortcut(id=str(uuid.uuid4()), name=name, category=category, keys=keys, description=description, action=action, is_custom=True)
        self._shortcuts[sc.id] = sc
        self._save()
        return sc

    def get_by_category(self, category: ShortcutCategory) -> list[Shortcut]:
        return [s for s in self._shortcuts.values() if s.category == category and s.is_active]

    def get_all(self) -> list[Shortcut]:
        return [s for s in self._shortcuts.values() if s.is_active]

    def create_profile(self, user_id: str, name: str) -> ShortcutProfile:
        prof = ShortcutProfile(id=str(uuid.uuid4()), user_id=user_id, name=name)
        self._profiles[prof.id] = prof
        self._save()
        return prof

    def get_telemetry(self) -> dict: return dict(self._telemetry)
