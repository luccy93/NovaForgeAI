"""Connectors — source control (GitHub, GitLab, Bitbucket, Azure DevOps, Gitea, Forgejo), project management (Jira, Linear, Azure Boards, Asana, ClickUp, Monday.com, Trello, YouTrack, Shortcut), documentation (Confluence, Notion, GitBook, Docusaurus, ReadTheDocs, MkDocs), communication (Slack, Discord, Teams, Google Chat, Mattermost, Rocket.Chat)."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


CONNECTOR_CATEGORIES = {
    "source_control": ["github", "gitlab", "bitbucket", "azure_devops", "gitea", "forgejo"],
    "project_management": ["jira", "linear", "azure_boards", "asana", "clickup", "monday", "trello", "youtrack", "shortcut"],
    "documentation": ["confluence", "notion", "gitbook", "docusaurus", "readthedocs", "mkdocs"],
    "communication": ["slack", "discord", "microsoft_teams", "google_chat", "mattermost", "rocket_chat"],
}


@dataclass
class ConnectorConfig:
    id: str
    org_id: str
    category: str
    provider: str
    name: str
    base_url: str = ""
    api_key: str = ""
    webhook_secret: str = ""
    enabled: bool = True
    sync_interval: int = 300
    config: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["api_key"] = "***" if self.api_key else ""
        d["webhook_secret"] = "***" if self.webhook_secret else ""
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorConfig": return cls(**data)


@dataclass
class ConnectorSyncLog:
    id: str
    config_id: str
    status: str
    records_synced: int = 0
    error: str = ""
    duration_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorSyncLog": return cls(**data)


class Connectors:
    def __init__(self, storage_dir: str = "integration_data/connectors"):
        self.storage_dir = storage_dir
        self._configs: dict[str, ConnectorConfig] = {}
        self._sync_logs: list[ConnectorSyncLog] = []
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _cfg_path(self) -> str: return os.path.join(self.storage_dir, "configs.json")
    def _log_path(self) -> str: return os.path.join(self.storage_dir, "sync_logs.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._cfg_path(), self._configs, ConnectorConfig),
            (self._log_path(), None, None),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if cls:
                        for k, v in data.items():
                            try: store[k] = cls.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._sync_logs = [ConnectorSyncLog.from_dict(l) for l in data]
                except Exception as e: logger.error("Failed to load connectors: %s", e)

    def _save(self) -> None:
        try:
            with open(self._cfg_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._configs.items()}, f, indent=2, default=str)
            with open(self._log_path(), "w", encoding="utf-8") as f:
                json.dump([l.to_dict() for l in self._sync_logs[-1000:]], f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save connectors: %s", e)

    def configure(self, org_id: str, category: str, provider: str, name: str, base_url: str = "", api_key: str = "", webhook_secret: str = "", config: dict = None) -> ConnectorConfig:
        cfg = ConnectorConfig(id=str(uuid.uuid4()), org_id=org_id, category=category, provider=provider, name=name, base_url=base_url, api_key=api_key, webhook_secret=webhook_secret, config=config or {})
        self._configs[cfg.id] = cfg
        self._save()
        return cfg

    def get(self, cfg_id: str) -> Optional[ConnectorConfig]: return self._configs.get(cfg_id)

    def update(self, cfg_id: str, updates: dict) -> Optional[ConnectorConfig]:
        cfg = self._configs.get(cfg_id)
        if not cfg: return None
        for k, v in updates.items():
            if hasattr(cfg, k) and k not in ("id", "created_at"): setattr(cfg, k, v)
        cfg.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return cfg

    def delete(self, cfg_id: str) -> bool:
        if cfg_id not in self._configs: return False
        del self._configs[cfg_id]
        self._save()
        return True

    def list_by_org(self, org_id: str, category: str = "") -> list[ConnectorConfig]:
        results = [c for c in self._configs.values() if c.org_id == org_id]
        if category: results = [c for c in results if c.category == category]
        return results

    def list_by_provider(self, provider: str) -> list[ConnectorConfig]:
        return [c for c in self._configs.values() if c.provider == provider]

    def get_available_providers(self, category: str) -> list[str]:
        return CONNECTOR_CATEGORIES.get(category, [])

    def log_sync(self, config_id: str, status: str, records_synced: int = 0, error: str = "", duration_ms: float = 0.0) -> ConnectorSyncLog:
        log = ConnectorSyncLog(id=str(uuid.uuid4()), config_id=config_id, status=status, records_synced=records_synced, error=error, duration_ms=duration_ms)
        self._sync_logs.append(log)
        self._save()
        return log

    def get_sync_logs(self, config_id: str = "", limit: int = 100) -> list[ConnectorSyncLog]:
        results = list(self._sync_logs)
        if config_id: results = [l for l in results if l.config_id == config_id]
        return sorted(results, key=lambda l: l.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
