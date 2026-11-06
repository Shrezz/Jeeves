"""Tracing must preserve API behavior and avoid sending request text."""
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.observability import tracing


class FakeSpan:
    def __init__(self):
        self.updates = []

    def update(self, **kwargs):
        self.updates.append(kwargs)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.span = FakeSpan()

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.calls.append(kwargs)
        yield self.span


def test_trace_omits_user_message_and_claim_id(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)
    response = TestClient(app).post("/workflow/route", json={
        "message": "The repair is complete. Sensitive sample text.",
        "selected_claim_id": "private-claim-id",
    })
    assert response.status_code == 200
    assert fake.calls == [{"as_type": "span", "name": "workflow-route", "input": {"claim_selected": True}}]
    recorded = repr((fake.calls, fake.span.updates))
    assert "Sensitive sample text" not in recorded
    assert "private-claim-id" not in recorded
    assert fake.span.updates[0]["output"]["intent"] == "save_claim_status"


def test_tracing_disabled_without_credentials(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing.get_trace_client() is None
    assert TestClient(app).post("/workflow/estimate", json={"eligible_loss": 150, "deductible": 1000}).json()["estimated_payment"] == "0.00"


def test_observation_preserves_application_exception(monkeypatch):
    monkeypatch.setattr(tracing, "get_trace_client", lambda: FakeClient())
    with pytest.raises(ValueError, match="workflow failed"):
        with tracing.observation("example"):
            raise ValueError("workflow failed")


def test_trace_failure_does_not_block_workflow(monkeypatch):
    class BrokenClient:
        def start_as_current_observation(self, **kwargs):
            raise RuntimeError("collector unavailable")

    monkeypatch.setattr(tracing, "get_trace_client", lambda: BrokenClient())
    response = TestClient(app).post("/workflow/route", json={"message": "Is this covered?"})
    assert response.status_code == 200
    assert response.json()["intent"] == "answer_claim"


def test_ingestion_records_counts_without_policy_content(monkeypatch):
    from app.services.rag import ingestion
    from app.services.rag.types import PolicyChunk, PolicyPage

    fake = FakeClient()
    monkeypatch.setattr(tracing, "get_trace_client", lambda: fake)
    page = PolicyPage(page=1, text="private policy text")
    chunk = PolicyChunk(id="chunk-1", user_id="private-user", policy_id="private-policy",
                        policy_version="1", page=1, section="coverage", content=page.text,
                        embedding=(0.1,))
    monkeypatch.setattr(ingestion, "extract_pdf_pages", lambda _: [page])
    monkeypatch.setattr(ingestion, "chunk_policy_pages", lambda *args, **kwargs: [chunk])
    monkeypatch.setattr(ingestion, "_embed_chunks", lambda *args, **kwargs: [chunk])
    class Store:
        def upsert(self, chunks):
            assert chunks == [chunk]
    assert ingestion.ingest_policy_pdf("private-path.pdf", user_id="private-user",
                                       policy_id="private-policy", policy_version="1",
                                       embedder=object(), store=Store()) == 1
    assert {call["name"] for call in fake.calls} == {"policy-ingestion", "pdf-extraction", "policy-chunking", "policy-embedding", "policy-chunk-storage"}
    captured = repr((fake.calls, fake.span.updates))
    for secret in ("private policy text", "private-user", "private-policy", "private-path.pdf"):
        assert secret not in captured
