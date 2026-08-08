"""Changelog Engine — auto-generate, categorize, template, version history."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ChangelogEntry:
    id: str; version: str; title: str; category: str = "other"  # feature, fix, breaking, perf, docs, security, refactor, other
    description: str = ""; author_id: str = ""; pr_id: str = ""
    references: list = field(default_factory=list); tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ChangelogEntry": return cls(**data)

class ChangelogEngine:
    def __init__(self, storage_dir: str = "release_data/changelogs"):
        self.storage_dir = storage_dir; self._entries: dict[str, ChangelogEntry] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "changelogs.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._entries[k] = ChangelogEntry.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._entries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def add_entry(self, version: str, title: str, category: str = "other", description: str = "", author_id: str = "", pr_id: str = "") -> ChangelogEntry:
        e = ChangelogEntry(id=str(uuid.uuid4()), version=version, title=title, category=category, description=description, author_id=author_id, pr_id=pr_id)
        self._entries[e.id] = e; self._save(); return e

    def generate(self, version: str, format: str = "markdown") -> str:
        entries = sorted([e for e in self._entries.values() if e.version == version], key=lambda e: e.created_at)
        if format == "markdown":
            lines = [f"## Version {version}", "", "### Changes", ""]
            for e in entries:
                lines.append(f"- **[{e.category}]** {e.title}")
                if e.description: lines.append(f"  {e.description}")
            lines.append(""); return "\n".join(lines)
        if format == "json":
            return json.dumps([e.to_dict() for e in entries], indent=2, default=str)
        return ""

    def list_by_version(self, version: str) -> list[ChangelogEntry]:
        return sorted([e for e in self._entries.values() if e.version == version], key=lambda e: e.created_at, reverse=True)

    def get_telemetry(self) -> dict: return {"total_entries": len(self._entries)}
