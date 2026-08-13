"""Data Archival Engine - ledger of archived snapshots with retrieval and deletion."""
import time, json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ArchiveEntry:
    snapshot_id: str
    dataset: str
    rows: int
    payload: list[dict]
    policy: str = ""
    created_at: str = ""


class ArchiveLedger:
    """Append-only ledger of archived dataset snapshots."""

    def __init__(self, storage=None, namespace: str = "lakehouse.archive"):
        self.storage = storage
        self.namespace = namespace
        self._entries: list[ArchiveEntry] = []

    def archive(self, dataset: str, payload: list[dict], policy: str = "") -> ArchiveEntry:
        entry = ArchiveEntry(
            snapshot_id=f"arch-{int(time.time() * 1000)}",
            dataset=dataset,
            rows=len(payload),
            payload=list(payload),
            policy=policy,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._entries.append(entry)
        if self.storage is not None:
            self.storage.save_json(self.namespace, entry.snapshot_id, entry.__dict__)
        return entry

    def find(self, dataset: str, limit: int = 25) -> list[ArchiveEntry]:
        matches = [e for e in self._entries if e.dataset == dataset]
        return matches[-limit:]

    def restore(self, snapshot_id: str) -> Optional[list[dict]]:
        for e in self._entries:
            if e.snapshot_id == snapshot_id:
                return list(e.payload)
        return None

    def count(self) -> int:
        return len(self._entries)


class ArchivalEngine:
    """Coordinates retention-driven archiving: receives expired items and archives them."""

    def __init__(self, ledger: Optional[ArchiveLedger] = None):
        self.ledger = ledger or ArchiveLedger()
        self.runs: list[dict] = []

    def archive(self, dataset: str, payload: list[dict], policy: str = "") -> dict:
        entry = self.ledger.archive(dataset, payload, policy)
        record = {"dataset": dataset, "snapshot_id": entry.snapshot_id,
                  "rows": entry.rows, "policy": policy,
                  "at": datetime.now(timezone.utc).isoformat()}
        self.runs.append(record)
        return record

    def restore(self, snapshot_id: str) -> Optional[list[dict]]:
        return self.ledger.restore(snapshot_id)

    def find(self, dataset: str, limit: int = 25) -> list[dict]:
        return [{"snapshot_id": e.snapshot_id, "dataset": e.dataset, "rows": e.rows,
                 "policy": e.policy, "created_at": e.created_at}
                for e in self.ledger.find(dataset, limit)]

    def ingest_retention_output(self, merged: dict) -> dict:
        self.runs.append(merged)
        return merged