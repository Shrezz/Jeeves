"""Read-only workflow utilities.

These endpoints intentionally cannot prepare, file, approve, or mutate a claim.
The full authenticated workflow requires the database and approval implementation.
"""
from decimal import Decimal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .agents.workflow import RouterResult, estimate_payment, route_message
from .observability.tracing import flush_traces, observation


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    flush_traces()


app = FastAPI(title="Claim Companion API", version="0.1.0", lifespan=lifespan)


class RouteRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    selected_claim_id: str | None = None


class EstimateRequest(BaseModel):
    eligible_loss: Decimal = Field(ge=0)
    deductible: Decimal = Field(ge=0)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/workflow/route", response_model=RouterResult)
def route(request: RouteRequest) -> RouterResult:
    """Preview a route only; no claim data is accessed or changed."""
    with observation("workflow-route", input={"claim_selected": bool(request.selected_claim_id)}) as span:
        result = route_message(request.message, selected_claim_id=request.selected_claim_id)
        span.update(output={"intent": result.intent, "needs_clarification": result.needs_clarification})
        return result


@app.post("/workflow/estimate")
def estimate(request: EstimateRequest) -> dict[str, str]:
    """Return a deterministic estimate; this is not a coverage determination."""
    with observation("workflow-estimate") as span:
        payment = estimate_payment(request.eligible_loss, request.deductible)
        span.update(output={"estimate_calculated": True})
        return {"estimated_payment": str(payment), "submitted": "false"}
