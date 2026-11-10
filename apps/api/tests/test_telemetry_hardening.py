"""Failure isolation and privacy regressions at the telemetry boundary."""

import threading
from contextlib import contextmanager

import pytest

from app.observability import tracing


def test_production_never_enables_content_capture(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "production")
    monkeypatch.setenv("JEEVES_MODE", "demo")
    monkeypatch.setenv("LANGFUSE_CAPTURE_SYNTHETIC_CONTENT", "true")
    monkeypatch.setenv("JEEVES_SYNTHETIC_TRACE_CLAIM_IDS", "fictional")
    with tracing.synthetic_claim_capture("fictional"):
        assert not tracing.capture_synthetic_content()


def test_broken_span_update_and_close_preserve_business_exception(monkeypatch):
    class Span:
        def update(self, **kw):
            raise RuntimeError("export failure")

    class Manager:
        def __enter__(self):
            return Span()

        def __exit__(self, *args):
            raise RuntimeError("export failure")

    class Client:
        def start_as_current_observation(self, **kw):
            return Manager()

    monkeypatch.setattr(tracing, "get_trace_client", lambda: Client())
    with pytest.raises(ValueError, match="original failure"), tracing.observation("test") as span:
        span.update(output={"ok": True})
        raise ValueError("original failure")


def test_flush_failure_does_not_fail_request(monkeypatch, caplog):
    class Client:
        def flush(self):
            raise RuntimeError("private export response")

    monkeypatch.setattr(tracing, "_client", Client())
    tracing.flush_traces()
    assert "telemetry_flush_failed" in caplog.text
    assert "private export response" not in caplog.text


def test_worker_session_starts_before_root_observation_and_always_flushes(monkeypatch):
    events = []

    @contextmanager
    def session(_):
        events.append("session")
        yield

    @contextmanager
    def observation(*args, **kwargs):
        events.append("root")
        yield

    monkeypatch.setattr(tracing, "trace_session", session)
    monkeypatch.setattr(tracing, "observation", observation)
    monkeypatch.setattr(tracing, "flush_traces", lambda: events.append("flush"))
    with pytest.raises(ValueError), tracing.worker_trace("test", "run"):
        raise ValueError()
    assert events == ["session", "root", "flush"]


def test_projection_digest_binds_sources_content_and_revision():
    original = {"content": "A", "sources": [], "workflow": {"version": 1}}
    digest = tracing.result_fingerprint(original)
    assert digest == tracing.result_fingerprint(dict(reversed(list(original.items()))))
    for key, value in (("content", "B"), ("sources", [{"page": 2}]), ("workflow", {"version": 2})):
        assert digest != tracing.result_fingerprint({**original, key: value})


def test_stuck_exporter_has_a_bounded_drain_and_does_not_spawn_more_threads(monkeypatch, caplog):
    release = threading.Event()
    calls = []

    class Client:
        def flush(self):
            calls.append(1)
            release.wait(15)

    monkeypatch.setattr(tracing, "_client", Client())
    try:
        tracing.flush_traces()
        assert "telemetry_flush_timeout" in caplog.text
        thread = tracing._flush_thread
        assert thread.is_alive() and calls == [1]
    finally:
        release.set()
        tracing._flush_thread.join(1)


def test_exporter_logs_are_redacted_but_operationally_visible(caplog):
    import logging

    handler = tracing._ExporterLogHandler()
    handler.emit(
        logging.LogRecord("langfuse", logging.ERROR, "", 0, "private provider body", (), None)
    )
    assert "telemetry_export_failed" in caplog.text
    assert "private provider body" not in caplog.text
