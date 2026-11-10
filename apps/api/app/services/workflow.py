"""UI-independent run service. All workflow entry points pass through this boundary."""

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from app.agents.context import AgentContext
from app.agents.prompt_scope import OUT_OF_SCOPE_MESSAGE, in_scope
from app.agents.state import AgentState
from app.observability.tracing import current_run_id, observation, trace_session
from app.schemas.agents import AgentRequest
from app.schemas.workflow_api import PendingAction, ResumeRun, RunView, StartRun

logger = logging.getLogger("jeeves.workflow")
ContextFactory = Callable[[str, str, str | None], Awaitable[AgentContext]]


class Conflict(ValueError):
    """An idempotency key, version, or human action no longer matches."""


@dataclass
class RunRecord:
    owner_id: str
    context: AgentContext
    state: AgentState = field(default_factory=dict)
    stages: list[str] = field(default_factory=list)
    interrupts: tuple = ()
    running: bool = False
    error: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    responses: dict[str, tuple[str, RunView]] = field(default_factory=dict)


class WorkflowService:
    """Single-process MVP service. Replace run storage alongside durable checkpoints for deployment."""

    def __init__(
        self,
        graph,
        context_factory: ContextFactory,
        *,
        artifacts=None,
        mode="integrated",
        model_mode="injected",
    ):
        self.graph = graph
        self.context_factory = context_factory
        self.artifacts = artifacts
        self.mode = mode
        self.model_mode = model_mode
        self.runs: dict[str, RunRecord] = {}
        self.starts: dict[tuple[str, str], tuple[str, str]] = {}
        self.start_lock = asyncio.Lock()

    def owned_run(self, user_id: str, run_id: str) -> RunRecord:
        run = self.runs.get(run_id)
        if run is None or run.owner_id != user_id:
            raise PermissionError("Run not found")
        return run

    async def start(self, user_id: str, request: StartRun) -> RunView:
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        async with self.start_lock:
            key = (user_id, request.request_key)
            if key in self.starts:
                previous, run_id = self.starts[key]
                if previous != digest:
                    raise Conflict("This request_key was already used for another request")
                return self.view(user_id, run_id)
            context = await self.context_factory(user_id, request.policy_id, request.claim_id)
            # Defense in depth when separately developed adapters are integrated.
            if context.user_id != user_id or context.policy_id != request.policy_id:
                raise PermissionError("Context does not match authenticated selection")
            run_id = str(uuid4())
            run = RunRecord(owner_id=user_id, context=context, running=True)
            self.runs[run_id] = run
            self.starts[key] = (digest, run_id)
        async with run.lock:
            await self.execute(
                run_id,
                {
                    "run_id": run_id,
                    "request": AgentRequest(
                        message=request.message,
                        claim_id=request.claim_id,
                        explicit_route=request.explicit_route,
                        web_search_query=request.web_search_query,
                    ),
                },
            )
        return self.view(user_id, run_id)

    async def resume(self, user_id: str, run_id: str, request: ResumeRun) -> RunView:
        run = self.owned_run(user_id, run_id)
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        async with run.lock:
            if request.request_key in run.responses:
                previous, response = run.responses[request.request_key]
                if previous != digest:
                    raise Conflict("This response key was already used for another response")
                return response
            if run.error or not run.interrupts or request.interrupt_id != run.interrupts[0].id:
                raise Conflict("This action is no longer pending")
            pending = run.interrupts[0].value
            if pending["kind"] == "human_review":
                if (
                    not request.decision
                    or request.decision.artifact_version != pending["artifact_version"]
                ):
                    raise Conflict("Provide a decision for the currently reviewed artifact version")
                value = request.decision.model_dump(mode="json")
            else:
                if request.clarification is None:
                    raise Conflict("This run is waiting for clarification")
                if not in_scope(request.clarification.message, followup=True):
                    raise Conflict(OUT_OF_SCOPE_MESSAGE)
                value = request.clarification.model_dump(mode="json")
            if (
                request.decision
                and request.decision.action == "edit"
                and not in_scope(request.decision.feedback or "", followup=True)
            ):
                raise Conflict(OUT_OF_SCOPE_MESSAGE)
            await self.execute(run_id, Command(resume={request.interrupt_id: value}))
            response = self.view(user_id, run_id)
            run.responses[request.request_key] = (digest, response)
            return response

    async def execute(self, run_id: str, graph_input: Any) -> None:
        with (
            trace_session(run_id),
            observation(
                "agent-workflow", input={"mode": self.mode, "model_mode": self.model_mode}
            ) as span,
        ):
            await self._execute_impl(run_id, graph_input)
            failed = bool(self.runs[run_id].error)
            span.update(output={"failed": failed})
            if failed:
                span.update(level="ERROR", status_message="Workflow execution failed")

    async def _execute_impl(self, run_id: str, graph_input: Any) -> None:
        run = self.runs[run_id]
        run.running, run.error = True, None
        trace_token = current_run_id.set(run_id)
        started = perf_counter()
        try:
            config = {"configurable": {"thread_id": run_id}, "recursion_limit": 40}
            async for update in self.graph.astream(
                graph_input, config, context=run.context, stream_mode="updates"
            ):
                for stage in update:
                    if stage != "__interrupt__":
                        run.stages.append(stage)
                        logger.info(
                            json.dumps(
                                {
                                    "event": "node_completed",
                                    "run_id": run_id,
                                    "node": stage,
                                    "mode": self.mode,
                                }
                            )
                        )
            snapshot = await self.graph.aget_state(config)
            run.state, run.interrupts = snapshot.values, snapshot.interrupts
        except Exception as exc:  # noqa: BLE001 - sanitize all failures at the public run boundary
            run.error = "Workflow could not complete. No unreviewed result is available."
            logger.error(
                json.dumps(
                    {"event": "run_failed", "run_id": run_id, "error_type": type(exc).__name__}
                )
            )
        finally:
            current_run_id.reset(trace_token)
            run.running = False
            logger.info(
                json.dumps(
                    {
                        "event": "run_finished",
                        "run_id": run_id,
                        "elapsed_ms": round((perf_counter() - started) * 1000),
                        "failed": bool(run.error),
                    }
                )
            )

    def view(self, user_id: str, run_id: str) -> RunView:
        run = self.owned_run(user_id, run_id)
        state = run.state
        route = state.get("route")
        base = {
            "run_id": run_id,
            "mode": self.mode,
            "model_mode": self.model_mode,
            "stages": list(run.stages),
            "route": route.route if route else None,
            "web_search": state.get("web_search"),
        }
        if run.running:
            return RunView(**base, status="running")
        if run.error:
            return RunView(**base, status="failed", error=run.error)
        if state.get("scope_decision") == "out_of_scope":
            return RunView(**base, status="blocked", error=OUT_OF_SCOPE_MESSAGE)
        if run.interrupts:
            item = run.interrupts[0]
            pending = PendingAction.model_validate(item.value | {"interrupt_id": item.id})
            return RunView(
                **base,
                status="awaiting_review"
                if pending.kind == "human_review"
                else "awaiting_information",
                pending=pending,
                citations=state.get("evidence", []) if pending.kind == "human_review" else [],
            )
        phase = state.get("phase")
        if phase == "answer_ready":
            review = state.get("review")
            if (
                review
                and review.verdict.outcome == "pass"
                and review.artifact_version == state["artifact_version"]
            ):
                return RunView(
                    **base,
                    status="completed",
                    answer=state["answer"],
                    citations=state.get("evidence", []),
                )
        if phase == "completed":
            return RunView(**base, status="completed", action_result=state["action_result"])
        if phase == "rejected":
            return RunView(**base, status="rejected")
        review = state.get("review")
        return RunView(**base, status="blocked", issues=review.verdict.issues if review else [])
