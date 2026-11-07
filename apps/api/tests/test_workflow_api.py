"""Exercise the public API against the same graph used by the UI."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.main import create_app
from app.services.bootstrap import demo_auth
from app.services.fixtures import FixtureStore, fixture_context
from app.services.workflow import WorkflowService


@pytest.fixture
def backend():
    store = FixtureStore.seeded()
    service = WorkflowService(
        build_graph(memory_checkpointer()), fixture_context(store), artifacts=store, mode="fixture"
    )
    with TestClient(create_app(service, demo_auth("test-token"))) as client:
        client.headers["Authorization"] = "Bearer test-token"
        yield client, store, service


def start(client, message, key="start", **kwargs):
    response = client.post(
        "/agent/runs",
        json={
            "request_key": key,
            "policy_id": "demo-policy",
            "claim_id": "demo-window",
            "message": message,
            **kwargs,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def decision(client, run, action="approve", key="decision", **kwargs):
    pending = run["pending"]
    body = {
        "request_key": key,
        "interrupt_id": pending["interrupt_id"],
        "decision": {"artifact_version": pending["artifact_version"], "action": action, **kwargs},
    }
    return client.post(f"/agent/runs/{run['run_id']}/responses", json=body)


def test_full_coverage_to_packet_and_download(backend):
    client, store, _ = backend
    answer = start(client, "Is my window covered?")
    assert answer["status"] == "completed" and answer["answer"]
    assert answer["mode"] == "fixture" and answer["citations"]
    assert "draft" not in answer and "evidence" not in answer
    packet = start(client, "I paid $150. Prepare the packet.", "file")
    assert packet["status"] == "awaiting_review"
    assert packet["pending"]["estimate"]["estimated_payment"] == "0.00"
    assert not store.artifacts and store.claims["demo-window"].version == 1
    completed = decision(client, packet).json()
    assert completed["action_result"]["outcome"] == "prepared"
    assert store.claims["demo-window"].status == "prepared"
    artifact = client.get("/artifacts/" + completed["action_result"]["artifact_id"])
    assert artifact.status_code == 200
    assert "Not submitted" in artifact.text
    assert "attachment" in artifact.headers["content-disposition"]
    assert store.claims["demo-window"].facts.repair_cost == 150
    assert len(store.events) == 1


def test_human_edit_rechecks_and_replaces_approval(backend):
    client, store, _ = backend
    packet = start(client, "I paid $150. Prepare the packet.")
    edited = decision(client, packet, "edit", feedback="The repair actually cost $175.").json()
    assert edited["status"] == "awaiting_review"
    assert edited["pending"]["artifact_version"] == 2
    assert edited["pending"]["draft"]["facts"]["repair_cost"] == "175"
    assert not store.events
    assert decision(client, packet, key="old-approval").status_code == 409
    assert decision(client, edited, key="new-approval").json()["status"] == "completed"


def test_repeated_requests_and_approvals_are_idempotent(backend):
    client, store, _ = backend
    first = start(client, "I paid $150. Save the repair update.")
    duplicate = start(client, "I paid $150. Save the repair update.")
    assert first["run_id"] == duplicate["run_id"]
    completed = decision(client, first).json()
    assert decision(client, first).json() == completed
    assert len(store.events) == 1
    conflict = client.post(
        "/agent/runs",
        json={"request_key": "start", "policy_id": "demo-policy", "message": "Different request"},
    )
    assert conflict.status_code == 409


def test_rejection_does_not_write(backend):
    client, store, _ = backend
    run = start(client, "I paid $150. Save the repair update.")
    assert decision(client, run, "reject").json()["status"] == "rejected"
    assert not store.events


def test_missing_claim_can_be_supplied_through_clarification(backend):
    client, _, _ = backend
    run = start(client, "I paid $150. Prepare the packet.", claim_id=None)
    assert run["status"] == "awaiting_information"
    response = client.post(
        f"/agent/runs/{run['run_id']}/responses",
        json={
            "request_key": "clarification",
            "interrupt_id": run["pending"]["interrupt_id"],
            "clarification": {"message": "Use my window claim.", "claim_id": "demo-window"},
        },
    )
    assert response.json()["status"] == "awaiting_review"


def test_claim_changed_during_approval_does_not_write(backend):
    client, store, _ = backend
    run = start(client, "I paid $150. Save the repair update.")
    store.claims["demo-window"] = store.claims["demo-window"].model_copy(update={"version": 2})
    assert decision(client, run).json()["status"] == "failed"
    assert not store.events


def test_authentication_and_run_artifact_isolation(backend):
    client, _, service = backend
    run = start(client, "I paid $150. Prepare the packet.")
    artifact_id = decision(client, run).json()["action_result"]["artifact_id"]
    assert (
        client.get(f"/agent/runs/{run['run_id']}", headers={"Authorization": "bad"}).status_code
        == 401
    )

    async def different_user(request: Request):
        return "another-user"

    with TestClient(create_app(service, different_user)) as other:
        assert other.get(f"/agent/runs/{run['run_id']}").status_code == 404
        assert other.get(f"/artifacts/{artifact_id}").status_code == 404
        assert (
            other.post(
                "/agent/runs",
                json={"request_key": "x", "policy_id": "demo-policy", "message": "Is it covered?"},
            ).status_code
            == 404
        )


def test_ui_cannot_inject_review_or_owner_fields(backend):
    client, _, _ = backend
    response = client.post(
        "/agent/runs",
        json={
            "request_key": "x",
            "policy_id": "demo-policy",
            "message": "Prepare claim",
            "approved": True,
            "user_id": "demo-user",
        },
    )
    assert response.status_code == 422


def test_default_app_exposes_contracts_without_fake_success(monkeypatch):
    monkeypatch.delenv("JEEVES_MODE", raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        paths = client.get("/openapi.json").json()["paths"]
        assert {"/agent/runs", "/workflow/route", "/workflow/estimate"} <= paths.keys()
        response = client.post(
            "/agent/runs", json={"request_key": "x", "policy_id": "p", "message": "Hi"}
        )
        assert response.status_code == 503


def test_explicit_demo_bootstrap_and_openapi_auth(monkeypatch):
    monkeypatch.setenv("JEEVES_MODE", "demo")
    monkeypatch.setenv("MODEL_MODE", "fixture")
    monkeypatch.setenv("JEEVES_DEMO_TOKEN", "bootstrap-test")
    with TestClient(create_app()) as client:
        client.headers["Authorization"] = "Bearer bootstrap-test"
        result = start(client, "Is the window covered?")
        assert result["model_mode"] == "fixture"
        assert "HTTPBearer" in client.get("/openapi.json").json()["components"]["securitySchemes"]
