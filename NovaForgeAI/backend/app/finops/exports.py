import json
import uuid
import hashlib
import time
import math
import os
import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"
    JSON = "json"
    HTML = "html"
    MARKDOWN = "markdown"
    PARQUET = "parquet"
    API = "api"


class ExportStatus(Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ExportCompression(Enum):
    NONE = "none"
    GZIP = "gzip"
    ZIP = "zip"
    BROTLI = "brotli"


class ExportScope(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    LAST_MONTH = "last_month"
    LAST_QUARTER = "last_quarter"
    LAST_YEAR = "last_year"
    CUSTOM_RANGE = "custom_range"
    CURRENT = "current"


@dataclass
class ExportRequest:
    id: str
    org_id: str
    user_id: str
    name: str
    format: ExportFormat
    scope: ExportScope
    data_type: str
    filters: dict
    columns: list
    compression: ExportCompression
    include_headers: bool = True
    schedule_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["format"] = self.format.value
        d["scope"] = self.scope.value
        d["compression"] = self.compression.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExportRequest":
        data = data.copy()
        data["format"] = ExportFormat(data.get("format", "csv"))
        data["scope"] = ExportScope(data.get("scope", "full"))
        data["compression"] = ExportCompression(data.get("compression", "none"))
        return cls(**data)


@dataclass
class ExportResult:
    id: str
    request_id: str
    org_id: str
    name: str
    format: ExportFormat
    status: ExportStatus
    file_path: str = ""
    file_size_bytes: int = 0
    row_count: int = 0
    error_message: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""
    download_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["format"] = self.format.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExportResult":
        data = data.copy()
        data["format"] = ExportFormat(data.get("format", "csv"))
        data["status"] = ExportStatus(data.get("status", "pending"))
        return cls(**data)


@dataclass
class ScheduledExport:
    id: str
    org_id: str
    name: str
    format: ExportFormat
    frequency: str
    data_type: str
    filters: dict
    recipients: list
    is_active: bool = True
    next_run: str = ""
    last_run: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["format"] = self.format.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledExport":
        data = data.copy()
        data["format"] = ExportFormat(data.get("format", "csv"))
        return cls(**data)


@dataclass
class ExportTemplate:
    id: str
    org_id: str
    name: str
    format: ExportFormat
    data_type: str
    columns: list
    filters: dict
    options: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["format"] = self.format.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExportTemplate":
        data = data.copy()
        data["format"] = ExportFormat(data.get("format", "csv"))
        return cls(**data)


class ExportManager:
    def __init__(self, storage_dir: str = "export_data"):
        self.storage_dir = storage_dir
        self._requests: dict[str, ExportRequest] = {}
        self._results: dict[str, ExportResult] = {}
        self._scheduled: dict[str, ScheduledExport] = {}
        self._templates: dict[str, ExportTemplate] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(os.path.join(self.storage_dir, "export"), exist_ok=True)
        self._load()

    def _requests_path(self) -> str:
        return os.path.join(self.storage_dir, "export_requests.json")

    def _results_path(self) -> str:
        return os.path.join(self.storage_dir, "export_results.json")

    def _scheduled_path(self) -> str:
        return os.path.join(self.storage_dir, "scheduled_exports.json")

    def _templates_path(self) -> str:
        return os.path.join(self.storage_dir, "export_templates.json")

    def _save(self) -> None:
        try:
            requests_data = {rid: r.to_dict() for rid, r in self._requests.items()}
            with open(self._requests_path(), "w", encoding="utf-8") as f:
                json.dump(requests_data, f, indent=2, default=str)

            results_data = {rid: r.to_dict() for rid, r in self._results.items()}
            with open(self._results_path(), "w", encoding="utf-8") as f:
                json.dump(results_data, f, indent=2, default=str)

            scheds_data = {sid: s.to_dict() for sid, s in self._scheduled.items()}
            with open(self._scheduled_path(), "w", encoding="utf-8") as f:
                json.dump(scheds_data, f, indent=2, default=str)

            templates_data = {tid: t.to_dict() for tid, t in self._templates.items()}
            with open(self._templates_path(), "w", encoding="utf-8") as f:
                json.dump(templates_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save export data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._requests_path()):
                with open(self._requests_path(), "r", encoding="utf-8") as f:
                    requests_data = json.load(f)
                for rid, data in requests_data.items():
                    try:
                        self._requests[rid] = ExportRequest.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed export request %s: %s", rid, e)

            if os.path.exists(self._results_path()):
                with open(self._results_path(), "r", encoding="utf-8") as f:
                    results_data = json.load(f)
                for rid, data in results_data.items():
                    try:
                        self._results[rid] = ExportResult.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed export result %s: %s", rid, e)

            if os.path.exists(self._scheduled_path()):
                with open(self._scheduled_path(), "r", encoding="utf-8") as f:
                    scheds_data = json.load(f)
                for sid, data in scheds_data.items():
                    try:
                        self._scheduled[sid] = ScheduledExport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed scheduled export %s: %s", sid, e)

            if os.path.exists(self._templates_path()):
                with open(self._templates_path(), "r", encoding="utf-8") as f:
                    templates_data = json.load(f)
                for tid, data in templates_data.items():
                    try:
                        self._templates[tid] = ExportTemplate.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed export template %s: %s", tid, e)
        except Exception as e:
            logger.error("Failed to load export data: %s", e, exc_info=True)

    def create_export_request(self, request: ExportRequest) -> ExportRequest:
        self._telemetry["create_export_request_calls"] += 1
        if not request.id:
            request.id = str(uuid.uuid4())
        if not request.created_at:
            request.created_at = datetime.now(timezone.utc).isoformat()
        self._requests[request.id] = request
        self._save()
        logger.info("Created export request %s: %s (%s)", request.id, request.name, request.format.value)
        return request

    def export_to_csv(self, request_id: str, data: list[dict]) -> ExportResult:
        self._telemetry["export_to_csv_calls"] += 1
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Export request {request_id} not found")

        result_id = str(uuid.uuid4())
        filename = f"export_{request_id}_{result_id[:8]}.csv"
        file_path = os.path.join(self.storage_dir, "export", filename)

        try:
            output = io.StringIO()
            if data:
                fieldnames = request.columns if request.columns else list(data[0].keys())
                writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
                if request.include_headers:
                    writer.writeheader()
                for row in data:
                    filtered = {k: v for k, v in row.items() if k in fieldnames}
                    writer.writerow(filtered)
            else:
                output.write("")

            csv_bytes = output.getvalue().encode("utf-8")
            with open(file_path, "wb") as f:
                f.write(csv_bytes)

            output.close()

            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.CSV,
                status=ExportStatus.COMPLETED,
                file_path=file_path,
                file_size_bytes=len(csv_bytes),
                row_count=len(data),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            )
        except Exception as e:
            logger.error("CSV export failed: %s", e, exc_info=True)
            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.CSV,
                status=ExportStatus.FAILED,
                error_message=str(e),
            )

        self._results[result.id] = result
        self._save()
        logger.info("CSV export %s completed: %d rows, %d bytes", result.id, result.row_count, result.file_size_bytes)
        return result

    def export_to_json(self, request_id: str, data: list[dict]) -> ExportResult:
        self._telemetry["export_to_json_calls"] += 1
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Export request {request_id} not found")

        result_id = str(uuid.uuid4())
        filename = f"export_{request_id}_{result_id[:8]}.json"
        file_path = os.path.join(self.storage_dir, "export", filename)

        try:
            if request.columns:
                filtered = [{k: row.get(k) for k in request.columns} for row in data]
            else:
                filtered = data
            json_str = json.dumps(filtered, indent=2, default=str)
            json_bytes = json_str.encode("utf-8")
            with open(file_path, "wb") as f:
                f.write(json_bytes)

            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.JSON,
                status=ExportStatus.COMPLETED,
                file_path=file_path,
                file_size_bytes=len(json_bytes),
                row_count=len(data),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            )
        except Exception as e:
            logger.error("JSON export failed: %s", e, exc_info=True)
            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.JSON,
                status=ExportStatus.FAILED,
                error_message=str(e),
            )

        self._results[result.id] = result
        self._save()
        logger.info("JSON export %s completed: %d rows, %d bytes", result.id, result.row_count, result.file_size_bytes)
        return result

    def export_to_html(self, request_id: str, data: list[dict], title: str = "") -> ExportResult:
        self._telemetry["export_to_html_calls"] += 1
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Export request {request_id} not found")

        result_id = str(uuid.uuid4())
        filename = f"export_{request_id}_{result_id[:8]}.html"
        file_path = os.path.join(self.storage_dir, "export", filename)

        try:
            report_title = title or request.name
            columns = request.columns if request.columns else (list(data[0].keys()) if data else [])
            filtered = [{k: row.get(k, "") for k in columns} for row in data] if columns else data

            header_cells = "".join(f"<th>{c}</th>" for c in columns)
            row_html = ""
            for item in filtered:
                cells = "".join(f"<td>{str(item.get(k, ''))}</td>" for k in columns)
                row_html += f"<tr>{cells}</tr>\n"

            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report_title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 2rem; color: #333; background: #f5f7fa; }}
  h1 {{ color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 0.5rem; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  th {{ background: #1a1a2e; color: white; padding: 12px 16px; text-align: left; font-weight: 600; }}
  td {{ padding: 10px 16px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #f0f0f5; }}
  .footer {{ margin-top: 1rem; color: #999; font-size: 0.85rem; text-align: center; }}
  .count {{ background: #e94560; color: white; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>{report_title}</h1>
<div class="meta">Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} &nbsp;|&nbsp; <span class="count">{len(data)} rows</span></div>
<table>
<thead><tr>{header_cells}</tr></thead>
<tbody>{row_html}</tbody>
</table>
<div class="footer">NovaForge AI Export &mdash; {report_title}</div>
</body>
</html>"""

            html_bytes = html_content.encode("utf-8")
            with open(file_path, "wb") as f:
                f.write(html_bytes)

            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.HTML,
                status=ExportStatus.COMPLETED,
                file_path=file_path,
                file_size_bytes=len(html_bytes),
                row_count=len(data),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            )
        except Exception as e:
            logger.error("HTML export failed: %s", e, exc_info=True)
            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.HTML,
                status=ExportStatus.FAILED,
                error_message=str(e),
            )

        self._results[result.id] = result
        self._save()
        logger.info("HTML export %s completed: %d rows, %d bytes", result.id, result.row_count, result.file_size_bytes)
        return result

    def export_to_markdown(self, request_id: str, data: list[dict], title: str = "") -> ExportResult:
        self._telemetry["export_to_markdown_calls"] += 1
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Export request {request_id} not found")

        result_id = str(uuid.uuid4())
        filename = f"export_{request_id}_{result_id[:8]}.md"
        file_path = os.path.join(self.storage_dir, "export", filename)

        try:
            report_title = title or request.name
            columns = request.columns if request.columns else (list(data[0].keys()) if data else [])
            filtered = [{k: row.get(k, "") for k in columns} for row in data] if columns else data

            lines = []
            lines.append(f"# {report_title}")
            lines.append("")
            lines.append(f"> Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            lines.append(f"> Rows: {len(data)}")
            lines.append("")
            header_sep = "| " + " | ".join(columns) + " |"
            lines.append(header_sep)
            lines.append("| " + " | ".join("---" for _ in columns) + " |")
            for item in filtered:
                row_values = [str(item.get(k, "")) for k in columns]
                lines.append("| " + " | ".join(row_values) + " |")
            lines.append("")
            lines.append("---")
            lines.append(f"*NovaForge AI Export — {report_title}*")
            lines.append("")

            md_content = "\n".join(lines)
            md_bytes = md_content.encode("utf-8")
            with open(file_path, "wb") as f:
                f.write(md_bytes)

            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.MARKDOWN,
                status=ExportStatus.COMPLETED,
                file_path=file_path,
                file_size_bytes=len(md_bytes),
                row_count=len(data),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            )
        except Exception as e:
            logger.error("Markdown export failed: %s", e, exc_info=True)
            result = ExportResult(
                id=result_id,
                request_id=request_id,
                org_id=request.org_id,
                name=request.name,
                format=ExportFormat.MARKDOWN,
                status=ExportStatus.FAILED,
                error_message=str(e),
            )

        self._results[result.id] = result
        self._save()
        logger.info("Markdown export %s completed: %d rows, %d bytes", result.id, result.row_count, result.file_size_bytes)
        return result

    def export_data(self, request_id: str, data: list[dict]) -> ExportResult:
        self._telemetry["export_data_calls"] += 1
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Export request {request_id} not found")

        fmt = request.format
        if fmt == ExportFormat.CSV:
            return self.export_to_csv(request_id, data)
        elif fmt == ExportFormat.JSON:
            return self.export_to_json(request_id, data)
        elif fmt == ExportFormat.HTML:
            return self.export_to_html(request_id, data, request.name)
        elif fmt == ExportFormat.MARKDOWN:
            return self.export_to_markdown(request_id, data, request.name)
        elif fmt == ExportFormat.EXCEL:
            return self._export_fallback(request_id, data, ExportFormat.EXCEL, "Excel export not yet implemented")
        elif fmt == ExportFormat.PDF:
            return self._export_fallback(request_id, data, ExportFormat.PDF, "PDF export not yet implemented")
        elif fmt == ExportFormat.PARQUET:
            return self._export_fallback(request_id, data, ExportFormat.PARQUET, "Parquet export not yet implemented")
        elif fmt == ExportFormat.API:
            return self._export_fallback(request_id, data, ExportFormat.API, "API export not yet implemented")
        else:
            return self.export_to_csv(request_id, data)

    def _export_fallback(self, request_id: str, data: list[dict], fmt: ExportFormat, message: str) -> ExportResult:
        request = self._requests.get(request_id)
        result_id = str(uuid.uuid4())
        result = ExportResult(
            id=result_id,
            request_id=request_id,
            org_id=request.org_id if request else "",
            name=request.name if request else "export",
            format=fmt,
            status=ExportStatus.FAILED,
            error_message=message,
        )
        self._results[result.id] = result
        self._save()
        return result

    def get_export_result(self, result_id: str) -> Optional[ExportResult]:
        self._telemetry["get_export_result_calls"] += 1
        return self._results.get(result_id)

    def list_exports(self, org_id: str, status: Optional[ExportStatus] = None) -> list[ExportResult]:
        self._telemetry["list_exports_calls"] += 1
        results = []
        for result in self._results.values():
            if result.org_id != org_id:
                continue
            if status is not None and result.status != status:
                continue
            results.append(result)
        results.sort(key=lambda r: r.generated_at, reverse=True)
        return results

    def create_export_template(self, template: ExportTemplate) -> ExportTemplate:
        self._telemetry["create_export_template_calls"] += 1
        if not template.id:
            template.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        template.created_at = now
        template.updated_at = now
        self._templates[template.id] = template
        self._save()
        logger.info("Created export template %s: %s", template.id, template.name)
        return template

    def list_templates(self, org_id: str) -> list[ExportTemplate]:
        self._telemetry["list_templates_calls"] += 1
        results = []
        for template in self._templates.values():
            if template.org_id == org_id:
                results.append(template)
        results.sort(key=lambda t: t.updated_at, reverse=True)
        return results

    def schedule_export(self, scheduled: ScheduledExport) -> ScheduledExport:
        self._telemetry["schedule_export_calls"] += 1
        if not scheduled.id:
            scheduled.id = str(uuid.uuid4())
        if not scheduled.created_at:
            scheduled.created_at = datetime.now(timezone.utc).isoformat()
        if not scheduled.next_run:
            scheduled.next_run = self._compute_next_run(scheduled.frequency)
        self._scheduled[scheduled.id] = scheduled
        self._save()
        logger.info("Scheduled export %s: frequency=%s, next_run=%s", scheduled.id, scheduled.frequency, scheduled.next_run)
        return scheduled

    def _compute_next_run(self, frequency: str) -> str:
        now = datetime.now(timezone.utc)
        freq = frequency.lower()
        if freq in ("daily", "daily"):
            next_dt = now + timedelta(days=1)
        elif freq in ("weekly", "weekly"):
            next_dt = now + timedelta(weeks=1)
        elif freq in ("monthly", "monthly"):
            next_dt = now + timedelta(days=30)
        elif freq in ("quarterly", "quarterly"):
            next_dt = now + timedelta(days=91)
        elif freq in ("yearly", "annually"):
            next_dt = now + timedelta(days=365)
        elif freq in ("hourly", "hourly"):
            next_dt = now + timedelta(hours=1)
        else:
            next_dt = now + timedelta(days=1)
        return next_dt.isoformat()

    def run_scheduled_exports(self) -> list[ExportResult]:
        self._telemetry["run_scheduled_exports_calls"] += 1
        now = datetime.now(timezone.utc)
        executed = []

        for schedule in list(self._scheduled.values()):
            if not schedule.is_active:
                continue
            if not schedule.next_run:
                continue
            next_run = datetime.fromisoformat(schedule.next_run) if isinstance(schedule.next_run, str) else schedule.next_run
            if next_run > now:
                continue

            request = ExportRequest(
                id=str(uuid.uuid4()),
                org_id=schedule.org_id,
                user_id="system",
                name=schedule.name,
                format=schedule.format,
                scope=ExportScope.FULL,
                data_type=schedule.data_type,
                filters=schedule.filters,
                columns=[],
                compression=ExportCompression.NONE,
                schedule_id=schedule.id,
            )
            self.create_export_request(request)
            result = self.export_data(request.id, [])
            if result.status == ExportStatus.COMPLETED:
                schedule.last_run = now.isoformat()
                schedule.next_run = self._compute_next_run(schedule.frequency)
                executed.append(result)
                logger.info("Executed scheduled export %s: %s", schedule.id, result.id)

        if executed:
            self._save()

        return executed

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
