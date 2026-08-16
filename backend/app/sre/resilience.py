"""Resilience primitives (Volume 35).

Circuit breakers, bounded retries with exponential backoff + jitter,
and explicit timeout policies for external operations.

Rules enforced here:
  - Never retry permanent failures (auth, validation, 4xx, idempotency-safe).
  - Circuit breakers transition CLOSED -> OPEN -> HALF_OPEN -> CLOSED.
  - Retries are bounded by max attempts and a retry budget.
"""

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, TypeVar

from app.sre.constants import CIRCUIT_CLOSED, CIRCUIT_HALF_OPEN, CIRCUIT_OPEN
from app.sre.otel import span

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryDecision(str, Enum):
    RETRY = "retry"
    NO_RETRY = "no_retry"


# ---------------------------------------------------------------------------
# Retry classification
# ---------------------------------------------------------------------------

# HTTP status codes that must never be retried (permanent failures).
NON_RETRYABLE_STATUS_CODES = frozenset(
    {400, 401, 402, 403, 404, 405, 406, 409, 410, 411, 412, 413, 414, 415, 416, 417, 422}
)
# Status codes representing provider-side overload (safe to retry).
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def classify_retry(exc: Optional[BaseException] = None, status_code: Optional[int] = None) -> RetryDecision:
    """Classify whether an operation failure may be retried.

    Authentication errors, invalid requests, permission failures and
    known permanent failures must never be retried.
    """
    if status_code is not None:
        if status_code in NON_RETRYABLE_STATUS_CODES:
            return RetryDecision.NO_RETRY
        if status_code in RETRYABLE_STATUS_CODES:
            return RetryDecision.RETRY
    if exc is not None:
        message = str(exc).lower()
        permanent_hints = (
            "invalid",
            "unauthorized",
            "forbidden",
            "permission",
            "not found",
            "not supported",
            "bad request",
            "authentication",
            "api key",
            "quota exceeded",
            "invalid_request_error",
            "permission_error",
            "authentication_error",
            "content_policy",
        )
        if any(hint in message for hint in permanent_hints):
            return RetryDecision.NO_RETRY
    return RetryDecision.RETRY


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    """Bounded retry policy with exponential backoff and jitter."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.2
    max_delay_seconds: float = 8.0
    backoff_factor: float = 2.0
    jitter: float = 0.2  # fraction of delay randomized
    retry_budget_seconds: float = 30.0  # hard cap on total retry wall-clock time

    def delay_for(self, attempt: int) -> float:
        if attempt < 1:
            return 0.0
        exponential = min(self.base_delay_seconds * (self.backoff_factor ** (attempt - 1)), self.max_delay_seconds)
        jitter_amount = exponential * self.jitter
        return max(0.0, min(self.max_delay_seconds, exponential + random.uniform(-jitter_amount, jitter_amount)))


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: Optional[RetryPolicy] = None,
    name: str = "operation",
    should_retry: Optional[Callable[[BaseException], RetryDecision]] = None,
) -> T:
    """Execute an async operation with bounded retries.

    Never retries classified-permanent failures. Enforces an overall
    retry budget so retries cannot run away.
    """
    policy = policy or RetryPolicy()
    attempts = 0
    started = time.monotonic()
    while True:
        attempts += 1
        try:
            with span(name):
                return await operation()
        except Exception as exc:
            decision = should_retry(exc) if should_retry else classify_retry(exc)
            if decision is RetryDecision.NO_RETRY:
                logger.info("%s failed permanently (attempt %d): %s", name, attempts, exc)
                raise
            if attempts >= policy.max_attempts:
                logger.warning("%s exhausted %d attempts: %s", name, attempts, exc)
                raise
            if time.monotonic() - started >= policy.retry_budget_seconds:
                logger.warning("%s retry budget exhausted: %s", name, exc)
                raise
            delay = policy.delay_for(attempts)
            logger.debug("%s attempt %d failed; retrying in %.2fs", name, attempts, delay)
            await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitOpenError(RuntimeError):
    """Raised when a circuit breaker is OPEN and rejects the call."""


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5            # consecutive failures before OPEN
    timeout_seconds: float = 30.0         # time in OPEN before HALF_OPEN
    recovery_window_seconds: float = 60.0  # success period in HALF_OPEN to close
    half_open_max_calls: int = 1
    name: str = "dependency"


class CircuitBreaker:
    """Trip-wire for unreliable dependencies.

    CLOSED   - calls pass through; failures counted.
    OPEN     - calls rejected fast; after timeout, moves to HALF_OPEN.
    HALF_OPEN- limited probe calls; success closes, failure re-opens.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.state: str = CIRCUIT_CLOSED
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._lock = threading.Lock()
        self._calls_total = 0
        self._calls_failed = 0

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._calls_failed += 1
            if self.state == CIRCUIT_HALF_OPEN:
                self.state = CIRCUIT_OPEN
                self._opened_at = time.monotonic()
                self._half_open_calls = 0
                self._half_open_successes = 0
            elif self.state == CIRCUIT_CLOSED and self._consecutive_failures >= self.config.failure_threshold:
                self.state = CIRCUIT_OPEN
                self._opened_at = time.monotonic()
                logger.warning("Circuit %s OPEN after %d failures", self.config.name, self._consecutive_failures)

    def _record_success(self) -> None:
        with self._lock:
            if self.state == CIRCUIT_HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.config.half_open_max_calls:
                    self.state = CIRCUIT_CLOSED
                    self._consecutive_failures = 0
                    self._opened_at = None
                    self._half_open_calls = 0
                    logger.info("Circuit %s CLOSED after successful probes", self.config.name)
            else:
                self._consecutive_failures = 0

    def allow_call(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._calls_total += 1
            if self.state == CIRCUIT_OPEN:
                if self._opened_at is not None and (now - self._opened_at) >= self.config.timeout_seconds:
                    self.state = CIRCUIT_HALF_OPEN
                    self._half_open_calls = 0
                    self._half_open_successes = 0
                    logger.info("Circuit %s HALF_OPEN (recovery probe)", self.config.name)
                else:
                    return False
            if self.state == CIRCUIT_HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    return False
                self._half_open_calls += 1
            return True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "name": self.config.name,
                "state": self.state,
                "consecutive_failures": self._consecutive_failures,
                "calls_total": self._calls_total,
                "calls_failed": self._calls_failed,
                "opened_at": self._opened_at,
            }

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run an operation guarded by this breaker."""
        if not self.allow_call():
            raise CircuitOpenError(f"Circuit {self.config.name} is OPEN; call rejected")
        try:
            result = await operation()
            self._record_success()
            return result
        except Exception as exc:
            self._record_failure()
            raise


class CircuitBreakerRegistry:
    """Named circuit breaker registry (process-local)."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> CircuitBreaker:
        with self._lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                breaker = CircuitBreaker(CircuitBreakerConfig(name=name))
                self._breakers[name] = breaker
            return breaker

    def register(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        with self._lock:
            breaker = CircuitBreaker(config or CircuitBreakerConfig(name=name))
            self._breakers[name] = breaker
            return breaker

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {name: breaker.snapshot() for name, breaker in self._breakers.items()}

    def states(self) -> dict[str, str]:
        with self._lock:
            return {name: breaker.state for name, breaker in self._breakers.items()}


circuit_breaker_registry = CircuitBreakerRegistry()


# ---------------------------------------------------------------------------
# Timeout framework
# ---------------------------------------------------------------------------

@dataclass
class TimeoutPolicy:
    """Explicit timeouts for external operations."""

    connect_seconds: float = 2.0
    read_seconds: float = 10.0
    write_seconds: float = 10.0
    overall_seconds: float = 30.0


def timeout_settings(policy: Optional[TimeoutPolicy] = None) -> dict:
    """Map a TimeoutPolicy to common client timeout kwargs."""
    policy = policy or TimeoutPolicy()
    return {
        "connect_timeout": policy.connect_seconds,
        "read_timeout": policy.read_seconds,
        "write_timeout": policy.write_seconds,
        "timeout": policy.overall_seconds,
    }


async def with_timeout(coro: Awaitable[T], seconds: float, name: str = "operation") -> T:
    """Run a coroutine under an overall timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"{name} timed out after {seconds}s") from exc
