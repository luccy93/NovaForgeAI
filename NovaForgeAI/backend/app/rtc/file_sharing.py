"""File Sharing — documents, diagrams, logs, artifacts, secure sharing."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SharedFile:
    id: str; org_id: str; name: str; file_path: str; size_bytes: int = 0
    content_type: str = ""; uploaded_by: str = ""; shared_with: list = field(default_factory=list)
    is_secure: bool = False; expires_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "SharedFile": return cls(**data)

class FileSharing:
    def __init__(self, storage_dir: str = "rtc_data/files"):
        self.storage_dir = storage_dir; self._files: dict[str, SharedFile] = {}
        self._upload_dir = os.path.join(storage_dir, "uploads")
        os.makedirs(self._upload_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "files.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._files[k] = SharedFile.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._files.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def upload(self, org_id: str, name: str, content: bytes, uploaded_by: str = "") -> SharedFile:
        file_path = os.path.join(self._upload_dir, f"{uuid.uuid4()}_{name}")
        with open(file_path, "wb") as f: f.write(content)
        sf = SharedFile(id=str(uuid.uuid4()), org_id=org_id, name=name, file_path=file_path, size_bytes=len(content), uploaded_by=uploaded_by)
        self._files[sf.id] = sf; self._save(); return sf

    def share_with(self, file_id: str, user_id: str) -> bool:
        sf = self._files.get(file_id)
        if not sf: return False
        if user_id not in sf.shared_with: sf.shared_with.append(user_id); self._save()
        return True

    def get_telemetry(self) -> dict: return {"files": len(self._files)}
