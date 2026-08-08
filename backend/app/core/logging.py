import logging
import sys
import uuid
from datetime import datetime, timezone


def configure_logging(level: str = "INFO") -> None:
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


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
