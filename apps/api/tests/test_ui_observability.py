"""Integrated worker tracing exports metadata without request content."""

import asyncio
from contextlib import contextmanager

import httpx

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
