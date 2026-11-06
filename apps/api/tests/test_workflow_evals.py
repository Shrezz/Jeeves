"""Exercise the full dataset adapter with synthetic HTTP responses."""
import importlib
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def eval_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "evals"))
    return importlib.import_module("run_eval"), importlib.import_module("evaluators"), importlib.import_module("langfuse_workflow_experiment")


def test_unmeasured_checks_are_not_passes(eval_modules):
    _, evaluators, experiment = eval_modules
    checks = evaluators.evaluate({"route": "file_claim", "citation_required": True,
                                  "must_not_invent_coverage": True},
                                 {"route": "file_claim", "citations": []})
    assert [c.passed for c in checks] == [True, False, None]
    scores = experiment.score_checks(output={"route": "file_claim"},
                                     expected_output={"route": "file_claim", "citation_required": True})
    assert {s.name: s.value for s in scores} == {"check_route": 1, "unscored_checks": 1}


def test_all_cases_report_without_automatically_approving(eval_modules):
    runner, _, _ = eval_modules
    seen = []
    def handler(request):
        seen.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"route": "file_claim", "status": "awaiting_review",
                                         "pending": {"kind": "human_review", "estimate": {"estimated_payment": "0.00"}},
                                         "citations": []})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        dev = runner.run_dataset(ROOT / "evals/datasets/dev.jsonl", client, policy_id="fixture-policy")
        held = runner.run_dataset(ROOT / "evals/datasets/held_out.jsonl", client, policy_id="fixture-policy")
    assert len(dev["cases"]) == 8
    assert len(held["cases"]) == 4
    assert held["unscored_checks"] > 0
    assert all(method == "POST" and path == "/agent/runs" for method, path, _ in seen)
    assert all(payload["policy_id"] == "fixture-policy" for _, _, payload in seen)


def test_http_failures_are_unscored_not_passed(eval_modules):
    runner, _, _ = eval_modules
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)), base_url="http://test") as client:
        report = runner.run_dataset(ROOT / "evals/datasets/dev.jsonl", client)
    assert report["passed_checks"] == 0
    assert report["failed_checks"] == 0
    assert report["unscored_checks"] > 0
    assert report["error_cases"] > 0


def test_stale_approval_uses_wrong_version_only_in_fixture_mode(eval_modules):
    runner, _, _ = eval_modules
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/responses"):
            decision = json.loads(request.content)["decision"]
            assert decision["artifact_version"] == 2
            return httpx.Response(409)
        return httpx.Response(200, json={"run_id": "test-run", "mode": "fixture",
            "status": "awaiting_review", "action_result": None,
            "pending": {"kind": "human_review", "artifact_version": 1, "interrupt_id": "i"}})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        result = runner.stale_approval_case(client, policy_id="p", claim_id="c")
    assert result == {"approval_rejected": True, "execution_error": False, "action_performed": False}
    assert len(requests) == 3


def test_stale_approval_never_submits_to_integrated_mode(eval_modules):
    runner, _, _ = eval_modules
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"run_id": "test-run", "mode": "integrated",
            "pending": {"kind": "human_review", "artifact_version": 1, "interrupt_id": "i"}})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        result = runner.stale_approval_case(client, policy_id="p", claim_id="c")
    assert "unscored_reason" in result
    assert len(requests) == 1


def test_langfuse_workflow_experiment_uses_adapter_and_flushes(eval_modules, monkeypatch):
    _, _, experiment = eval_modules
    class FakeLangfuse:
        flushed = False
        def run_experiment(self, **kwargs):
            item = kwargs["data"][0]
            output = kwargs["task"](item=item)
            self.scores = kwargs["evaluators"][0](output=output, expected_output=item["expected_output"])
            class Result:
                def format(self):
                    return "synthetic run"
            return Result()
        def flush(self):
            self.flushed = True
    lf = FakeLangfuse()
    original_client = httpx.Client
    def api_client(**kwargs):
        return original_client(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"route": "answer_claim", "status": "completed", "citations": ["chunk"]})),
            **kwargs)
    monkeypatch.setattr(experiment, "get_client", lambda: lf)
    monkeypatch.setattr(experiment.httpx, "Client", api_client)
    monkeypatch.setenv("EVAL_API_TOKEN", "synthetic-token")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "synthetic-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "synthetic-secret")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setattr("sys.argv", ["runner", str(ROOT / "evals/datasets/dev.jsonl")])
    experiment.main()
    assert lf.flushed
    assert {score.name: score.value for score in lf.scores}["check_route"] == 1
