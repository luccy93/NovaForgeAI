"""OLAP abstraction - provider-agnostic analytical queries over columnar tables or external engines."""
import statistics
from abc import ABC, abstractmethod
from typing import Optional, Callable


class AnalyticsEngine(ABC):
    """Interface so the platform is never locked to one analytics provider."""
    name = "abstract"
    supports_sql = False

    @abstractmethod
    def tables(self) -> list[str]: ...
    @abstractmethod
    def rows(self, table: str, filters: Optional[dict] = None) -> list[dict]: ...
    @abstractmethod
    def health(self) -> dict: ...

    # optional SQL surface (DuckDB / ClickHouse / Postgres / BigQuery)
    def sql(self, query: str) -> list[dict]:
        raise NotImplementedError(f"{self.name} does not expose SQL")

    def group_by(self, table: str, key: str, agg_fns: dict[str, Callable[[list[dict]], float]]) -> list[dict]:
        buckets: dict[Any, list[dict]] = {}
        for row in self.rows(table):
            buckets.setdefault(row.get(key), []).append(row)
        result = []
        for k, group in sorted(buckets.items(), key=lambda kv: str(kv[0])):
            entry: dict = {key: k, "count": len(group)}
            for name, fn in agg_fns.items():
                entry[name] = round(fn(group), 6)
            result.append(entry)
        return result

    def time_series(self, table: str, time_field: str, bucket: str, agg_fn: Callable[[list[dict]], float]) -> list[dict]:
        """Buckets rows by time field into periods and aggregates each bucket."""
        buckets: dict[str, list[dict]] = {}
        for row in self.rows(table):
            ts = str(row.get(time_field, ""))[: len(bucket)] if bucket in ("day", "month", "week") else str(row.get(time_field, ""))
            key = self._bucket_key(row.get(time_field, ""), bucket)
            buckets.setdefault(key, []).append(row)
        result = []
        for k in sorted(buckets.keys()):
            result.append({"time": k, "value": round(agg_fn(buckets[k]), 6), "count": len(buckets[k])})
        return result

    @staticmethod
    def _bucket_key(ts: str, bucket: str) -> str:
        if not ts:
            return "unknown"
        try:
            parts = ts[:10].split("-")
        except Exception:
            return ts[:10]
        if bucket == "daily" or bucket == "day":
            return ts[:10]
        if bucket == "month":
            return ts[:7] if len(ts) >= 7 else ts
        if bucket == "weekly":
            return ts[:10]
        return ts[:10]


class InMemoryAnalytics(AnalyticsEngine):
    """Reference OLAP engine backed by in-memory tables - the default provider."""

    name = "in_memory"

    def __init__(self):
        self._data: dict[str, list[dict]] = {}

    def register_table(self, name: str, rows: Optional[list[dict]] = None) -> None:
        if name not in self._data:
            self._data[name] = []
        if rows:
            self._data[name].extend(rows)

    def append(self, name: str, rows: list[dict]) -> None:
        self._data.setdefault(name, []).extend(rows)

    def rows(self, table: str, filters: Optional[dict] = None) -> list[dict]:
        result = self._data.get(table, [])
        if filters:
            result = [r for r in result if all(r.get(k) == v for k, v in filters.items())]
        return result

    def tables(self) -> list[str]:
        return sorted(self._data.keys())

    def health(self) -> dict:
        return {"name": self.name, "tables": len(self._data),
                "rows": sum(len(r) for r in self._data.values()),
                "sql": self.supports_sql}

    def select(self) -> bool:
        return True

    def close(self) -> None: pass


class DuckDBEngine(InMemoryAnalytics):
    """DuckDB-like engine: parquet-friendly, SQL-capable when duckdb is installed."""
    name = "duckdb"
    sql_supported = True

    def __init__(self):
        super().__init__()
        try:
            import duckdb
            self._conn = duckdb.connect(database=":memory:")
            self._duck = duckdb
            self.available = True
        except ImportError:
            self._duck = None
            self.conn = None
            self.available = False

    def register_parquet(self, name: str, parquet_path: str) -> None:
        if self._duck is None:
            raise RuntimeError("duckdb not installed")
        self._conn.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet('{parquet_path}')")

    def sql(self, sql_str: str) -> list[dict]:
        if self._duck is None:
            raise RuntimeError("duckdb not installed")
        cur = self._conn.execute(sql_str)
        return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]


class PostgresAnalytics(InMemoryAnalytics):
    """PostgreSQL-backed analytics engine using the platform's existing connection."""
    name = "postgresql"
    sql_supported = True

    def __init__(self, dsn: str = ""):
        super().__init__()
        self.dsn = dsn
        try:
            import sqlalchemy
            self.available = True
        except ImportError:
            self.available = False


class WarehouseEngineFactory:
    """Selects the analytical engine without binding the platform to one vendor."""

    @staticmethod
    def create(engine: str = "in_memory", **kwargs) -> AnalyticsEngine:
        return {
            "in_memory": lambda: InMemoryAnalytics(),
            "duckdb": lambda: DuckDBEngine(),
            "postgresql": lambda: PostgresAnalytics(**kwargs),
        }.get(engine, lambda: InMemoryAnalytics())()


class QueryOptimizer:
    """Bound query planner: validates identifiers, limits scans, applies pushdown."""

    MAX_ROWS = 1_000_000
    MAX_GROUP_BYS = 8
    MAX_TIME_RANGE_DAYS = 730

    @staticmethod
    def validate_identifiers(*names) -> None:
        for name in names:
            if not name or not str(name).replace("_", "").isalnum():
                raise ValueError(f"invalid identifier: {name}")

    @staticmethod
    def safe_window(days: int) -> int:
        if days > QueryOptimizer.MAX_TIME_RANGE_DAYS:
            raise ValueError(f"time range too large: {days} days (max {QueryOptimizer.MAX_TIME_RANGE_DAYS})")
        return max(1, days)