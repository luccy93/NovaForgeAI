"""Workflow marketplace (Volume 33).

Publish / import validated workflows across tenants. Marketplace entries
store the validated DSL plus metadata; imports re-validate on install.
"""
import logging, time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)


@dataclass
class MarketplaceEntry:
    entry_id: str
    name: str
    description: str = ""
    workflow: dict = field(default_factory=dict)
    publisher: str = ""
    version: int = 1
    installed: int = 0
    published_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict:
        return self.__dict__


def _new_id() -> str:
    import uuid
    return f"mkt_{uuid.uuid4().hex[:10]}"


class Marketplace:
    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self._storage = storage or JsonFileStorage(
            "data/automation/marketplace.json")

    def publish(self, workflow: dict, name: str = "",
                description: str = "", publisher: str = "") -> MarketplaceEntry:
        entry = MarketplaceEntry(
            entry_id=_new_id(), name=name or workflow.get("name", "workflow"),
            description=description,
            workflow=workflow, publisher=publisher)
        self._storage.set(entry.entry_id, entry.to_dict())
        return entry

    def list(self, query: str = "") -> list[dict]:
        rows = [v for v in self._storage.get_all().values()]
        if query:
            q = query.lower()
            rows = [r for r in rows if q in r.get("name", "").lower()
                    or q in r.get("description", "").lower()]
        return rows

    def get(self, entry_id: str) -> Optional[MarketplaceEntry]:
        raw = self._storage.get(entry_id)
        return MarketplaceEntry(**raw) if raw else None

    def import_workflow(self, entry_id: str) -> Optional[dict]:
        entry = self.get(entry_id)
        if entry is None:
            return None
        entry.installed += 1
        self._storage.set(entry.entry_id, entry.to_dict())
        return entry.workflow

    def count(self) -> int:
        return len(self._storage.get_all())