import os, uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class ScanResult:
    id: str
    repo_id: str = ""
    scan_type: str = "full"
    status: str = "completed"
    findings: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class SecurityScanning:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)

    def scan(self, repo_id, scan_type="full"):
        return ScanResult(id=uuid.uuid4().hex, repo_id=repo_id, scan_type=scan_type)

    def get_findings(self, scan_id):
        return []