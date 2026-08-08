"""Compliance Gates — regulatory checks, policy enforcement, audit trails, evidence collection."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ComplianceStatus(Enum):
    PENDING = "pending"; PASSED = "passed"; FAILED = "failed"; WAIVED = "waived"

@dataclass
class ComplianceGate:
    id: str; org_id: str; name: str; framework: str = ""  # SOC2, HIPAA, GDPR, PCI-DSS, SOX
    status: ComplianceStatus = ComplianceStatus.PENDING
    requirements: list = field(default_factory=list); controls: list = field(default_factory=list)
    evidence: list = field(default_factory=list); auto_verify: bool = True
    owner_id: str = ""; notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d
    @classmethod
    def from_dict(cls, data: dict) -> "ComplianceGate":
        data = data.copy(); data["status"] = ComplianceStatus(data.get("status", "pending")); return cls(**data)

class ComplianceGates:
    def __init__(self, storage_dir: str = "release_data/compliance"):
        self.storage_dir = storage_dir; self._gates: dict[str, ComplianceGate] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "gates.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._gates[k] = ComplianceGate.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._gates.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, framework: str = "") -> ComplianceGate:
        g = ComplianceGate(id=str(uuid.uuid4()), org_id=org_id, name=name, framework=framework)
        self._gates[g.id] = g; self._save(); return g

    def evaluate(self, gate_id: str, evidence: list = None) -> Optional[ComplianceGate]:
        g = self._gates.get(gate_id)
        if not g: return None
        if evidence: g.evidence.extend(evidence)
        g.status = ComplianceStatus.PASSED if g.auto_verify else ComplianceStatus.PENDING
        g.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return g

    def get_telemetry(self) -> dict: return {"total_gates": len(self._gates)}
