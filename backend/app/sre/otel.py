"""OpenTelemetry integration (Volume 35).

Centralized tracer/span helpers and correlation-id plumbing. Uses the
OpenTelemetry SDK when available and degrades to a no-op context manager
otherwise so the platform keeps working without an OTLP collector.

Correlation model:
    trace_id  - OTel trace (16 bytes hex)
    span_id   - OTel span
    request_id / workflow_id / execution_id / agent_id / repository_id /
    organization_id - forwarded as span attributes and log correlation keys
"""

import contextlib
import logging
import os
import uuid
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

try:  # OpenTelemetry is an optional runtime dependency.
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - import failure path
    _OTEL_AVAILABLE = False

SERVICE_NAME = os.getenv("SRE_SERVICE_NAME", "novaforge-backend")
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"

_tracer = None
_provider = None


def setup_otel(service_name: str = SERVICE_NAME, endpoint: Optional[str] = None) -> bool:
    """Initialize the global tracer provider.

    Safe to call multiple times; returns True when OpenTelemetry is active.
    """
    global _tracer, _provider
    if not _OTEL_AVAILABLE:
        logger.info("OpenTelemetry SDK not installed; tracing disabled")
        return False
    if _provider is not None:
        return True
    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
                OTLPSpanExporter,
            )

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        _otel_trace.set_tracer_provider(provider)
        _provider = provider
        _tracer = _otel_trace.get_tracer(service_name)
        logger.info("OpenTelemetry tracing enabled (service=%s)", service_name)
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("OpenTelemetry setup failed: %s", exc)
        return False


def get_tracer():
    if not OTEL_ENABLED and not _OTEL_AVAILABLE:
        return None
    global _tracer
    if _tracer is None:
        setup_otel()
    return _tracer


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:24]}"


@contextlib.contextmanager
def span(
    name: str,
    attributes: Optional[dict[str, Any]] = None,
) -> Iterator[None]:
    """Start a child span; no-op when OpenTelemetry is unavailable."""
    tracer = get_tracer()
    if tracer is None or not OTEL_ENABLED:
        yield
        return
    with tracer.start_as_current_span(name, attributes=attributes or {}):
        yield


def set_span_attributes(attributes: dict[str, Any]) -> None:
    """Attach correlation attributes to the current span (if any)."""
    if not OTEL_ENABLED:
        return
    current = _otel_trace.get_current_span()
    if current is not None and current.is_recording():
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, str(value))


def current_trace_id() -> Optional[str]:
    """Return the current trace id as hex, or None."""
    if not (_OTEL_AVAILABLE and OTEL_ENABLED):
        return None
    try:
        span = _otel_trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is not None and ctx.trace_id not in (0, None):
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


def current_span_id() -> Optional[str]:
    if not (_OTEL_AVAILABLE and OTEL_ENABLED):
        return None
    try:
        span = _otel_trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is not None and ctx.span_id not in (0, None):
            return format(ctx.span_id, "016x")
    except Exception:
        pass
    return None
