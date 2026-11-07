"""Evaluate the real local Chroma/embedding pipeline with an isolated fictional PDF."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import unicodedata
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "RAG"))
from policy_rag.local_index import LocalPolicyIndex


def assess_retrieval(case, hits, source_pages):
    def normalized(text):
        return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

    def supported(hit):
        page = hit.get("page")
        excerpt = hit.get("excerpt")
        if not (
            isinstance(page, int)
            and not isinstance(page, bool)
            and 1 <= page <= len(source_pages)
            and isinstance(excerpt, str)
            and bool(excerpt.strip())
        ):
            return False
        # Layout extraction removes page decorations and joins text blocks.
        # Require every cited token in source order, allowing omitted tokens.
        source = iter(normalized(source_pages[page - 1]).split())
        return all(any(word == token for word in source) for token in normalized(excerpt).split())

    excerpts_match = bool(hits) and all(supported(hit) for hit in hits)
    if "expected_absent" in case:
        phrase = case["expected_absent"].casefold()
        source_absent = all(phrase not in text.casefold() for text in source_pages)
        returned_absent = all(phrase not in hit["excerpt"].casefold() for hit in hits)
        return {
            "case_type": "unsupported_topic",
            "pass": source_absent and returned_absent and excerpts_match if hits else None,
            "matching_rank": None,
            "retrieved_count": len(hits),
            "citation_page_valid": bool(hits)
            and all(1 <= hit["page"] <= len(source_pages) for hit in hits),
            "source_absent": source_absent,
            "returned_text_absent": returned_absent,
            "citation_excerpt_matches_source": excerpts_match,
            "answer_abstention": None,
        }
    phrase = case["expected_text"].casefold()
    page = case["page"]
    matching = [
        i + 1
        for i, hit in enumerate(hits)
        if hit["page"] == page and phrase in hit["excerpt"].casefold() and supported(hit)
    ]
    page_exists = 1 <= page <= len(source_pages)
    source_has_expected = page_exists and phrase in source_pages[page - 1].casefold()
    return {
        "case_type": "expected_passage",
        "pass": bool(matching) and source_has_expected and excerpts_match,
        "matching_rank": matching[0] if matching else None,
        "retrieved_count": len(hits),
        "citation_page_valid": bool(hits)
        and all(1 <= hit["page"] <= len(source_pages) for hit in hits),
        "source_has_expected_text": source_has_expected,
        "citation_excerpt_matches_source": excerpts_match,
    }


def validate_cases(cases, source_pages):
    if not cases:
        raise ValueError("Dataset is empty")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each scenario must be an object")  # noqa: TRY004 - dataset validation
        case_id, question = case.get("id"), case.get("question")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError("Scenario IDs must be unique nonempty strings")
        seen.add(case_id)
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Scenario {case_id} needs a question")
        negative = "expected_absent" in case
        if negative:
            phrase = case["expected_absent"]
            if (
                not isinstance(phrase, str)
                or not phrase.strip()
                or "expected_text" in case
                or "page" in case
            ):
                raise ValueError(f"Scenario {case_id} has invalid absence expectations")
            if any(phrase.casefold() in page.casefold() for page in source_pages):
                raise ValueError(f"Scenario {case_id} expects a phrase present in the source")
        else:
            phrase, page = case.get("expected_text"), case.get("page")
            if (
                not isinstance(phrase, str)
                or not phrase.strip()
                or not isinstance(page, int)
                or isinstance(page, bool)
                or not 1 <= page <= len(source_pages)
            ):
                raise ValueError(f"Scenario {case_id} has invalid page or expected text")
            if phrase.casefold() not in source_pages[page - 1].casefold():
                raise ValueError(f"Scenario {case_id} expected text is not on its source page")


def embedding_metrics(first, second):
    a, b = list(first), list(second)
    dimensions_match = bool(a) and len(a) == len(b)
    try:
        finite = dimensions_match and all(math.isfinite(float(value)) for value in a + b)
        nonzero = (
            dimensions_match and any(float(x) != 0 for x in a) and any(float(x) != 0 for x in b)
        )
        difference = max(abs(float(x) - float(y)) for x, y in zip(a, b)) if finite else None
    except (TypeError, ValueError, OverflowError):
        finite, nonzero, difference = False, False, None
    return {
        "dimension": len(a),
        "dimensions_match": dimensions_match,
        "finite": finite,
        "nonzero": nonzero,
        "repeat_max_abs_difference": difference,
        "model_quality": "unscored: no reviewed semantic similarity labels",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals/datasets/rag_dev.jsonl")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--langfuse", action="store_true")
    parser.add_argument("--run-name", default="local-rag-dev")
    parser.add_argument(
        "--strict", action="store_true", help="Exit nonzero for measured failures or errors"
    )
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    if not cases:
        parser.error("Dataset is empty")
    if args.langfuse and (
        os.getenv("LANGFUSE_TRACING_ENABLED", "").lower() != "true"
        or not os.getenv("LANGFUSE_PUBLIC_KEY")
        or not os.getenv("LANGFUSE_SECRET_KEY")
    ):
        parser.error("Langfuse tracing and both keys are required")
    if args.langfuse and args.dataset.resolve() not in {
        (ROOT / "evals/datasets/rag_dev.jsonl").resolve(),
        (ROOT / "evals/datasets/rag_held_out.jsonl").resolve(),
    }:
        parser.error("Langfuse export is restricted to the supplied synthetic datasets")
    policy = uuid4()
    with pymupdf.open(ROOT / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf") as document:
        source_pages = [page.get_text() for page in document]
    try:
        validate_cases(cases, source_pages)
    except ValueError as exc:
        parser.error(str(exc))
    report = {"embedding_model": "all-MiniLM-L6-v2", "dataset": str(args.dataset), "cases": []}
    with tempfile.TemporaryDirectory(prefix="jeeves-rag-eval-") as temp:
        index = LocalPolicyIndex(Path(temp))
        start = perf_counter()
        count = index.index(
            "user_synthetic_a", policy, ROOT / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf"
        )
        report["ingestion"] = {
            "chunks": count,
            "elapsed_ms": round((perf_counter() - start) * 1000, 2),
            "idempotent": index.index(
                "user_synthetic_a",
                policy,
                ROOT / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf",
            )
            == count,
        }
        vectors = index.embed([cases[0]["question"], cases[0]["question"]])
        report["embedding"] = embedding_metrics(vectors[0], vectors[1])
        pairs = [
            (
                "temporary boarding after a window breaks",
                "temporary window boarding to keep rain out",
                "policy number and dates",
            ),
            (
                "damage from gradual wear",
                "gradual wear and long-term water seepage",
                "policy term and insurer name",
            ),
            (
                "deductible per covered occurrence",
                "flat deductible per covered occurrence",
                "temporary boarding receipt",
            ),
        ]

        def cosine(x, y):
            if not len(x) or len(x) != len(y):
                return None
            try:
                x, y = [float(v) for v in x], [float(v) for v in y]
                denom = math.sqrt(sum(p * p for p in x)) * math.sqrt(sum(q * q for q in y))
                value = sum(p * q for p, q in zip(x, y)) / denom if denom else None
                return value if value is not None and math.isfinite(value) else None
            except (TypeError, ValueError, OverflowError):
                return None

        report["embedding"]["synthetic_similarity_probes"] = []
        for query, positive, negative in pairs:
            q, p, n = index.embed([query, positive, negative])
            positive_score, negative_score = cosine(q, p), cosine(q, n)
            report["embedding"]["synthetic_similarity_probes"].append(
                {
                    "positive_similarity": positive_score,
                    "negative_similarity": negative_score,
                    "positive_higher": positive_score is not None
                    and negative_score is not None
                    and positive_score > negative_score,
                }
            )
        report["isolation"] = {
            "foreign_user_empty": not index.search(
                "user_synthetic_b", policy, cases[0]["question"]
            ),
            "foreign_policy_empty": not index.search(
                "user_synthetic_a", uuid4(), cases[0]["question"]
            ),
        }

        def task(case):
            start = perf_counter()
            try:
                hits = index.search("user_synthetic_a", policy, case["question"], for_chat=True)
                return {
                    "case_id": case["id"],
                    **assess_retrieval(case, hits, source_pages),
                    "elapsed_ms": round((perf_counter() - start) * 1000, 2),
                    "execution_error": False,
                }
            except Exception as exc:  # noqa: BLE001 - record per-case errors and continue
                return {"case_id": case["id"], "pass": None, "execution_error": type(exc).__name__}

        report["cases"] = [task(case) for case in cases]
        measured = [
            case
            for case in report["cases"]
            if case["pass"] is not None and case["case_type"] == "expected_passage"
        ]
        absent_cases = [
            case for case in report["cases"] if case.get("case_type") == "unsupported_topic"
        ]
        report["retrieval_summary"] = {
            "cases": len(cases),
            "measured": len(measured),
            "recall_at_returned_k": sum(case["pass"] for case in measured) / len(measured)
            if measured
            else None,
            "top_one_rate": sum(case["matching_rank"] == 1 for case in measured) / len(measured)
            if measured
            else None,
            "mean_reciprocal_rank": sum(
                1 / case["matching_rank"] if case["matching_rank"] else 0 for case in measured
            )
            / len(measured)
            if measured
            else None,
            "execution_errors": sum(bool(case["execution_error"]) for case in report["cases"]),
            "unsupported_topic_checks": len(absent_cases),
            "unsupported_topic_checks_passed": sum(case["pass"] is True for case in absent_cases),
            "unsupported_topic_checks_unscored": sum(case["pass"] is None for case in absent_cases),
        }
        report["component_checks"] = {
            "ingestion_idempotent": report["ingestion"]["idempotent"],
            "embedding_finite_nonzero": report["embedding"]["finite"]
            and report["embedding"]["nonzero"],
            "embedding_repeatable": report["embedding"]["repeat_max_abs_difference"] is not None
            and report["embedding"]["repeat_max_abs_difference"] < 1e-5,
            "synthetic_embedding_similarity": all(
                p["positive_higher"] for p in report["embedding"]["synthetic_similarity_probes"]
            ),
            "foreign_user_isolated": report["isolation"]["foreign_user_empty"],
            "foreign_policy_isolated": report["isolation"]["foreign_policy_empty"],
        }
        report["unscored"] = [
            "answer faithfulness requires human review",
            "no-answer abstention is not measured by retrieval-only tests",
            "real-world policies and live-model accuracy are not measured",
        ]
        if args.langfuse:
            from langfuse import Evaluation, get_client

            client = get_client()
            indexed = {result["case_id"]: result for result in report["cases"]}
            for name, passed in report["component_checks"].items():
                indexed[name] = {
                    "case_id": name,
                    "pass": passed,
                    "execution_error": False,
                    "citation_page_valid": True,
                    "component_check": True,
                }

            def evaluate(*, output, **kwargs):
                values = [
                    Evaluation(name="execution_error", value=float(bool(output["execution_error"])))
                ]
                if output["pass"] is not None:
                    name = (
                        "component_check_passed"
                        if output.get("component_check")
                        else "unsupported_topic_not_in_source_or_passages"
                        if output.get("case_type") == "unsupported_topic"
                        else "expected_passage_found"
                    )
                    values.append(Evaluation(name=name, value=float(output["pass"])))
                    if not output.get("component_check"):
                        values.append(
                            Evaluation(
                                name="citation_page_valid",
                                value=float(output["citation_page_valid"]),
                            )
                        )
                        values.append(
                            Evaluation(
                                name="citation_excerpt_matches_source",
                                value=float(output["citation_excerpt_matches_source"]),
                            )
                        )
                        if output.get("case_type") == "expected_passage":
                            values.append(
                                Evaluation(
                                    name="source_has_expected_text",
                                    value=float(output["source_has_expected_text"]),
                                )
                            )
                return values

            try:
                experiment = client.run_experiment(
                    name=args.run_name,
                    data=(
                        [
                            {
                                "input": case,
                                "expected_output": {
                                    k: case[k]
                                    for k in ("page", "expected_text", "expected_absent")
                                    if k in case
                                },
                            }
                            for case in cases
                        ]
                        + [
                            {"input": {"id": name}, "expected_output": {"pass": True}}
                            for name in report["component_checks"]
                        ]
                    ),
                    task=lambda *, item, **kwargs: indexed[item["input"]["id"]],
                    evaluators=[evaluate],
                    max_concurrency=1,
                )
                report["langfuse_experiment"] = experiment.format()
            finally:
                client.flush()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if args.strict and (
        any(
            not case["pass"] or not case.get("citation_page_valid", False)
            for case in report["cases"]
        )
        or not all(report["component_checks"].values())
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
