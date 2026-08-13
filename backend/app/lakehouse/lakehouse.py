"""Data Lakehouse - columnar analytical storage, partition pruning, compaction, evolution, snapshots."""
import json, os, uuid
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from .data_lake import LocalObjectStore


@dataclass
class ColumnSpec:
    name: str
    type: str  # string | int | float | bool | json
    nullable: bool = True
    default: object = None


class Schema:
    """Columnar table schema with versioning and compatibility checks."""

    def __init__(self, name: str, columns: list[ColumnSpec], version: int = 1):
        self.name = name
        self.columns = columns
        self.version = version
        self._by_name = {c.name: c for c in columns}

    def add_column(self, spec: ColumnSpec) -> "Schema":
        self.columns.append(spec)
        self._by_name[spec.name] = spec
        self.version += 1
        return self

    def is_compatible(self, other: "Schema", direction: str) -> bool:
        """direction: 'backward' (new writers, old readers) or 'forward' (old writers, new readers)."""
        if direction == "backward":
            base, ref = other._by_name, self._by_name
        else:
            base, ref = self._by_name, other._by_name
        for name, col in base.items():
            if name not in ref:
                return False
            if ref[name].type != col.type and not Schema._coercible(col.type, ref[name].type):
                return False
        return True

    @staticmethod
    def _coercible(a: str, b: str) -> bool:
        return (a, b) in {("int", "float"), ("string", "json")}

    def validate_row(self, row: dict) -> list[str]:
        errors = []
        for col in self.columns:
            if col.name not in row:
                if not col.nullable and col.default is None:
                    errors.append(f"missing non-null column: {col.name}")
            elif row[col.name] is None and not col.nullable:
                errors.append(f"null in non-null column: {col.name}")
            elif row[col.name] is not None and not self._type_ok(col.type, row[col.name]):
                errors.append(f"type mismatch for {col.name}: expected {col.type}")
        return errors

    @staticmethod
    def _type_ok(col_type: str, value) -> bool:
        if col_type == "string":
            return isinstance(value, str)
        if col_type == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if col_type == "float":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if col_type == "bool":
            return isinstance(value, bool)
        if col_type == "json":
            return isinstance(value, (dict, list))
        return True


@dataclass
class Snapshot:
    """Immutable table snapshot (Iceberg-style): version, data files, row count."""
    version: int
    created_at: str
    data_files: list[str] = field(default_factory=list)
    row_count: int = 0
    schema_version: int = 1


class LakeTable:
    """Analytical table on the lake: columnar batches, partitioning, pruning, compaction, snapshots."""

    def __init__(self, lakehouse: "Lakehouse", name: str, schema: Schema, partition_cols: tuple = ()):
        self.lakehouse = lakehouse
        self.name = name
        self.schema = schema
        self.partition_cols = partition_cols
        self.files: list[str] = []
        self.snapshots: list[Snapshot] = []
        self.current_snapshot: Optional[Snapshot] = None
        self.row_count = 0
        self._seq = 0
        self._buckets: dict[str, list[dict]] = {}
        if not self.current_snapshot:
            self._take_snapshot()

    def write_batch(self, rows: list[dict]) -> dict:
        accepted = []
        rejected = []
        batch_key = uuid.uuid4().hex[:8]
        for row in rows:
            errs = self.schema.validate_row(row)
            if errs:
                rejected.append({"row": row, "errors": errs})
                continue
            accepted.append(row)
        for row in accepted:
            partition = self._partition_of(row)
            self._buckets.setdefault(partition, []).append(row)
        for partition, bucket in self._buckets.items():
            key = self._batch_key(partition, batch_key)
            payload = self._serialize(bucket)
            self.lakehouse.store.put(key, payload)
            self.files.append(key)
            self.row_count += len(bucket)
        self._buckets.clear()
        self._take_snapshot()
        return {"rows_written": len(accepted), "rejected": rejected,
                "snapshot_version": self.current_snapshot.version}

    def _partition_of(self, row: dict) -> str:
        if not self.partition_cols:
            return "all"
        return "/".join(f"{c}={row.get(c, 'null')}" for c in self.partition_cols)

    def _batch_key(self, partition: str, batch_id: str) -> str:
        return f"tables/{self.name}/{partition}/part-{batch_id}.json"

    def _serialize(self, rows: list[dict]) -> bytes:
        data = {"format": "columnar-json", "schema_version": self.schema.version,
                "columns": [c.name for c in self.schema.columns],
                "rows": rows}
        return json.dumps(data, default=str).encode("utf-8")

    def _take_snapshot(self) -> None:
        version = (self.current_snapshot.version + 1) if self.current_snapshot else 1
        self.current_snapshot = Snapshot(version=version,
                                         created_at=datetime.now(timezone.utc).isoformat(),
                                         data_files=list(self.files),
                                         row_count=self.row_count,
                                         schema_version=self.schema.version)
        self.snapshots.append(self.current_snapshot)

    def scan(self, filters: Optional[dict] = None, partition: Optional[dict] = None) -> list[dict]:
        """Partition-pruned scan applying predicate filters."""
        rows = []
        for key in self.files:
            if partition and not all(f"{k}={v}" in key for k, v in partition.items()):
                continue
            if not self.lakehouse.store.exists(key):
                continue
            data = json.loads(self.lakehouse.store.get(key).decode("utf-8"))
            for row in data.get("rows", []):
                if self._matches(row, filters or {}):
                    rows.append(row)
        return rows

    @staticmethod
    def _matches(row: dict, filters: dict) -> bool:
        for k, v in filters.items():
            if row.get(k) != v:
                return False
        return True

    def count(self, filters: Optional[dict] = None) -> int:
        return len(self.scan(filters))

    def compact(self) -> "LakeTable":
        """Compaction: merges all data files into one, preserving data and versioning."""
        rows = self.scan()
        key = f"tables/{self.name}/compact/part-{self._seq:05d}.json"
        self._seq += 1
        self.lakehouse.store.put(key, self._serialize(rows))
        self.files = [key]
        self._take_snapshot()
        return self

    def evolve(self, new_schema: Schema, direction: str = "backward") -> bool:
        if not self.schema.is_compatible(new_schema, direction):
            return False
        self.schema = new_schema
        return True

    def snapshot_at(self, version: int) -> Optional[Snapshot]:
        for s in self.snapshots:
            if s.version == version:
                return s
        return None

    def size(self) -> int:
        return sum(self.lakehouse.store.size(k) for k in self.files)


class Lakehouse:
    """Lakehouse catalog: partitioned columnar tables with snapshots over a local store."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.store = LocalObjectStore(os.path.join(data_dir, "lakehouse"))
        self.tables: dict[str, LakeTable] = {}

    def create_table(self, name: str, schema: Schema, partition_cols: tuple = ()) -> LakeTable:
        if name in self.tables:
            return self.tables[name]
        table = LakeTable(self, name, schema, partition_cols)
        self.tables[name] = table
        return table

    def table(self, name: str) -> Optional[LakeTable]:
        return self.tables.get(name)

    def list_tables(self) -> list[str]:
        return sorted(self.tables.keys())

    def health(self) -> dict:
        return {"tables": len(self.tables),
                "rows": sum(t.row_count for t in self.tables.values()),
                "size_bytes": sum(t.size() for t in self.tables.values())}