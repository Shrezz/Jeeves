"""The node wrapper preserves behavior and records only allowed metadata."""
import asyncio
import inspect

import pytest

from app.observability import agent_nodes, tracing


def test_sync_node_signature_and_safe_output(monkeypatch):
    events = []
    class Span:
        def update(self, **kwargs):
            events.append(kwargs)
    class Client:
        def start_as_current_observation(self, **kwargs):
            from contextlib import nullcontext
            return nullcontext(Span())
    monkeypatch.setattr(tracing, "get_trace_client", lambda: Client())
    def node(state):
        return {"phase": "review_pending", "revision_count": 1, "secret": state["message"]}
    wrapped = agent_nodes.instrument_node("file_claim", node)
    result = wrapped({"message": "private incident"})
    assert inspect.signature(wrapped) == inspect.signature(node)
    assert result["secret"] == "private incident"
    assert events == [{"output": {"phase": "review_pending", "revision_count": 1}}]


def test_async_node_propagates_exceptions():
    async def node(state, runtime):
        raise ValueError("workflow failure")
    wrapped = agent_nodes.instrument_node("reviewer", node)
    assert inspect.signature(wrapped) == inspect.signature(node)
    with pytest.raises(ValueError, match="workflow failure"):
        asyncio.run(wrapped({}, None))


def test_unknown_node_is_rejected():
    with pytest.raises(ValueError):
        agent_nodes.instrument_node("arbitrary-sensitive-name", lambda state: state)
