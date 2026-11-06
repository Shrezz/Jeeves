"""API assembly with replaceable workflow and authenticated-session dependencies."""

import os
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agents.workflow import RouterResult, estimate_payment, route_message
from app.api.agents import router
from app.observability.tracing import configure_tracing, flush_traces, observation
from app.services.bootstrap import demo_backend


class RouteRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    selected_claim_id: str | None = None


class EstimateRequest(BaseModel):
    eligible_loss: Decimal = Field(ge=0)
    deductible: Decimal = Field(ge=0)


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

    @application.post("/workflow/route", response_model=RouterResult)
    def route(request: RouteRequest) -> RouterResult:
        """Preview a route without accessing or changing claim data."""
        with observation(
            "workflow-route", input={"claim_selected": bool(request.selected_claim_id)}
        ) as span:
            result = route_message(request.message, selected_claim_id=request.selected_claim_id)
            span.update(
                output={"intent": result.intent, "needs_clarification": result.needs_clarification}
            )
            return result

    @application.post("/workflow/estimate")
    def estimate(request: EstimateRequest) -> dict[str, str]:
        """Calculate an estimate without making a coverage determination."""
        with observation("workflow-estimate") as span:
            payment = estimate_payment(request.eligible_loss, request.deductible)
            span.update(output={"estimate_calculated": True})
            return {"estimated_payment": str(payment), "submitted": "false"}

    return application


app = create_app()
