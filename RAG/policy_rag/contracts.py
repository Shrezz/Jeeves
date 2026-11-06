"""
contracts.py
============
Data shapes exchanged between the PARENT MODULE (front-end / auth layer) and
this RAG package. These are the only types the parent needs to know.

Inputs  (parent -> RAG): IngestRequest, QueryRequest
Outputs (RAG -> parent): IngestResult, QueryResult
"""
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inputs from the parent module
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IngestRequest:
    """Sent by the parent after it has saved an uploaded PDF into config.UPLOAD_DIR."""
    user_id: str                  # authenticated user's id (REQUIRED, used for access control)
    policy_number: str            # policy number the user claims for this file (REQUIRED)
    file_name: str                # file name inside UPLOAD_DIR, e.g. "MCM_Policy_01_..._v1.pdf"
    insured_name: Optional[str] = None   # optional display name, stored as metadata
    doc_version: str = "v1"       # optional version tag of the uploaded document


@dataclass(frozen=True)
class QueryRequest:
    """Sent by the parent for every user question."""
    user_id: str                  # authenticated user's id (REQUIRED)
    policy_number: str            # policy the question is about (REQUIRED)
    question: str                 # the user's natural-language question


# ---------------------------------------------------------------------------
# LLM structured output (internal, but returned inside QueryResult)
# ---------------------------------------------------------------------------
class PaymentLine(BaseModel):
    """One component of a payment. Most answers have one line; some have two
    (e.g. dwelling repair + tree debris removal)."""
    label: str = Field(description="What this line pays for, e.g. 'Coverage A dwelling repair'")
    loss_value: float = Field(description="Value of the covered loss after valuation (replacement cost, ACV or functional), BEFORE deductible")
    deductible: float = Field(description="Deductible applied to this line. Apply the deductible only once per occurrence; use 0 if none applies")
    special_limit: Optional[float] = Field(default=None, description="Special limit or sublimit that caps this line, if any")
    coverage_limit: Optional[float] = Field(default=None, description="Coverage or endorsement limit that caps this line, if any")


class CoverageAnswer(BaseModel):
    """Schema the LLM must fill. Amounts are recomputed in Python (calculator.py)."""
    covered: Literal["Yes", "No", "Partial", "N/A", "Not addressed"] = Field(
        description="Yes = paid in full after deductible; Partial = paid but capped by a limit or reduced; "
                    "No = not covered or nothing payable; N/A = factual question with no payment; "
                    "Not addressed = the policy text provided does not answer the question")
    answer_summary: str = Field(description="One or two sentence plain-English answer")
    payment_lines: List[PaymentLine] = Field(default_factory=list, description="Empty when nothing is payable or the question is factual")
    llm_amount: Optional[float] = Field(default=None, description="Your own computed total amount payable")
    calculation_explanation: str = Field(description="Step-by-step calculation following the policy's payment rule")
    sources: List[str] = Field(description="Source tags of the chunks used, e.g. ['S2', 'S5']")


# ---------------------------------------------------------------------------
# Outputs to the parent module
# ---------------------------------------------------------------------------
@dataclass
class IngestResult:
    policy_number: str
    file_name: str
    chunks_stored: int
    form: Optional[str]
    replaced_existing: bool       # True if older chunks for this policy were deleted first
    trace_id: Optional[str] = None  # id of the trace file in logs/ingestion


@dataclass
class SourceChunk:
    chunk_id: str
    heading_path: str
    page: int
    chunk_type: str


@dataclass
class QueryResult:
    policy_number: str
    question: str
    covered: str
    amount_payable: Optional[float]      # computed deterministically from payment_lines
    llm_amount: Optional[float]          # what the LLM itself said
    amount_check: str                    # "match", "mismatch" or "n/a"
    answer_summary: str
    calculation_explanation: str
    sources: List[SourceChunk] = field(default_factory=list)
    trace_id: Optional[str] = None       # id of the trace file in logs/queries (for support / debugging)
