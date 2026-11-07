"""Perform an explicitly requested public search without changing policy evidence."""

import logging

from langgraph.runtime import Runtime

from .context import AgentContext
from .state import AgentState

logger = logging.getLogger("jeeves.web_search")


async def web_search(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    query = state["request"].web_search_query
    if not query:
        return {"web_search": None}
    if runtime.context.web_search is None:
        return {"web_search": {"status": "unavailable", "results": []}}
    try:
        results = await runtime.context.web_search.search(query)
    except Exception:  # noqa: BLE001 - provider errors must not break the claim workflow
        logger.warning("Public web search unavailable")
        return {"web_search": {"status": "unavailable", "results": []}}
    return {"web_search": {"status": "ok", "results": results}}
