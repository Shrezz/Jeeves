"""Verify workflow tracing captures useful metadata without sensitive content."""

import asyncio
from contextlib import contextmanager, nullcontext

import httpx
import pytest
from fastapi.testclient import TestClient
from langgraph.errors import GraphInterrupt

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.main import create_app
from app.observability import tracing
from app.schemas.agents import RouteDecision
from app.services import workflow
from app.services.bootstrap import demo_auth
from app.services.fixtures import FixtureStore, fixture_context
from app.services.nebius import NebiusModel
from app.services.workflow import WorkflowService


class FakeClient:
    def __init__(self):
        self.events = []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        event = {"start": kwargs, "updates": []}
        self.events.append(event)

        class Span:
            def update(self, **values):
                event["updates"].append(values)

        yield Span()

    def flush(self):
        pass


def test_expected_graph_interrupt_is_not_recorded_as_error(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)
    with pytest.raises(GraphInterrupt), tracing.observation("agent-human_review"):
        raise GraphInterrupt()
    assert fake.events[0]["updates"] == [{"output": {"interrupted": True, "awaiting_user": True}}]


def test_agent_graph_traces_nodes_and_human_approval_without_raw_content(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)
    monkeypatch.setattr(workflow, "trace_session", lambda _: nullcontext())
    store = FixtureStore.seeded()
    service = WorkflowService(
        build_graph(memory_checkpointer()),
        fixture_context(store),
        artifacts=store,
        mode="fixture",
        model_mode="fixture",
    )
    with TestClient(create_app(service, demo_auth("private-token"))) as client:
        headers = {"Authorization": "Bearer private-token"}
        response = client.post(
            "/agent/runs",
            headers=headers,
            json={
                "request_key": "request-1",
                "policy_id": "demo-policy",
                "claim_id": "demo-window",
                "message": "I paid $150. Prepare the packet. private incident text",
            },
        )
        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "awaiting_review"
        pending = run["pending"]
        response = client.post(
            f"/agent/runs/{run['run_id']}/responses",
            headers=headers,
            json={
                "request_key": "request-2",
                "interrupt_id": pending["interrupt_id"],
                "decision": {"artifact_version": pending["artifact_version"], "action": "approve"},
            },
        )
        assert response.json()["status"] == "completed"
    names = [item["start"]["name"] for item in fake.events]
    assert {
        "agent-workflow",
        "agent-router",
        "agent-file_claim",
        "agent-reviewer",
        "agent-human_review",
        "agent-commit_action",
        "retrieve-evidence",
        "model-generation",
    }.issubset(names)
    captured = repr(fake.events)
    assert "private incident text" not in captured
    assert "private-token" not in captured
    assert "demo-policy" not in captured
    assert "human_action" in captured


def test_provider_usage_is_recorded_without_prompt_or_response(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)

    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"route":"answer_claim","clarification":null}'},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    async def invoke():
        async with httpx.AsyncClient(
            base_url="https://example.test/", transport=httpx.MockTransport(handler)
        ) as client:
            return await NebiusModel(client, "synthetic-model").generate(
                prompt="private prompt",
                payload={"message": "private incident"},
                output_type=RouteDecision,
            )

    assert asyncio.run(invoke()).route == "answer_claim"
    generation = fake.events[0]
    assert generation["start"]["as_type"] == "generation"
    assert next(u["usage_details"] for u in generation["updates"] if "usage_details" in u) == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    assert "private prompt" not in repr(fake.events)
    assert "private incident" not in repr(fake.events)


def test_exception_message_is_not_sent_to_tracing(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)
    try:
        with tracing.observation("operation"):
            raise ValueError("private provider response")
    except ValueError:
        pass
    assert "private provider response" not in repr(fake.events)
    assert fake.events[0]["updates"] == [{"level": "ERROR", "status_message": "Operation failed"}]


def test_detailed_capture_is_demo_only_and_redacts_common_secrets(monkeypatch):
    monkeypatch.setenv("LANGFUSE_CAPTURE_SYNTHETIC_CONTENT", "true")
    monkeypatch.setenv("JEEVES_MODE", "production")
    assert not tracing.capture_synthetic_content()
    monkeypatch.setenv("JEEVES_MODE", "demo")
    assert tracing.capture_synthetic_content()
    sanitized = tracing.sanitize_content(
        {
            "password": "secret-value",
            "nested": {"authorization": "Bearer access-token", "message": "Bearer hidden-token"},
        }
    )
    assert sanitized["password"] == "[redacted]"
    assert sanitized["nested"]["authorization"] == "[redacted]"
    assert "hidden-token" not in repr(sanitized)


def test_ui_content_capture_is_limited_to_explicit_synthetic_claim(monkeypatch):
    monkeypatch.delenv("JEEVES_MODE", raising=False)
    monkeypatch.setenv("LANGFUSE_CAPTURE_SYNTHETIC_CONTENT", "true")
    monkeypatch.setenv("JEEVES_SYNTHETIC_TRACE_CLAIM_IDS", "synthetic-claim")
    assert not tracing.capture_synthetic_content()
    with tracing.synthetic_claim_capture("another-claim"):
        assert not tracing.capture_synthetic_content()
    with tracing.synthetic_claim_capture("synthetic-claim"):
        assert tracing.capture_synthetic_content()
        assert tracing.sanitize_content({"user_id": "private"})["user_id"] == "[redacted]"
    assert not tracing.capture_synthetic_content()


def test_model_content_capture_is_redacted_when_explicitly_enabled(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)
    monkeypatch.setenv("JEEVES_MODE", "demo")
    monkeypatch.setenv("LANGFUSE_CAPTURE_SYNTHETIC_CONTENT", "true")

    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"route":"answer_claim","clarification":null}'},
                    }
                ]
            },
        )

    async def invoke():
        async with httpx.AsyncClient(
            base_url="https://example.test/", transport=httpx.MockTransport(handler)
        ) as client:
            return await NebiusModel(client, "synthetic-model").generate(
                prompt="synthetic prompt",
                payload={"password": "hidden-password", "message": "Bearer hidden-token"},
                output_type=RouteDecision,
            )

    asyncio.run(invoke())
    captured = repr(fake.events)
    assert "synthetic prompt" in captured
    assert "hidden-password" not in captured
    assert "hidden-token" not in captured
    assert "answer_claim" in captured


def test_real_sdk_exports_parented_spans_and_session_without_network(monkeypatch):
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-lf-test-observability",
        secret_key="sk-lf-test-observability",
        base_url="https://example.test",
        tracer_provider=TracerProvider(),
        span_exporter=exporter,
    )
    monkeypatch.setattr(tracing, "get_trace_client", lambda: client)
    monkeypatch.delenv("LANGFUSE_CAPTURE_SYNTHETIC_CONTENT", raising=False)
    store = FixtureStore.seeded()
    service = WorkflowService(
        build_graph(memory_checkpointer()),
        fixture_context(store),
        artifacts=store,
        mode="fixture",
        model_mode="fixture",
    )
    try:
        with TestClient(create_app(service, demo_auth("test-token"))) as api:
            headers = {"Authorization": "Bearer test-token"}
            run = api.post(
                "/agent/runs",
                headers=headers,
                json={
                    "request_key": "start",
                    "policy_id": "demo-policy",
                    "claim_id": "demo-window",
                    "message": "I paid $150. Prepare the packet. private detail",
                },
            ).json()
            pending = run["pending"]
            result = api.post(
                f"/agent/runs/{run['run_id']}/responses",
                headers=headers,
                json={
                    "request_key": "approve",
                    "interrupt_id": pending["interrupt_id"],
                    "decision": {
                        "artifact_version": pending["artifact_version"],
                        "action": "approve",
                    },
                },
            )
            assert result.json()["status"] == "completed"
        client.flush()
        spans = exporter.get_finished_spans()
        roots = [span for span in spans if span.name == "agent-workflow"]
        assert len(roots) == 2
        assert all(span.attributes.get("session.id") == run["run_id"] for span in roots)
        assert len({span.context.trace_id for span in roots}) == 2
        assert any(span.name == "agent-reviewer" and span.parent for span in spans)
        assert any(span.name == "agent-commit_action" and span.parent for span in spans)
        assert "private detail" not in repr([dict(span.attributes) for span in spans])
        assert "test-token" not in repr([dict(span.attributes) for span in spans])
    finally:
        client.shutdown()


def test_human_interrupt_is_a_normal_pause_and_excludes_its_payload(monkeypatch):
    from langgraph.errors import GraphInterrupt
    from langgraph.types import Interrupt
    import pytest

    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)
    with pytest.raises(GraphInterrupt):
        with tracing.observation("agent-human_review"):
            raise GraphInterrupt((Interrupt(value={"draft": "private packet content"}),))
    assert fake.events[0]["updates"] == [{"output": {"interrupted": True, "awaiting_user": True}}]
    assert "private packet content" not in repr(fake.events)
