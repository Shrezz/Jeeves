"""Evaluate one existing fictional signed-in UI run without making model calls.

The local read-only adapter accepts only explicitly allowlisted claims linked to
the exact checked-in synthetic policy PDF. Human semantic labels remain unscored
unless supplied for this specific run. Optional Langfuse upload uses aggregates
and scores, not claim text.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import unicodedata
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from evaluators import Check
from psycopg.rows import dict_row
from pypdf import PdfReader
from pypdf.errors import PdfReadError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf"
DEFAULT_DATASET = ROOT / "evals/datasets/ui_dev.jsonl"


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def source_integrity(sources: list, policy_id: str, pdf: bytes) -> bool | None:
    """Validate page, policy ownership and literal excerpt, not semantic support."""
    if not sources:
        return False
    try:
        pages = PdfReader(io.BytesIO(pdf)).pages
        unknown = False
        for source in sources:
            if not isinstance(source, dict):
                return False
            page, excerpt, chunk = source.get("page"), source.get("excerpt"), source.get("chunkId")
            if (
                isinstance(page, bool)
                or not isinstance(page, int)
                or page < 1
                or page > len(pages)
                or not isinstance(excerpt, str)
                or not excerpt.strip()
                or not isinstance(chunk, str)
                or not chunk.startswith(policy_id + ":")
            ):
                return False
            page_text = pages[page - 1].extract_text() or ""
            if not page_text.strip():
                unknown = True
            elif normalized(excerpt) not in normalized(page_text):
                return False
        return None if unknown else True
    except (ValueError, TypeError, OSError, PdfReadError):
        return None


def evaluate_ui(
    case: dict, observed: dict, pdf: bytes, annotation: dict | None = None
) -> list[Check]:
    """Return only directly measured checks; never infer semantic correctness."""
    expected = case["expected"]
    flow = observed.get("workflow") or {}
    ready = observed.get("state") == "ready"
    sources = observed.get("sources") or []
    content = observed.get("content") or ""
    fields = {f.get("label"): f.get("value") for f in flow.get("fields", []) if isinstance(f, dict)}
    checks = []

    def equal(name, wanted, actual):
        checks.append(Check(name, None if actual is None else actual == wanted, wanted, actual))

    for key in ("route", "phase"):
        if key in expected:
            equal(key, expected[key], flow.get(key, "<missing>") if ready else None)
    if "citations_required" in expected:
        equal("citations_present", expected["citations_required"], bool(sources) if ready else None)
        if ready:
            integrity = source_integrity(sources, observed["policy_id"], pdf)
            equal("citation_excerpt_matches_policy_page", True, integrity)
        else:
            equal("citation_excerpt_matches_policy_page", True, None)
    for index, term in enumerate(expected.get("cited_terms", []), 1):
        actual = (
            any(
                isinstance(s, dict)
                and s.get("page") == term["page"]
                and isinstance(s.get("excerpt"), str)
                and normalized(term["text"]) in normalized(s.get("excerpt", ""))
                for s in sources
            )
            if ready
            else None
        )
        equal(f"cited_term_{index}_page_{term['page']}", True, actual)
    if "answer_term_groups" in expected:
        actual = (
            all(
                any(normalized(term) in normalized(content) for term in group)
                for group in expected["answer_term_groups"]
            )
            if ready
            else None
        )
        equal("answer_expected_terms_present", True, actual)
    if "conditional_language" in expected:
        actual = (
            bool(
                re.search(
                    r"\b(?:if|assuming|subject to|depending on|may|might|likely|conditional)\b",
                    content,
                    re.IGNORECASE,
                )
            )
            if ready
            else None
        )
        equal("conditional_language_present", expected["conditional_language"], actual)
    if "public_search_status" in expected:
        actual = (
            ((flow.get("publicWebSearch") or {}).get("status") or "not_requested")
            if ready
            else None
        )
        equal("public_search_status", expected["public_search_status"], actual)
    if expected.get("human_review_required"):
        actual = (
            bool(flow.get("phase") == "human_review" and flow.get("interruptId")) if ready else None
        )
        equal("human_review_required", True, actual)
    if "conditional_payment" in expected:
        raw = (
            fields.get("Illustrative payment if fully eligible")
            or fields.get("Estimated payment (conditional)")
            or fields.get("Estimated payment")
        )
        equal("payment_displayed", True, bool(raw) if flow.get("phase") == "human_review" else None)
        basis = fields.get("Illustration basis") or fields.get("Estimate basis")
        equal("payment_basis_displayed", True, bool(basis) if raw is not None else None)
        try:
            amount = (
                Decimal(str(raw).replace("$", "").replace(",", "")) if raw is not None else None
            )
            if amount is None:
                actual, matches = None, None
            elif not amount.is_finite():
                actual, matches = str(raw), False
            else:
                actual = str(amount)
                matches = amount == Decimal(str(expected["conditional_payment"]))
        except (InvalidOperation, ValueError):
            actual, matches = str(raw), False
        checks.append(
            Check("conditional_payment_amount", matches, expected["conditional_payment"], actual)
        )
    if "repair_status" in expected:
        actual = fields.get("Repair status") if flow.get("phase") == "human_review" else None
        equal(
            "repair_status",
            expected["repair_status"],
            actual.lower() if isinstance(actual, str) else None,
        )
        if flow.get("phase") == "human_review" and actual is None:
            # A reviewable packet that omits the clarified value failed to retain it.
            checks[-1] = Check("repair_status", False, expected["repair_status"], None)
    if expected.get("manual_review"):
        for name in ("citation_support_human", "explanation_correct_human"):
            value = (annotation or {}).get(name)
            value = value if isinstance(value, bool) else None
            equal(name, True, value)
    return checks


def load_case(dataset: Path, case_id: str) -> dict:
    cases = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matches = [case for case in cases if case.get("id") == case_id]
    if len(matches) != 1:
        raise ValueError("Case ID must identify exactly one dataset entry")
    return matches[0]


def load_observation(url: str, run_id: str, allowlisted_claims: set[str]) -> tuple[dict, bytes]:
    """Fetch a run only from the explicit synthetic allowlist and fixture policy."""
    run = str(UUID(run_id))
    if not allowlisted_claims:
        raise ValueError("Set JEEVES_SYNTHETIC_TRACE_CLAIM_IDS for explicitly fictional claims")
    allowed = [str(UUID(item)) for item in allowlisted_claims]
    with psycopg.connect(
        url, autocommit=True, options="-c default_transaction_read_only=on", row_factory=dict_row
    ) as db:
        row = db.execute(
            """SELECT g.claim_id::text, c.policy_id::text, g.state, g.content, g.sources,
                      g.workflow, m.content AS message, d.content AS policy_pdf
               FROM public.claim_guidance g
               JOIN public.claims c ON c.id=g.claim_id
               JOIN public.claim_messages m ON m.id=g.message_id AND m.claim_id=c.id
               JOIN public.policies p ON p.id=c.policy_id AND p.owner_id=c.owner_id
               JOIN public.policy_documents d ON d.policy_id=p.id
               WHERE g.id=%s AND g.claim_id=ANY(%s::uuid[])""",
            (run, allowed),
        ).fetchone()
    if not row:
        raise ValueError("Run not found in an allowlisted fictional claim with a policy PDF")
    pdf = bytes(row.pop("policy_pdf"))
    if hashlib.sha256(pdf).digest() != hashlib.sha256(FIXTURE.read_bytes()).digest():
        raise ValueError("The selected policy is not the exact checked-in fictional fixture")
    return row, pdf


def publish_scores(run_id: str, case_id: str, checks: list[Check], observed: dict) -> dict:
    if os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() != "true" or not all(
        os.getenv(key) for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    ):
        raise ValueError("Enable Langfuse and provide both project keys to export scores")
    from langfuse import get_client

    client = get_client()
    roots = client.api.observations.get_many(
        session_id=run_id, name="ui-claim-workflow", limit=100, fields="basic,io"
    ).data
    complete = [root for root in roots if root.end_time is not None and root.start_time is not None]
    if not complete:
        raise ValueError("No completed Langfuse UI trace found for this run")
    root = max(complete, key=lambda item: item.start_time)
    try:
        output = json.loads(root.output) if isinstance(root.output, str) else root.output
    except (ValueError, TypeError):
        output = None
    flow = observed.get("workflow") or {}
    if (
        not isinstance(output, dict)
        or output.get("status") != flow.get("phase")
        or output.get("route") != flow.get("route")
    ):
        raise ValueError(
            "Latest trace does not match the saved workflow state; scores were not sent"
        )
    submitted = set()
    for check in checks:
        if check.passed is None:
            continue
        score_id = str(uuid5(NAMESPACE_URL, f"ui-eval-v1:{root.trace_id}:{case_id}:{check.name}"))
        client.create_score(
            trace_id=root.trace_id,
            name="ui_eval_" + check.name,
            value=float(check.passed),
            data_type="BOOLEAN",
            score_id=score_id,
            comment="Fictional UI scenario; 1=pass, 0=fail. Semantic checks require human annotation.",
        )
        submitted.add(score_id)
    unscored = sum(check.passed is None for check in checks)
    count_id = str(uuid5(NAMESPACE_URL, f"ui-eval-v1:{root.trace_id}:{case_id}:unscored_count"))
    client.create_score(
        trace_id=root.trace_id,
        name="ui_eval_unscored_count",
        value=unscored,
        data_type="NUMERIC",
        score_id=count_id,
        comment="Checks lacking a measurement or human annotation; not passes or failures.",
    )
    submitted.add(count_id)
    client.flush()
    visible = client.api.scores.get_many(trace_id=root.trace_id, limit=100).data
    verified = submitted.issubset({score.id for score in visible})
    return {
        "trace_id": root.trace_id,
        "submitted_checks": len(submitted),
        "unscored_checks": unscored,
        "status": "verified" if verified else "submitted_not_yet_visible",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--annotations", type=Path, help="Human labels keyed by exact run ID")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--langfuse", action="store_true", help="Attach measured scores to the latest trace"
    )
    parser.add_argument(
        "--fail-on-failed", action="store_true", help="Exit nonzero on a failed check"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Also fail when any check is unscored"
    )
    args = parser.parse_args()
    url = os.getenv("UI_EVAL_DATABASE_URL")
    if not url:
        parser.error("Set UI_EVAL_DATABASE_URL for the local synthetic database")
    try:
        case = load_case(args.dataset, args.case_id)
        allowed = {
            item.strip()
            for item in os.getenv("JEEVES_SYNTHETIC_TRACE_CLAIM_IDS", "").split(",")
            if item.strip()
        }
        observed, pdf = load_observation(url, args.run_id, allowed)
        if not all(
            normalized(term) in normalized(observed["message"] or "")
            for term in case.get("message_terms", [])
        ):
            raise ValueError("The run message does not match this synthetic case")
        labels = json.loads(args.annotations.read_text()) if args.annotations else {}
        if not isinstance(labels, dict):
            raise TypeError("Human annotations must be a JSON object keyed by run ID")
        annotation = labels.get(str(UUID(args.run_id)))
        if annotation is not None and (
            not isinstance(annotation, dict)
            or any(not isinstance(value, bool) for value in annotation.values())
            or any(
                key not in {"citation_support_human", "explanation_correct_human"}
                for key in annotation
            )
        ):
            raise ValueError(
                "Human annotations must contain only supported boolean labels for the run"
            )
        checks = evaluate_ui(case, observed, pdf, annotation)
        report = {
            "case_id": args.case_id,
            "run_id": str(UUID(args.run_id)),
            "checks": [asdict(check) for check in checks],
            "passed_checks": sum(c.passed is True for c in checks),
            "failed_checks": sum(c.passed is False for c in checks),
            "unscored_checks": sum(c.passed is None for c in checks),
            "limitations": [
                "Exact quote and keyword checks do not prove semantic faithfulness.",
                "This evaluates an existing run; it does not execute a model or establish general accuracy.",
            ],
        }
        if args.langfuse:
            report["langfuse"] = publish_scores(
                str(UUID(args.run_id)), args.case_id, checks, observed
            )
        result = json.dumps(report, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result + "\n", encoding="utf-8")
        print(result)
        return int(
            (args.fail_on_failed and report["failed_checks"] > 0)
            or (args.strict and (report["failed_checks"] > 0 or report["unscored_checks"] > 0))
        )
    except (ValueError, KeyError, TypeError, OSError, psycopg.Error) as exc:
        print("Evaluation failed:", str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
