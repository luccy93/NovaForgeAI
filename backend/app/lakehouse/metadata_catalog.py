"""Metadata Catalog - datasets, tables, columns, schemas, pipelines, reports, metrics, owners."""
import os, json, uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class CatalogKinds:
    DATASET = "dataset"
    TABLE = "table"
    COLUMN = "column"
    SCHEMA = "schema"
    PIPELINE = "pipeline"
    REPORT = "report"
    METRIC = "metric"
    DASHBOARD = "dashboard"
    OWNER = "owner"
    CLASSIFICATION = "classification"
    RETENTION_POLICY = "retention_policy"
    LINEAGE = "lineage"


@dataclass
class CatalogEntry:
    kind: str
    name: str
    attrs: dict = field(default_factory=dict)
    id: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class MetadataCatalog:
    """Central catalog of data assets with ownership, classification, and search."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.entries: list[CatalogEntry] = []

    def register(self, kind: str, name: str, **attrs) -> CatalogEntry:
        entry = CatalogEntry(kind=kind, name=name, attrs=attrs)
        self.entries.append(entry)
        return entry

    def search(self, query: str = "", kind: Optional[str] = None) -> list[dict]:
        q = query.lower()
        result = []
        for e in self.entries:
            if kind and e.kind != kind:
                continue
            name_hit = q in e.name.lower()
            attr_hit = any(q in str(v).lower() for v in e.attrs.values())
            if not q or name_hit or attr_hit:
                result.append(self._render(e))
        return result

    def get(self, entry_id: str) -> Optional[dict]:
        for e in self.entries:
            if e.id == entry_id:
                return self._render(e)
        return None

    def by_kind(self, kind: str) -> list[dict]:
        return [self._render(e) for e in self.entries if e.kind == kind]

    def owners_for(self, name: str) -> list[dict]:
        return [self._render(e) for e in self.entries
                if e.kind == CatalogKinds.OWNER and e.attrs.get("asset") == name]

    def lineage_for(self, asset: str) -> list[dict]:
        return [self._render(e) for e in self.entries
                if e.kind == CatalogKinds.LINEAGE and e.attrs.get("asset") == asset]

    @staticmethod
    def _render(e: CatalogEntry) -> dict:
        return {"id": e.id, "kind": e.kind, "name": e.name, "attrs": e.attrs,
                "created_at": e.created_at}

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.kind] = counts.get(e.kind, 0) + 1
        return {"total": len(self.entries), "by_kind": counts}