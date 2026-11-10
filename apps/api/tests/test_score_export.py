"""Exercise bounded score delivery without credentials or remote API traffic."""

import copy
import io
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

import score_export as exporter
from evaluators import Check


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert 0 <= seconds <= 0.5
        self.sleeps.append(seconds)
        self.now += seconds


def page(rows, cursor=None):
    return SimpleNamespace(data=rows, meta=SimpleNamespace(cursor=cursor))


def readback(request):
    return SimpleNamespace(
        id=request.id,
        name=request.name,
        value=request.value,
        data_type=request.data_type,
        environment=request.environment,
        timestamp=request.timestamp,
        metadata=copy.deepcopy(request.metadata),
        subject=SimpleNamespace(kind="trace", id=request.trace_id),
    )


@pytest.fixture
def scenario(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(exporter, "time", clock)
    for key in ("LANGFUSE_TRACING_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(key, "true")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "wrong-exporter-environment")
    observed = {
        "content": "Fictional packet",
        "workflow": {"route": "file_claim", "phase": "human_review", "version": 2},
    }
    timestamp = datetime(2026, 1, 2, 1, tzinfo=timezone(timedelta(hours=5)))
    root = SimpleNamespace(
        trace_id="trace-1",
        start_time=timestamp,
        end_time=timestamp + timedelta(seconds=2),
        environment="verification",
        release="jeeves-source-sha",
        output={
            "route": "file_claim",
            "status": "human_review",
            "artifact_version": 2,
            "result_fingerprint": exporter.result_fingerprint(observed),
        },
    )
    state = SimpleNamespace(
        clock=clock,
        observed=observed,
        root=root,
        roots=[root],
        case={"id": "synthetic", "expected": {"route": "file_claim"}},
        checks=[
            Check("route", True, "file_claim", "file_claim"),
            Check("phase", False, "approved", "human_review"),
            Check("citation_support_human", None, True, None),
        ],
        batches=[],
        observation_calls=[],
        score_calls=[],
        write_options=[],
        response=SimpleNamespace(message="Accepted"),
        transform=lambda rows: rows,
    )

    def observations(**kwargs):
        state.observation_calls.append(kwargs)
        return page(state.roots)

    def create(*, request, request_options):
        state.batches.append(request)
        state.write_options.append(request_options)
        return state.response

    def scores(**kwargs):
        state.score_calls.append(kwargs)
        return page(state.transform([readback(s) for s in state.batches[-1]]))

    state.client = SimpleNamespace(
        observations=SimpleNamespace(get_many=observations),
        scores=SimpleNamespace(create=create, get_many=scores),
    )
    monkeypatch.setattr(exporter, "_api_client", lambda: state.client)

    def publish(**kwargs):
        options = {"case_definition": state.case, "visibility_timeout": 0}
        options.update(kwargs)
        return exporter._publish_scores(
            "run-1", "synthetic", state.checks, state.observed, **options
        )

    state.publish = publish
    return state


def test_export_verifies_full_identity_provenance_and_trace_context(scenario):
    result = scenario.publish()
    assert result["status"] == "verified"
    assert result["submitted_checks"] == 3
    assert result["unscored_checks"] == 1
    assert result["environment"] == "verification"
    batch = scenario.batches[0]
    assert [(s.name, s.value, s.data_type) for s in batch] == [
        ("ui_eval_route", 1, "BOOLEAN"),
        ("ui_eval_phase", 0, "BOOLEAN"),
        ("ui_eval_unscored_count", 1, "NUMERIC"),
    ]
    assert all(s.trace_id == "trace-1" and s.environment == "verification" for s in batch)
    assert all(s.timestamp == scenario.root.start_time.astimezone(UTC) for s in batch)
    metadata = result["provenance"]
    assert metadata == exporter.provenance(scenario.case) | {
        "artifact_version": 2,
        "result_fingerprint": exporter.result_fingerprint(scenario.observed),
        "source_release": "jeeves-source-sha",
    }
    assert all(s.metadata == metadata for s in batch)
    assert len(metadata["evaluator_sha256"]) == len(metadata["case_sha256"]) == 64
    assert scenario.observation_calls[0]["session_id"] == "run-1"
    assert scenario.observation_calls[0]["name"] == "ui-claim-workflow"
    assert scenario.observation_calls[0]["is_root_observation"] is True
    assert scenario.score_calls[0]["trace_id"] == "trace-1"
    assert scenario.score_calls[0]["fields"] == "details,subject"
    for call in [*scenario.observation_calls, *scenario.score_calls]:
        assert call["request_options"] == {"timeout_in_seconds": 5, "max_retries": 0}
    assert scenario.write_options == [{"timeout_in_seconds": 5, "max_retries": 0}]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("route", "answer_claim"),
        ("status", "blocked"),
        ("artifact_version", 1),
        ("artifact_version", None),
        ("result_fingerprint", "0" * 64),
    ],
)
def test_scores_are_not_attached_to_a_different_saved_outcome(scenario, field, value):
    scenario.root.output[field] = value
    with pytest.raises(ValueError, match="does not match"):
        scenario.publish()
    assert not scenario.batches
    assert scenario.clock.now == 30


def test_same_workflow_revision_with_different_content_is_rejected(scenario):
    scenario.observed["content"] = "Changed after trace completion"
    with pytest.raises(ValueError, match="does not match"):
        scenario.publish()
    assert not scenario.batches


@pytest.mark.parametrize("output", [None, "not JSON", "[]", "null"])
def test_malformed_root_output_does_not_receive_scores(scenario, output):
    scenario.root.output = output
    with pytest.raises(ValueError, match="does not match"):
        scenario.publish()
    assert not scenario.batches


def test_json_encoded_root_output_is_supported(scenario):
    scenario.root.output = json.dumps(scenario.root.output)
    assert scenario.publish()["status"] == "verified"


def test_latest_completed_root_must_match_even_when_an_older_root_matches(scenario):
    newer = copy.deepcopy(scenario.root)
    newer.start_time += timedelta(seconds=10)
    newer.output["result_fingerprint"] = "0" * 64
    scenario.roots.append(newer)
    with pytest.raises(ValueError, match="does not match"):
        scenario.publish()
    assert not scenario.batches


@pytest.mark.parametrize("field", ["start_time", "end_time"])
def test_incomplete_root_cannot_receive_scores(scenario, field):
    setattr(scenario.root, field, None)
    with pytest.raises(ValueError, match="does not match"):
        scenario.publish()
    assert not scenario.batches


@pytest.mark.parametrize("environment", [None, "", "   "])
def test_missing_trace_environment_fails_before_submission(scenario, environment):
    scenario.root.environment = environment
    with pytest.raises(ValueError, match="environment is missing"):
        scenario.publish()
    assert not scenario.batches


@pytest.mark.parametrize(
    "key",
    ["LANGFUSE_TRACING_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"],
)
def test_missing_configuration_fails_without_api_calls(scenario, monkeypatch, key):
    monkeypatch.delenv(key)
    with pytest.raises(ValueError, match="configure project keys"):
        scenario.publish()
    assert not scenario.observation_calls
    assert not scenario.batches


@pytest.mark.parametrize("passed", [1, "true", [], {}])
def test_nonboolean_checks_fail_before_api_calls(scenario, passed):
    scenario.checks = [Check("route", passed, True, True)]
    with pytest.raises(ValueError, match="unique names and boolean"):
        scenario.publish()
    assert not scenario.observation_calls


def test_duplicate_check_names_fail_before_api_calls(scenario):
    scenario.checks.append(scenario.checks[0])
    with pytest.raises(ValueError, match="unique names"):
        scenario.publish()
    assert not scenario.observation_calls


def test_case_identity_mismatch_fails_before_api_calls(scenario):
    with pytest.raises(ValueError, match="case identity"):
        scenario.publish(case_definition={"id": "different"})
    assert not scenario.observation_calls


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("value", 99),
        ("name", "wrong_metric"),
        ("data_type", "NUMERIC"),
        ("environment", "wrong-environment"),
        ("timestamp", None),
        ("timestamp", datetime(2026, 1, 2, tzinfo=UTC)),
        ("subject", SimpleNamespace(kind="session", id="trace-1")),
        ("subject", SimpleNamespace(kind="trace", id="other-trace")),
        ("subject", None),
        ("metadata", {}),
    ],
)
def test_mismatched_score_identity_is_never_verified(scenario, field, value):
    def mutate(rows):
        setattr(rows[0], field, value)
        return rows

    scenario.transform = mutate
    assert scenario.publish()["status"] == "submitted_not_yet_visible"
    assert len(scenario.batches) == 1


@pytest.mark.parametrize(
    "key",
    [
        "evaluator_version",
        "evaluator_sha256",
        "case_id",
        "case_sha256",
        "artifact_version",
        "result_fingerprint",
        "source_release",
    ],
)
def test_every_provenance_field_is_verified(scenario, key):
    def mutate(rows):
        rows[0].metadata[key] = "changed"
        return rows

    scenario.transform = mutate
    assert scenario.publish()["status"] == "submitted_not_yet_visible"


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong-id"])
def test_readback_requires_exactly_one_score_for_each_submitted_id(scenario, mutation):
    def mutate(rows):
        if mutation == "missing":
            return rows[1:]
        if mutation == "duplicate":
            return rows + [rows[0]]
        rows[0].id = "different-id"
        return rows

    scenario.transform = mutate
    assert scenario.publish()["status"] == "submitted_not_yet_visible"


def test_score_timestamp_is_compared_by_utc_date(scenario):
    def mutate(rows):
        for row in rows:
            row.timestamp = datetime(2026, 1, 1, 12, tzinfo=UTC)
        return rows

    scenario.transform = mutate
    assert scenario.publish()["status"] == "verified"


def test_repeated_exports_keep_identity_timestamp_and_environment(scenario):
    assert scenario.publish()["status"] == "verified"
    first = scenario.batches[-1]
    assert scenario.publish()["status"] == "verified"
    assert [(s.id, s.timestamp, s.environment) for s in scenario.batches[-1]] == [
        (s.id, s.timestamp, s.environment) for s in first
    ]


def test_case_definition_or_evaluator_changes_create_distinct_score_identity(scenario, monkeypatch):
    scenario.publish()
    original = {s.id for s in scenario.batches[-1]}
    scenario.case["expected"]["route"] = "answer_claim"
    scenario.publish()
    revised_case = {s.id for s in scenario.batches[-1]}
    assert original.isdisjoint(revised_case)
    monkeypatch.setattr(exporter, "evaluator_fingerprint", lambda: "f" * 64)
    scenario.publish()
    assert revised_case.isdisjoint({s.id for s in scenario.batches[-1]})


def test_case_hash_is_canonical_but_sensitive_to_expectations():
    first = exporter.provenance({"id": "case", "expected": {"a": 1, "b": 2}})
    reordered = exporter.provenance({"expected": {"b": 2, "a": 1}, "id": "case"})
    assert first == reordered
    assert (
        first["case_sha256"]
        != exporter.provenance({"id": "case", "expected": {"a": 2}})["case_sha256"]
    )


def test_evaluator_hash_tracks_source_bytes(monkeypatch):
    original = exporter.evaluator_fingerprint()
    read_bytes = Path.read_bytes

    def changed(path):
        data = read_bytes(path)
        return data + b"\n# changed" if path.name == "score_export.py" else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert exporter.evaluator_fingerprint() != original


def test_partial_acceptance_is_reported_without_replay_or_raw_errors(scenario):
    scenario.response = SimpleNamespace(accepted=1, rejected=2, errors=["private API body"])
    result = scenario.publish()
    assert result["status"] == "partially_accepted"
    assert result["accepted"] == 1 and result["rejected"] == 2
    assert len(scenario.batches) == 1 and not scenario.score_calls
    assert "private API body" not in json.dumps(result)


@pytest.mark.parametrize("response", [SimpleNamespace(), SimpleNamespace(message="Unexpected")])
def test_unknown_acceptance_is_not_reported_as_verified(scenario, response):
    scenario.response = response
    assert scenario.publish()["status"] == "acceptance_unconfirmed"
    assert len(scenario.batches) == 1 and not scenario.score_calls


def test_cursor_pagination_collects_every_page_with_bounded_requests(scenario):
    calls = []

    def get_many(**kwargs):
        calls.append(kwargs)
        return page(["first"], "next") if "cursor" not in kwargs else page(["second"])

    assert exporter._all_pages(get_many, exporter.Deadline(2), trace_id="trace") == [
        "first",
        "second",
    ]
    assert "cursor" not in calls[0] and calls[1]["cursor"] == "next"
    assert all(c["request_options"] == {"timeout_in_seconds": 2, "max_retries": 0} for c in calls)


@pytest.mark.parametrize("endpoint", ["observations", "scores"])
def test_pagination_cap_fails_closed_for_root_lookup_and_readback(scenario, endpoint):
    calls = []

    def forever(**kwargs):
        calls.append(kwargs)
        rows = [scenario.root] if endpoint == "observations" else []
        return page(rows, "more")

    getattr(scenario.client, endpoint).get_many = forever
    with pytest.raises(ValueError, match="pagination limit"):
        scenario.publish()
    assert len(calls) == exporter.MAX_PAGES
    assert len(scenario.batches) == (0 if endpoint == "observations" else 1)


def test_visibility_lag_retries_reads_but_never_replays_batch(scenario):
    scenario.transform = lambda rows: [] if len(scenario.score_calls) < 3 else rows
    assert scenario.publish(visibility_timeout=2)["status"] == "verified"
    assert len(scenario.score_calls) == 3 and len(scenario.batches) == 1
    assert scenario.clock.now == 1


def test_visibility_polling_stops_at_its_deadline(scenario):
    scenario.transform = lambda rows: []
    assert scenario.publish(visibility_timeout=1.25)["status"] == "submitted_not_yet_visible"
    assert scenario.clock.now == 1.25
    assert len(scenario.batches) == 1


def test_total_deadline_includes_root_ingestion_wait(scenario):
    scenario.roots = []
    with pytest.raises(exporter.ExportDeadlineExceeded):
        scenario.publish(total_timeout=1)
    assert scenario.clock.now == 1
    assert not scenario.batches


def test_per_request_timeout_shrinks_with_remaining_global_budget(scenario):
    original = scenario.client.observations.get_many

    def slow_lookup(**kwargs):
        scenario.clock.now += 3
        return original(**kwargs)

    scenario.client.observations.get_many = slow_lookup
    assert scenario.publish(total_timeout=4)["status"] == "verified"
    assert scenario.observation_calls[0]["request_options"]["timeout_in_seconds"] == 4
    assert scenario.write_options[0] == {"timeout_in_seconds": 1, "max_retries": 0}
    assert scenario.score_calls[0]["request_options"]["timeout_in_seconds"] == 1


def test_public_export_serializes_checks_and_filters_child_environment(monkeypatch):
    captured = {}

    def child(command, payload, timeout, env):
        captured.update(command=command, payload=payload, timeout=timeout, env=env)
        return {"status": "verified"}

    monkeypatch.setattr(exporter, "_run_child", child)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "synthetic-project-key")
    monkeypatch.setenv("DATABASE_URL", "never-forward-db-password")
    monkeypatch.setenv("KEENABLE_API_KEY", "never-forward-model-key")
    monkeypatch.setenv("PYTHONPATH", "never-forward-module-injection")
    case = {"id": "case"}
    assert exporter.publish_scores(
        "run",
        "case",
        [Check("route", True, "x", "x")],
        {},
        case_definition=case,
        total_timeout=10,
        visibility_timeout=2,
    ) == {"status": "verified"}
    assert captured["command"] == [sys.executable, str(Path(exporter.__file__).resolve())]
    assert captured["timeout"] == 10
    assert captured["payload"]["total_timeout"] == 9
    assert captured["payload"]["visibility_timeout"] == 2
    assert captured["payload"]["checks"] == [
        {"name": "route", "passed": True, "expected": "x", "actual": "x"}
    ]
    assert captured["payload"]["case_definition"] == case
    assert captured["env"]["LANGFUSE_SECRET_KEY"] == "synthetic-project-key"
    assert not {"DATABASE_URL", "KEENABLE_API_KEY", "PYTHONPATH"} & captured["env"].keys()


@pytest.mark.parametrize("timeout", [0, 0.5, 121, float("inf"), float("nan")])
def test_public_export_rejects_invalid_total_timeout(timeout):
    with pytest.raises(ValueError, match="between 1 and 120"):
        exporter.publish_scores(
            "run", "case", [], {}, case_definition={"id": "case"}, total_timeout=timeout
        )


@pytest.mark.parametrize("timeout", [-1, 46, float("inf"), float("nan")])
def test_public_export_rejects_invalid_visibility_timeout(timeout):
    with pytest.raises(ValueError, match="Visibility timeout"):
        exporter.publish_scores(
            "run", "case", [], {}, case_definition={"id": "case"}, visibility_timeout=timeout
        )


def test_actual_child_is_killed_at_timeout_and_output_is_not_exposed():
    start = time.monotonic()
    result = exporter._run_child(
        [
            sys.executable,
            "-c",
            "import time; print('synthetic-sensitive-body', flush=True); time.sleep(20)",
        ],
        {},
        0.15,
        os.environ.copy(),
    )
    assert result == {"status": "timed_out", "delivery": "unknown"}
    assert time.monotonic() - start < 3
    assert "synthetic-sensitive-body" not in json.dumps(result)


@pytest.mark.parametrize(
    "program",
    [
        "import sys; print('synthetic-sensitive-body'); print('private traceback', file=sys.stderr); sys.exit(1)",
        "print('synthetic-sensitive-body')",
        "print('[]')",
        "print('{}')",
    ],
)
def test_child_failure_or_malformed_output_is_sanitized(program):
    result = exporter._run_child([sys.executable, "-c", program], {}, 3, os.environ.copy())
    assert result["status"] == "export_failed"
    assert "synthetic-sensitive-body" not in json.dumps(result)
    assert "traceback" not in json.dumps(result)


def test_real_export_child_sanitizes_configuration_errors(monkeypatch):
    for key in (
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_TRACING_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    result = exporter.publish_scores(
        "run", "case", [], {}, case_definition={"id": "case"}, total_timeout=5, visibility_timeout=0
    )
    assert result == {"status": "export_failed", "delivery": "unknown"}


@pytest.mark.parametrize("trace_id", [None, "", "   ", 123])
def test_missing_trace_identity_fails_before_submission(scenario, trace_id):
    scenario.root.trace_id = trace_id
    with pytest.raises(ValueError, match="Trace identity is missing"):
        scenario.publish()
    assert not scenario.batches


def test_trace_ingestion_lag_over_ten_seconds_is_allowed_within_global_deadline(scenario):
    original = scenario.client.observations.get_many

    def delayed(**kwargs):
        return page([]) if scenario.clock.now < 15 else original(**kwargs)

    scenario.client.observations.get_many = delayed
    assert scenario.publish()["status"] == "verified"
    assert scenario.clock.now == 15
    assert len(scenario.batches) == 1


def test_unmatched_root_uses_specific_no_delivery_exception(scenario):
    scenario.roots = []
    with pytest.raises(exporter.TraceNotVisibleOrMismatched):
        scenario.publish()
    assert scenario.clock.now == 30
    assert not scenario.batches


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            exporter.TraceNotVisibleOrMismatched("private details"),
            {"status": "trace_not_visible_or_mismatched", "delivery": "not_sent"},
        ),
        (
            exporter.ExportDeadlineExceeded("private details"),
            {"status": "timed_out", "delivery": "unknown"},
        ),
        (RuntimeError("private SDK response"), {"status": "export_failed", "delivery": "unknown"}),
    ],
)
def test_child_reports_safe_distinct_failure_states(monkeypatch, error, expected):
    def fail(**kwargs):
        raise error

    monkeypatch.setattr(exporter, "_publish_scores", fail)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"checks": []}'))
    assert exporter._child_main() == expected
