"""
evaluation.py
=============
Scores the RAG pipeline against the ground-truth answer key (Decision D12).

Usage (from the project root):
    python -m policy_rag.evaluation --ingest          # ingest test PDFs, then evaluate
    python -m policy_rag.evaluation                   # evaluate only (already ingested)
    python -m policy_rag.evaluation --limit 20        # first 20 questions only

Inputs
    config.UPLOAD_DIR       the 10 MCM_Policy_*.pdf test files
    config.ANSWER_KEY_PATH  MCM_RAG_Answer_Key_v1.xlsx ("Answer Key" sheet)

Metrics
    1. covered_accuracy   expected Yes/No/Partial/N/A equals predicted
    2. amount_accuracy    |predicted amount - expected| < $1 (dollar questions only)
    3. retrieval_recall   approximate: every expected source section is found in a
                          retrieved chunk (token overlap with heading path + text)
    4. amount_check_mismatch_rate  how often the LLM's own arithmetic disagreed

Output
    eval_results/eval_results_vN.csv (N auto-increments, never overwritten)
    plus a summary printed to the console.
"""
import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List

from openpyxl import load_workbook

from . import config
from .contracts import IngestRequest, QueryRequest
from .ingestion import ingest_policy
from .pdf_parser import parse_pdf
from .policy_identity import read_identity
from .qa import answer_with_context

STOPWORDS = {"the", "of", "and", "or", "a", "to", "for", "section", "i", "ii", "endorsement", "-", "by"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_answer_key(path: Path) -> List[Dict]:
    """Read the 'Answer Key' sheet into a list of dicts keyed by header."""
    ws = load_workbook(path, read_only=True, data_only=True)["Answer Key"]
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h) for h in rows[0]]
    return [dict(zip(headers, r)) for r in rows[1:] if r[0] is not None]


def ingest_test_policies() -> None:
    """Ingest every PDF in UPLOAD_DIR under the evaluation user id."""
    for pdf in sorted(config.UPLOAD_DIR.glob("*.pdf")):
        policy_number = read_identity(parse_pdf(pdf)).policy_number
        res = ingest_policy(IngestRequest(user_id=config.EVAL_USER_ID, policy_number=policy_number, file_name=pdf.name))
        print(f"ingested {res.file_name}: {res.chunks_stored} chunks")


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------
def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS}


def source_hit(expected_sources: str, docs) -> bool:
    """True if each expected source label overlaps (>= 60% of its tokens) with some retrieved chunk."""
    haystacks = [_tokens(d.metadata["heading_path"] + " " + d.page_content[:300]) for d in docs]
    for label in str(expected_sources).split(";"):
        need = _tokens(label)
        if need and not any(len(need & h) / len(need) >= 0.6 for h in haystacks):
            return False
    return True


def _next_output_path() -> Path:
    """eval_results_v1.csv, eval_results_v2.csv, ... (never overwrite)."""
    config.EVAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 1
    while (config.EVAL_OUTPUT_DIR / f"eval_results_v{n}.csv").exists():
        n += 1
    return config.EVAL_OUTPUT_DIR / f"eval_results_v{n}.csv"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def evaluate(limit: int = None) -> Path:
    key = load_answer_key(config.ANSWER_KEY_PATH)[:limit]
    out_rows, stats = [], {"n": 0, "cov_ok": 0, "amt_n": 0, "amt_ok": 0, "ret_ok": 0, "mismatch": 0}

    for row in key:
        exp_cov = str(row["Expected Covered (Yes / No / Partial / N/A)"]).strip()
        exp_amt = row["Expected Amount Payable"]
        result, docs = answer_with_context(QueryRequest(
            user_id=config.EVAL_USER_ID, policy_number=row["Policy Number"], question=row["Question"]))

        cov_ok = result.covered == exp_cov
        amt_ok = None
        if isinstance(exp_amt, (int, float)):
            stats["amt_n"] += 1
            amt_ok = result.amount_payable is not None and abs(result.amount_payable - exp_amt) < 1
            stats["amt_ok"] += int(amt_ok)
        ret_ok = source_hit(row["Source Section(s)"], docs)
        stats["n"] += 1
        stats["cov_ok"] += int(cov_ok)
        stats["ret_ok"] += int(ret_ok)
        stats["mismatch"] += int(result.amount_check == "mismatch")

        out_rows.append({
            "S.No": stats["n"], "Question ID": row["Question ID"], "Policy Number": row["Policy Number"],
            "Question": row["Question"], "Expected Covered": exp_cov, "Predicted Covered": result.covered,
            "Covered OK": cov_ok, "Expected Amount": exp_amt, "Predicted Amount": result.amount_payable,
            "LLM Amount": result.llm_amount, "Amount OK": amt_ok, "Amount Check": result.amount_check,
            "Retrieval Hit": ret_ok, "Expected Sources": row["Source Section(s)"],
            "Cited Sources": " | ".join(s.heading_path for s in result.sources),
            "Explanation": result.calculation_explanation, "Difficulty": row["Difficulty"],
            "Trace ID": result.trace_id,
        })
        print(f"{row['Question ID']}: covered {'OK ' if cov_ok else 'BAD'} amount {amt_ok} retrieval {ret_ok}")

    path = _next_output_path()
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    n = max(stats["n"], 1)
    print("\n================ SUMMARY ================")
    print(f"questions                 : {stats['n']}")
    print(f"covered accuracy          : {stats['cov_ok'] / n:.1%}")
    print(f"amount accuracy           : {stats['amt_ok'] / max(stats['amt_n'], 1):.1%} of {stats['amt_n']}")
    print(f"retrieval recall (approx) : {stats['ret_ok'] / n:.1%}")
    print(f"LLM arithmetic mismatches : {stats['mismatch']}")
    print(f"settings                  : TOP_K={config.TOP_K} FETCH_K={config.FETCH_K} HYBRID={config.HYBRID_ENABLED}")
    print(f"details                   : {path}")
    print(f"per-question traces       : {config.LOG_DIR / 'queries'}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate policy_rag against the answer key")
    parser.add_argument("--ingest", action="store_true", help="ingest the test PDFs first")
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N questions")
    args = parser.parse_args()
    if args.ingest:
        ingest_test_policies()
    evaluate(args.limit)
