"""Version Manager — semantic versioning, channels, auto-bump, Git tags."""
import json, uuid, os, logging, re
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ReleaseChannel(Enum):
    ALPHA = "alpha"; BETA = "beta"; RC = "rc"; STABLE = "stable"
    LTS = "lts"; NIGHTLY = "nightly"; CANARY = "canary"

@dataclass
class Version:
    id: str; org_id: str; repository_id: str
    major: int = 0; minor: int = 0; patch: int = 0
    pre_release: str = ""; build_metadata: str = ""
    channel: ReleaseChannel = ReleaseChannel.STABLE
    git_tag: str = ""; commit_sha: str = ""
    is_current: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def semver(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release: base += f"-{self.pre_release}"
        if self.build_metadata: base += f"+{self.build_metadata}"
        return base

    def bump(self, part: str = "patch") -> None:
        if part == "major": self.major += 1; self.minor = 0; self.patch = 0
        elif part == "minor": self.minor += 1; self.patch = 0
        else: self.patch += 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["channel"] = self.channel.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Version":
        data = data.copy()
        data["channel"] = ReleaseChannel(data.get("channel", "stable"))
        return cls(**data)

class VersionManager:
    def __init__(self, storage_dir: str = "release_data/versions"):
        self.storage_dir = storage_dir; self._versions: dict[str, Version] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "versions.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._versions[k] = Version.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load versions: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._versions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save versions: %s", e)

    def create(self, org_id: str, repo_id: str, channel: ReleaseChannel = ReleaseChannel.STABLE) -> Version:
        ver = Version(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, channel=channel, is_current=True)
        ver.git_tag = f"v{ver.semver()}"
        self._versions[ver.id] = ver; self._save(); return ver

    def bump(self, org_id: str, repo_id: str, part: str = "patch", channel: ReleaseChannel = ReleaseChannel.STABLE) -> Optional[Version]:
        current = self.get_current(org_id, repo_id)
        if not current: return self.create(org_id, repo_id, channel)
        nv = Version(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, channel=channel, commit_sha=current.commit_sha)
        nv.major, nv.minor, nv.patch = current.major, current.minor, current.patch
        nv.bump(part)
        nv.git_tag = f"v{nv.semver()}"; nv.is_current = True
        current.is_current = False
        self._versions[nv.id] = nv; self._save(); return nv

    def get_current(self, org_id: str, repo_id: str) -> Optional[Version]:
        for v in self._versions.values():
            if v.org_id == org_id and v.repository_id == repo_id and v.is_current: return v
        return None

    def get_history(self, org_id: str, repo_id: str, limit: int = 50) -> list[Version]:
        return sorted([v for v in self._versions.values() if v.org_id == org_id and v.repository_id == repo_id], key=lambda v: v.created_at, reverse=True)[:limit]

    def parse_semver(self, s: str) -> Optional[dict]:
        m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([\w.]+))?(?:\+([\w.]+))?$", s)
        if m: return {"major": int(m.group(1)), "minor": int(m.group(2)), "patch": int(m.group(3)), "pre": m.group(4) or "", "build": m.group(5) or ""}
        return None

    def get_telemetry(self) -> dict: return dict(self._telemetry)
