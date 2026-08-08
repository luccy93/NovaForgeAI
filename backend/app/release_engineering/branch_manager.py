"""Branch Manager — policies, lifecycle, naming conventions, auto-cleanup."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Branch:
    id: str; org_id: str; repository_id: str; name: str; source_branch: str = ""
    is_default: bool = False; is_protected: bool = False
    commit_sha: str = ""; author_id: str = ""; pr_id: str = ""
    policies: dict = field(default_factory=dict); tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Branch": return cls(**data)

class BranchManager:
    def __init__(self, storage_dir: str = "release_data/branches"):
        self.storage_dir = storage_dir; self._branches: dict[str, Branch] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "branches.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._branches[k] = Branch.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._branches.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, repo_id: str, name: str, source: str = "", protected: bool = False) -> Branch:
        b = Branch(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, name=name, source_branch=source, is_protected=protected)
        self._branches[b.id] = b; self._save(); return b

    def get(self, branch_id: str) -> Optional[Branch]: return self._branches.get(branch_id)

    def list_by_repo(self, org_id: str, repo_id: str) -> list[Branch]:
        return sorted([b for b in self._branches.values() if b.org_id == org_id and b.repository_id == repo_id], key=lambda b: b.name)

    def protect(self, branch_id: str, policies: dict = None) -> Optional[Branch]:
        b = self._branches.get(branch_id)
        if not b: return None
        b.is_protected = True
        if policies: b.policies.update(policies)
        b.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return b

    def merge(self, source_id: str, target_id: str) -> Optional[Branch]:
        target = self._branches.get(target_id); source = self._branches.get(source_id)
        if not target or not source: return None
        target.commit_sha = source.commit_sha; target.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(); return target
