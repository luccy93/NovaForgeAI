import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math, re
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptType(Enum):
    SYSTEM = "system"
    AGENT = "agent"
    TASK = "task"
    REVIEW = "review"
    DOCUMENTATION = "documentation"
    SECURITY = "security"
    TESTING = "testing"
    ANALYSIS = "analysis"
    CUSTOM = "custom"


class PromptStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"
    TESTING = "testing"


@dataclass
class PromptEntry:
    id: str = ""
    name: str = ""
    prompt_type: PromptType = PromptType.CUSTOM
    content: str = ""
    description: str = ""
    version: int = 1
    author: str = ""
    status: PromptStatus = PromptStatus.DRAFT
    org_id: str = ""
    tags: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    token_count: int = 0
    avg_latency_ms: float = 0.0
    avg_cost: float = 0.0
    usage_count: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        d = asdict(self)
        d["prompt_type"] = self.prompt_type.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "PromptEntry":
        data = data.copy()
        data["prompt_type"] = PromptType(data.get("prompt_type", "custom"))
        data["status"] = PromptStatus(data.get("status", "draft"))
        return PromptEntry(**data)


@dataclass
class PromptVersion:
    id: str = ""
    prompt_id: str = ""
    version: int = 1
    content: str = ""
    author: str = ""
    reason: str = ""
    status: str = "draft"
    token_count: int = 0
    performance_metrics: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "PromptVersion":
        return PromptVersion(**data)


class PromptRegistry:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._entries_file = self.storage_dir / "prompt_registry.json"
        self._versions_file = self.storage_dir / "prompt_versions.json"
        self._entries: dict[str, PromptEntry] = {}
        self._versions: dict[str, list[PromptVersion]] = defaultdict(list)
        self._load()
        self._telemetry = defaultdict(int)
        logger.info("PromptRegistry initialized at %s", storage_dir)

    def _save(self):
        entries_data = {k: v.to_dict() for k, v in self._entries.items()}
        versions_data = {k: [pv.to_dict() for pv in v] for k, v in self._versions.items()}
        try:
            self._entries_file.write_text(json.dumps(entries_data, indent=2))
            self._versions_file.write_text(json.dumps(versions_data, indent=2))
        except Exception as e:
            logger.error("Failed to save prompt registry: %s", e)
            raise

    def _load(self):
        try:
            if self._entries_file.exists():
                entries_data = json.loads(self._entries_file.read_text())
                for k, v in entries_data.items():
                    self._entries[k] = PromptEntry.from_dict(v)
            if self._versions_file.exists():
                versions_data = json.loads(self._versions_file.read_text())
                for k, v in versions_data.items():
                    self._versions[k] = [PromptVersion.from_dict(pv) for pv in v]
        except Exception as e:
            logger.error("Failed to load prompt registry: %s", e)

    def register_prompt(self, entry: PromptEntry) -> PromptEntry:
        if entry.id in self._entries:
            raise ValueError(f"Prompt {entry.id} already exists")
        self._entries[entry.id] = entry
        version = PromptVersion(
            prompt_id=entry.id,
            version=entry.version,
            content=entry.content,
            author=entry.author,
            reason="Initial creation",
            status=entry.status.value,
            token_count=entry.token_count,
        )
        self._versions[entry.id].append(version)
        self._save()
        self._telemetry["prompts_registered"] += 1
        logger.info("Registered prompt %s (%s)", entry.id, entry.name)
        return entry

    def get_prompt(self, prompt_id: str) -> Optional[PromptEntry]:
        return self._entries.get(prompt_id)

    def update_prompt(self, prompt_id: str, **updates) -> Optional[PromptEntry]:
        entry = self._entries.get(prompt_id)
        if not entry:
            logger.warning("Prompt %s not found for update", prompt_id)
            return None
        old_content = entry.content
        for key, val in updates.items():
            if hasattr(entry, key):
                if key == "prompt_type":
                    val = PromptType(val) if isinstance(val, str) else val
                elif key == "status":
                    val = PromptStatus(val) if isinstance(val, str) else val
                setattr(entry, key, val)
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        if updates.get("content") and updates["content"] != old_content:
            entry.version += 1
            version = PromptVersion(
                prompt_id=entry.id,
                version=entry.version,
                content=entry.content,
                author=entry.author,
                reason=updates.get("reason", "Updated"),
                status=entry.status.value,
                token_count=entry.token_count,
            )
            self._versions[entry.id].append(version)
        self._save()
        self._telemetry["prompts_updated"] += 1
        return entry

    def archive_prompt(self, prompt_id: str) -> bool:
        entry = self._entries.get(prompt_id)
        if not entry:
            return False
        entry.status = PromptStatus.ARCHIVED
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._telemetry["prompts_archived"] += 1
        return True

    def deprecate_prompt(self, prompt_id: str) -> bool:
        entry = self._entries.get(prompt_id)
        if not entry:
            return False
        entry.status = PromptStatus.DEPRECATED
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._telemetry["prompts_deprecated"] += 1
        return True

    def list_prompts(self, org_id: Optional[str] = None) -> list[PromptEntry]:
        if org_id:
            return [e for e in self._entries.values() if e.org_id == org_id]
        return list(self._entries.values())

    def search_prompts(self, query: str) -> list[PromptEntry]:
        q = query.lower()
        results = []
        for entry in self._entries.values():
            if q in entry.name.lower() or q in entry.content.lower() or q in entry.description.lower():
                results.append(entry)
                continue
            for tag in entry.tags:
                if q in tag.lower():
                    results.append(entry)
                    break
        return results

    def get_prompts_by_type(self, prompt_type: PromptType) -> list[PromptEntry]:
        return [e for e in self._entries.values() if e.prompt_type == prompt_type]

    def get_active_prompts(self) -> list[PromptEntry]:
        return [e for e in self._entries.values() if e.status == PromptStatus.ACTIVE]

    def get_prompt_stats(self, prompt_id: str) -> dict:
        entry = self._entries.get(prompt_id)
        if not entry:
            return {}
        versions = self._versions.get(prompt_id, [])
        return {
            "id": entry.id,
            "name": entry.name,
            "version": entry.version,
            "status": entry.status.value,
            "type": entry.prompt_type.value,
            "total_versions": len(versions),
            "token_count": entry.token_count,
            "avg_latency_ms": entry.avg_latency_ms,
            "avg_cost": entry.avg_cost,
            "usage_count": entry.usage_count,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    def render_prompt(self, prompt_id: str, variables: dict[str, str]) -> Optional[str]:
        entry = self._entries.get(prompt_id)
        if not entry:
            return None
        content = entry.content
        for var in entry.variables:
            placeholder = "{{" + var + "}}"
            value = variables.get(var, "")
            content = content.replace(placeholder, value)
        self._telemetry["prompts_rendered"] += 1
        return content

    def estimate_tokens(self, content: str) -> int:
        return len(re.findall(r"\S+", content)) + len(content) // 4

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
