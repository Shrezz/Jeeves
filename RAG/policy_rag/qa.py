"""
qa.py
=====
Question pipeline: retrieve -> prompt -> structured LLM answer -> calculator.

    QueryRequest
        -> validate + confirm the policy exists for this user
        -> retriever.retrieve           (pinned Declarations + top-k chunks)
        -> build_messages               (chunks tagged [S1], [S2], ...)
        -> call_llm                     (gpt-4o-mini, structured CoverageAnswer)
        -> calculator.compute_amount    (deterministic amount + cross-check)
        -> QueryResult (includes trace_id)

Every step above is recorded in one trace file under logs/queries/.
"""
from functools import lru_cache
from typing import List, Optional, Tuple

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from . import config
from . import vector_store as vs
from .observability import span
from .calculator import compute_amount
from .contracts import CoverageAnswer, QueryRequest, QueryResult, SourceChunk
from .errors import InvalidRequestError, PolicyNotIngestedError, PolicyRagError
from .prompts import ANSWER_PROMPT, format_context
from .retriever import retrieve
from .tracing import chunk_summary, request_trace, trace_log, traced

_llm_override: Optional[BaseChatModel] = None      # tests can inject a fake model


class LLMOutputError(PolicyRagError):
    """The model's reply could not be parsed into CoverageAnswer."""


def set_llm(llm: BaseChatModel) -> None:
    """Replace the chat model (used only by offline tests)."""
    global _llm_override
    _llm_override = llm
    _structured_llm.cache_clear()


@lru_cache(maxsize=1)
def _structured_llm():
    """LLM constrained to the CoverageAnswer schema; include_raw keeps token usage for the trace."""
    llm = _llm_override or ChatOpenAI(model=config.LLM_MODEL, temperature=config.LLM_TEMPERATURE)
    return llm.with_structured_output(CoverageAnswer, include_raw=True)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
@traced
def validate_request(request: QueryRequest) -> Tuple[str, str, str]:
    """Check required fields and that this user has stored chunks for the policy."""
    fields = {"user_id": request.user_id, "policy_number": request.policy_number, "question": request.question}
    for name, value in fields.items():
        if not value or not str(value).strip():
            raise InvalidRequestError(f"'{name}' is required.")
    user_id, policy_number = request.user_id.strip(), request.policy_number.strip().upper()
    stored = vs.count_policy_chunks(user_id, policy_number)
    trace_log("stored_chunks_for_policy", stored)
    if stored == 0:
        raise PolicyNotIngestedError(f"No stored document for policy '{policy_number}' and this user.")
    return user_id, policy_number, request.question.strip()


@traced
def build_messages(policy_number: str, question: str, docs: List[Document]) -> List[BaseMessage]:
    """Render the prompt exactly as it will be sent to the LLM."""
    messages = ANSWER_PROMPT.format_messages(policy_number=policy_number, question=question,
                                             context=format_context(docs))
    trace_log("chunks_sent_to_llm", [{"source_tag": f"S{i}", **chunk_summary(d)} for i, d in enumerate(docs, 1)])
    trace_log("context_chars", sum(len(m.content) for m in messages))
    if config.TRACE_FULL_PROMPT:
        trace_log("messages", [{"role": m.type, "content": m.content} for m in messages])
    return messages


@traced
def call_llm(messages: List[BaseMessage]) -> CoverageAnswer:
    """Call the model and parse its structured answer."""
    with span("standalone-rag-generation", as_type="generation", model=config.LLM_MODEL) as generation:
        out = _structured_llm().invoke(messages)
        raw, parsed = out.get("raw"), out.get("parsed")
        usage = getattr(raw, "usage_metadata", None) or {}
        counts = {target: usage[source] for source, target in (
            ("input_tokens", "input"), ("output_tokens", "output"), ("total_tokens", "total")
        ) if isinstance(usage.get(source), int) and not isinstance(usage[source], bool) and usage[source] >= 0}
        if generation:
            if counts:
                generation.update(usage_details=counts)
            generation.update(metadata={"validated": parsed is not None})
        if parsed is None:
            raise LLMOutputError("Could not parse structured model output")
    if raw is not None:
        trace_log("model", (getattr(raw, "response_metadata", {}) or {}).get("model_name", config.LLM_MODEL))
        trace_log("token_usage", getattr(raw, "usage_metadata", None))
        trace_log("finish_reason", (getattr(raw, "response_metadata", {}) or {}).get("finish_reason"))
    trace_log("parsed_answer", parsed)
    return parsed


@traced
def map_sources(tags: List[str], docs: List[Document]) -> List[SourceChunk]:
    """Turn the model's [S#] tags back into chunk references."""
    out = []
    for tag in tags:
        digits = "".join(ch for ch in tag if ch.isdigit())
        if digits and 1 <= int(digits) <= len(docs):
            m = docs[int(digits) - 1].metadata
            out.append(SourceChunk(chunk_id=m["chunk_id"], heading_path=m["heading_path"],
                                   page=m["page"], chunk_type=m["chunk_type"]))
    trace_log("cited_tags", tags)
    trace_log("cited_chunks", out)
    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
@traced
def run_pipeline(request: QueryRequest) -> Tuple[QueryResult, List[Document]]:
    user_id, policy_number, question = validate_request(request)
    docs = retrieve(question, user_id, policy_number)
    answer = call_llm(build_messages(policy_number, question, docs))
    amount, check = compute_amount(answer)
    result = QueryResult(policy_number=policy_number, question=question, covered=answer.covered,
                         amount_payable=amount, llm_amount=answer.llm_amount, amount_check=check,
                         answer_summary=answer.answer_summary,
                         calculation_explanation=answer.calculation_explanation,
                         sources=map_sources(answer.sources, docs))
    return result, docs


def answer_with_context(request: QueryRequest) -> Tuple[QueryResult, List[Document]]:
    """Answer a question and also return every retrieved chunk (used by evaluation)."""
    with request_trace("query", user_id=request.user_id, policy_number=request.policy_number,
                       question=request.question) as trace:
        result, docs = run_pipeline(request)
        if trace is not None:
            result.trace_id = trace.trace_id
            trace.result = result
        return result, docs


def answer_question(request: QueryRequest) -> QueryResult:
    """Answer one user question about one of their policies."""
    return answer_with_context(request)[0]
