"""API assembly with replaceable workflow and authenticated-session dependencies."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router
from app.observability.tracing import configure_tracing, flush_traces
from app.services.bootstrap import demo_backend


def create_app(service=None, principal_resolver=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configure_tracing()
        try:
            if service is None and os.environ.get("JEEVES_MODE") == "demo":
                async with demo_backend() as (backend, auth):
                    application.state.workflow, application.state.principal_resolver = backend, auth
                    yield
            else:
                yield
        finally:
            flush_traces()

    application = FastAPI(title="Jeeves Claim Companion API", version="0.2.0", lifespan=lifespan)
    application.state.workflow = service
    application.state.principal_resolver = principal_resolver
    origins = [
        origin.strip() for origin in os.environ.get("UI_ORIGINS", "").split(",") if origin.strip()
    ]
    if "*" in origins:
        raise ValueError("Configure explicit UI origins")
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )
    application.include_router(router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
