"""Engineering Discussions — threaded discussions, RFC reviews, design reviews, technical decisions."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Discussion:
    id: str; org_id: str; title: str; topic: str = "general"
    author_id: str = ""; participants: list = field(default_factory=list)
    comments: list = field(default_factory=list); tags: list = field(default_factory=list)
    is_resolved: bool = False; is_pinned: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Discussion": return cls(**data)

class EngineeringDiscussions:
    def __init__(self, storage_dir: str = "rtc_data/discussions"):
        self.storage_dir = storage_dir; self._discussions: dict[str, Discussion] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "discussions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._discussions[k] = Discussion.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._discussions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, title: str, topic: str = "general", author_id: str = "") -> Discussion:
        d = Discussion(id=str(uuid.uuid4()), org_id=org_id, title=title, topic=topic, author_id=author_id)
        self._discussions[d.id] = d; self._save(); return d

    def add_comment(self, disc_id: str, user_id: str, content: str) -> Optional[Discussion]:
        d = self._discussions.get(disc_id)
        if not d: return None
        d.comments.append({"user_id": user_id, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()})
        if user_id not in d.participants: d.participants.append(user_id)
        d.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return d

    def resolve(self, disc_id: str) -> Optional[Discussion]:
        d = self._discussions.get(disc_id)
        if not d: return None
        d.is_resolved = True; self._save(); return d
