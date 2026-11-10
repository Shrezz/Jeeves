"""Bounded, versioned export of the approved UI checks to exact trace artifacts.

The public entrypoint isolates synchronous API calls in a short-lived process.
No background score queue or SDK tracing client is created by this exporter.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from evaluators import Check

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.observability.tracing import result_fingerprint

EVALUATOR_VERSION = "jeeves-ui-v2"
MAX_PAGES = 20


def evaluator_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "ui_workflow_eval.py",
        "score_export.py",
        "evaluators.py",
        "annotation_validation.py",
    ):
        path = Path(__file__).with_name(name)
        digest.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def provenance(case: dict) -> dict:
    encoded = json.dumps(
        case, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_sha256": evaluator_fingerprint(),
        "case_id": case["id"],
        "case_sha256": hashlib.sha256(encoded).hexdigest(),
    }


class ExportDeadlineExceeded(TimeoutError):
    pass


class TraceNotVisibleOrMismatched(ValueError):
    pass


class Deadline:
    def __init__(self, seconds):
        self.end = time.monotonic() + seconds

    def remaining(self):
        left = self.end - time.monotonic()
        if left <= 0:
            raise ExportDeadlineExceeded("Score export deadline exceeded")
        return left

    def options(self):
        return {"timeout_in_seconds": min(5.0, self.remaining()), "max_retries": 0}


def _api_client():
    from langfuse.api import LangfuseAPI

    return LangfuseAPI(
        base_url=os.environ["LANGFUSE_BASE_URL"],
        username=os.environ["LANGFUSE_PUBLIC_KEY"],
        password=os.environ["LANGFUSE_SECRET_KEY"],
        timeout=5,
        follow_redirects=False,
    )


def _all_pages(get_many, deadline, **kwargs):
    rows, cursor = [], None
    for _ in range(MAX_PAGES):
        page = get_many(
            **kwargs,
            request_options=deadline.options(),
            **({"cursor": cursor} if cursor else {}),
        )
        rows.extend(page.data)
        cursor = getattr(getattr(page, "meta", None), "cursor", None)
        if not cursor:
            return rows
    raise ValueError(
        "Score export pagination limit reached; verification is incomplete"
    )


def _publish_scores(
    run_id,
    case_id,
    checks,
    observed,
    *,
    case_definition,
    visibility_timeout=30,
    total_timeout=40,
):
    """Synchronous implementation; production callers use publish_scores below."""
    from langfuse.api.scores.types.create_score_request import CreateScoreRequest

    deadline = Deadline(total_timeout)
    if os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() != "true" or not all(
        os.getenv(k)
        for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
    ):
        raise ValueError("Enable Langfuse and configure project keys and base URL")
    if case_definition.get("id") != case_id:
        raise ValueError("Evaluation case identity does not match")
    if len({c.name for c in checks}) != len(checks) or any(
        c.passed is not None and not isinstance(c.passed, bool) for c in checks
    ):
        raise ValueError(
            "Evaluation checks must have unique names and boolean or unknown values"
        )
    manifest = provenance(case_definition)
    client = _api_client()
    flow = observed.get("workflow") or {}
    fingerprint = result_fingerprint(observed)
    # Allow ingestion lag, without extending the global deadline or using an old root.
    lookup_end = min(deadline.end, time.monotonic() + 30)
    while True:
        roots = _all_pages(
            client.observations.get_many,
            deadline,
            session_id=run_id,
            name="ui-claim-workflow",
            is_root_observation=True,
            limit=100,
            fields="basic,io,trace_context",
        )
        complete = [
            r for r in roots if r.start_time is not None and r.end_time is not None
        ]
        root = max(complete, key=lambda r: r.start_time) if complete else None
        output = getattr(root, "output", None)
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except (ValueError, TypeError):
                output = None
        matches = (
            root is not None
            and isinstance(output, dict)
            and (
                output.get("status") == flow.get("phase")
                and output.get("route") == flow.get("route")
                and output.get("artifact_version") is not None
                and output.get("artifact_version") == flow.get("version")
                and output.get("result_fingerprint") == fingerprint
            )
        )
        if matches:
            break
        if time.monotonic() >= lookup_end:
            raise TraceNotVisibleOrMismatched(
                "Latest trace does not match the saved workflow state; scores were not sent"
            )
        time.sleep(min(0.5, max(0, lookup_end - time.monotonic())))
    trace_id = getattr(root, "trace_id", None)
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("Trace identity is missing; scores were not sent")
    environment = getattr(root, "environment", None)
    if not isinstance(environment, str) or not environment.strip():
        raise ValueError("Trace environment is missing; scores were not sent")
    timestamp = root.start_time.astimezone(UTC)
    metadata = manifest | {
        "artifact_version": flow["version"],
        "result_fingerprint": fingerprint,
        "source_release": getattr(root, "release", None) or "unknown",
    }
    identity = f"{EVALUATOR_VERSION}:{manifest['evaluator_sha256']}:{manifest['case_sha256']}:{root.trace_id}"
    submitted = []
    for c in checks:
        if c.passed is not None:
            submitted.append(
                CreateScoreRequest(
                    id=str(uuid5(NAMESPACE_URL, identity + ":" + c.name)),
                    trace_id=root.trace_id,
                    name="ui_eval_" + c.name,
                    value=float(c.passed),
                    data_type="BOOLEAN",
                    environment=environment,
                    timestamp=timestamp,
                    metadata=metadata,
                    comment="Fictional UI scenario; semantic checks require artifact-bound human annotation.",
                )
            )
    unscored = sum(c.passed is None for c in checks)
    submitted.append(
        CreateScoreRequest(
            id=str(uuid5(NAMESPACE_URL, identity + ":unscored_count")),
            trace_id=root.trace_id,
            name="ui_eval_unscored_count",
            value=unscored,
            data_type="NUMERIC",
            environment=environment,
            timestamp=timestamp,
            metadata=metadata,
            comment="Checks lacking a measurement or human annotation; not passes or failures.",
        )
    )
    report = {
        "trace_id": root.trace_id,
        "environment": environment,
        "score_timestamp": timestamp.isoformat(),
        "submitted_checks": len(submitted),
        "unscored_checks": unscored,
        "provenance": metadata,
    }
    response = client.scores.create(
        request=submitted, request_options=deadline.options()
    )
    # A partially accepted batch is NOT a successful export and must not be blindly replayed.
    if hasattr(response, "rejected"):
        return report | {
            "status": "partially_accepted",
            "accepted": response.accepted,
            "rejected": response.rejected,
        }
    if getattr(response, "message", None) != "Accepted":
        return report | {"status": "acceptance_unconfirmed"}
    visibility_end = min(deadline.end, time.monotonic() + visibility_timeout)
    while True:
        visible = _all_pages(
            client.scores.get_many,
            deadline,
            trace_id=root.trace_id,
            limit=100,
            fields="details,subject",
        )
        verified = True
        for expected in submitted:
            candidates = [s for s in visible if s.id == expected.id]
            if len(candidates) != 1:
                verified = False
                break
            actual = candidates[0]
            subject = getattr(actual, "subject", None)
            actual_time = getattr(actual, "timestamp", None)
            if (
                actual.value != expected.value
                or getattr(actual, "name", None) != expected.name
                or getattr(actual, "data_type", None) != expected.data_type
                or getattr(actual, "environment", None) != environment
                or actual_time is None
                or actual_time.astimezone(UTC).date() != timestamp.date()
                or getattr(subject, "kind", None) != "trace"
                or getattr(subject, "id", None) != root.trace_id
                or any(
                    (getattr(actual, "metadata", None) or {}).get(k) != v
                    for k, v in metadata.items()
                )
            ):
                verified = False
                break
        if verified or time.monotonic() >= visibility_end:
            return report | {
                "status": "verified" if verified else "submitted_not_yet_visible"
            }
        time.sleep(min(0.5, max(0, visibility_end - time.monotonic())))


def _run_child(command, payload, timeout, env):
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timed_out", "delivery": "unknown"}
    # Never expose SDK response bodies, credentials or child tracebacks.
    if result.returncode:
        return {"status": "export_failed", "delivery": "unknown"}
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        return {"status": "export_failed", "delivery": "unknown"}
    return (
        report
        if isinstance(report, dict) and "status" in report
        else {"status": "export_failed"}
    )


def publish_scores(
    run_id,
    case_id,
    checks,
    observed,
    *,
    case_definition=None,
    visibility_timeout=30,
    total_timeout=45,
):
    if not math.isfinite(total_timeout) or not 1 <= total_timeout <= 120:
        raise ValueError("Export timeout must be between 1 and 120 seconds")
    if (
        not math.isfinite(visibility_timeout)
        or not 0 <= visibility_timeout <= total_timeout
    ):
        raise ValueError("Visibility timeout must be within the total export timeout")
    if case_definition is None:
        from ui_workflow_eval import DEFAULT_DATASET, load_case

        case_definition = load_case(DEFAULT_DATASET, case_id)
    payload = {
        "run_id": run_id,
        "case_id": case_id,
        "checks": [asdict(c) for c in checks],
        "observed": observed,
        "case_definition": case_definition,
        "visibility_timeout": visibility_timeout,
        "total_timeout": max(0.5, total_timeout - 1),
    }
    allowed = {
        "PATH",
        "HOME",
        "SYSTEMROOT",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "LANGFUSE_TRACING_ENABLED",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
    }
    env = {k: v for k, v in os.environ.items() if k in allowed}
    return _run_child(
        [sys.executable, str(Path(__file__).resolve())], payload, total_timeout, env
    )


def _child_main():
    try:
        payload = json.load(sys.stdin)
        payload["checks"] = [Check(**c) for c in payload["checks"]]
        result = _publish_scores(**payload)
    except TraceNotVisibleOrMismatched:
        result = {"status": "trace_not_visible_or_mismatched", "delivery": "not_sent"}
    except ExportDeadlineExceeded:
        result = {"status": "timed_out", "delivery": "unknown"}
    except Exception:  # noqa: BLE001 - sanitize the isolated SDK process boundary
        result = {"status": "export_failed", "delivery": "unknown"}
    return result


if __name__ == "__main__":
    print(json.dumps(_child_main()), flush=True)
