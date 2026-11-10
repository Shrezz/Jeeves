import asyncio
import json

import pytest

from app.observability import tracing
from app.services import local_policy_search


def test_session_context_is_nested_and_restored_after_failure(monkeypatch):
    monkeypatch.setattr(tracing, "get_trace_client", lambda: object())
    assert tracing.current_trace_session_id.get() is None
    with tracing.trace_session("outer-opaque-session"):
        assert tracing.current_trace_session_id.get() == "outer-opaque-session"
        with pytest.raises(ValueError), tracing.trace_session("inner-opaque-session"):
            assert tracing.current_trace_session_id.get() == "inner-opaque-session"
            raise ValueError("application failure")
        assert tracing.current_trace_session_id.get() == "outer-opaque-session"
    assert tracing.current_trace_session_id.get() is None


@pytest.mark.parametrize("enabled", [True, False])
def test_search_passes_only_explicit_session_and_trace_context(monkeypatch, enabled):
    from opentelemetry import propagate

    captured = {}
    class Process:
        returncode = 0
        async def communicate(self, payload):
            assert json.loads(payload)["question"] == "private-query"
            return b'{"passages": []}', b""
    async def spawn(*args, **kwargs):
        captured.update(kwargs["env"])
        return Process()
    monkeypatch.setenv("LOCAL_RAG_ROOT", "/synthetic/rag")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", str(enabled).lower())
    monkeypatch.setenv("JEEVES_TRACE_SESSION_ID", "stale-session-must-not-leak")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(propagate, "inject", lambda carrier: carrier.update({
        "traceparent": "safe-trace-context", "baggage": "private-unrelated-baggage"
    }))
    token = tracing.current_trace_session_id.set("opaque-session")
    try:
        assert asyncio.run(local_policy_search._search_passages(
            "private-owner", "private-policy", "private-query"
        )) == []
    finally:
        tracing.current_trace_session_id.reset(token)
    assert captured.get("JEEVES_TRACE_SESSION_ID") == ("opaque-session" if enabled else None)
    assert captured["TRACEPARENT"] == "safe-trace-context"
    assert "BAGGAGE" not in captured
    assert "private" not in repr(captured)
