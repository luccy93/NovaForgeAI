import json
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone

STRUCTURED_LOGGING = os.getenv("STRUCTURED_LOGGING", "false").lower() == "true"


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line.

    Includes standard fields plus SRE correlation keys when present on the
    record (request_id, trace_id, organization_id, ...). Never logs secrets:
    only the message text (already sanitized by callers) is included.
    """

    _RESERVED = {"message", "asctime", "levelname", "name", "exc_info", "args", "stack_info", "msg", "created", "msecs", "relativeCreated", "levelno", "pathname", "filename", "module", "funcName", "lineno", "thread", "process", "taskName", "processName", "threadName"}

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "trace_id", "span_id", "organization_id", "workspace_id", "user_id", "operation", "duration_ms", "status", "service", "environment", "region", "instance"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class JsonFormatterFilter(logging.Filter):
    """Attach service-level correlation attributes to every record."""

    def __init__(self, service: str, environment: str, region: str, instance: str):
        super().__init__()
        self._service = service
        self._environment = environment
        self._region = region
        self._instance = instance

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        record.environment = self._environment
        record.region = self._region
        record.instance = self._instance
        return True


def configure_logging(level: str = "INFO") -> None:
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if STRUCTURED_LOGGING:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    service_filter = JsonFormatterFilter(
        service=os.getenv("SRE_SERVICE_NAME", "novaforge-backend"),
        environment=os.getenv("NOVAFORGE_ENV", "development"),
        region=os.getenv("NOVAFORGE_REGION", "local"),
        instance=os.getenv("NOVAFORGE_INSTANCE", os.uname().nodename if hasattr(os, "uname") else "local"),
    )
    logger.addFilter(service_filter)


class RequestIDFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self._request_id: str = ""

    def set_request_id(self, request_id: str) -> None:
        self._request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", self._request_id or "-")
        record.timestamp = datetime.now(timezone.utc).isoformat()
        return True


_request_id_filter = RequestIDFilter()


def get_request_id_filter() -> RequestIDFilter:
    return _request_id_filter


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.addFilter(_request_id_filter)
    return logger
