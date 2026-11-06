"""Confirm the evaluation adapter exercises the real public workflow contract."""

import importlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.main import create_app
from app.services.bootstrap import demo_auth
from app.services.fixtures import FixtureStore, fixture_context
from app.services.workflow import WorkflowService


def test_eval_adapter_and_explicitly_unscored_semantic_checks(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "evals"))
    runner = importlib.import_module("run_eval")
    evaluator = importlib.import_module("evaluators")
    store = FixtureStore.seeded()
    service = WorkflowService(
        build_graph(memory_checkpointer()),
        fixture_context(store),
        artifacts=store,
        mode="fixture",
        model_mode="fixture",
    )
    with TestClient(create_app(service, demo_auth("eval-test"))) as client:
        client.headers["Authorization"] = "Bearer eval-test"
        actual = runner.run_case(
            {"message": "I paid $150. Prepare a claim.", "selected_policy_id": "legacy-id"},
            client,
            policy_id="demo-policy",
            claim_id="demo-window",
        )
    checks = evaluator.evaluate(
        {
            "route": "file_claim",
            "estimated_payment": 0,
            "human_approval_required": True,
            "must_not_invent_coverage": True,
        },
        actual,
    )
    assert [check.passed for check in checks] == [True, True, True, None]
    assert not store.events  # Evaluations never auto-approve an action.
