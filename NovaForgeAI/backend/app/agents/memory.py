"""Memory system — short-term, long-term, repository, decision, architecture memory."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.schemas import MemoryScope


class MemoryStore:
    """Persistent memory for agents using JSON files with optional DB backing."""

    def __init__(self, base_path: Optional[str] = None):
        import os
        self.base_path = base_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", ".agent_memory"
        )
        os.makedirs(self.base_path, exist_ok=True)

    def _scope_dir(self, scope: str) -> str:
        import os
        d = os.path.join(self.base_path, scope)
        os.makedirs(d, exist_ok=True)
        return d

    def _key_path(self, scope: str, key: str) -> str:
        import os
        safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return os.path.join(self._scope_dir(scope), f"{safe}.json")

    async def store(self, scope: str, key: str, value: Any) -> None:
        path = self._key_path(scope, key)
        entry = {
            "key": key,
            "scope": scope,
            "value": value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "id": str(uuid.uuid4()),
        }
        with open(path, "w") as f:
            json.dump(entry, f, indent=2, default=str)

    async def retrieve(self, scope: str, key: str) -> Optional[Any]:
        path = self._key_path(scope, key)
        import os
        if not os.path.exists(path):
            return None
        with open(path) as f:
            entry = json.load(f)
        return entry.get("value")

    async def search(self, scope: str, query: str, limit: int = 10) -> list[dict]:
        import os
        results = []
        scope_dir = self._scope_dir(scope)
        if not os.path.isdir(scope_dir):
            return results
        for fname in os.listdir(scope_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(scope_dir, fname)
                with open(fpath) as f:
                    try:
                        entry = json.load(f)
                        if query.lower() in json.dumps(entry).lower():
                            results.append(entry)
                            if len(results) >= limit:
                                break
                    except json.JSONDecodeError:
                        continue
        return results

    async def list_keys(self, scope: str) -> list[str]:
        import os
        scope_dir = self._scope_dir(scope)
        if not os.path.isdir(scope_dir):
            return []
        return [f.replace(".json", "") for f in os.listdir(scope_dir) if f.endswith(".json")]

    async def delete(self, scope: str, key: str) -> bool:
        path = self._key_path(scope, key)
        import os
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    async def get_recent(self, scope: str, limit: int = 10) -> list[dict]:
        import os
        entries = []
        scope_dir = self._scope_dir(scope)
        if not os.path.isdir(scope_dir):
            return entries
        for fname in os.listdir(scope_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(scope_dir, fname)
                with open(fpath) as f:
                    try:
                        entries.append(json.load(f))
                    except json.JSONDecodeError:
                        continue
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return entries[:limit]

    async def get_context(self, scope: MemoryScope, context_key: str) -> str:
        val = await self.retrieve(scope.value, context_key)
        if val is None:
            return ""
        if isinstance(val, dict):
            return json.dumps(val, indent=2, default=str)[:2000]
        return str(val)[:2000]

    async def compress(self, scope: str) -> str:
        entries = await self.get_recent(scope, 50)
        if not entries:
            return ""
        summary_parts = []
        for e in entries:
            v = e.get("value", {})
            if isinstance(v, dict):
                summary_parts.append(f"- {v.get('agent', 'unknown')}: {str(v.get('output', ''))[:100]}")
            else:
                summary_parts.append(f"- {str(v)[:100]}")
        return "\n".join(summary_parts)
