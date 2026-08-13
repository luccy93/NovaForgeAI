"""Data Transformation Layer - idempotent, deterministic, lineage-aware transforms over tables."""
import hashlib, uuid
from dataclasses import dataclass
from typing import Callable, Optional
from datetime import datetime, timezone


@dataclass
class Transformation:
    """A named, versioned transformation over an input table with deterministic output."""
    id: str
    name: str
    source: str
    destination: str
    fn: Callable[[list[dict]], list[dict]]
    version: int = 1
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def run(self, source_rows: list[dict]) -> list[dict]:
        return self.fn(source_rows)


class TransformEngine:
    """Registry and executor for named transforms, wired to the OLAP store."""

    def __init__(self, olap):
        self.olap = olap
        self.transforms: dict[str, Transformation] = {}
        self.history: list[dict] = []

    def register(self, name: str, source: str, destination: str,
                 fn: Callable[[list[dict]], list[dict]]) -> Transformation:
        t = Transformation(id=uuid.uuid4().hex[:12], name=name, source=source,
                           destination=destination, fn=fn)
        self.transforms[name] = t
        return t

    def run(self, name: str) -> dict:
        t = self.transforms.get(name)
        if not t:
            raise KeyError(f"unknown transform: {name}")
        rows = self.olap.rows(t.source)
        out = t.run(rows)
        self.olap.register_table(t.destination, out)
        record = {"name": name, "rows_in": len(rows), "rows_out": len(out),
                  "at": datetime.now(timezone.utc).isoformat()}
        self.history.append(record)
        return record

    def list(self) -> list[str]:
        return sorted(self.transforms.keys())


def idempotent_filter(pred) -> Callable[[list[dict]], list[dict]]:
    def _fn(rows: list[dict]) -> list[dict]:
        return [r for r in rows if pred(r)]
    return _fn


def idempotent_map(mapper) -> Callable[[list[dict]], list[dict]]:
    def _fn(rows: list[dict]) -> list[dict]:
        return [mapper(r) for r in rows]
    return _fn


def aggregate(fields: list[str], metric_fns: dict[str, Callable[[list[dict]], float]]) -> Callable[[list[dict]], list[dict]]:
    """Groups by fields and computes metrics; deterministic order by group key."""
    def _fn(rows: list[dict]) -> list[dict]:
        buckets: dict = {}
        for r in rows:
            key = tuple(r.get(f, "") for f in fields)
            buckets.setdefault(key, []).append(r)
        out = []
        for key in sorted(buckets):
            group = buckets[key]
            row = {f: key[i] for i, f in enumerate(fields)}
            row["count"] = len(group)
            for mname, mfn in metric_fns.items():
                row[mname] = round(mfn(group), 6)
            out.append(row)
        return out
    return _fn