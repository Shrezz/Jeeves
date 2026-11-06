"""Exercise the synthetic experiment without contacting Langfuse."""
import importlib.util
import json
from pathlib import Path

import langfuse

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("langfuse_experiment", ROOT / "evals/langfuse_experiment.py")
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)


def test_preview_dataset_exercises_real_functions():
    dataset = ROOT / "evals/datasets/workflow_preview.jsonl"
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    assert len(cases) == 6
    for case in cases:
        actual = experiment.run_task(item=case)
        assert actual == case["expected_output"]
        assert experiment.score_output(output=actual, expected_output=case["expected_output"]).value == 1


def test_experiment_calls_sdk_and_flushes(monkeypatch):
    class FakeClient:
        flushed = False
        def run_experiment(self, **kwargs):
            self.args = kwargs
            class Result:
                def format(self):
                    return "fake result"
            return Result()
        def flush(self):
            self.flushed = True

    client = FakeClient()
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "synthetic-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "synthetic-secret")
    monkeypatch.setattr(langfuse, "get_client", lambda: client)
    monkeypatch.setattr("sys.argv", ["langfuse_experiment.py"])
    experiment.main()
    assert client.args["task"] is experiment.run_task
    assert len(client.args["data"]) == 6
    assert client.flushed
