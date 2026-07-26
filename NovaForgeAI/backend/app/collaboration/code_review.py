"""Collaborative Code Review — shared reviews, review threads, assignments, approval workflows, AI suggestions, comment resolution, review analytics."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ReviewStatus(Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    MERGED = "merged"
    CLOSED = "closed"


@dataclass
class ReviewThread:
    id: str
    review_id: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    comment: str = ""
    author_id: str = ""
    resolved: bool = False
    resolved_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ReviewThread": return cls(**data)


@dataclass
class Review:
    id: str
    org_id: str
    repo_id: str
    pull_request_id: str
    title: str
    status: ReviewStatus = ReviewStatus.OPEN
    author_id: str = ""
    reviewers: list = field(default_factory=list)
    assignees: list = field(default_factory=list)
    threads: list = field(default_factory=list)
    ai_suggestions: list = field(default_factory=list)
    comments_count: int = 0
    files_changed: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Review":
        data = data.copy()
        data["status"] = ReviewStatus(data.get("status", "open"))
        return cls(**data)


class CodeReviewService:
    def __init__(self, storage_dir: str = "collab_data/reviews"):
        self.storage_dir = storage_dir
        self._reviews: dict[str, Review] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "reviews.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._reviews[k] = Review.from_dict(v)
                    except Exception as e: logger.warning("Skipping review %s: %s", k, e)
            except Exception as e: logger.error("Failed to load reviews: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reviews.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save reviews: %s", e)

    def create_review(self, org_id: str, repo_id: str, pull_request_id: str, title: str, author_id: str, reviewers: list = None, assignees: list = None) -> Review:
        review = Review(id=str(uuid.uuid4()), org_id=org_id, repo_id=repo_id, pull_request_id=pull_request_id, title=title, author_id=author_id, reviewers=reviewers or [], assignees=assignees or [])
        self._reviews[review.id] = review
        self._save()
        return review

    def get_review(self, review_id: str) -> Optional[Review]: return self._reviews.get(review_id)

    def update_review(self, review_id: str, updates: dict) -> Optional[Review]:
        review = self._reviews.get(review_id)
        if not review: return None
        for k, v in updates.items():
            if hasattr(review, k) and k not in ("id", "created_at"):
                if k == "status": setattr(review, k, ReviewStatus(v) if isinstance(v, str) else v)
                else: setattr(review, k, v)
        review.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return review

    def add_thread(self, review_id: str, file_path: str, comment: str, author_id: str, line_start: int = 0, line_end: int = 0) -> Optional[ReviewThread]:
        review = self._reviews.get(review_id)
        if not review: return None
        thread = ReviewThread(id=str(uuid.uuid4()), review_id=review_id, file_path=file_path, line_start=line_start, line_end=line_end, comment=comment, author_id=author_id)
        review.threads.append(thread.to_dict())
        review.comments_count += 1
        review.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return thread

    def resolve_thread(self, review_id: str, thread_id: str, resolved_by: str) -> bool:
        review = self._reviews.get(review_id)
        if not review: return False
        for t in review.threads:
            if t.get("id") == thread_id:
                t["resolved"] = True
                t["resolved_by"] = resolved_by
                break
        review.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def add_ai_suggestion(self, review_id: str, suggestion: str, file_path: str = "", line: int = 0) -> bool:
        review = self._reviews.get(review_id)
        if not review: return False
        review.ai_suggestions.append({"suggestion": suggestion, "file_path": file_path, "line": line, "created_at": datetime.now(timezone.utc).isoformat()})
        review.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def list_reviews(self, org_id: str = "", repo_id: str = "", reviewer_id: str = "", status: Optional[ReviewStatus] = None) -> list[Review]:
        results = list(self._reviews.values())
        if org_id: results = [r for r in results if r.org_id == org_id]
        if repo_id: results = [r for r in results if r.repo_id == repo_id]
        if reviewer_id: results = [r for r in results if reviewer_id in r.reviewers]
        if status: results = [r for r in results if r.status == status]
        return sorted(results, key=lambda r: r.updated_at, reverse=True)

    def get_analytics(self, org_id: str) -> dict:
        reviews = [r for r in self._reviews.values() if r.org_id == org_id]
        return {
            "total": len(reviews),
            "open": sum(1 for r in reviews if r.status == ReviewStatus.OPEN),
            "approved": sum(1 for r in reviews if r.status == ReviewStatus.APPROVED),
            "changes_requested": sum(1 for r in reviews if r.status == ReviewStatus.CHANGES_REQUESTED),
            "avg_comments": round(sum(r.comments_count for r in reviews) / max(len(reviews), 1), 2),
            "avg_reviewers": round(sum(len(r.reviewers) for r in reviews) / max(len(reviews), 1), 2),
        }

    def get_telemetry(self) -> dict: return dict(self._telemetry)
