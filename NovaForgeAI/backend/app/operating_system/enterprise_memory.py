"""Enterprise Memory — persistent organization, project, repository, architecture, decision, conversation, and engineering memory with versioned learning."""

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


class MemoryType(Enum):
    ORGANIZATION = "organization"
    PROJECT = "project"
    REPOSITORY = "repository"
    ARCHITECTURE = "architecture"
    DECISION = "decision"
    CONVERSATION = "conversation"
    ENGINEERING = "engineering"


@dataclass
class MemoryRecord:
    id: str
    type: MemoryType
    key: str
    content: Any
    source: str = ""
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5  # 0-1
    access_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    ttl_days: Optional[int] = 365
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemorySnapshot:
    timestamp: str
    total_records: int
    memory_types: dict[str, int]
    summary: str = ""


class EnterpriseMemory:
    """Persistent enterprise memory with cross-context recall, importance scoring, and TTL management."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage = Path(storage_path) if storage_path else Path(".novaforge/memory")
        self.storage.mkdir(parents=True, exist_ok=True)
        self.records: dict[str, MemoryRecord] = {}
        self.snapshots: list[MemorySnapshot] = []
        self._load()

    def remember(self, mem_type: MemoryType, key: str, content: Any, source: str = "",
                 tags: list[str] = None, importance: float = 0.5) -> MemoryRecord:
        rid = f"mem-{uuid.uuid4().hex[:12]}"
        existing = self._find_existing(mem_type, key)
        if existing:
            existing.content = content
            existing.source = source or existing.source
            existing.importance = max(existing.importance, importance)
            existing.access_count += 1
            if tags:
                existing.tags = list(set(existing.tags + tags))
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return existing

        record = MemoryRecord(
            id=rid, type=mem_type, key=key, content=content,
            source=source, tags=tags or [], importance=importance,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.records[rid] = record
        self._save()
        return record

    def recall(self, query: str, mem_type: Optional[MemoryType] = None,
               max_results: int = 10, min_importance: float = 0.0) -> list[MemoryRecord]:
        results = []
        for record in self.records.values():
            if mem_type and record.type != mem_type:
                continue
            if record.importance < min_importance:
                continue
            if query.lower() in record.key.lower() or query.lower() in str(record.content).lower():
                results.append(record)
                record.access_count += 1
            elif any(query.lower() in t.lower() for t in record.tags):
                results.append(record)
                record.access_count += 1

        results.sort(key=lambda r: (r.importance, r.access_count), reverse=True)
        self._save()
        return results[:max_results]

    def get_context(self, context_key: str, mem_types: list[MemoryType] = None) -> str:
        records = self.recall(context_key, max_results=20)
        if mem_types:
            records = [r for r in records if r.type in mem_types]
        if not records:
            return ""
        parts = []
        for r in records[:10]:
            content_str = str(r.content)[:200]
            parts.append(f"[{r.type.value}] {r.key}: {content_str}")
        return "\n".join(parts)

    def store_organization_memory(self, org_name: str, data: dict):
        self.remember(MemoryType.ORGANIZATION, f"org:{org_name}", data,
                      tags=["organization", org_name], importance=0.9)

    def store_project_memory(self, project_name: str, data: dict):
        self.remember(MemoryType.PROJECT, f"project:{project_name}", data,
                      tags=["project", project_name], importance=0.8)

    def store_repository_memory(self, repo_path: str, data: dict):
        self.remember(MemoryType.REPOSITORY, f"repo:{repo_path}", data,
                      tags=["repository"], importance=0.7)

    def store_architecture_memory(self, component: str, data: dict):
        self.remember(MemoryType.ARCHITECTURE, f"arch:{component}", data,
                      tags=["architecture", component], importance=0.8)

    def store_decision_memory(self, decision_id: str, data: dict):
        self.remember(MemoryType.DECISION, f"decision:{decision_id}", data,
                      tags=["decision"], importance=0.9)

    def store_conversation_memory(self, conversation_id: str, summary: str):
        self.remember(MemoryType.CONVERSATION, f"conv:{conversation_id}", summary,
                      tags=["conversation"], importance=0.4, ttl_days=90)

    def store_engineering_memory(self, key: str, data: Any):
        self.remember(MemoryType.ENGINEERING, f"eng:{key}", data,
                      tags=["engineering"], importance=0.6)

    def forget_old(self, max_age_days: int = 365):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        to_delete = []
        for rid, record in self.records.items():
            if record.ttl_days:
                ttl_cutoff = (datetime.fromisoformat(record.created_at) +
                              timedelta(days=record.ttl_days)).isoformat()
                if ttl_cutoff < datetime.now(timezone.utc).isoformat():
                    to_delete.append(rid)
        for rid in to_delete:
            del self.records[rid]
        if to_delete:
            self._save()

    def get_statistics(self) -> dict:
        type_counts = defaultdict(int)
        total_importance = 0.0
        total_access = 0

        for record in self.records.values():
            type_counts[record.type.value] += 1
            total_importance += record.importance
            total_access += record.access_count

        n = max(len(self.records), 1)
        return {
            "total_records": len(self.records),
            "memory_types": dict(type_counts),
            "avg_importance": round(total_importance / n, 3),
            "avg_access_count": round(total_access / n, 1),
            "snapshots_taken": len(self.snapshots),
        }

    def snapshot(self):
        type_counts = defaultdict(int)
        for r in self.records.values():
            type_counts[r.type.value] += 1
        snapshot = MemorySnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_records=len(self.records),
            memory_types=dict(type_counts),
            summary=f"{len(self.records)} records across {len(type_counts)} memory types",
        )
        self.snapshots.append(snapshot)
        if len(self.snapshots) > 100:
            self.snapshots = self.snapshots[-100:]

    def _find_existing(self, mem_type: MemoryType, key: str) -> Optional[MemoryRecord]:
        for record in self.records.values():
            if record.type == mem_type and record.key == key:
                return record
        return None

    def _save(self):
        data = {
            "records": {k: self._serialize(v) for k, v in self.records.items()},
            "snapshots": [s.__dict__ for s in self.snapshots],
        }
        (self.storage / "memory.json").write_text(json.dumps(data, indent=2, default=str))

    def _load(self):
        mem_file = self.storage / "memory.json"
        if mem_file.exists():
            try:
                data = json.loads(mem_file.read_text())
                for k, v in data.get("records", {}).items():
                    v["type"] = MemoryType(v["type"]) if isinstance(v["type"], str) else v["type"]
                    self.records[k] = MemoryRecord(**v)
                self.snapshots = [MemorySnapshot(**s) for s in data.get("snapshots", [])]
            except Exception:
                pass

    def _serialize(self, record: MemoryRecord) -> dict:
        d = record.__dict__.copy()
        d["type"] = record.type.value
        return d
