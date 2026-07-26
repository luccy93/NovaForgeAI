"""Version Manager — semantic versioning, release channels, version history, auto-bumping, Git tags."""
import json, uuid, os, logging, re
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ReleaseChannel(Enum):
    ALPHA = "alpha"
    BETA = "beta"
    RELEASE_CANDIDATE = "rc"
    STABLE = "stable"
    LTS = "lts"
    NIGHTLY = "nightly"
    CANARY = "canary"


@dataclass
class Version:
    id: str
    org_id: str
    repository_id: str
    major: int = 0
    minor: int = 0
    patch: int = 0
    pre_release: str = ""
    build_metadata: str = ""
    channel: ReleaseChannel = ReleaseChannel.STABLE
    git_tag: str = ""
    commit_sha: str = ""
    is_current: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def semver(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release: base += f"-{self.pre_release}"
        if self.build_metadata: base += f"+{self.build_metadata}"
        return base

    def bump_major(self) -> None:
        self.major += 1; self.minor = 0; self.patch = 0

    def bump_minor(self) -> None:
        self.minor += 1; self.patch = 0

    def bump_patch(self) -> None:
        self.patch += 1

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
        self.storage_dir = storage_dir
        self._versions: dict[str, Version] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "versions.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._versions[k] = Version.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load versions: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._versions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save versions: %s", e)

    def create(self, org_id: str, repository_id: str, channel: ReleaseChannel = ReleaseChannel.STABLE, major: int = 0, minor: int = 1, patch: int = 0) -> Version:
        ver = Version(id=str(uuid.uuid4()), org_id=org_id, repository_id=repository_id, major=major, minor=minor, patch=patch, channel=channel, git_tag=f"v{major}.{minor}.{patch}")
        self._versions[ver.id] = ver
        self._save()
        return ver

    def bump(self, org_id: str, repository_id: str, part: str = "patch", channel: ReleaseChannel = ReleaseChannel.STABLE) -> Optional[Version]:
        current = self.get_current(org_id, repository_id)
        if not current:
            return self.create(org_id, repository_id, channel)
        new_ver = Version(id=str(uuid.uuid4()), org_id=org_id, repository_id=repository_id, major=current.major, minor=current.minor, patch=current.patch, channel=channel, commit_sha=current.commit_sha)
        if part == "major": new_ver.bump_major()
        elif part == "minor": new_ver.bump_minor()
        else: new_ver.bump_patch()
        new_ver.git_tag = f"v{new_ver.semver()}"
        current.is_current = False
        new_ver.is_current = True
        self._versions[new_ver.id] = new_ver
        self._save()
        return new_ver

    def get_current(self, org_id: str, repository_id: str) -> Optional[Version]:
        for v in self._versions.values():
            if v.org_id == org_id and v.repository_id == repository_id and v.is_current:
                return v
        return None

    def get_history(self, org_id: str, repository_id: str, limit: int = 50) -> list[Version]:
        results = [v for v in self._versions.values() if v.org_id == org_id and v.repository_id == repository_id]
        return sorted(results, key=lambda v: v.created_at, reverse=True)[:limit]

    def parse_semver(self, version_str: str) -> Optional[dict]:
        pattern = r"^v?(\d+)\.(\d+)\.(\d+)(?:-([\w.]+))?(?:\+([\w.]+))?$"
        m = re.match(pattern, version_str)
        if m: return {"major": int(m.group(1)), "minor": int(m.group(2)), "patch": int(m.group(3)), "pre_release": m.group(4) or "", "build": m.group(5) or ""}
        return None

    def get_telemetry(self) -> dict: return dict(self._telemetry)
