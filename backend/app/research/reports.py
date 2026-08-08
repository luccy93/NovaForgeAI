"""Research Reports — automatically generate research, benchmark, comparison, evaluation, performance, architecture, AI insights, and innovation reports."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ReportType(Enum):
    RESEARCH = "research"
    BENCHMARK = "benchmark"
    COMPARISON = "comparison"
    EVALUATION = "evaluation"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    AI_INSIGHT = "ai_insight"
    INNOVATION = "innovation"


class ReportFormat(Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"
    PDF = "pdf"


class ReportStatus(Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class ReportSection:
    title: str
    content: str
    level: int = 1
    order: int = 0
    data_refs: list = field(default_factory=list)

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Report:
    id: str
    org_id: str
    title: str
    report_type: ReportType
    status: ReportStatus = ReportStatus.DRAFT
    sections: list = field(default_factory=list)
    executive_summary: str = ""
    methodology: str = ""
    conclusions: str = ""
    recommendations: list = field(default_factory=list)
    data_sources: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    version: int = 1
    generated_by: str = "system"
    published_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["report_type"] = self.report_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Report":
        data = data.copy()
        data["report_type"] = ReportType(data.get("report_type", "research"))
        data["status"] = ReportStatus(data.get("status", "draft"))
        return cls(**data)


class PublicationSystem:
    def __init__(self, storage_dir: str = "research_data/reports"):
        self.storage_dir = storage_dir
        self._reports: dict[str, Report] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "reports.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._reports[k] = Report.from_dict(v)
                    except Exception as e: logger.warning("Skipping report %s: %s", k, e)
            except Exception as e: logger.error("Failed to load reports: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reports.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save reports: %s", e)

    def create_report(self, title: str, org_id: str, report_type: ReportType = ReportType.RESEARCH) -> Report:
        report = Report(id=str(uuid.uuid4()), org_id=org_id, title=title, report_type=report_type)
        self._reports[report.id] = report
        self._save()
        return report

    def get_report(self, report_id: str) -> Optional[Report]:
        return self._reports.get(report_id)

    def update_report(self, report_id: str, updates: dict) -> Optional[Report]:
        report = self._reports.get(report_id)
        if not report: return None
        for k, v in updates.items():
            if hasattr(report, k) and k not in ("id", "created_at"):
                if k == "report_type": setattr(report, k, ReportType(v) if isinstance(v, str) else v)
                elif k == "status":
                    setattr(report, k, ReportStatus(v) if isinstance(v, str) else v)
                    if report.status == ReportStatus.PUBLISHED: report.published_at = datetime.now(timezone.utc).isoformat()
                else: setattr(report, k, v)
        report.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return report

    def add_section(self, report_id: str, title: str, content: str, level: int = 1, order: int = 0) -> Optional[ReportSection]:
        report = self._reports.get(report_id)
        if not report: return None
        section = ReportSection(title=title, content=content, level=level, order=order or len(report.sections) + 1)
        report.sections.append(section)
        report.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return section

    def publish_report(self, report_id: str) -> Optional[Report]:
        return self.update_report(report_id, {"status": ReportStatus.PUBLISHED})

    def generate_benchmark_report(self, org_id: str, benchmark_data: dict, title: str = "") -> Report:
        report = self.create_report(title or f"Benchmark Report {datetime.now(timezone.utc).strftime('%Y-%m-%d')}", org_id, ReportType.BENCHMARK)
        report.executive_summary = benchmark_data.get("summary", "")
        report.methodology = benchmark_data.get("methodology", "")
        report.conclusions = benchmark_data.get("conclusions", "")
        report.data_sources = benchmark_data.get("data_sources", [])
        for s in benchmark_data.get("sections", []):
            self.add_section(report.id, s.get("title", ""), s.get("content", ""), s.get("level", 1))
        self.update_report(report.id, {"status": ReportStatus.GENERATED})
        return report

    def generate_comparison_report(self, org_id: str, comparison_data: dict, title: str = "") -> Report:
        return self.generate_benchmark_report(org_id, comparison_data, title or f"Comparison Report {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")

    def list_reports(self, org_id: str = "", report_type: Optional[ReportType] = None, limit: int = 50) -> list[Report]:
        results = list(self._reports.values())
        if org_id: results = [r for r in results if r.org_id == org_id]
        if report_type: results = [r for r in results if r.report_type == report_type]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def delete_report(self, report_id: str) -> bool:
        if report_id not in self._reports: return False
        del self._reports[report_id]
        self._save()
        return True

    def render_report(self, report_id: str, fmt: ReportFormat = ReportFormat.MARKDOWN) -> Optional[str]:
        report = self._reports.get(report_id)
        if not report: return None
        if fmt == ReportFormat.MARKDOWN:
            lines = [f"# {report.title}", "", report.executive_summary, "", "## Methodology", "", report.methodology, ""]
            for s in sorted(report.sections, key=lambda x: x.order):
                prefix = "#" * s.level
                lines.append(f"{prefix} {s.title}")
                lines.append("")
                lines.append(s.content)
                lines.append("")
            if report.conclusions:
                lines.append("## Conclusions")
                lines.append("")
                lines.append(report.conclusions)
            if report.recommendations:
                lines.append("## Recommendations")
                for r in report.recommendations:
                    lines.append(f"- {r}")
            return "\n".join(lines)
        elif fmt == ReportFormat.JSON:
            return json.dumps(report.to_dict(), indent=2, default=str)
        return None

    def get_telemetry(self) -> dict: return dict(self._telemetry)
