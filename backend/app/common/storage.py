"""Unified Storage Backend — JSON-file, SQLite, in-memory with async, locking, migration support."""
import json, os, logging, threading, asyncio, sqlite3, time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Any, TypeVar, Generic
from contextlib import contextmanager

logger = logging.getLogger(__name__)
T = TypeVar("T")


class StorageBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]: ...
    @abstractmethod
    def set(self, key: str, value: Any) -> None: ...
    @abstractmethod
    def delete(self, key: str) -> bool: ...
    @abstractmethod
    def list_keys(self) -> list[str]: ...
    @abstractmethod
    def count(self) -> int: ...
    async def aget(self, key: str) -> Optional[Any]: return self.get(key)
    async def aset(self, key: str, value: Any) -> None: return self.set(key, value)
    async def adelete(self, key: str) -> bool: return self.delete(key)
    async def alist_keys(self) -> list[str]: return self.list_keys()
    async def acount(self) -> int: return self.count()


class JsonFileStorage(StorageBackend):
    def __init__(self, file_path: str, auto_save: bool = True):
        self.file_path = file_path; self.auto_save = auto_save
        self._data: dict[str, Any] = {}; self._lock = threading.RLock()
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f: self._data = json.load(f)
            except Exception as e: logger.error("Failed to load %s: %s", self.file_path, e)
        else: self._data = {}

    def _save(self) -> None:
        if not self.auto_save: return
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save %s: %s", self.file_path, e)

    def get(self, key: str) -> Optional[Any]:
        with self._lock: return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock: self._data[key] = value; self._save()

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data: del self._data[key]; self._save(); return True
            return False

    def list_keys(self) -> list[str]:
        with self._lock: return list(self._data.keys())

    def count(self) -> int:
        with self._lock: return len(self._data)

    def get_all(self) -> dict[str, Any]:
        with self._lock: return dict(self._data)

    def set_many(self, items: dict[str, Any]) -> None:
        with self._lock: self._data.update(items); self._save()


class MemoryStorage(StorageBackend):
    def __init__(self):
        self._data: dict[str, Any] = {}; self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock: return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock: self._data[key] = value

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data: del self._data[key]; return True
            return False

    def list_keys(self) -> list[str]:
        with self._lock: return list(self._data.keys())

    def count(self) -> int:
        with self._lock: return len(self._data)


class SQLiteStorage(StorageBackend):
    def __init__(self, db_path: str, table: str = "storage"):
        self.db_path = db_path; self.table = table
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
        self._conn.commit()

    def _serialize(self, value: Any) -> str: return json.dumps(value, default=str)

    def _deserialize(self, value: str) -> Any:
        try: return json.loads(value)
        except: return value

    def get(self, key: str) -> Optional[Any]:
        cur = self._conn.execute(f"SELECT value FROM {self.table} WHERE key = ?", (key,))
        row = cur.fetchone()
        return self._deserialize(row[0]) if row else None

    def set(self, key: str, value: Any) -> None:
        self._conn.execute(f"INSERT OR REPLACE INTO {self.table} (key, value, updated_at) VALUES (?, ?, ?)", (key, self._serialize(value), datetime.now(timezone.utc).isoformat()))
        self._conn.commit()

    def delete(self, key: str) -> bool:
        cur = self._conn.execute(f"DELETE FROM {self.table} WHERE key = ?", (key,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_keys(self) -> list[str]:
        cur = self._conn.execute(f"SELECT key FROM {self.table}")
        return [row[0] for row in cur.fetchall()]

    def count(self) -> int:
        cur = self._conn.execute(f"SELECT COUNT(*) FROM {self.table}")
        return cur.fetchone()[0]
