import importlib.util
from pathlib import Path


def scorer():
    path = Path(__file__).resolve().parents[2] / "evals/rag_suite.py"
    spec = importlib.util.spec_from_file_location("rag_suite", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.assess_retrieval


def test_retrieval_requires_matching_page_and_source_text():
    evaluate = scorer()
    case = {"page": 2, "expected_text": "W-17"}
    pages = ["declarations", "Policy clause W-17 applies"]
    assert evaluate(case, [{"page": 2, "excerpt": "Clause W-17"}], pages)["pass"]
    assert not evaluate(case, [{"page": 1, "excerpt": "Clause W-17"}], pages)["pass"]
    assert not evaluate(case, [{"page": 2, "excerpt": "unrelated"}], pages)["pass"]
    assert not evaluate(case, [{"page": 2, "excerpt": "invented W-17"}], ["a", "b"])["pass"]
    assert not evaluate(case, [{"page": 3, "excerpt": "W-17"}], pages)["citation_page_valid"]
