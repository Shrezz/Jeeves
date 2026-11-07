"""Integrated worker tracing exports metadata without request content."""

import asyncio
import io
import json
from contextlib import contextmanager

import httpx
import pytest

from app.schemas.agents import RouteDecision
from app.services.chat_worker import OllamaModel
from app.services.ui_claim_store import WebClaimStore


def test_ollama_generation_traces_only_safe_metadata(monkeypatch):
    records = []

    class Span:
        def update(self, **kw):
            records.append(kw)

    @contextmanager
    def capture(name, **kw):
        records.append({"name": name, **kw})
        yield Span()

    monkeypatch.setattr("app.services.chat_worker.observation", capture)

    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "done": True,
                    "message": {"content": '{"route":"answer_claim","clarification":null}'},
                },
            )
        )
        async with httpx.AsyncClient(base_url="http://localhost/", transport=transport) as client:
            return await OllamaModel(client, "test-model").generate(
                prompt="private prompt",
                payload={"message": "private claim"},
                output_type=RouteDecision,
            )

    assert asyncio.run(run()).route == "answer_claim"
    assert records == [
        {
            "name": "model-generation",
            "as_type": "generation",
            "model": "test-model",
            "metadata": {"provider": "ollama", "schema": "RouteDecision"},
        },
        {"input": {"capture": "metadata_only", "schema": "RouteDecision"}},
        {"output": {"validated": True}},
    ]


def test_policy_retrieval_traces_only_result_count(monkeypatch):
    records = []

    class Span:
        def update(self, **kw):
            records.append(kw)

    @contextmanager
    def capture(name, **kw):
        records.append({"name": name, **kw})
        yield Span()

    async def search(self, **kwargs):
        return ["private passage"]

    monkeypatch.setattr("app.observability.tracing.observation", capture)
    monkeypatch.setattr(WebClaimStore, "_retrieve_evidence", search)
    store = object.__new__(WebClaimStore)
    result = asyncio.run(
        store.retrieve_evidence(
            user_id="private owner",
            policy_id="private policy",
            question="private question",
            limit=3,
        )
    )
    assert result == ["private passage"]
    assert records == [
        {"name": "ui-policy-retrieval", "input": {"limit": 3}},
        {"output": {"passage_count": 1}},
    ]


def test_ollama_usage_sums_provider_counts_across_retries(monkeypatch):
    updates = []

    class Span:
        def update(self, **kw):
            updates.append(kw)

    @contextmanager
    def capture(name, **kw):
        yield Span()

    monkeypatch.setattr("app.services.chat_worker.observation", capture)
    responses = iter(
        [
            {"done": True, "prompt_eval_count": 10, "eval_count": 4, "message": {"content": "{}"}},
            {
                "done": True,
                "prompt_eval_count": 20,
                "eval_count": 5,
                "message": {"content": '{"route":"answer_claim","clarification":null}'},
            },
        ]
    )

    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=next(responses)))
        async with httpx.AsyncClient(base_url="http://localhost/", transport=transport) as client:
            return await OllamaModel(client, "test-model").generate(
                prompt="synthetic", payload={}, output_type=RouteDecision
            )

    assert asyncio.run(run()).route == "answer_claim"
    assert {
        "usage_details": {"prompt_tokens": 30, "completion_tokens": 9, "total_tokens": 39}
    } in updates


def test_unsupported_ollama_structured_output_is_recorded_without_response_body(monkeypatch):
    updates = []

    class Span:
        def update(self, **kwargs):
            updates.append(kwargs)

    @contextmanager
    def capture(name, **kwargs):
        yield Span()

    monkeypatch.setattr("app.services.chat_worker.observation", capture)

    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(501, json={"error": "private content"})
        )
        async with httpx.AsyncClient(base_url="http://localhost/", transport=transport) as client:
            await OllamaModel(client, "test-model").generate(
                prompt="synthetic", payload={}, output_type=RouteDecision
            )

    with pytest.raises(RuntimeError, match="structured output is unavailable"):
        asyncio.run(run())
    assert updates == [
        {"input": {"capture": "metadata_only", "schema": "RouteDecision"}},
        {
            "metadata": {
                "provider": "ollama",
                "schema": "RouteDecision",
                "failure_type": "structured_output_unavailable",
            }
        },
    ]


def test_ui_worker_flushes_trace_when_database_setup_fails(monkeypatch):
    from app.services import ui_workflow

    events = []

    @contextmanager
    def session(session_id):
        events.append(("session", session_id))
        yield

    @contextmanager
    def observation(name, **kwargs):
        events.append(("observation", name))
        yield None

    def fail(*args, **kwargs):
        raise RuntimeError("database not reachable")

    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/synthetic")
    monkeypatch.setattr(ui_workflow.sys, "argv", ["worker"])
    monkeypatch.setattr(
        ui_workflow.sys,
        "stdin",
        io.StringIO(json.dumps({"runId": "synthetic-run", "claimId": "synthetic-claim"})),
    )
    monkeypatch.setattr(ui_workflow, "trace_session", session)
    monkeypatch.setattr(ui_workflow, "observation", observation)
    monkeypatch.setattr(ui_workflow, "flush_traces", lambda: events.append(("flush",)))
    monkeypatch.setattr(ui_workflow.AsyncPostgresSaver, "from_conn_string", fail)
    with pytest.raises(RuntimeError, match="not reachable"):
        asyncio.run(ui_workflow.main())
    assert events == [
        ("session", "synthetic-run"),
        ("observation", "ui-claim-workflow"),
        ("flush",),
    ]
