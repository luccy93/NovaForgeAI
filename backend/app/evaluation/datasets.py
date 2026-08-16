"""Versioned evaluation dataset platform (Volume 34).

Immutability contract: published versions are never mutated. All changes go
through new versions; lineage tracks parent versions; diff/compare operate
on version snapshots. Backed by the unified JsonFileStorage backend.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..common.storage import JsonFileStorage
from .models import DatasetExample, DatasetVersion, EvalDataset

logger = logging.getLogger(__name__)

TASK_TYPES = {
    "qa", "code_generation", "code_repair", "code_review", "security",
    "testing", "documentation", "architecture", "repository_understanding",
    "rag", "agent", "multimodal", "tool_use", "workflow",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checksum(examples: list[dict]) -> str:
    blob = json.dumps(examples, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class DatasetManager:
    """Versioned dataset store with lineage, diff, compare and lifecycle."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/evaluation/datasets.json")

    # ─────────────────────────────────────────────── dataset CRUD ──
    def create(self, name: str, task_type: str = "qa", description: str = "",
               owner: str = "", organization_id: str = "",
               workspace: str = "", tags: Optional[list[str]] = None,
               metadata: Optional[dict] = None) -> dict:
        if not name or not name.strip():
            raise ValueError("dataset name must not be empty")
        if task_type not in TASK_TYPES:
            raise ValueError(f"unsupported task_type '{task_type}'")
        now = _now()
        dataset = EvalDataset(
            id=uuid.uuid4().hex[:12],
            name=name.strip(),
            task_type=task_type,
            description=description,
            owner=owner,
            organization_id=organization_id,
            workspace=workspace,
            tags=tags or [],
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.storage.set(dataset.id, dataset.to_dict())
        return dataset.to_dict()

    def get(self, dataset_id: str) -> dict:
        record = self.storage.get(dataset_id)
        if not record:
            raise KeyError(f"dataset '{dataset_id}' not found")
        return record

    def list_datasets(self, organization_id: str = "", task_type: str = "") -> list[dict]:
        datasets = []
        for record in self.storage.get_all().values():
            if not isinstance(record, dict):
                continue
            if organization_id and record.get("organization_id") != organization_id:
                continue
            if task_type and record.get("task_type") != task_type:
                continue
            datasets.append(record)
        return sorted(datasets, key=lambda d: d.get("updated_at", ""), reverse=True)

    def delete(self, dataset_id: str) -> bool:
        record = self.storage.get(dataset_id)
        if not record:
            raise KeyError(f"dataset '{dataset_id}' not found")
        for vid in record.get("version_ids", []):
            self.storage.delete(f"{dataset_id}::{vid}")
        self.storage.delete(dataset_id)
        return True

    # ─────────────────────────────────────────────── versioning ──
    def add_version(self, dataset_id: str, examples: list[dict],
                    notes: str = "", created_by: str = "") -> dict:
        """Create a new version from raw example dicts. Never mutates old ones."""
        dataset = self.get(dataset_id)
        cleaned = []
        for i, example in enumerate(examples):
            cleaned.append(self._normalize_example(example, i).to_dict())
        version_num = dataset.get("latest_version", 0) + 1
        parent = dataset.get("latest_version") or None
        version = DatasetVersion(
            id=uuid.uuid4().hex[:12],
            dataset_id=dataset_id,
            version=version_num,
            examples=cleaned,
            notes=notes,
            status="draft",
            parent_version=parent,
            created_at=_now(),
            created_by=created_by,
            checksum=_checksum(cleaned),
        )
        self.storage.set(f"{dataset_id}::{version_num}", version.to_dict())
        dataset["version_ids"] = dataset.get("version_ids", []) + [f"{dataset_id}::{version_num}"]
        dataset["latest_version"] = version_num
        dataset["updated_at"] = _now()
        self.storage.set(dataset_id, dataset)
        return version.to_dict()

    def get_version(self, dataset_id: str, version: int) -> dict:
        record = self.storage.get(f"{dataset_id}::{version}")
        if not record:
            raise KeyError(f"dataset '{dataset_id}' version {version} not found")
        return record

    def list_versions(self, dataset_id: str) -> list[dict]:
        self.get(dataset_id)
        versions = []
        for key, record in self.storage.get_all().items():
            if key.startswith(f"{dataset_id}::") and isinstance(record, dict):
                versions.append(record)
        return sorted(versions, key=lambda v: v.get("version", 0))

    def clone(self, dataset_id: str, new_name: str = "",
              organization_id: str = "") -> dict:
        """Clone the latest published (or latest) version into a new dataset."""
        src = self.get(dataset_id)
        latest = self.get_version(dataset_id, src.get("latest_version", 1))
        clone = self.create(
            name=new_name or f"{src['name']} (clone)",
            task_type=src.get("task_type", "qa"),
            description=src.get("description", ""),
            organization_id=organization_id or src.get("organization_id", ""),
            workspace=src.get("workspace", ""),
            tags=src.get("tags", []),
            metadata=dict(src.get("metadata", {}), cloned_from=dataset_id),
        )
        self.add_version(clone["id"], latest.get("examples", []),
                         notes=f"cloned from {dataset_id} v{latest['version']}")
        return self.get(clone["id"])

    def publish(self, dataset_id: str, version: int | None = None) -> dict:
        dataset = self.get(dataset_id)
        version_num = version or dataset.get("latest_version")
        record = self.get_version(dataset_id, version_num)
        if record.get("status") == "published":
            return record
        record["status"] = "published"
        record["published_at"] = _now()
        self.storage.set(f"{dataset_id}::{version_num}", record)
        return record

    def archive(self, dataset_id: str, archive_versions: bool = False) -> dict:
        dataset = self.get(dataset_id)
        dataset["status"] = "archived"
        dataset["updated_at"] = _now()
        if archive_versions:
            for vid in dataset.get("version_ids", []):
                record = self.storage.get(vid)
                if record:
                    record["status"] = "archived"
                    self.storage.set(vid, record)
        self.storage.set(dataset_id, dataset)
        return dataset

    def rollback(self, dataset_id: str, version: int) -> dict:
        """Roll back to an earlier version by creating a new version from it."""
        dataset = self.get(dataset_id)
        old = self.get_version(dataset_id, version)
        return self.add_version(dataset_id, old.get("examples", []),
                                notes=f"rolled back to v{version}",
                                created_by="rollback")

    def diff(self, dataset_id: str, version_a: int, version_b: int) -> dict:
        """Structural diff between two versions (example ids + content changes)."""
        a = self.get_version(dataset_id, version_a)
        b = self.get_version(dataset_id, version_b)
        by_id_a = {e.get("id"): e for e in a.get("examples", [])}
        by_id_b = {e.get("id"): e for e in b.get("examples", [])}
        added, removed, changed, unchanged = [], [], [], []
        for eid, example in by_id_b.items():
            if eid not in by_id_a:
                added.append(eid)
            elif example != by_id_a[eid]:
                changed.append(eid)
            else:
                unchanged.append(eid)
        for eid in by_id_a:
            if eid not in by_id_b:
                removed.append(eid)
        return {
            "dataset_id": dataset_id,
            "version_a": version_a,
            "version_b": version_b,
            "added": added, "removed": removed, "changed": changed,
            "unchanged": unchanged,
            "added_count": len(added), "removed_count": len(removed),
            "changed_count": len(changed),
        }

    def compare(self, dataset_id: str, version_a: int, version_b: int) -> dict:
        """Comparable summary of two versions (sizes, checksums, fields)."""
        a = self.get_version(dataset_id, version_a)
        b = self.get_version(dataset_id, version_b)
        return {
            "dataset_id": dataset_id,
            "a": {"version": version_a, "examples": len(a.get("examples", [])),
                  "checksum": a.get("checksum"), "status": a.get("status")},
            "b": {"version": version_b, "examples": len(b.get("examples", [])),
                  "checksum": b.get("checksum"), "status": b.get("status")},
            "identical": a.get("checksum") == b.get("checksum"),
        }

    def lineage(self, dataset_id: str, version: int | None = None) -> dict:
        """Walk parent pointers to build the version lineage chain."""
        dataset = self.get(dataset_id)
        current = version or dataset.get("latest_version")
        chain = []
        while current is not None:
            record = self.get_version(dataset_id, current)
            chain.append({"version": record["version"], "notes": record.get("notes", ""),
                          "checksum": record.get("checksum"), "status": record.get("status")})
            current = record.get("parent_version")
        return {"dataset_id": dataset_id, "lineage": chain}

    @staticmethod
    def _normalize_example(example: dict, index: int) -> DatasetExample:
        if isinstance(example, DatasetExample):
            return example
        if not isinstance(example, dict):
            raise ValueError(f"example {index} must be a dict")
        if "input" not in example:
            raise ValueError(f"example {index} is missing required field 'input'")
        return DatasetExample(
            id=example.get("id") or uuid.uuid4().hex[:12],
            input=str(example["input"]),
            context=list(example.get("context") or []),
            expected_output=str(example.get("expected_output", "")),
            reference_answer=str(example.get("reference_answer", "")),
            expected_files=list(example.get("expected_files") or []),
            expected_code=str(example.get("expected_code", "")),
            expected_citations=list(example.get("expected_citations") or []),
            expected_actions=list(example.get("expected_actions") or []),
            metadata=dict(example.get("metadata") or {}),
            difficulty=str(example.get("difficulty", "medium")),
            tags=list(example.get("tags") or []),
            created_at=_now(),
        )
