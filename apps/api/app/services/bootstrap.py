"""Explicit local-demo assembly. Production integrations inject their own service and auth."""

import hmac
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException, Request

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.services.fixtures import FixtureStore, fixture_context
from app.services.keenable import KeenableSearch
from app.services.nebius import NEBIUS_BASE_URL, nebius_pair
from app.services.workflow import WorkflowService


def demo_auth(token: str):
    async def authenticate(request: Request) -> str:
        received = request.headers.get("authorization", "")
        if not hmac.compare_digest(received, "Bearer " + token):
            raise HTTPException(
                401, "Valid demo bearer token required", headers={"WWW-Authenticate": "Bearer"}
            )
        return "demo-user"

    return authenticate


@asynccontextmanager
async def demo_backend():
    token = os.environ.get("JEEVES_DEMO_TOKEN", "")
    if not token or token == "replace-with-a-local-demo-token":
        raise ValueError("Set JEEVES_DEMO_TOKEN before enabling demo mode")
    model_mode = os.environ.get("MODEL_MODE", "fixture")
    if model_mode not in {"fixture", "nebius"}:
        raise ValueError("MODEL_MODE must be fixture or nebius")
    store = FixtureStore.seeded()
    client = None
    try:
        generator = reviewer = None
        if model_mode == "nebius":
            api_key = os.environ.get("NEBIUS_API_KEY", "")
            generator_id = os.environ.get("NEBIUS_GENERATOR_MODEL", "")
            reviewer_id = os.environ.get("NEBIUS_REVIEWER_MODEL", "")
            if not all((api_key, generator_id, reviewer_id)):
                raise ValueError("Nebius mode requires API key and both model IDs")
            client = httpx.AsyncClient(
                base_url=NEBIUS_BASE_URL,
                headers={"Authorization": "Bearer " + api_key},
            )
            generator, reviewer = nebius_pair(client, generator_id, reviewer_id)
        service = WorkflowService(
            build_graph(memory_checkpointer()),
            fixture_context(
                store, generator, reviewer,
                web_search=KeenableSearch(os.environ.get("KEENABLE_API_KEY", ""))
                if os.environ.get("KEENABLE_SEARCH_ENABLED", "false").lower() == "true"
                else None,
            ),
            artifacts=store,
            mode="fixture",
            model_mode=model_mode,
        )
        yield service, demo_auth(token)
    finally:
        if client:
            await client.aclose()
