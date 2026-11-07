"""Read passages from one owner-scoped local index, without creating a claim."""

import asyncio
import json
import os
from pathlib import Path

from app.observability.tracing import observation


async def search_passages(user_id: str, policy_id: str, query: str) -> list[dict]:
    with observation("policy-search", as_type="retriever") as span:
        hits = await _search_passages(user_id, policy_id, query)
        span.update(output={"passages": len(hits)})
        return hits


async def _search_passages(user_id: str, policy_id: str, query: str) -> list[dict]:
    root = Path(os.environ["LOCAL_RAG_ROOT"])
    python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    from opentelemetry.propagate import inject

    carrier: dict[str, str] = {}
    inject(carrier)
    tracing_keys = (
        (
            "LANGFUSE_TRACING_ENABLED",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_BASE_URL",
        )
        if os.getenv("LANGFUSE_TRACING_ENABLED", "").lower() == "true"
        else ()
    )
    proc = await asyncio.create_subprocess_exec(
        str(python),
        "-m",
        "policy_rag.local_worker",
        cwd=root,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={
            k: os.environ[k]
            for k in ("PATH", "HOME", "LOCAL_RAG_DATA_DIR", *tracing_keys)
            if k in os.environ
        }
        | {
            "ANONYMIZED_TELEMETRY": "False",
            "POLICY_RAG_TRACE": "0",
            "TOKENIZERS_PARALLELISM": "false",
            **{
                key.upper(): value
                for key, value in carrier.items()
                if key in {"traceparent", "tracestate"}
            },
        },
    )
    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(
                json.dumps(
                    {
                        "operation": "search",
                        "owner": user_id,
                        "policy": policy_id,
                        "question": query,
                        "forChat": True,
                    }
                ).encode()
            ),
            60,
        )
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    if proc.returncode:
        raise RuntimeError("Policy search unavailable")
    hits = json.loads(out)["passages"]
    if any(not hit["chunkId"].startswith(policy_id + ":") for hit in hits):
        raise ValueError("Unexpected policy passage")
    return hits
