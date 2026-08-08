"""Enterprise Collaboration — cross-team, cross-repository, cross-organization, partner collaboration, guest access, external reviewers."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CollaborationScope(Enum):
    CROSS_TEAM = "cross_team"
    CROSS_REPO = "cross_repo"
    CROSS_ORG = "cross_org"
    PARTNER = "partner"
    GUEST = "guest"


class AccessLevel(Enum):
    VIEWER = "viewer"
    COMMENTATOR = "commentator"
    CONTRIBUTOR = "contributor"
    ADMIN = "admin"


@dataclass
class ExternalCollaborator:
    id: str
    org_id: str
    email: str
    name: str = ""
    scope: CollaborationScope = CollaborationScope.GUEST
    access_level: AccessLevel = AccessLevel.VIEWER
    invited_by: str = ""
    resource_ids: list = field(default_factory=list)
    resource_types: list = field(default_factory=list)
    expires_at: str = ""
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope"] = self.scope.value
        d["access_level"] = self.access_level.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExternalCollaborator":
        data = data.copy()
        data["scope"] = CollaborationScope(data.get("scope", "guest"))
        data["access_level"] = AccessLevel(data.get("access_level", "viewer"))
        return cls(**data)


@dataclass
class CrossOrgLink:
    id: str
    source_org_id: str
    target_org_id: str
    link_type: str
    resources_shared: list = field(default_factory=list)
    bidirectional: bool = False
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "CrossOrgLink": return cls(**data)


class EnterpriseCollaboration:
    def __init__(self, storage_dir: str = "collab_data/enterprise"):
        self.storage_dir = storage_dir
        self._collaborators: dict[str, ExternalCollaborator] = {}
        self._org_links: dict[str, CrossOrgLink] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _collab_path(self) -> str: return os.path.join(self.storage_dir, "collaborators.json")
    def _links_path(self) -> str: return os.path.join(self.storage_dir, "org_links.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._collab_path(), self._collaborators, ExternalCollaborator),
            (self._links_path(), self._org_links, CrossOrgLink),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load enterprise data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._collab_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._collaborators.items()}, f, indent=2, default=str)
            with open(self._links_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._org_links.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save enterprise data: %s", e)

    def invite_collaborator(self, org_id: str, email: str, name: str = "", scope: CollaborationScope = CollaborationScope.GUEST, access_level: AccessLevel = AccessLevel.VIEWER, invited_by: str = "", resource_ids: list = None, resource_types: list = None, expires_at: str = "") -> ExternalCollaborator:
        collab = ExternalCollaborator(id=str(uuid.uuid4()), org_id=org_id, email=email, name=name, scope=scope, access_level=access_level, invited_by=invited_by, resource_ids=resource_ids or [], resource_types=resource_types or [], expires_at=expires_at)
        self._collaborators[collab.id] = collab
        self._save()
        return collab

    def update_access(self, collab_id: str, access_level: AccessLevel) -> bool:
        collab = self._collaborators.get(collab_id)
        if not collab: return False
        collab.access_level = access_level
        collab.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def list_collaborators(self, org_id: str = "", scope: Optional[CollaborationScope] = None) -> list[ExternalCollaborator]:
        results = [c for c in self._collaborators.values() if c.is_active]
        if org_id: results = [c for c in results if c.org_id == org_id]
        if scope: results = [c for c in results if c.scope == scope]
        return results

    def create_org_link(self, source_org_id: str, target_org_id: str, link_type: str, resources_shared: list = None, bidirectional: bool = False) -> CrossOrgLink:
        link = CrossOrgLink(id=str(uuid.uuid4()), source_org_id=source_org_id, target_org_id=target_org_id, link_type=link_type, resources_shared=resources_shared or [], bidirectional=bidirectional)
        self._org_links[link.id] = link
        self._save()
        return link

    def list_org_links(self, org_id: str) -> list[CrossOrgLink]:
        return [l for l in self._org_links.values() if (l.source_org_id == org_id or l.target_org_id == org_id) and l.is_active]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
