"""Keep nested exporter failures visible without disclosing subprocess stderr."""

import asyncio
import json

from app.services import local_policy_search


def test_nested_rag_failure_is_visible_without_losing_retrieval(monkeypatch, caplog):
    monkeypatch.setenv("LOCAL_RAG_ROOT", "/synthetic/rag")

    class Process:
        returncode = 0

        async def communicate(self, data):
            assert json.loads(data)["policy"] == "synthetic-policy"
            return json.dumps(
                {"passages": [{"chunkId": "synthetic-policy:0"}], "telemetry_export_failed": True}
            ).encode(), None

    async def start(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    hits = asyncio.run(
        local_policy_search.search_passages(
            "synthetic-user", "synthetic-policy", "private question"
        )
    )
    assert hits == [{"chunkId": "synthetic-policy:0"}]
    assert "telemetry_export_failed" in caplog.text
    assert "private question" not in caplog.text
