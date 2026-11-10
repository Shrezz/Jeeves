"""Pre-claim chat starts at the shared router. This graph has no claim write tools."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agents.context import StructuredModel
from app.agents.graph import selected_agent
from app.agents.router import router
from app.agents.state import AgentState
from app.observability.agent_nodes import instrument_node
from app.observability.tracing import worker_trace
from app.schemas.agents import AgentRequest
from app.services.chat_guidance import guidance
from app.services.chat_worker import chat_models
from app.services.local_policy_search import search_passages
from app.services.nebius import JsonSchemaModel


@dataclass(frozen=True)
class ChatContext:
    owner: str
    policy_id: str | None
    generator: StructuredModel
    reviewer: StructuredModel


async def answer(state: AgentState, runtime: Runtime[ChatContext]):
    ctx = runtime.context
    question, history = state["request"].message, state["recent_turns"]
    passages = []
    if ctx.policy_id:
        prior = "\n".join(turn["content"][:500] for turn in history[-3:])
        passages = await search_passages(ctx.owner, ctx.policy_id, question[:1200] + "\n" + prior)
        if not passages:
            return {
                "chat_reply": {
                    "content": "I couldn’t find wording for that question in the selected policy. Which coverage or incident detail would you like to check?",
                    "sources": [],
                }
            }
    reply = await guidance(
        {
            "question": question,
            "recentNotes": history,
            "policyAccess": "Selected indexed policy"
            if ctx.policy_id
            else "No policy selected. Explain general concepts; for personal coverage ask the user to choose or upload their policy.",
            "scope": "Read-only dashboard chat before any claim. Answer briefly; do not imply any claim exists.",
        },
        passages,
        ctx.generator,
        ctx.reviewer,
    )
    return {"chat_reply": reply}


def handoff(state: AgentState):
    route = selected_agent(state)
    content = {
        "file_claim": "I can prepare a packet from what you’ve shared. Choose a claim or start a new draft below to review it before filing.",
        "save_claim_status": "Choose the claim you want to update. You can check the status and note before saving them.",
        "clarify": (
            state.get("questions")
            or ["Would you like to check coverage, prepare a claim, or update a claim’s status?"]
        )[0],
    }[route]
    return {"chat_reply": {"content": content, "sources": []}}


def build_dashboard_graph():
    graph = StateGraph(AgentState, context_schema=ChatContext)
    graph.add_node("router", instrument_node("router", router))
    graph.add_node("answer_claim", instrument_node("answer_claim", answer))
    graph.add_node("handoff", instrument_node("handoff", handoff))
    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        selected_agent,
        {
            "answer_claim": "answer_claim",
            "file_claim": "handoff",
            "save_claim_status": "handoff",
            "clarify": "handoff",
        },
    )
    graph.add_edge("answer_claim", END)
    graph.add_edge("handoff", END)
    return graph.compile()


@asynccontextmanager
async def dashboard_models():
    # Keep explicitly provisioned hosted chat usable through the same router.
    # Local chat never sends policy wording to a fallback provider.
    if os.environ.get("CLAIM_CHAT_PROVIDER") == "openai":
        async with httpx.AsyncClient(
            base_url=os.environ["AI_INTEGRATIONS_OPENAI_BASE_URL"].rstrip("/") + "/",
            headers={"Authorization": "Bearer " + os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"]},
            trust_env=False,
        ) as client:
            yield tuple(
                JsonSchemaModel(
                    client,
                    "gpt-5.4-mini",
                    max_tokens=4096,
                    token_limit_field="max_completion_tokens",
                    role=role,
                )
                for role in ("generator", "reviewer")
            )
    else:
        async with chat_models() as models:
            yield models


async def main():
    data = json.load(sys.stdin)
    with worker_trace("dashboard-chat", data["conversationId"]) as span:
        async with dashboard_models() as (generator, reviewer):
            result = await build_dashboard_graph().ainvoke(
                {
                    "request": AgentRequest(message=data["question"]),
                    "recent_turns": data["previous"],
                },
                context=ChatContext(data["owner"], data["policyId"], generator, reviewer),
            )
            span.update(
                output={
                    "route": selected_agent(result),
                    "source_count": len(result["chat_reply"]["sources"]),
                }
            )
    print(json.dumps({**result["chat_reply"], "route": selected_agent(result)}))


if __name__ == "__main__":
    from app.services.worker_runtime import run_worker

    run_worker(lambda: asyncio.run(main()))
