"""Knowledge store for automation (Volume 33).

Structured learnings attached to workflows: runbook entries, step
troubleshooting, and post-run outcomes. Tenants keep their own entries.
"""
import logging, time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    knowledge_id: str
    workflow_id: str
    step_id: str = ""
    title: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = "manual"  # manual | run_outcome | ai
    organization_id: str = ""
    created_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict:
        return self.__dict__


def _new_id() -> str:
    import uuid
    return f"kn_{uuid.uuid4().hex[:10]}"


class KnowledgeStore:
    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self._storage = storage or JsonFileStorage(
            "data/automation/knowledge.json")

    def add(self, body: str, workflow_id: str = "", step_id: str = "",
            title: str = "", tags: list[str] | None = None,
            source: str = "manual",
            organization_id: str = "") -> KnowledgeEntry:
        entry = KnowledgeEntry(knowledge_id=_new_id(), workflow_id=workflow_id,
                               step_id=step_id, title=title or body[:60],
                               body=body, tags=tags or [], source=source,
                               organization_id=organization_id)
        self._storage.set(
            f"{organization_id or 'default'}:{entry.knowledge_id}",
            entry.to_dict())
        return entry

    def search(self, query: str = "", organization_id: str = "",
               tags: list[str] | None = None, limit: int = 20) -> list[dict]:
        prefix = f"{organization_id or 'default'}:"
        rows = [v for k, v in self._storage.get_all().items()
                if k.startswith(prefix)]
        q = query.lower()
        if q:
            rows = [r for r in rows if q in r.get("body", "").lower()
                    or q in r.get("title", "").lower()
                    or q in r.get("workflow_id", "").lower()]
        if tags:
            rows = [r for r in rows if any(t in r.get("tags", [])
                                           for t in tags)]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def count(self) -> int:
        return len(self._storage.get_all())