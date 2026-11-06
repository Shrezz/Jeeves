"""Local JSON logs and opt-in, metadata-only Langfuse observations."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

# Optional telemetry errors must not affect requests or expose SDK exception details.
logger = logging.getLogger(__name__)
_client: Any = None


def get_trace_client() -> Any:
    """Initialize lazily; missing configuration must not block the API."""
    global _client
    if os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() != "true":
        return None
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        return None
    if _client is None:
        try:
            from langfuse import get_client

            _client = get_client()
        except Exception:  # noqa: BLE001 - best-effort telemetry boundary
            logger.warning("Unable to initialize Langfuse tracing")
            return None
    return _client


class SafeSpan:
    def __init__(self, span: Any = None) -> None:
        self._span = span

    def update(self, **kwargs: Any) -> None:
        if self._span is not None:
            try:
                self._span.update(**kwargs)
            except Exception:  # noqa: BLE001 - best-effort telemetry boundary
                logger.warning("Unable to update Langfuse observation")


@contextmanager
def observation(name: str, *, input: dict[str, Any] | None = None) -> Iterator[SafeSpan]:
    """Trace safe metadata only, without changing application error behavior."""
    client = get_trace_client()
    if client is None:
        yield SafeSpan()
        return
    try:
        manager = client.start_as_current_observation(as_type="span", name=name, input=input)
        span = manager.__enter__()
    except Exception:  # noqa: BLE001 - best-effort telemetry boundary
        logger.warning("Unable to start Langfuse observation")
        yield SafeSpan()
        return
    try:
        yield SafeSpan(span)
    except BaseException:
        try:
            manager.__exit__(*sys.exc_info())
        except Exception:  # noqa: BLE001 - best-effort telemetry boundary
            logger.warning("Unable to close Langfuse observation")
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 - best-effort telemetry boundary
            logger.warning("Unable to close Langfuse observation")


def flush_traces() -> None:
    if _client is not None:
        try:
            _client.flush()
        except Exception:  # noqa: BLE001 - best-effort telemetry boundary
            logger.warning("Unable to flush Langfuse observations")


current_run_id: ContextVar[str | None] = ContextVar("jeeves_run_id", default=None)


def configure_tracing() -> None:
    logger = logging.getLogger("jeeves")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
