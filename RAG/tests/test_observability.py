import pytest
from policy_rag import observability


def test_disabled_tracing_is_noop(monkeypatch):
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    with observability.span("retrieval") as current:
        assert current is None


def test_error_status_does_not_export_exception_details(monkeypatch):
    updates = []

    class Current:
        def update(self, **kw):
            updates.append(kw)

    class Manager:
        def __enter__(self):
            return Current()

        def __exit__(self, *args):
            return False

    class Client:
        def start_as_current_observation(self, **kw):
            return Manager()

    monkeypatch.setattr(observability, "client", lambda: Client())
    with pytest.raises(ValueError), observability.span("retrieval"):
        raise ValueError("private policy contents")
    assert updates == [{"level": "ERROR", "status_message": "Policy operation failed"}]


def test_safe_span_preserves_results_and_reports_telemetry_failure(monkeypatch):
    class Broken:
        def update(self, **kwargs):
            raise RuntimeError("private body")

    monkeypatch.setattr(observability, "_failed", False)
    observability.SafeSpan(Broken()).update(output={"ok": True})
    assert observability.export_failed()


def test_standalone_pipeline_exports_metadata_with_local_files_disabled(monkeypatch):
    from contextlib import contextmanager

    from policy_rag import tracing

    records = []

    @contextmanager
    def capture(name, **kwargs):
        records.append((name, kwargs))
        yield None

    monkeypatch.setattr(tracing, "span", capture)
    monkeypatch.setattr(tracing, "flush", lambda: records.append("flushed"))
    monkeypatch.setattr(tracing.config, "TRACE_ENABLED", False)

    @tracing.traced
    def calculate(value):
        return value + 1

    with tracing.request_trace("query", question="private question"):
        assert calculate(2) == 3
    assert records[0][0] == "standalone-rag-query"
    assert "calculate" in records[1][0]
    assert records[-1] == "flushed"
    assert "private" not in repr(records)


def test_production_suppresses_detailed_local_trace_files(monkeypatch, tmp_path):
    from policy_rag import tracing

    monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "production")
    monkeypatch.setattr(tracing.config, "TRACE_ENABLED", True)
    monkeypatch.setattr(tracing.config, "LOG_DIR", tmp_path)
    with tracing._file_trace("query", question="private question") as record:
        assert record is None
    assert not list(tmp_path.rglob("*.json*"))


def test_standalone_generation_exports_usage_but_not_messages(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from policy_rag import qa

    updates = []

    @contextmanager
    def capture(name, **kwargs):
        updates.append({"name": name, **kwargs})

        class Span:
            def update(self, **values):
                updates.append(values)

        yield Span()

    parsed = object()

    class Model:
        def invoke(self, messages):
            return {
                "raw": SimpleNamespace(
                    usage_metadata={"input_tokens": 5, "output_tokens": 2},
                    response_metadata={},
                ),
                "parsed": parsed,
            }

    monkeypatch.setattr(qa, "span", capture)
    monkeypatch.setattr(qa, "_structured_llm", lambda: Model())
    assert qa.call_llm(["private prompt"]) is parsed
    assert {"usage_details": {"input": 5, "output": 2}} in updates
    assert "private" not in repr(updates)


def test_real_sdk_preserves_standalone_hierarchy_and_privacy(monkeypatch):
    import json

    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from policy_rag import tracing

    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-lf-rag-test",
        secret_key="sk-lf-rag-test",
        base_url="https://example.test",
        tracer_provider=TracerProvider(),
        span_exporter=exporter,
        environment="test",
        release="test-build",
    )
    monkeypatch.setattr(observability, "client", lambda: client)
    monkeypatch.setattr(tracing.config, "TRACE_ENABLED", False)

    @tracing.traced
    def operation():
        with observability.span("query-embedding", model="test-embedding"):
            return 42

    try:
        with tracing.request_trace("query", question="private wording"):
            assert operation() == 42
        client.flush()
        records = exporter.get_finished_spans()
        root = next(s for s in records if s.name == "standalone-rag-query")
        assert all(s.context.trace_id == root.context.trace_id for s in records)
        assert all(s.parent is not None for s in records if s is not root)
        assert any(
            s.attributes.get("langfuse.observation.type") == "embedding"
            for s in records
        )
        assert "private wording" not in json.dumps(
            [dict(s.attributes) for s in records]
        )
    finally:
        client.shutdown()


def test_worker_restores_session_on_all_nested_remote_parent_spans(monkeypatch, tmp_path):
    import io
    import json

    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from policy_rag import local_worker

    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-lf-worker-session-test", secret_key="sk-lf-worker-session-test",
        base_url="https://example.test", tracer_provider=TracerProvider(),
        span_exporter=exporter, environment="test",
    )
    monkeypatch.setattr(observability, "client", lambda: client)
    monkeypatch.setenv("LOCAL_RAG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JEEVES_TRACE_SESSION_ID", "opaque-worker-session")
    trace_id, parent_id = "1" * 32, "2" * 16
    monkeypatch.setenv("TRACEPARENT", f"00-{trace_id}-{parent_id}-01")
    monkeypatch.setattr(local_worker.sys, "stdin", io.StringIO(json.dumps({
        "owner": "private-owner", "policy": "33333333-3333-4333-8333-333333333333",
    })))
    def perform(*args):
        with observability.span("local-policy-search"):
            with observability.span("query-embedding"):
                pass
            with observability.span("vector-search"):
                pass
        return {"passages": []}
    monkeypatch.setattr(local_worker, "perform", perform)
    try:
        local_worker.main()
        records = exporter.get_finished_spans()
        assert len(records) == 3
        assert all(s.context.trace_id == int(trace_id, 16) for s in records)
        root = next(s for s in records if s.name == "local-policy-search")
        assert root.parent.span_id == int(parent_id, 16)
        assert all(s.parent.span_id == root.context.span_id for s in records if s is not root)
        assert all(s.attributes.get("session.id") == "opaque-worker-session" for s in records)
        assert "private-owner" not in json.dumps([dict(s.attributes) for s in records])
    finally:
        client.shutdown()
