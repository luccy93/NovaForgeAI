"""PR Automation — auto-create, review, labels, merge, changelog generation."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class PRStatus(Enum):
    OPEN = "open"; APPROVED = "approved"; MERGED = "merged"; CLOSED = "closed"; DRAFT = "draft"

@dataclass
class PullRequest:
    id: str; org_id: str; repository_id: str; title: str; description: str = ""
    source_branch: str = ""; target_branch: str = "main"
    status: PRStatus = PRStatus.DRAFT
    author_id: str = ""; reviewers: list = field(default_factory=list)
    labels: list = field(default_factory=list); tags: list = field(default_factory=list)
    commit_count: int = 0; changed_files: list = field(default_factory=list)
    ai_summary: str = ""; merge_commit_sha: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    merged_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d
    @classmethod
    def from_dict(cls, data: dict) -> "PullRequest":
        data = data.copy(); data["status"] = PRStatus(data.get("status", "draft")); return cls(**data)

class PRAutomation:
    def __init__(self, storage_dir: str = "release_data/prs"):
        self.storage_dir = storage_dir; self._prs: dict[str, PullRequest] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "prs.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._prs[k] = PullRequest.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._prs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, repo_id: str, title: str, source: str, target: str = "main", description: str = "") -> PullRequest:
        pr = PullRequest(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, title=title, source_branch=source, target_branch=target, description=description)
        self._prs[pr.id] = pr; self._save(); return pr

    def auto_create_from_branch(self, org_id: str, repo_id: str, branch: str, target: str = "main") -> PullRequest:
        title = f"Auto PR: {branch.replace('_', ' ').replace('-', ' ').title()}"
        return self.create(org_id, repo_id, title, branch, target)

    def approve(self, pr_id: str, reviewer_id: str) -> Optional[PullRequest]:
        pr = self._prs.get(pr_id)
        if not pr: return None
        if reviewer_id not in pr.reviewers: pr.reviewers.append(reviewer_id)
        pr.status = PRStatus.APPROVED; pr.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return pr

    def merge(self, pr_id: str) -> Optional[PullRequest]:
        pr = self._prs.get(pr_id)
        if not pr: return None
        pr.status = PRStatus.MERGED; pr.merged_at = datetime.now(timezone.utc).isoformat()
        pr.merge_commit_sha = str(uuid.uuid4()).replace("-", ""); self._save(); return pr

    def generate_ai_summary(self, pr_id: str) -> Optional[PullRequest]:
        pr = self._prs.get(pr_id)
        if not pr: return None
        pr.ai_summary = f"Auto-generated summary for PR: {pr.title} (files: {', '.join(pr.changed_files) if pr.changed_files else 'N/A'})"
        self._save(); return pr
