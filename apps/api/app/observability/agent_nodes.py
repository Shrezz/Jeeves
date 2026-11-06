"""Opt-in wrapper for the separate LangGraph agent branch's workflow nodes.

The graph owner must apply this wrapper when the agent branch is integrated.
It records only a small allowlist of state fields; prompts and artifacts are
never passed to tracing.
"""
from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable

from .tracing import observation

_NODES = {"begin_request", "router", "answer_claim", "file_claim", "save_claim_status",
          "reviewer", "human_review", "clarify", "commit_action"}


def _summary(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    summary = {}
    phase = result.get("phase")
    if phase in {"routed", "needs_information", "review_pending", "revision_required",
                 "human_review", "answer_ready", "approved", "rejected", "blocked", "completed"}:
        summary["phase"] = phase
    revision = result.get("revision_count")
    if isinstance(revision, int) and not isinstance(revision, bool):
        summary["revision_count"] = revision
    route = getattr(result.get("route"), "route", None)
    if route in {"answer_claim", "file_claim", "save_claim_status"}:
        summary["route"] = route
    verdict = getattr(getattr(result.get("review"), "verdict", None), "outcome", None)
    if verdict in {"pass", "revise", "needs_information"}:
        summary["reviewer_outcome"] = verdict
    evidence = result.get("evidence")
    if isinstance(evidence, (list, tuple)):
        summary["evidence_count"] = len(evidence)
    return summary


def instrument_node(name: str, node: Callable) -> Callable:
    """Preserve a node's signature and return type while tracing safe metadata."""
    if name not in _NODES:
        raise ValueError("Unsupported agent node")
    if inspect.iscoroutinefunction(node):
        @wraps(node)
        async def async_node(*args, **kwargs):
            with observation(f"agent-{name}") as span:
                result = await node(*args, **kwargs)
                span.update(output=_summary(result))
                return result
        return async_node

    @wraps(node)
    def sync_node(*args, **kwargs):
        with observation(f"agent-{name}") as span:
            result = node(*args, **kwargs)
            span.update(output=_summary(result))
            return result
    return sync_node
