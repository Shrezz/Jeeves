"""Read-only workflow utilities.

These endpoints intentionally cannot prepare, file, approve, or mutate a claim.
The full authenticated workflow requires the database and approval implementation.
"""
from decimal import Decimal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .agents.workflow import RouterResult, estimate_payment, route_message

app = FastAPI(title="Claim Companion API", version="0.1.0")


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
    return route_message(request.message, selected_claim_id=request.selected_claim_id)


@app.post("/workflow/estimate")
def estimate(request: EstimateRequest) -> dict[str, str]:
    """Return a deterministic estimate; this is not a coverage determination."""
    payment = estimate_payment(request.eligible_loss, request.deductible)
    return {"estimated_payment": str(payment), "submitted": "false"}
