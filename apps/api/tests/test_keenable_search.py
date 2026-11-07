import asyncio

import httpx
from fastapi.testclient import TestClient

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.main import create_app
from app.services.bootstrap import demo_auth
from app.services.fixtures import FixtureStore, fixture_context
from app.services.keenable import KeenableSearch
from app.services.workflow import WorkflowService


def test_keenable_search_sends_only_explicit_query():
    def handler(request):
        assert request.url.path == "/v1/search"
        assert request.headers["X-API-Key"] == "test-key"
        assert b"public insurance guidance" in request.content
        assert b"private-claim" not in request.content
        return httpx.Response(200, json={"results": [
            {"title": "Guidance", "url": "https://example.org/guidance", "snippet": "Info"}
        ]})

    search = KeenableSearch("test-key", transport=httpx.MockTransport(handler))
    assert asyncio.run(search.search("public insurance guidance")) == [
        {"title": "Guidance", "url": "https://example.org/guidance", "snippet": "Info"}
    ]


def test_agent_opt_in_search_is_separate_from_policy_citations():
    class Search:
        async def search(self, query):
            assert query == "public guidance"
            return [{"title": "Public", "url": "https://example.org", "snippet": "Context"}]

    store = FixtureStore.seeded()
    service = WorkflowService(build_graph(memory_checkpointer()), fixture_context(store, web_search=Search()),
                              artifacts=store, mode="fixture", model_mode="fixture")
    with TestClient(create_app(service, demo_auth("test-token"))) as client:
        response = client.post("/agent/runs", headers={"Authorization": "Bearer test-token"}, json={
            "request_key": "search-case", "policy_id": "demo-policy",
            "message": "Is sudden accidental broken-window damage covered?",
            "web_search_query": "public guidance",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["web_search"]["status"] == "ok"
    assert body["web_search"]["results"][0]["url"] == "https://example.org"
    assert all(citation["chunk_id"] != "https://example.org" for citation in body["citations"])


def test_agent_search_failure_does_not_break_claim():
    class Search:
        async def search(self, query):
            raise httpx.ConnectError("provider unavailable")

    store = FixtureStore.seeded()
    service = WorkflowService(build_graph(memory_checkpointer()), fixture_context(store, web_search=Search()),
                              artifacts=store, mode="fixture", model_mode="fixture")
    with TestClient(create_app(service, demo_auth("test-token"))) as client:
        response = client.post("/agent/runs", headers={"Authorization": "Bearer test-token"}, json={
            "request_key": "failed-search", "policy_id": "demo-policy",
            "message": "Is sudden accidental broken-window damage covered?",
            "web_search_query": "public guidance",
        })
    assert response.status_code == 200
    assert response.json()["web_search"] == {"status": "unavailable", "results": []}
    assert response.json()["status"] != "failed"
