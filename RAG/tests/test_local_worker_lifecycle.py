import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from policy_rag import local_worker


@pytest.mark.parametrize("fails", [False, True])
def test_worker_releases_index_on_success_and_failure(monkeypatch, tmp_path, fails):
    events = []

    class Index:
        def __init__(self, directory):
            assert directory == tmp_path

        def search(self, *args, **kwargs):
            if fails:
                raise ValueError("private-policy-error")
            return []

        def close(self):
            events.append("closed")

    monkeypatch.setattr(local_worker, "LocalPolicyIndex", Index)
    request = {"operation": "search", "question": "Synthetic"}
    if fails:
        with pytest.raises(ValueError, match="private-policy-error"):
            local_worker.perform(request, "owner", uuid4(), tmp_path)
    else:
        assert local_worker.perform(request, "owner", uuid4(), tmp_path) == {"passages": []}
    assert events == ["closed"]


def test_index_survives_real_cli_exit_and_reopens_in_next_worker(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fixture = root.parent / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf"
    policy = str(uuid4())
    # Only embeddings are replaced; exercise real parser, Chroma persistence,
    # worker cleanup, JSON output, and immediate process exit.
    code = """
import runpy
from policy_rag import local_index
real_index = local_index.LocalPolicyIndex
def embed(texts):
    return [[float("boarding" in text.lower()), 0.1] for text in texts]
local_index.LocalPolicyIndex = lambda directory: real_index(directory, embed)
runpy.run_module("policy_rag.local_worker", run_name="__main__")
"""
    def request(operation):
        completed = subprocess.run(
            [sys.executable, "-c", code], check=False,
            input=json.dumps({"owner": "synthetic-owner", "policy": policy, **operation}),
            text=True, capture_output=True, timeout=15,
            cwd=root,
            env={
                "PATH": os.environ["PATH"],
                "PYTHONDONTWRITEBYTECODE": "1",
                "LOCAL_RAG_DATA_DIR": str(tmp_path),
                "ANONYMIZED_TELEMETRY": "False",
                "POLICY_RAG_TRACE": "0",
                "LANGFUSE_TRACING_ENABLED": "false",
            },
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)

    assert request({"operation": "index", "pdf": str(fixture)})["count"] > 1
    result = request({"operation": "search", "question": "boarding"})
    assert any(hit["page"] == 2 and "$275" in hit["excerpt"] for hit in result["passages"])
    assert all(hit["chunkId"].startswith(policy + ":") for hit in result["passages"])
