"""Engineering Discussions — discussion threads, architecture reviews, technical RFCs, design reviews, proposal discussions, AI moderation, decision tracking."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DiscussionType(Enum):
    DISCUSSION = "discussion"
    ARCHITECTURE_REVIEW = "architecture_review"
    RFC = "rfc"
    DESIGN_REVIEW = "design_review"
    PROPOSAL = "proposal"


class DiscussionStatus(Enum):
    DRAFT = "draft"
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    DECIDED = "decided"
    CLOSED = "closed"


@dataclass
class DiscussionComment:
    id: str
    author_id: str
    content: str
    parent_id: str = ""
    votes: int = 0
    is_accepted: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "DiscussionComment": return cls(**data)


@dataclass
class Discussion:
    id: str
    org_id: str
    title: str
    discussion_type: DiscussionType
    status: DiscussionStatus = DiscussionStatus.DRAFT
    author_id: str = ""
    description: str = ""
    comments: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    decision: str = ""
    decided_by: str = ""
    references: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["discussion_type"] = self.discussion_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Discussion":
        data = data.copy()
        data["discussion_type"] = DiscussionType(data.get("discussion_type", "discussion"))
        data["status"] = DiscussionStatus(data.get("status", "draft"))
        return cls(**data)


class EngineeringDiscussions:
    def __init__(self, storage_dir: str = "collab_data/discussions"):
        self.storage_dir = storage_dir
        self._discussions: dict[str, Discussion] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "discussions.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._discussions[k] = Discussion.from_dict(v)
                    except Exception as e: logger.warning("Skipping discussion %s: %s", k, e)
            except Exception as e: logger.error("Failed to load discussions: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._discussions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save discussions: %s", e)

    def create_discussion(self, org_id: str, title: str, discussion_type: DiscussionType, author_id: str, description: str = "", tags: list = None) -> Discussion:
        disc = Discussion(id=str(uuid.uuid4()), org_id=org_id, title=title, discussion_type=discussion_type, author_id=author_id, description=description, tags=tags or [])
        self._discussions[disc.id] = disc
        self._save()
        return disc

    def get_discussion(self, disc_id: str) -> Optional[Discussion]: return self._discussions.get(disc_id)

    def update_discussion(self, disc_id: str, updates: dict) -> Optional[Discussion]:
        disc = self._discussions.get(disc_id)
        if not disc: return None
        for k, v in updates.items():
            if hasattr(disc, k) and k not in ("id", "created_at"):
                if k == "discussion_type": setattr(disc, k, DiscussionType(v) if isinstance(v, str) else v)
                elif k == "status": setattr(disc, k, DiscussionStatus(v) if isinstance(v, str) else v)
                else: setattr(disc, k, v)
        disc.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return disc

    def add_comment(self, disc_id: str, author_id: str, content: str, parent_id: str = "") -> Optional[DiscussionComment]:
        disc = self._discussions.get(disc_id)
        if not disc: return None
        comment = DiscussionComment(id=str(uuid.uuid4()), author_id=author_id, content=content, parent_id=parent_id)
        disc.comments.append(comment.to_dict())
        disc.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return comment

    def record_decision(self, disc_id: str, decision: str, decided_by: str) -> bool:
        disc = self._discussions.get(disc_id)
        if not disc: return False
        disc.decision = decision
        disc.decided_by = decided_by
        disc.status = DiscussionStatus.DECIDED
        disc.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def list_by_org(self, org_id: str, disc_type: Optional[DiscussionType] = None, status: Optional[DiscussionStatus] = None) -> list[Discussion]:
        results = [d for d in self._discussions.values() if d.org_id == org_id]
        if disc_type: results = [d for d in results if d.discussion_type == disc_type]
        if status: results = [d for d in results if d.status == status]
        return sorted(results, key=lambda d: d.updated_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
