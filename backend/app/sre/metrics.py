"""Operational metrics (Volume 35).

Prometheus-compatible golden-signal instrumentation for every critical
service: latency, traffic, errors, saturation. Also exposes request-level
counters used by the SLO engine (good/total per SLO).

Metrics are process-local. The /metrics endpoint (registered in the API
layer) renders them for the Prometheus scraper configured in
monitoring/prometheus/prometheus.yml.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    _PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover - dependency fallback
    _PROMETHEUS_AVAILABLE = False
    CollectorRegistry = None
    Counter = None
    Gauge = None
    Histogram = None
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


REGISTRY = CollectorRegistry() if _PROMETHEUS_AVAILABLE else None

# Golden signals per service.
_REQUEST_TOTAL = None
_REQUEST_DURATION = None
_REQUEST_ERRORS = None
_INFLIGHT = None
_QUEUE_DEPTH = None
_AI_LATENCY = None
_AI_TOKENS = None
_DEPENDENCY_STATUS = None

if _PROMETHEUS_AVAILABLE:
    _REQUEST_TOTAL = Counter(
        "novaforge_http_requests_total",
        "Total HTTP requests by method, path and status",
        ["method", "path", "status", "service"],
        registry=REGISTRY,
    )
    _REQUEST_DURATION = Histogram(
        "novaforge_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path", "service"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
        registry=REGISTRY,
    )
    _REQUEST_ERRORS = Counter(
        "novaforge_http_request_errors_total",
        "HTTP request errors (5xx) by service",
        ["service", "status"],
        registry=REGISTRY,
    )
    _INFLIGHT = Gauge(
        "novaforge_http_inflight_requests",
        "Current in-flight requests by service",
        ["service"],
        registry=REGISTRY,
    )
    _QUEUE_DEPTH = Gauge(
        "novaforge_queue_depth",
        "Queue depth by queue name",
        ["queue"],
        registry=REGISTRY,
    )
    _AI_LATENCY = Histogram(
        "novaforge_ai_request_duration_seconds",
        "AI provider request duration in seconds",
        ["provider", "model"],
        buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
        registry=REGISTRY,
    )
    _AI_TOKENS = Counter(
        "novaforge_ai_tokens_total",
        "AI tokens consumed by provider and direction",
        ["provider", "direction"],
        registry=REGISTRY,
    )
    _DEPENDENCY_STATUS = Gauge(
        "novaforge_dependency_status",
        "Dependency health: 1 healthy, 0 down",
        ["dependency"],
        registry=REGISTRY,
    )
    _SLO_GOOD = Counter(
        "novaforge_sli_good_total",
        "SLI good events by slo",
        ["slo_id", "service_id", "sli_type"],
        registry=REGISTRY,
    )
    _SLO_TOTAL = Counter(
        "novaforge_sli_total_total",
        "SLI total events by slo",
        ["slo_id", "service_id", "sli_type"],
        registry=REGISTRY,
    )


def prometheus_enabled() -> bool:
    return _PROMETHEUS_AVAILABLE


def render_metrics() -> tuple[bytes, str]:
    """Render the Prometheus exposition format."""
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus-client not installed\n", CONTENT_TYPE_LATEST
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def record_request(method: str, path: str, status: int, duration_seconds: float, service: str = "api") -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        status_label = str(status)
        _REQUEST_TOTAL.labels(method=method, path=path, status=status_label, service=service).inc()
        _REQUEST_DURATION.labels(method=method, path=path, service=service).observe(duration_seconds)
        if status >= 500:
            _REQUEST_ERRORS.labels(service=service, status=status_label).inc()
    except Exception:  # pragma: no cover - metrics must never break requests
        logger.debug("metric recording failed", exc_info=True)


def inflight_inc(service: str = "api") -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            _INFLIGHT.labels(service=service).inc()
        except Exception:
            pass


def inflight_dec(service: str = "api") -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            _INFLIGHT.labels(service=service).dec()
        except Exception:
            pass


def set_queue_depth(queue: str, depth: int) -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            _QUEUE_DEPTH.labels(queue=queue).set(depth)
        except Exception:
            pass


def record_ai_request(provider: str, model: str, duration_seconds: float) -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            _AI_LATENCY.labels(provider=provider, model=model).observe(duration_seconds)
        except Exception:
            pass


def record_ai_tokens(provider: str, direction: str, tokens: int) -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            _AI_TOKENS.labels(provider=provider, direction=direction).inc(tokens)
        except Exception:
            pass


def set_dependency_status(dependency: str, healthy: bool) -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            _DEPENDENCY_STATUS.labels(dependency=dependency).set(1 if healthy else 0)
        except Exception:
            pass


def record_sli(slo_id: str, service_id: str, sli_type: str, good: float, total: float) -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            _SLO_GOOD.labels(slo_id=slo_id, service_id=service_id, sli_type=sli_type).inc(good)
            _SLO_TOTAL.labels(slo_id=slo_id, service_id=service_id, sli_type=sli_type).inc(total)
        except Exception:
            pass


class GoldenSignals:
    """Per-service golden-signal registry (latency, traffic, errors, saturation)."""

    def __init__(self) -> None:
        self._signals: dict[str, dict] = {}
        self._lock = threading.Lock()

    def record(self, service: str, *, latency_ms: float = 0.0, traffic: float = 0.0, errors: float = 0.0, saturation: float = 0.0) -> None:
        with self._lock:
            signal = self._signals.setdefault(
                service,
                {"latency_ms": 0.0, "traffic": 0.0, "errors": 0.0, "saturation": 0.0, "samples": 0},
            )
            signal["latency_ms"] = latency_ms
            signal["traffic"] += traffic
            signal["errors"] += errors
            signal["saturation"] = saturation
            signal["samples"] += 1

    def snapshot(self, service: Optional[str] = None) -> dict:
        with self._lock:
            if service:
                signal = self._signals.get(service)
                return dict(signal) if signal else {}
            return {name: dict(s) for name, s in self._signals.items()}


golden_signals = GoldenSignals()
