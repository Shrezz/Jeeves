"""One private stdin/stdout request from Express; no HTTP port, credentials, or paid calls."""

import json
import os
import sys
from contextlib import closing, redirect_stdout
from pathlib import Path
from uuid import UUID

from filelock import FileLock

from .local_index import LocalPolicyIndex
from .observability import export_failed, flush, span, trace_session


def main():
    request = json.load(sys.stdin)
    owner, policy = request["owner"], UUID(request["policy"])
    directory = Path(os.environ["LOCAL_RAG_DATA_DIR"])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Uploads, dashboard searches, and graph workers share one embedded Chroma writer.
    from opentelemetry import context, propagate

    carrier = {
        key.lower(): os.environ[key] for key in ("TRACEPARENT", "TRACESTATE") if key in os.environ
    }
    token = context.attach(propagate.extract(carrier))
    try:
        with trace_session(os.environ.get("JEEVES_TRACE_SESSION_ID")):
            result = perform(request, owner, policy, directory)
    finally:
        flush()
        context.detach(token)
    result["telemetry_export_failed"] = export_failed()
    print(json.dumps(result))


def perform(request, owner, policy, directory):
    if request.get("operation") not in {"index", "search"}:
        raise ValueError("Unknown operation")
    with (
        FileLock(directory / "worker.lock", timeout=45),
        redirect_stdout(sys.stderr),
        span(
            "local-policy-" + request["operation"],
            as_type="tool" if request["operation"] == "search" else "span",
        ),
        closing(LocalPolicyIndex(directory)) as index,
    ):
        if request["operation"] == "index":
            result = {"count": index.index(owner, policy, Path(request["pdf"]))}
        elif request["operation"] == "search":
            result = {
                "passages": index.search(
                    owner, policy, request["question"], for_chat=request.get("forChat", False)
                )
            }
        else:
            raise ValueError("Unknown operation")
    return result


if __name__ == "__main__":
    from .worker_runtime import run_worker

    run_worker(main)
