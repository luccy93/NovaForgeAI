"""Error Experience — automatically explain errors, suggest fixes, generate stack trace analysis, recommend documentation, provide recovery steps."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ErrorReport:
    id: str
    user_id: str
    org_id: str
    error_message: str
    error_type: str = ""
    stack_trace: str = ""
    language: str = ""
    file_path: str = ""
    line_number: int = 0
    explanation: str = ""
    suggested_fix: str = ""
    recovery_steps: list = field(default_factory=list)
    documentation_refs: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ErrorReport": return cls(**data)


class ErrorExperience:
    def __init__(self, storage_dir: str = "dx_data/errors"):
        self.storage_dir = storage_dir
        self._reports: dict[str, ErrorReport] = {}
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
                    try: self._reports[k] = ErrorReport.from_dict(v)
                    except Exception as e: logger.warning("Skipping error %s: %s", k, e)
            except Exception as e: logger.error("Failed to load error reports: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reports.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save error reports: %s", e)

    def report_error(self, user_id: str, org_id: str, error_message: str, error_type: str = "", stack_trace: str = "", language: str = "", file_path: str = "", line_number: int = 0) -> ErrorReport:
        report = ErrorReport(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, error_message=error_message, error_type=error_type, stack_trace=stack_trace, language=language, file_path=file_path, line_number=line_number)
        report.explanation = self._generate_explanation(error_message, error_type)
        report.suggested_fix = self._generate_fix(error_message, error_type)
        report.recovery_steps = self._generate_recovery_steps(error_type)
        self._reports[report.id] = report
        self._save()
        return report

    def _generate_explanation(self, message: str, error_type: str) -> str:
        if "syntax" in message.lower(): return "A syntax error occurred. Check for missing brackets, quotes, or invalid syntax near the indicated line."
        if "import" in message.lower(): return "An import error occurred. The module or package could not be found or loaded."
        if "type" in message.lower() or "TypeError" in error_type: return "A type mismatch occurred. An operation received an unexpected data type."
        return f"Error of type '{error_type or 'unknown'}' occurred. Review the stack trace for details."

    def _generate_fix(self, message: str, error_type: str) -> str:
        if "syntax" in message.lower(): return "Review the syntax at the indicated line. Ensure all brackets, parentheses, and quotes are properly closed."
        if "import" in message.lower(): return "Install the missing package or check that the import path is correct."
        if "type" in message.lower(): return "Check the variable types being used. Use type hints and assertions to catch issues early."
        return "Review the stack trace and error context to identify the root cause."

    def _generate_recovery_steps(self, error_type: str) -> list[str]:
        return [
            "Review the error message and stack trace carefully",
            "Check the indicated file and line number",
            "Search documentation for similar error patterns",
            "Run the code in a debugger to inspect state",
            "Consider adding error handling for this case",
        ]

    def get_reports(self, user_id: str = "", limit: int = 50) -> list[ErrorReport]:
        results = list(self._reports.values())
        if user_id: results = [r for r in results if r.user_id == user_id]
        return sorted(results, key=lambda r: r.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
