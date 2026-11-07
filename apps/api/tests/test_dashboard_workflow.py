import asyncio

import pytest

from app.schemas.agents import AgentRequest
from app.services import dashboard_workflow as dashboard
from app.services.chat_guidance import guidance
from tests.fakes import ScriptedModel

HIT = {
    "chunkId": "policy-a:1",
    "page": 4,
    "section": "Declarations",
    "excerpt": "The deductible is $1,000.",
}


def run(question, model, reviewer, policy="policy-a", history=None):
    return asyncio.run(
        dashboard.build_dashboard_graph().ainvoke(
            {"request": AgentRequest(message=question), "recent_turns": history or []},
            context=dashboard.ChatContext("user_a", policy, model, reviewer),
        )
    )


def test_router_then_owned_retrieval_then_review_for_follow_up(monkeypatch):
    calls = []

    async def search(owner, policy, query):
        calls.append((owner, policy, query))
        return [HIT]

    monkeypatch.setattr(dashboard, "search_passages", search)
    model = ScriptedModel(
        [
            {"route": "answer_claim"},
            {
                "kind": "policy",
                "answer": "Your deductible is $1,000.",
                "citations": [{"source": 1, "quote": "deductible is $1,000"}],
            },
        ]
    )
    review = ScriptedModel([{"approved": True, "feedback": ""}])
    history = [{"content": "Wind broke my window.", "reply": "What was the cost?"}]
    state = run("It was $150. What is my deductible?", model, review, history=history)
    assert state["route"].route == "answer_claim"
    assert calls == [
        ("user_a", "policy-a", "It was $150. What is my deductible?\nWind broke my window.")
    ]
    assert model.calls[0]["payload"]["recent_turns"] == history
    assert model.calls[1]["payload"]["sources"] == review.calls[0]["payload"]["sources"]
    assert state["chat_reply"]["sources"] == [{**HIT, "excerpt": "deductible is $1,000"}]


@pytest.mark.parametrize(
    ("question", "decision"),
    [
        ("Let’s file the claim", {"route": "file_claim"}),
        ("Mark my claim resolved", {"route": "save_claim_status"}),
        ("Can you help?", {"route": None, "clarification": "What would you like to do?"}),
    ],
)
def test_action_routes_require_user_handoff_without_retrieval(question, decision, monkeypatch):
    async def unexpected(*args):
        pytest.fail("No policy search or claim writes before choosing an action target")

    monkeypatch.setattr(dashboard, "search_passages", unexpected)
    result = run(question, ScriptedModel([decision]), ScriptedModel())
    assert result["route"].route == decision["route"]
    assert result["chat_reply"]["content"] and not result["chat_reply"]["sources"]


def test_no_chunks_abstains_without_asking_model_to_guess(monkeypatch):
    async def empty(*args):
        return []

    monkeypatch.setattr(dashboard, "search_passages", empty)
    result = run("Is it covered?", ScriptedModel([{"route": "answer_claim"}]), ScriptedModel())
    assert "couldn’t find wording" in result["chat_reply"]["content"]
    assert result["chat_reply"]["sources"] == []


def test_long_answer_is_revised_instead_of_truncating_away_a_qualifier():
    model = ScriptedModel(
        [
            {"kind": "other", "answer": "One. Two. Three. Four. Five. Six.", "citations": []},
            {
                "kind": "other",
                "answer": "It depends on the cause. What broke the window?",
                "citations": [],
            },
        ]
    )
    result = asyncio.run(
        guidance({}, [], model, ScriptedModel([{"approved": True, "feedback": ""}]))
    )
    assert "five sentences" in model.calls[1]["payload"]["feedback"]
    assert result["content"].endswith("What broke the window?")
