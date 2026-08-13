"""Retry policy handling for workflow steps (Volume 33)."""
import logging, random, time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetryOutcome:
    attempts: int
    succeeded: bool
    error: Optional[str] = None
    delays: list[float] = field(default_factory=list)


def effective_backoff_delays(max_retries: int, backoff_s: float,
                             max_backoff_s: float, jitter: float = 0.2,
                             seed: Optional[int] = None) -> list[float]:
    """Compute delay between attempts using capped exponential backoff."""
    rng = random.Random(seed)
    delays = []
    for i in range(max_retries):
        base = min(backoff_s * (2 ** i), max_backoff_s)
        delay = base * (1.0 - jitter + rng.random() * jitter * 2)
        delays.append(round(max(0.0, delay), 3))
    return delays


def run_with_retry(step_id: str, fn: Callable[[], Any],
                   max_retries: int = 0, backoff_s: float = 1.0,
                   max_backoff_s: float = 60.0, retryable=None,
                   jitter: float = 0.2, seed: Optional[int] = None,
                   sleep=time.sleep) -> tuple[Any, RetryOutcome]:
    """Run fn with capped exponential backoff. `retryable` is an optional
    predicate on the raised exception; default retries everything except
    non-retryable ToolError markers."""
    delays = effective_backoff_delays(max_retries, backoff_s, max_backoff_s,
                                      jitter, seed)
    attempts = 0
    last_error: Optional[str] = None
    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        try:
            result = fn()
            return result, RetryOutcome(attempts=attempts, succeeded=True)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("step %s attempt %d failed: %s",
                           step_id, attempts, last_error)
            if attempt < max_retries and (retryable is None or retryable(exc)):
                sleep(delays[attempt])
            else:
                break
    return None, RetryOutcome(attempts=attempts, succeeded=False,
                              error=last_error, delays=delays[: attempts - 1])


def is_transient(exc: BaseException) -> bool:
    """Retryable classification: timeouts, connection errors, 5xx."""
    import socket
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionError)):
        return True
    msg = str(exc).lower()
    return any(token in msg for token in ("timeout", "timed out",
                                          "connection refused",
                                          "temporarily unavailable", "500"))