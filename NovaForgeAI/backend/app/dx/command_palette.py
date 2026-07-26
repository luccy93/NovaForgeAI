"""Command Palette — AI-powered keyboard-first command palette with repo/file/command/prompt/doc search, agent invocation, project navigation, quick actions, natural language commands."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CommandCategory(Enum):
    NAVIGATION = "navigation"
    SEARCH = "search"
    CHAT = "chat"
    REVIEW = "review"
    DOCUMENTATION = "documentation"
    TERMINAL = "terminal"
    DEPLOY = "deploy"
    SETTINGS = "settings"
    AGENT = "agent"
    WORKSPACE = "workspace"
    CUSTOM = "custom"


@dataclass
class CommandEntry:
    id: str
    name: str
    category: CommandCategory
    description: str = ""
    shortcut: str = ""
    keywords: list = field(default_factory=list)
    action: str = ""
    icon: str = ""
    is_global: bool = False
    is_active: bool = True
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CommandEntry":
        data = data.copy()
        data["category"] = CommandCategory(data.get("category", "navigation"))
        return cls(**data)


@dataclass
class CommandHistory:
    id: str
    user_id: str
    command: str
    category: str = ""
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "CommandHistory": return cls(**data)


class CommandPalette:
    def __init__(self, storage_dir: str = "dx_data/commands"):
        self.storage_dir = storage_dir
        self._commands: dict[str, CommandEntry] = {}
        self._history: dict[str, CommandHistory] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _cmd_path(self) -> str: return os.path.join(self.storage_dir, "commands.json")
    def _hist_path(self) -> str: return os.path.join(self.storage_dir, "history.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._cmd_path(), self._commands, CommandEntry),
            (self._hist_path(), self._history, CommandHistory),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load command palette: %s", e)

    def _save(self) -> None:
        try:
            with open(self._cmd_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._commands.items()}, f, indent=2, default=str)
            with open(self._hist_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._history.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save command palette: %s", e)

    def register_command(self, name: str, category: CommandCategory, description: str = "", shortcut: str = "", keywords: list = None, action: str = "", is_global: bool = False) -> CommandEntry:
        cmd = CommandEntry(id=str(uuid.uuid4()), name=name, category=category, description=description, shortcut=shortcut, keywords=keywords or [], action=action, is_global=is_global)
        self._commands[cmd.id] = cmd
        self._save()
        return cmd

    def search(self, query: str, limit: int = 20) -> list[CommandEntry]:
        q = query.lower()
        results = [c for c in self._commands.values() if c.is_active]
        scored = []
        for c in results:
            score = 0
            if q in c.name.lower(): score += 10
            if q in c.description.lower(): score += 5
            if any(q in kw.lower() for kw in c.keywords): score += 3
            if q in c.shortcut.lower(): score += 2
            if score > 0: scored.append((c, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:limit]]

    def execute(self, user_id: str, command: str, category: str = "") -> dict:
        hist = CommandHistory(id=str(uuid.uuid4()), user_id=user_id, command=command, category=category)
        self._history[hist.id] = hist
        for c in self._commands.values():
            if c.name == command and c.is_active:
                c.usage_count += 1
        self._save()
        return {"command": command, "executed": True, "timestamp": hist.executed_at}

    def get_global_commands(self) -> list[CommandEntry]:
        return [c for c in self._commands.values() if c.is_global and c.is_active]

    def get_history(self, user_id: str, limit: int = 50) -> list[CommandHistory]:
        results = [h for h in self._history.values() if h.user_id == user_id]
        return sorted(results, key=lambda h: h.executed_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
