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


@pytest.mark.parametrize("async_node", [False, True])
@pytest.mark.parametrize("phase", ["revision_required", "blocked", "needs_information", "human_review"])
def test_review_rejections_warn_without_leaking_feedback(monkeypatch, async_node, phase):
    from contextlib import nullcontext

    events = []

    class Span:
        def update(self, **kwargs):
            events.append(kwargs)

    class Client:
        def start_as_current_observation(self, **kwargs):
            return nullcontext(Span())

    monkeypatch.setattr(tracing, "get_trace_client", lambda: Client())
    value = {"phase": phase, "private_feedback": "private incident"}

    def sync(state):
        return value

    async def asynchronous(state):
        return value

    wrapped = agent_nodes.instrument_node("reviewer", asynchronous if async_node else sync)
    actual = asyncio.run(wrapped({})) if async_node else wrapped({})
    assert actual is value
    assert "private incident" not in repr(events)
    assert events[0]["output"] == {"phase": phase}
    assert events[0].get("level") == (
        "WARNING" if phase in {"revision_required", "blocked"} else None
    )
