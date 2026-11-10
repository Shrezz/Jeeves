"""Opt-in, metadata-only Langfuse instrumentation for the synthetic demo."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langgraph.errors import GraphInterrupt

logger = logging.getLogger(__name__)
_client: Any = None
_flush_lock = threading.Lock()
_flush_thread: threading.Thread | None = None
current_trace_session_id: ContextVar[str | None] = ContextVar("jeeves_trace_session_id", default=None)
current_run_id: ContextVar[str | None] = ContextVar("jeeves_run_id", default=None)
_ui_synthetic_capture: ContextVar[bool] = ContextVar("jeeves_ui_synthetic_capture", default=False)
_SECRET_KEY = re.compile(
    r"password|token|authorization|secret|api[_-]?key|cookie|session|user[_-]?id|claim[_-]?id|policy[_-]?id",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)\b(bearer\s+)\S+")
_API_KEY = re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{8,}\b")


def capture_synthetic_content() -> bool:
    """Extra content capture is opt-in and only available in demo mode."""
    return (
        os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development") != "production"
        and os.getenv("LANGFUSE_CAPTURE_SYNTHETIC_CONTENT", "false").lower() == "true"
        and (os.getenv("JEEVES_MODE") == "demo" or _ui_synthetic_capture.get())
    )


@contextmanager
def synthetic_claim_capture(claim_id: str) -> Iterator[None]:
    """Allow opt-in content capture only for explicitly listed fictional claim IDs."""
    allowed = {
        item.strip()
        for item in os.getenv("JEEVES_SYNTHETIC_TRACE_CLAIM_IDS", "").split(",")
        if item.strip()
    }
    token = _ui_synthetic_capture.set(bool(claim_id) and claim_id in allowed)
    try:
        yield
    finally:
        _ui_synthetic_capture.reset(token)


def sanitize_content(value: Any, *, depth: int = 0) -> Any:
    """Best-effort redaction for demo content; never put real secrets in inputs."""
    if depth > 8:
        return "[depth limit]"
    if isinstance(value, dict):
        return {
            str(key): "[redacted]"
            if _SECRET_KEY.search(str(key))
            else sanitize_content(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_content(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return _API_KEY.sub("[redacted]", _BEARER.sub(r"\1[redacted]", value))[:4000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return "[unsupported value]"


def configure_tracing() -> None:
    local_logger = logging.getLogger("jeeves")
    if not local_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        local_logger.addHandler(handler)
    local_logger.setLevel(logging.INFO)
    local_logger.propagate = False


class _ExporterLogHandler(logging.Handler):
    """Do not forward SDK error bodies; expose a safe operational event instead."""

    def emit(self, record):
        logger.warning("telemetry_export_failed")


def _safe_exporter_logs():
    for name in ("langfuse", "opentelemetry.exporter.otlp.proto.http.trace_exporter"):
        target = logging.getLogger(name)
        if not any(isinstance(h, _ExporterLogHandler) for h in target.handlers):
            target.handlers = [_ExporterLogHandler(level=logging.WARNING)]
            target.propagate = False


def get_trace_client() -> Any:
    """Initialize lazily; missing configuration must not block the API."""
    global _client
    if os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() != "true":
        return None
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        return None
    if _client is None:
        try:
            from langfuse import Langfuse

            _safe_exporter_logs()
            _client = Langfuse(
                environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development"),
                release=os.getenv("LANGFUSE_RELEASE", "local"),
                timeout=5,
            )
        except Exception:  # noqa: BLE001 - telemetry failures must not break the application
            logger.warning("telemetry_export_failed: initialize Langfuse tracing")
            return None
    return _client


class SafeSpan:
    def __init__(self, span: Any = None) -> None:
        self._span = span

    def update(self, **kwargs: Any) -> None:
        if self._span is not None:
            try:
                self._span.update(**kwargs)
            except Exception:  # noqa: BLE001 - telemetry failures must not break the application
                logger.warning("telemetry_export_failed: update Langfuse observation")


@contextmanager
def observation(
    name: str,
    *,
    input: dict[str, Any] | None = None,
    as_type: str = "span",
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[SafeSpan]:
    """Trace safe metadata only, without changing application error behavior."""
    client = get_trace_client()
    if client is None:
        yield SafeSpan()
        return
    try:
        options = {"as_type": as_type, "name": name, "input": input}
        if model is not None:
            options["model"] = model
        if metadata is not None:
            options["metadata"] = metadata
        manager = client.start_as_current_observation(**options)
        span = manager.__enter__()
    except Exception:  # noqa: BLE001 - telemetry failures must not break the application
        logger.warning("telemetry_export_failed: start Langfuse observation")
        yield SafeSpan()
        return
    try:
        yield SafeSpan(span)
    except BaseException as exc:
        # Do not export exception messages or stacks: provider errors can contain
        # policy text, headers, or credentials. Preserve the original exception.
        if isinstance(exc, GraphInterrupt):
            SafeSpan(span).update(output={"interrupted": True, "awaiting_user": True})
        else:
            SafeSpan(span).update(level="ERROR", status_message="Operation failed")
        try:
            manager.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 - telemetry failures must not break the application
            logger.warning("telemetry_export_failed: close Langfuse observation")
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 - telemetry failures must not break the application
            logger.warning("telemetry_export_failed: close Langfuse observation")


def flush_traces() -> None:
    """Bound telemetry drain latency; a stuck exporter never holds a worker indefinitely.

    One daemon per process prevents repeated timeouts from creating unbounded threads.
    A timeout can lose telemetry; emit a safe warning so external logs can alert on it.
    """
    global _flush_thread
    if _client is None:
        return

    def drain():
        try:
            _client.flush()
        except Exception:  # noqa: BLE001 - export failures must not affect requests
            logger.warning("telemetry_flush_failed")

    with _flush_lock:
        if _flush_thread is None or not _flush_thread.is_alive():
            _flush_thread = threading.Thread(target=drain, daemon=True)
            _flush_thread.start()
        thread = _flush_thread
    thread.join(timeout=5)
    if thread.is_alive():
        logger.warning("telemetry_flush_timeout")


def result_fingerprint(result: dict) -> str:
    """Bind a score to the exact stored projection without exporting its contents."""
    import json

    projection = {key: result.get(key) for key in ("content", "sources", "workflow")}
    return hashlib.sha256(
        json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@contextmanager
def trace_session(session_id: str) -> Iterator[None]:
    """Group start and resume traces under an opaque workflow run ID."""
    if get_trace_client() is None:
        yield
        return
    try:
        from langfuse import propagate_attributes

        manager = propagate_attributes(session_id=session_id)
        manager.__enter__()
    except Exception:  # noqa: BLE001 - telemetry failures must not break the application
        logger.warning("telemetry_export_failed: associate Langfuse session")
        yield
        return
    token = current_trace_session_id.set(session_id)
    try:
        yield
    except BaseException:
        try:
            manager.__exit__(*sys.exc_info())
        except Exception:  # noqa: BLE001 - telemetry failures must not break the application
            logger.warning("telemetry_export_failed: close Langfuse session")
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 - telemetry failures must not break the application
            logger.warning("telemetry_export_failed: close Langfuse session")

    finally:
        current_trace_session_id.reset(token)


@contextmanager
def worker_trace(name: str, session_id: str) -> Iterator[SafeSpan]:
    """One trace per invocation, grouped across resumes, flushed before the process exits."""
    try:
        with (
            trace_session(session_id),
            observation(name, input={"capture": "metadata_only"}) as span,
        ):
            yield span
    finally:
        flush_traces()
