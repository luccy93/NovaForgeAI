"""Live Code Review — real-time review, inline comments, AI suggestions, approval, analytics."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ReviewComment:
    id: str; review_id: str; user_id: str; file: str; line: int = 0; content: str = ""
    is_ai_suggestion: bool = False; resolved: bool = False; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class LiveReview:
    id: str; org_id: str; repository_id: str; title: str; pr_id: str = ""
    participants: list = field(default_factory=list); comments: list = field(default_factory=list)
    status: str = "open"; approval_count: int = 0; required_approvals: int = 1
    ai_summary: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "LiveReview": return cls(**data)

class LiveCodeReview:
    def __init__(self, storage_dir: str = "rtc_data/reviews"):
        self.storage_dir = storage_dir; self._reviews: dict[str, LiveReview] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "reviews.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._reviews[k] = LiveReview.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._reviews.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, repo_id: str, title: str) -> LiveReview:
        r = LiveReview(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, title=title)
        self._reviews[r.id] = r; self._save(); return r

    def add_comment(self, review_id: str, user_id: str, file: str, line: int, content: str) -> Optional[LiveReview]:
        r = self._reviews.get(review_id)
        if not r: return None
        c = ReviewComment(id=str(uuid.uuid4()), review_id=review_id, user_id=user_id, file=file, line=line, content=content)
        r.comments.append(c); self._save(); return r

    def approve(self, review_id: str, user_id: str) -> Optional[LiveReview]:
        r = self._reviews.get(review_id)
        if not r: return None
        if user_id not in r.participants: r.participants.append(user_id)
        r.approval_count += 1
        if r.approval_count >= r.required_approvals: r.status = "approved"
        self._save(); return r

    def get_active(self, org_id: str) -> list[LiveReview]:
        return [r for r in self._reviews.values() if r.org_id == org_id and r.status == "open"]
