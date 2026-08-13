"""Reporting Engine - scheduled, versioned reports with multi-channel delivery."""
import os, json, uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class ReportChannels:
    EMAIL = "email"
    WEBHOOK = "webhook"
    API = "api"
    OBJECT_STORAGE = "object_storage"
    SLACK = "slack"
    TEAMS = "teams"


@dataclass
class ReportDef:
    name: str
    period: str  # daily | weekly | monthly | quarterly
    kind: str = "generic"
    channels: list[str] = field(default_factory=lambda: [ReportChannels.EMAIL])
    id: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class ReportingEngine:
    """Builds, schedules, versions, and delivers reports."""

    def __init__(self, data_dir: str = ""):
        self.data_dir = data_dir
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)
        self.defs: dict[str, ReportDef] = {}
        self.history: list[dict] = []
        self.delivery_log: list[dict] = []

    def define(self, name: str, kind: str = "generic", period: str = "daily",
               channels: Optional[list[str]] = None) -> ReportDef:
        r = ReportDef(name=name, period=period, kind=kind,
                      channels=channels or [ReportChannels.EMAIL])
        self.defs[name] = r
        return r

    def generate(self, name: str, sections: Optional[dict] = None,
                 data: Optional[dict] = None) -> dict:
        """Creates a versioned report artifact from data sections."""
        report_def = self.defs.get(name)
        if not report_def:
            raise KeyError(f"no report '{name}' defined")
        version = sum(1 for h in self.history if h["name"] == name) + 1
        rendered = self._render(report_def, sections or {}, data or {})
        artifact = {"name": name, "kind": report_def.kind, "version": version,
                    "rendered_the": datetime.now(timezone.utc).isoformat(),
                    "content": rendered,
                    "channels": report_def.channels}
        self.history.append(artifact)
        self._deliver(name, artifact)
        return artifact

    def _render(self, report_def: ReportDef, sections: dict, data: dict) -> str:
        lines = [
            f"# {report_def.name}",
            f"Period: {report_def.period} | Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        for title, body in sections.items():
            lines.append(f"## {title}")
            if isinstance(body, list):
                if body and isinstance(body[0], dict):
                    headers = sorted({k for row in body for k in row.keys()})
                    lines.append("| " + " | ".join(headers) + " |")
                    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
                    for row in body:
                        lines.append("| " + " | ".join(str(row.get(h) or "") for h in headers) + " |")
                else:
                    lines.append(" | ".join(str(int(b)) for b in body))
            elif isinstance(body, dict):
                lines.append(json.dumps(body, indent=2, default=str))
            else:
                lines.append(str(body))
            lines.append("")
        return "\n".join(lines)

    def _deliver(self, name: str, artifact: dict) -> None:
        for channel in artifact["channels"]:
            self.delivery_log.append({"name": name, "channel": channel,
                                      "status": "dispatched",
                                      "at": datetime.now(timezone.utc).isoformat()})

    def history_of(self, name: str) -> list[dict]:
        return [h for h in self.history if h["name"] == name]

    def version(self, name: str, version: int) -> Optional[dict]:
        for h in self.history:
            if h["name"] == name and h["version"] == version:
                return h
        return None

    def status(self) -> dict:
        return {"definitions": len(self.defs), "generated": len(self.history),
                "deliveries": len(self.delivery_log)}