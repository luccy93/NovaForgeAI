"""Developer Preferences — theme, AI provider, model, coding style, formatting, language, keyboard shortcuts, workspace settings, notification prefs."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DeveloperPreferences:
    id: str
    user_id: str
    org_id: str
    theme: str = "dark"
    ai_provider: str = "openai"
    ai_model: str = "gpt-4"
    coding_style: str = ""
    formatting_rules: dict = field(default_factory=dict)
    language: str = "python"
    keyboard_shortcuts: dict = field(default_factory=dict)
    workspace_settings: dict = field(default_factory=dict)
    notification_prefs: dict = field(default_factory=lambda: {"email": True, "push": True, "slack": False, "digest": "daily"})
    extensions: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "DeveloperPreferences": return cls(**data)


class DevPreferencesService:
    def __init__(self, storage_dir: str = "dx_data/preferences"):
        self.storage_dir = storage_dir
        self._prefs: dict[str, DeveloperPreferences] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "preferences.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._prefs[k] = DeveloperPreferences.from_dict(v)
                    except Exception as e: logger.warning("Skipping prefs %s: %s", k, e)
            except Exception as e: logger.error("Failed to load preferences: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._prefs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save preferences: %s", e)

    def get_or_create(self, user_id: str, org_id: str) -> DeveloperPreferences:
        for p in self._prefs.values():
            if p.user_id == user_id: return p
        prefs = DeveloperPreferences(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id)
        self._prefs[prefs.id] = prefs
        self._save()
        return prefs

    def update(self, user_id: str, updates: dict) -> Optional[DeveloperPreferences]:
        for p in self._prefs.values():
            if p.user_id == user_id:
                for k, v in updates.items():
                    if hasattr(p, k) and k not in ("id", "user_id", "created_at"): setattr(p, k, v)
                p.updated_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return p
        return None

    def get_telemetry(self) -> dict: return dict(self._telemetry)
