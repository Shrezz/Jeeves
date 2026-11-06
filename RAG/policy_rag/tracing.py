"""
tracing.py
==========
Per-request trace logging (Decision D14).

Every ingest and every question gets ONE JSON trace file that records each
processing step in order:

    {
      "trace_id": "...", "kind": "query", "status": "ok",
      "started_at": "2026-11-06T10:22:33.120-08:00", "duration_ms": 2140.5,
      "context":  {user_id, policy_number, question},
      "settings": {models, K values, hybrid flag, chunk size, package version},
      "steps": [
        {"step_no": 1, "depth": 0, "function": "policy_rag.qa.answer_with_context",
         "started_at": ..., "ended_at": ..., "duration_ms": ..., "status": "ok",
         "details": {...anything the step logged...}},
        ...
      ],
      "result": {...}, "error": null
    }

Files
    logs/queries/<YYYY-MM-DD>/<HHMMSS>_<policy>_<trace8>.json   one per question
    logs/ingestion/<YYYY-MM-DD>/<HHMMSS>_<policy>_<trace8>.json one per upload
    logs/query_index.jsonl      one summary line per question (quick scanning)
    logs/ingestion_index.jsonl  one summary line per upload

How code uses it
    1. A public entry point opens a trace:   with request_trace("query", ...) as t:
    2. Any function decorated with @traced becomes a step (name, timing, status).
    3. Inside a step, trace_log("key", value) attaches details to that step.
    4. When no trace is open (e.g. unit tests), the decorator and trace_log do nothing.

Never logged: the OpenAI API key or any environment variable.
Logged on purpose: user_id, policy number, question text and policy excerpts.
Treat the logs folder as confidential.
"""
import contextvars
import functools
import json
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

PACKAGE_VERSION = "v2"
_current: contextvars.ContextVar = contextvars.ContextVar("policy_rag_trace", default=None)


def _now() -> str:
    """Local time with UTC offset, millisecond precision."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _jsonable(value: Any) -> Any:
    """Make dataclasses, pydantic models, paths and other objects JSON friendly."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dataclass_fields__"):
        return {k: _jsonable(getattr(value, k)) for k in value.__dataclass_fields__}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def settings_snapshot() -> Dict[str, Any]:
    """Settings in force for this request, so runs can be compared later."""
    return {
        "package_version": PACKAGE_VERSION,
        "embedding_model": config.EMBEDDING_MODEL, "llm_model": config.LLM_MODEL,
        "llm_temperature": config.LLM_TEMPERATURE,
        "top_k": config.TOP_K, "fetch_k": config.FETCH_K, "mmr_lambda": config.MMR_LAMBDA,
        "hybrid_enabled": config.HYBRID_ENABLED, "pin_declarations": config.PIN_DECLARATIONS,
        "chunk_size_chars": config.CHUNK_SIZE_CHARS, "chunk_overlap_chars": config.CHUNK_OVERLAP_CHARS,
    }


# ---------------------------------------------------------------------------
# Trace object
# ---------------------------------------------------------------------------
class Trace:
    """Collects the steps of one request."""

    def __init__(self, kind: str, context: Dict[str, Any]):
        self.trace_id = uuid.uuid4().hex
        self.kind = kind                         # "query" or "ingestion"
        self.context = context
        self.started_at = _now()
        self._t0 = time.perf_counter()
        self.steps: List[Dict[str, Any]] = []
        self._stack: List[Dict[str, Any]] = []   # open steps (for nesting)
        self.result: Any = None
        self.error: Optional[Dict[str, str]] = None

    # -- steps --------------------------------------------------------------
    def open_step(self, function: str) -> Dict[str, Any]:
        step = {"step_no": len(self.steps) + 1, "depth": len(self._stack),
                "parent_step": self._stack[-1]["step_no"] if self._stack else None,
                "function": function, "started_at": _now(), "_t0": time.perf_counter(),
                "ended_at": None, "duration_ms": None, "status": "running", "details": {}}
        self.steps.append(step)
        self._stack.append(step)
        return step

    def close_step(self, step: Dict[str, Any], status: str, error: Optional[str] = None) -> None:
        step["ended_at"] = _now()
        step["duration_ms"] = round((time.perf_counter() - step.pop("_t0")) * 1000, 1)
        step["status"] = status
        if error:
            step["error"] = error
        self._stack.pop()

    def log(self, key: str, value: Any) -> None:
        """Attach a detail to the innermost open step (or to the trace if none)."""
        target = self._stack[-1]["details"] if self._stack else self.context
        target[key] = _jsonable(value)

    # -- output -------------------------------------------------------------
    def to_dict(self, status: str) -> Dict[str, Any]:
        return {"trace_id": self.trace_id, "kind": self.kind, "status": status,
                "started_at": self.started_at, "ended_at": _now(),
                "duration_ms": round((time.perf_counter() - self._t0) * 1000, 1),
                "context": _jsonable(self.context), "settings": settings_snapshot(),
                "steps": self.steps, "result": _jsonable(self.result), "error": self.error}


# ---------------------------------------------------------------------------
# Writing files
# ---------------------------------------------------------------------------
def _write(trace: Trace, status: str) -> Path:
    data = trace.to_dict(status)
    folder = config.LOG_DIR / ("queries" if trace.kind == "query" else "ingestion") / datetime.now().strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    policy = str(trace.context.get("policy_number", "unknown")).replace("/", "_")
    path = folder / f"{datetime.now().strftime('%H%M%S')}_{policy}_{trace.trace_id[:8]}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # One-line summary for quick scanning / grep.
    summary = {"trace_id": trace.trace_id, "started_at": data["started_at"], "status": status,
               "duration_ms": data["duration_ms"], "file": str(path), **{
                   k: trace.context.get(k) for k in ("user_id", "policy_number", "question", "file_name")
                   if k in trace.context}}
    if isinstance(data["result"], dict):
        for k in ("covered", "amount_payable", "amount_check", "chunks_stored"):
            if k in data["result"]:
                summary[k] = data["result"][k]
    index = config.LOG_DIR / ("query_index.jsonl" if trace.kind == "query" else "ingestion_index.jsonl")
    with index.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return path


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
@contextmanager
def request_trace(kind: str, **context):
    """Open a trace for one request; the file is written even if the request fails."""
    if not config.TRACE_ENABLED:
        yield None
        return
    trace = Trace(kind, dict(context))
    token = _current.set(trace)
    status = "ok"
    try:
        yield trace
    except Exception as exc:
        status = "error"
        trace.error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        raise
    finally:
        _current.reset(token)
        try:
            _write(trace, status)
        except OSError:
            pass                                   # logging must never break the request


def current_trace() -> Optional[Trace]:
    return _current.get()


def trace_log(key: str, value: Any) -> None:
    """Attach a detail to the current step. No-op when tracing is off."""
    trace = _current.get()
    if trace is not None:
        trace.log(key, value)


def traced(fn):
    """Decorator: record the function as a step (module.function, timing, status)."""
    name = f"{fn.__module__}.{fn.__qualname__}"

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        trace = _current.get()
        if trace is None:
            return fn(*args, **kwargs)
        step = trace.open_step(name)
        try:
            out = fn(*args, **kwargs)
        except Exception as exc:
            trace.close_step(step, "error", f"{type(exc).__name__}: {exc}")
            raise
        trace.close_step(step, "ok")
        return out
    return wrapper


def chunk_summary(doc, include_text: bool = True, score: Optional[float] = None, **extra) -> Dict[str, Any]:
    """Compact, consistent description of a chunk for the logs."""
    m = doc.metadata
    item = {"chunk_id": m.get("chunk_id"), "heading_path": m.get("heading_path"), "page": m.get("page"),
            "chunk_type": m.get("chunk_type"), "is_table": m.get("is_table"), "chars": len(doc.page_content)}
    if score is not None:
        item["score"] = round(float(score), 5)
    item.update(extra)
    if include_text:
        limit = config.TRACE_CHUNK_TEXT_CHARS
        item["text"] = doc.page_content if not limit else doc.page_content[:limit]
    return item
