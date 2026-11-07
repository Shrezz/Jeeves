"""Opt-in wrapper for the separate LangGraph agent branch's workflow nodes.

The graph owner must apply this wrapper when the agent branch is integrated.
It records only a small allowlist of state fields; prompts and artifacts are
never passed to tracing.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from functools import wraps
from typing import Any

from .tracing import capture_synthetic_content, observation, sanitize_content

_NODES = {
    "begin_request",
    "scope_guard",
    "web_search",
    "router",
    "answer_claim",
    "file_claim",
    "save_claim_status",
    "reviewer",
    "human_review",
    "handoff",
    "clarify",
    "commit_action",
}


def _summary(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    summary = {}
    scope = result.get("scope_decision")
    if scope in {"allowed", "out_of_scope"}:
        summary["scope_decision"] = scope
    web_search = result.get("web_search")
    if isinstance(web_search, dict):
        summary["web_search_status"] = web_search.get("status", "unknown")
        summary["web_result_count"] = len(web_search.get("results", []))
    elif "web_search" in result:
        summary["web_search_status"] = "not_requested"
    phase = result.get("phase")
    if phase in {
        "routed",
        "needs_information",
        "review_pending",
        "revision_required",
        "human_review",
        "handoff",
        "answer_ready",
        "approved",
        "rejected",
        "blocked",
        "completed",
    }:
        summary["phase"] = phase
    revision = result.get("revision_count")
    if isinstance(revision, int) and not isinstance(revision, bool):
        summary["revision_count"] = revision
    version = result.get("artifact_version")
    if isinstance(version, int) and not isinstance(version, bool):
        summary["artifact_version"] = version
    route = getattr(result.get("route"), "route", None)
    if route in {"answer_claim", "file_claim", "save_claim_status"}:
        summary["route"] = route
    verdict = getattr(getattr(result.get("review"), "verdict", None), "outcome", None)
    if verdict in {"pass", "revise", "needs_information"}:
        summary["reviewer_outcome"] = verdict
    issues = getattr(getattr(result.get("review"), "verdict", None), "issues", None)
    if isinstance(issues, (list, tuple)):
        summary["issue_checks"] = [
            code
            for issue in issues
            if isinstance((code := getattr(issue, "check", None)), str)
            and re.fullmatch(r"[A-Za-z0-9_]{1,64}", code)
        ]
        summary["issue_count"] = len(issues)
        if capture_synthetic_content():
            summary["reviewer_feedback"] = sanitize_content(
                [
                    {
                        "check": getattr(issue, "check", ""),
                        "detail": getattr(issue, "detail", ""),
                        "field": getattr(issue, "field", None),
                    }
                    for issue in issues
                ]
            )
    decision = getattr(result.get("human_decision"), "action", None)
    if decision in {"approve", "edit", "reject"}:
        summary["human_action"] = decision
    evidence = result.get("evidence")
    if isinstance(evidence, (list, tuple)):
        summary["evidence_count"] = len(evidence)
    if capture_synthetic_content():
        for key in ("draft", "chat_reply", "review"):
            value = result.get(key)
            if value is not None:
                if hasattr(value, "model_dump"):
                    value = value.model_dump(mode="json")
                summary[key] = sanitize_content(value)
    return summary


def _input(name: str, args: tuple) -> dict[str, Any]:
    value: dict[str, Any] = {"node": name}
    if capture_synthetic_content() and args and isinstance(args[0], dict):
        request = args[0].get("request")
        if hasattr(request, "model_dump"):
            value["request"] = sanitize_content(request.model_dump(mode="json"))
    return value


def instrument_node(name: str, node: Callable) -> Callable:
    """Preserve a node's signature and return type while tracing safe metadata."""
    if name not in _NODES:
        raise ValueError("Unsupported agent node")
    if inspect.iscoroutinefunction(node):

        @wraps(node)
        async def async_node(*args, **kwargs):
            with observation(f"agent-{name}", input=_input(name, args)) as span:
                result = await node(*args, **kwargs)
                span.update(output=_summary(result))
                return result

        return async_node

    @wraps(node)
    def sync_node(*args, **kwargs):
        with observation(f"agent-{name}", input=_input(name, args)) as span:
            result = node(*args, **kwargs)
            span.update(output=_summary(result))
            return result

    return sync_node
