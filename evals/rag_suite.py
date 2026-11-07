"""Evaluate the real local Chroma/embedding pipeline with an isolated fictional PDF."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "RAG"))
from policy_rag.local_index import LocalPolicyIndex


def assess_retrieval(case, hits, source_pages):
    phrase = case["expected_text"].casefold()
    page = case["page"]
    matching = [
        i + 1
        for i, hit in enumerate(hits)
        if hit["page"] == page and phrase in hit["excerpt"].casefold()
    ]
    page_exists = 1 <= page <= len(source_pages)
    source_has_expected = page_exists and phrase in source_pages[page - 1].casefold()
    return {
        "pass": bool(matching) and source_has_expected,
        "matching_rank": matching[0] if matching else None,
        "retrieved_count": len(hits),
        "citation_page_valid": all(1 <= hit["page"] <= len(source_pages) for hit in hits),
        "source_has_expected_text": source_has_expected,
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
    policy = uuid4()
    with pymupdf.open(ROOT / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf") as document:
        source_pages = [page.get_text() for page in document]
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
        a, b = list(vectors[0]), list(vectors[1])
        report["embedding"] = {
            "dimension": len(a),
            "finite": bool(a) and all(math.isfinite(float(x)) for x in a),
            "nonzero": any(float(x) != 0 for x in a),
            "repeat_max_abs_difference": max(abs(float(x) - float(y)) for x, y in zip(a, b)),
            "model_quality": "unscored: no reviewed semantic similarity labels",
        }
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
            return sum(float(p) * float(q) for p, q in zip(x, y)) / (
                math.sqrt(sum(float(p) ** 2 for p in x)) * math.sqrt(sum(float(q) ** 2 for q in y))
            )

        report["embedding"]["synthetic_similarity_probes"] = []
        for query, positive, negative in pairs:
            q, p, n = index.embed([query, positive, negative])
            positive_score, negative_score = cosine(q, p), cosine(q, n)
            report["embedding"]["synthetic_similarity_probes"].append(
                {
                    "positive_similarity": positive_score,
                    "negative_similarity": negative_score,
                    "positive_higher": positive_score > negative_score,
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
        measured = [case for case in report["cases"] if case["pass"] is not None]
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
            "execution_errors": len(cases) - len(measured),
        }
        report["component_checks"] = {
            "ingestion_idempotent": report["ingestion"]["idempotent"],
            "embedding_finite_nonzero": report["embedding"]["finite"]
            and report["embedding"]["nonzero"],
            "embedding_repeatable": report["embedding"]["repeat_max_abs_difference"] < 1e-5,
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
                                    "page": case["page"],
                                    "expected_text": case["expected_text"],
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
