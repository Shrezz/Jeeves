"""
api.py  -  PUBLIC ENTRY POINT OF THE policy_rag PACKAGE
=======================================================

WHAT THIS PACKAGE DOES
----------------------
Answers "is this covered, and how much will be paid?" questions about home
insurance policy PDFs, using LangChain + Chroma + OpenAI.

    Upload flow   : PDF in UPLOAD_DIR -> parse -> verify policy number -> chunk
                    with metadata -> embed (text-embedding-3-small) -> Chroma
    Question flow : question -> filtered retrieval (user + policy only) ->
                    gpt-4o-mini structured answer -> Python recomputes amount
                    -> QueryResult

This package does NOT do authentication, authorization, file upload handling,
UI, or user management. Those belong to the parent module.

=====================================================================
CONTRACT WITH THE PARENT MODULE (front-end / auth application)
=====================================================================

A. ENVIRONMENT the parent must provide before importing this package
   1. OPENAI_API_KEY        (required) shell variable, or a line in <project root>/.env
   2. POLICY_RAG_UPLOAD_DIR (optional, default <project root>/policy_documents)
   3. POLICY_RAG_CHROMA_DIR (optional, default <project root>/chroma_store)
   4. POLICY_RAG_LOG_DIR    (optional, default <project root>/logs)
   5. POLICY_RAG_TRACE      (optional, "0" switches trace files off)
   6. Write access to all three folders. The logs contain user ids, questions
      and policy text: protect them like the policies themselves.

B. BEFORE calling ingest_policy()
   1. Authenticate the user.
   2. Confirm the user is entitled to the policy number (e.g. it belongs to
      their account). This package trusts user_id as already authenticated.
   3. Save the uploaded PDF into UPLOAD_DIR. Pass only the FILE NAME, not a
      path. Names that escape UPLOAD_DIR are rejected.
   4. Call ingest_policy(IngestRequest(...)) with:
        user_id        str  required  stable id of the authenticated user
        policy_number  str  required  e.g. "MCM-HO3-CA-100231"
        file_name      str  required  e.g. "MCM_Policy_01_Okafor-Raman_HO3_v1.pdf"
        insured_name   str  optional  display name; read from the PDF if omitted
        doc_version    str  optional  default "v1"
   5. Ingestion is synchronous and calls the OpenAI embeddings API. Run it in
      a background worker if the UI must not block (about 50 to 60 chunks
      per policy).

C. FOR EVERY QUESTION
   1. Take user_id from the authenticated session and policy_number from
      the user's selection. NEVER take either from the question text.
   2. Call answer_question(QueryRequest(user_id, policy_number, question)).

D. WHAT YOU GET BACK
   IngestResult: policy_number, file_name, chunks_stored, form, replaced_existing, trace_id
   QueryResult : covered          "Yes" | "No" | "Partial" | "N/A" | "Not addressed"
                 amount_payable   float or None   (computed in Python, use this one)
                 llm_amount       float or None   (model's own figure, for audit)
                 amount_check     "match" | "mismatch" | "n/a"  (flag mismatches)
                 answer_summary, calculation_explanation
                 sources          list of SourceChunk(chunk_id, heading_path, page, chunk_type)
                 trace_id         id of the trace file (show it in support screens / logs)

E. ERRORS TO CATCH (all subclass errors.PolicyRagError)
   InvalidRequestError     missing field, or bad file name
   DocumentNotFoundError   file not found in UPLOAD_DIR
   PolicyMismatchError     PDF's policy number differs from the request
   PolicyNotIngestedError  question for a policy this user has not uploaded
   Errors from the OpenAI client (network, rate limit) are not wrapped.

F. GUARANTEES
   1. A user only ever retrieves chunks stored under their own user_id and
      the requested policy_number.
   2. Re-uploading the same policy for the same user replaces the old chunks.
   3. Answers come only from the stored policy text; if it does not contain
      the answer, covered = "Not addressed".
   4. Every ingest and every question writes one JSON trace file:
        logs/ingestion/<date>/<time>_<policy>_<id>.json
        logs/queries/<date>/<time>_<policy>_<id>.json
      plus one summary line in logs/ingestion_index.jsonl or logs/query_index.jsonl.
      A trace is written even when the request fails (status "error").

EXAMPLE
-------
    from policy_rag.api import ingest_policy, answer_question, IngestRequest, QueryRequest

    ingest_policy(IngestRequest(user_id="u-1029", policy_number="MCM-HO3-CA-100231",
                                file_name="MCM_Policy_01_Okafor-Raman_HO3_v1.pdf"))
    result = answer_question(QueryRequest(user_id="u-1029", policy_number="MCM-HO3-CA-100231",
                                          question="Jewelry worth $9,200 was stolen. How much is paid?"))
    print(result.covered, result.amount_payable)      # Partial 1500.0
=====================================================================
"""
from .contracts import IngestRequest, IngestResult, QueryRequest, QueryResult, SourceChunk  # noqa: F401
from .errors import (DocumentNotFoundError, InvalidRequestError, PolicyMismatchError,  # noqa: F401
                     PolicyNotIngestedError, PolicyRagError)
from .ingestion import delete_policy, ingest_policy  # noqa: F401
from .qa import answer_question  # noqa: F401

__all__ = [
    "ingest_policy", "answer_question", "delete_policy",
    "IngestRequest", "IngestResult", "QueryRequest", "QueryResult", "SourceChunk",
    "PolicyRagError", "InvalidRequestError", "DocumentNotFoundError",
    "PolicyMismatchError", "PolicyNotIngestedError",
]
