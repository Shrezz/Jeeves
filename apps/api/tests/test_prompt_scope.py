import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.agents.prompt_scope import OUT_OF_SCOPE_MESSAGE, in_scope, include_in_history
from app.main import create_app
from app.services.bootstrap import demo_auth
from app.services.fixtures import FixtureStore, fixture_context
from app.services.workflow import WorkflowService
from tests.fakes import ScriptedModel

CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "evals/datasets/prompt_scope_cases.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["text"])
def test_shared_scope_examples(case):
    assert in_scope(case["text"], followup=case.get("followup", False)) is case["allowed"]


def test_blocked_messages_do_not_enter_later_model_history():
    assert not include_in_history("How's the weather?", None)
    assert not include_in_history("yes", OUT_OF_SCOPE_MESSAGE)
    assert include_in_history("yes", "Thanks for clarifying.")
    assert include_in_history("What is my deductible?", None)


@pytest.mark.parametrize(
    ("message", "query", "explicit_route"),
    [
        ("How's the weather?", None, None),
        ("Tell me a joke about insurance claims", None, "file_claim"),
        ("What is my deductible?", "weather today", None),
    ],
)
def test_out_of_scope_never_calls_model_or_web_search(message, query, explicit_route):
    class Search:
        async def search(self, query):
            raise AssertionError("Out-of-scope input must not invoke search")

    model = ScriptedModel()
    store = FixtureStore.seeded()
    service = WorkflowService(
        build_graph(memory_checkpointer()),
        fixture_context(store, generator=model, reviewer=model, web_search=Search()),
        artifacts=store,
        mode="fixture",
        model_mode="fixture",
    )
    with TestClient(create_app(service, demo_auth("test-token"))) as client:
        response = client.post(
            "/agent/runs",
            headers={"Authorization": "Bearer test-token"},
            json={
                "request_key": "scope-test",
                "policy_id": "demo-policy",
                "message": message,
                "explicit_route": explicit_route,
                "web_search_query": query,
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["error"] == OUT_OF_SCOPE_MESSAGE
    assert "scope_guard" in response.json()["stages"]
    assert "web_search" not in response.json()["stages"]
    assert not model.calls


def test_ui_projects_guard_message_without_a_route():
    from types import SimpleNamespace

    from app.services.ui_workflow import project

    result = project(
        SimpleNamespace(
            values={
                "phase": "answer_ready",
                "scope_decision": "out_of_scope",
                "chat_reply": {"content": OUT_OF_SCOPE_MESSAGE, "sources": []},
            },
            interrupts=[],
        ),
        {},
    )
    assert result["content"] == OUT_OF_SCOPE_MESSAGE
    assert result["sources"] == []
