"""Run or resume the compiled claim graph for a Clerk-authorized, saved message."""

import asyncio
import json
import os
import re
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.runtime import Runtime
from langgraph.types import Command
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.agents.checkpoints import checkpoint_serializer
from app.agents.context import AgentContext
from app.agents.graph import build_graph
from app.agents.state import AgentState
from app.observability.tracing import flush_traces, observation, trace_session
from app.schemas.agents import AgentRequest, Clarification, HumanDecision, PacketDraft
from app.services.chat_guidance import guidance
from app.services.chat_worker import chat_models
from app.services.ui_claim_store import ClaimChanged, WebClaimStore


def source(c):
    return {
        "chunkId": c.policy_id + ":" + c.chunk_id[1:],
        "page": c.page,
        "section": c.section or "",
        "excerpt": c.excerpt,
    }


async def chat_answer(state: AgentState, runtime: Runtime[AgentContext]):
    context = runtime.context
    store = context.claims
    question = state["request"].message
    hits = await store.retrieve_evidence(
        user_id=context.user_id, policy_id=context.policy_id, question=question, limit=10
    )
    result = await guidance(
        {
            "question": question,
            "recentNotes": store.history,
            "policyAccess": "Indexed policy"
            if hits
            else "No indexed wording available for this claim.",
        },
        [source(c) for c in hits],
        context.generator,
        context.reviewer,
    )
    return {"phase": "answer_ready", "chat_reply": result}


def project(snapshot, files):
    """Only a passed, version-matched draft may leave the graph for human review."""
    state = snapshot.values
    route = state["route"].route if state.get("route") else None
    phase = state["phase"]
    pending = snapshot.interrupts[0] if snapshot.interrupts else None
    version = state.get("artifact_version", 0)
    flow = {"route": route or "clarify", "phase": phase, "version": version, "fields": []}
    reply = {"content": "", "sources": [], "workflow": flow}
    if pending:
        flow["interruptId"] = pending.id
    if phase == "answer_ready":
        return {**reply, **state["chat_reply"]}
    if phase == "needs_information":
        reply["content"] = " ".join(state["questions"])
        return reply
    if phase == "rejected":
        reply["content"] = "You declined this proposal. Nothing was submitted."
        return reply
    review = state.get("review")
    if (
        phase not in ("human_review", "completed")
        or not review
        or review.verdict.outcome != "pass"
        or review.artifact_version != version
    ):
        flow["phase"] = "blocked"
        reply["content"] = (
            "The reviewer couldn’t verify this draft. Please check the incident facts and try again."
        )
        return reply
    draft = state["draft"]

    def field(label, value):
        if value is not None:
            flow["fields"].append({"label": label, "value": str(value)})

    if isinstance(draft, PacketDraft):
        flow["narrative"] = draft.narrative
        field("Incident date", draft.facts.occurred_on)
        field("Cause", draft.facts.cause)
        field("Repair", draft.facts.description)
        field(
            "Repair cost",
            f"${draft.facts.repair_cost:,.2f}" if draft.facts.repair_cost is not None else None,
        )
        estimate = state.get("estimate")
        if estimate:
            field("Eligible expense before deductible", f"${estimate.covered_amount:,.2f}")
            field("Deductible", f"${estimate.deductible:,.2f}")
            field("Estimated payment", f"${estimate.estimated_payment:,.2f}")
        pages = {c.chunk_id: c.page for c in state["evidence"]}
        mentioned = set(re.findall(r"\bC\d+\b", draft.coverage.explanation))
        explanation = re.sub(
            r"\bC\d+\b",
            lambda m: "p. " + str(pages[m[0]]) if m[0] in pages else m[0],
            draft.coverage.explanation,
        )
        field("Coverage assessment", explanation)
        field(
            "Attached evidence",
            ", ".join(files[i] for i in draft.attachment_ids) or "No files attached",
        )
        wanted = set(draft.coverage.citation_ids) | mentioned
        reply["sources"] = [source(c) for c in state["evidence"] if c.chunk_id in wanted]
        if draft.missing_information or draft.coverage.missing_information:
            field(
                "For your review",
                " ".join(
                    dict.fromkeys(draft.missing_information + draft.coverage.missing_information)
                ),
            )
        reply["content"] = (
            "Your claim packet is ready for your review. Nothing has been submitted to an insurer."
            if pending
            else "You approved this packet. Prepared — not submitted."
        )
    else:
        flow["narrative"] = draft.note
        field("Proposed status", draft.status)
        field("Reported insurer outcome", draft.insurer_outcome)
        for name, value in draft.facts.model_dump(mode="json", exclude_none=True).items():
            field(name.replace("_", " ").capitalize(), value)
        reply["content"] = (
            "Review the proposed update before saving it."
            if pending
            else "You approved and saved the status update."
        )
    return reply


async def execute(db, saver, request, generator, reviewer):
    owner, claim_id, run_id = request["owner"], request["claimId"], request["runId"]
    # Every lookup and resume is bound to the claim owner; run IDs alone confer no authority.
    row = await (
        await db.execute(
            """SELECT m.content,m.kind,g.message_id,g.workflow FROM public.claim_guidance g
        JOIN public.claims c ON c.id=g.claim_id JOIN public.claim_messages m ON m.id=g.message_id AND m.claim_id=c.id
        WHERE g.id=%s AND c.id=%s AND c.owner_id=%s""",
            (run_id, claim_id, owner),
        )
    ).fetchone()
    if not row:
        raise PermissionError("Run not found")
    locked = await (
        await db.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", (run_id,))
    ).fetchone()
    if not locked["ok"]:
        raise ClaimChanged("This request is already being processed.")
    store = WebClaimStore(db, owner, claim_id, run_id)
    claim = await store.load_claim(user_id=owner, claim_id=claim_id)
    context = AgentContext(
        owner,
        store.policy,
        "1",
        generator,
        reviewer,
        store,
        store,
        actions=store,
        prior_coverage=store.prior_coverage,
    )
    graph = build_graph(saver, reviewed_chat_node=chat_answer)
    config = {"configurable": {"thread_id": run_id}}
    snapshot = await graph.aget_state(config)
    decision = request.get("response")
    # If a worker stopped between checkpointing the user's decision and updating
    # the UI row, reconcile the newer checkpoint without applying another decision.
    visible_interrupt = (row["workflow"] or {}).get("interruptId")
    if (
        decision
        and visible_interrupt == decision["interruptId"]
        and not any(i.id == visible_interrupt for i in snapshot.interrupts)
    ):
        decision = None
    if decision:
        if not snapshot.interrupts or decision["interruptId"] != snapshot.interrupts[0].id:
            raise ClaimChanged("This review changed. Refresh to see the latest version.")
        pending = snapshot.interrupts[0].value
        if pending["kind"] == "human_review":
            if decision["action"] not in {"approve", "reject", "edit"}:
                raise ClaimChanged("This version is waiting for a review decision.")
            if decision["version"] != pending["artifact_version"]:
                raise ClaimChanged("Review version changed.")
            if claim.version != snapshot.values["claim"].version:
                raise ClaimChanged("Claim changed. Request a new draft in chat.")
            value = HumanDecision(
                artifact_version=decision["version"],
                action=decision["action"],
                feedback=decision.get("feedback"),
            )
        elif decision["action"] == "clarify":
            prior_claim = snapshot.values.get("claim")
            if prior_claim and prior_claim.version != claim.version:
                raise ClaimChanged("Claim changed. Request a new draft in chat.")
            value = Clarification(message=decision["feedback"])
        else:
            raise ClaimChanged("This run is waiting for clarification.")
        await graph.ainvoke(
            Command(resume={snapshot.interrupts[0].id: value.model_dump(mode="json")}),
            config,
            context=context,
        )
    elif not snapshot.values:
        await graph.ainvoke(
            {
                "run_id": run_id,
                "request": AgentRequest(
                    message=row["content"] or "Help me document the attached claim evidence.",
                    claim_id=claim_id,
                    explicit_route="file_claim" if row["kind"] == "preparation_request" else None,
                ),
            },
            config,
            context=context,
        )
    elif snapshot.next and not snapshot.interrupts:
        # A transient worker failure can be retried from the most recent completed node.
        await graph.ainvoke(None, config, context=context)
    snapshot = await graph.aget_state(config)
    result = project(snapshot, store.files)
    await db.execute(
        """UPDATE public.claim_guidance SET state='ready',content=%s,sources=%s,workflow=%s,updated_at=now()
        WHERE id=%s AND claim_id=%s""",
        (result["content"], Jsonb(result["sources"]), Jsonb(result["workflow"]), run_id, claim_id),
    )


async def main():
    url = os.environ["DATABASE_URL"]
    graph_url = make_conninfo(url, options="-c search_path=claim_graph")
    if sys.argv[1:] == ["--setup"]:
        async with AsyncPostgresSaver.from_conn_string(
            graph_url, serde=checkpoint_serializer()
        ) as saver:
            await saver.setup()
        return
    request = json.load(sys.stdin)
    try:
        with (
            trace_session(request["runId"]),
            observation(
                "ui-claim-workflow",
                metadata={"provider": os.environ.get("CLAIM_CHAT_PROVIDER", "ollama")},
            ) as span,
        ):
            async with (
                AsyncPostgresSaver.from_conn_string(
                    graph_url, serde=checkpoint_serializer()
                ) as saver,
                await AsyncConnection.connect(url, autocommit=True, row_factory=dict_row) as db,
                chat_models() as (generator, reviewer),
            ):
                try:
                    await execute(db, saver, request, generator, reviewer)
                    print(json.dumps({"ok": True}))
                except ClaimChanged as e:
                    span.update(output={"conflict": True})
                    print(json.dumps({"conflict": str(e)}))
    finally:
        flush_traces()


if __name__ == "__main__":
    asyncio.run(main())
