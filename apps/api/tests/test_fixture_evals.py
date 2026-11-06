"""Check the golden-scenario runner against the real synthetic agent graph."""

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def suite(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "evals"))
    return importlib.import_module("fixture_suite")


def test_all_scenarios_execute_and_preserve_missing_measurements(suite):
    dev = suite.load_cases(ROOT / "evals/datasets/dev.jsonl")
    held = suite.load_cases(ROOT / "evals/datasets/held_out.jsonl")
    assert len(dev) == 8 and len(held) == 4
    dev_report = suite.report(dev)
    held_report = suite.report(held)
    assert dev_report["execution_errors"] == held_report["execution_errors"] == 0
    assert dev_report["unscored_checks"] > 0  # Human labels are never fabricated.
    restart = next(case for case in held_report["cases"] if case["id"] == "held_01_restart_resume")
    assert restart["checks"][0]["passed"] is False  # Fixture storage is not durable.
    isolation = next(
        case for case in held_report["cases"] if case["id"] == "held_04_user_isolation"
    )
    assert isolation["checks"][0]["passed"] is None  # No real pgvector ownership adapter.
    assert all(
        item["before_review_citation_valid"] is False
        and item["after_review_citation_valid"] is True
        for item in dev_report["reviewer_comparison"]
    )


def test_manual_annotations_are_opt_in_and_not_invented(suite):
    case = suite.load_cases(ROOT / "evals/datasets/dev.jsonl")[0]
    unreviewed = suite.run_one(case)
    by_name = {item["name"]: item["passed"] for item in unreviewed["checks"]}
    assert by_name["citation_support_human"] is None
    reviewed = suite.run_one(
        case, {case["id"]: {"citation_support_human": True, "explanation_correct_human": False}}
    )
    by_name = {item["name"]: item["passed"] for item in reviewed["checks"]}
    assert by_name["citation_support_human"] is True
    assert by_name["explanation_correct_human"] is False


def test_strict_mode_does_not_succeed_on_failed_or_unscored_cases(suite, monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["fixture_suite.py", str(ROOT / "evals/datasets/dev.jsonl"), "--strict"]
    )
    with pytest.raises(SystemExit) as error:
        suite.main()
    assert error.value.code == 1


def test_real_langfuse_experiment_runs_with_in_memory_exporter(suite, monkeypatch, tmp_path):
    import json

    import langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from app.observability import tracing

    case = suite.load_cases(ROOT / "evals/datasets/dev.jsonl")[0]
    dataset = tmp_path / "one-case.jsonl"
    dataset.write_text(json.dumps(case) + "\n")
    exporter = InMemorySpanExporter()
    client = langfuse.Langfuse(
        public_key="pk-lf-test-eval",
        secret_key="sk-lf-test-eval",
        base_url="https://example.test",
        tracer_provider=TracerProvider(),
        span_exporter=exporter,
    )
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-eval")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test-eval")
    monkeypatch.setattr(langfuse, "get_client", lambda: client)
    monkeypatch.setattr(tracing, "get_trace_client", lambda: client)
    monkeypatch.setattr("sys.argv", ["fixture_suite.py", str(dataset), "--langfuse"])
    try:
        suite.main()
        client.flush()
        spans = exporter.get_finished_spans()
        assert any(span.name == "agent-workflow" for span in spans)
        assert any("experiment" in span.name.lower() for span in spans)
    finally:
        client.shutdown()
