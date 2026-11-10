"""Metadata-only tracing for the local policy worker."""

import logging
import os
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)
_client = None
_flush_lock = threading.Lock()
_flush_thread = None
_failed = False


class _ExporterLogHandler(logging.Handler):
    def emit(self, record):
        report_failure()


def report_failure():
    global _failed
    _failed = True
    logger.warning("telemetry_export_failed")


def export_failed():
    return _failed


class SafeSpan:
    def __init__(self, current):
        self.current = current

    def update(self, **kwargs):
        try:
            self.current.update(**kwargs)
        except Exception:  # noqa: BLE001 - tracing must preserve application behavior
            report_failure()


def client():
    global _client
    if (
        os.getenv("LANGFUSE_TRACING_ENABLED", "").lower() != "true"
        or not os.getenv("LANGFUSE_PUBLIC_KEY")
        or not os.getenv("LANGFUSE_SECRET_KEY")
    ):
        return None
    try:
        from langfuse import Langfuse

        if _client is None:
            for name in (
                "langfuse",
                "opentelemetry.exporter.otlp.proto.http.trace_exporter",
            ):
                target = logging.getLogger(name)
                target.handlers = [_ExporterLogHandler(level=logging.WARNING)]
                target.propagate = False
            _client = Langfuse(
                environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development"),
                release=os.getenv("LANGFUSE_RELEASE", "local"),
                timeout=5,
            )
        return _client
    except Exception:  # noqa: BLE001 - telemetry must not stop policy access
        report_failure()
        return None


@contextmanager
def span(name, *, as_type=None, **metadata):
    lf = client()
    if lf is None:
        yield None
        return
    try:
        manager = lf.start_as_current_observation(
            as_type=as_type
            or (
                "embedding"
                if "embedding" in name
                else "retriever"
                if name == "vector-search"
                else "span"
            ),
            model=metadata.get("model"),
            name=name,
            input={"operation": name},
            metadata=metadata,
        )
        current = manager.__enter__()
    except Exception:  # noqa: BLE001 - tracing must not affect policy processing
        report_failure()
        yield None
        return
    try:
        yield SafeSpan(current)
        try:
            current.update(output={"status": "completed"})
        except Exception:  # noqa: BLE001 - tracing must not affect policy processing
            report_failure()
    except BaseException:
        try:
            current.update(level="ERROR", status_message="Policy operation failed")
        except Exception:  # noqa: BLE001 - tracing must not mask policy failures
            report_failure()
        raise
    finally:
        try:
            manager.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 - tracing must not affect policy processing
            report_failure()


def flush():
    global _flush_thread
    lf = client()
    if lf is None:
        return

    def drain():
        try:
            lf.flush()
        except Exception:  # noqa: BLE001 - telemetry must not fail policy access
            report_failure()
            logger.warning("telemetry_flush_failed")

    with _flush_lock:
        if _flush_thread is None or not _flush_thread.is_alive():
            _flush_thread = threading.Thread(target=drain, daemon=True)
            _flush_thread.start()
        thread = _flush_thread
    thread.join(timeout=5)
    if thread.is_alive():
        report_failure()
        logger.warning("telemetry_flush_timeout")


@contextmanager
def trace_session(session_id):
    """Restore only the opaque parent session, never arbitrary cross-process baggage."""
    if not session_id or client() is None:
        yield
        return
    try:
        from langfuse import propagate_attributes

        manager = propagate_attributes(session_id=session_id)
        manager.__enter__()
    except Exception:  # noqa: BLE001 - optional telemetry must preserve policy access
        report_failure()
        yield
        return
    try:
        yield
    finally:
        try:
            manager.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 - telemetry must not mask application errors
            report_failure()
