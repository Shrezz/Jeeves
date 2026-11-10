"""
ingestion.py
============
Upload pipeline: read PDF -> verify identity -> chunk -> store in Chroma.

    IngestRequest
        -> resolve file inside config.UPLOAD_DIR (path traversal blocked)
        -> pdf_parser.parse_pdf            (layout elements)
        -> policy_identity.read_identity   (policy no., form, insured from the PDF)
        -> policy_identity.verify          (PDF policy no. must equal request policy no.)
        -> chunker.build_chunks            (structure-aware chunks + metadata)
        -> vector_store.replace_policy_chunks (delete old, insert new)
        -> IngestResult
"""
from pathlib import Path

from . import config
from . import retriever
from . import vector_store as vs
from .chunker import build_chunks
from .contracts import IngestRequest, IngestResult
from .errors import DocumentNotFoundError, InvalidRequestError
from .pdf_parser import parse_pdf
from .policy_identity import read_identity, verify_policy_number
from .tracing import request_trace, traced


def _require(value: str, name: str) -> str:
    if not value or not str(value).strip():
        raise InvalidRequestError(f"'{name}' is required.")
    return str(value).strip()


def _resolve_upload(file_name: str) -> Path:
    """Return the absolute path of the uploaded file, refusing paths outside UPLOAD_DIR."""
    base = config.UPLOAD_DIR.resolve()
    path = (base / file_name).resolve()
    if base not in path.parents:
        raise InvalidRequestError(f"File name '{file_name}' points outside the upload folder.")
    if not path.is_file():
        raise DocumentNotFoundError(f"'{file_name}' was not found in {base}.")
    return path


def ingest_policy(request: IngestRequest) -> IngestResult:
    """Ingest one uploaded policy PDF for one user (traced to logs/ingestion/)."""
    with request_trace("ingestion", user_id=request.user_id, policy_number=request.policy_number,
                       file_name=request.file_name, doc_version=request.doc_version) as trace:
        result = _ingest(request)
        if trace is not None:
            result.trace_id = trace.trace_id
            trace.result = result
        return result


@traced
def _ingest(request: IngestRequest) -> IngestResult:
    user_id = _require(request.user_id, "user_id")
    policy_number = _require(request.policy_number, "policy_number").upper()
    path = _resolve_upload(_require(request.file_name, "file_name"))

    # 1. Parse and confirm the document really is the stated policy.
    elements = parse_pdf(path)
    identity = read_identity(elements)
    verify_policy_number(policy_number, identity, request.file_name)

    # 2. Metadata attached to every chunk (Chroma accepts str/int/float/bool only).
    base_meta = {
        "user_id": user_id,
        "policy_number": policy_number,
        "insured_name": request.insured_name or identity.insured_name or "",
        "form": identity.form or "",
        "source_file": path.name,
        "doc_version": request.doc_version,
    }
    docs = build_chunks(elements, base_meta)

    # 3. Store, replacing any earlier upload of this policy by this user.
    replaced = vs.replace_policy_chunks(user_id, policy_number, docs)
    retriever.clear_cache(user_id, policy_number)
    return IngestResult(policy_number=policy_number, file_name=path.name, chunks_stored=len(docs),
                        form=identity.form, replaced_existing=replaced)


@traced
def delete_policy(user_id: str, policy_number: str) -> int:
    """Remove a user's policy from the vector store. Returns chunks removed."""
    user_id = _require(user_id, "user_id")
    policy_number = _require(policy_number, "policy_number").upper()
    removed = vs.delete_policy_chunks(user_id, policy_number)
    retriever.clear_cache(user_id, policy_number)
    return removed
