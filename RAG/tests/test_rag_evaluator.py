import importlib.util
from pathlib import Path

import pytest


def load_suite():
    path = Path(__file__).resolve().parents[2] / "evals/rag_suite.py"
    spec = importlib.util.spec_from_file_location("rag_suite", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scorer():
    return load_suite().assess_retrieval


def test_retrieval_requires_matching_page_and_source_text():
    evaluate = scorer()
    case = {"page": 2, "expected_text": "W-17"}
    pages = ["declarations", "Policy clause W-17 applies"]
    assert evaluate(case, [{"page": 2, "excerpt": "Clause W-17"}], pages)["pass"]
    assert not evaluate(case, [{"page": 1, "excerpt": "Clause W-17"}], pages)["pass"]
    assert not evaluate(case, [{"page": 2, "excerpt": "unrelated"}], pages)["pass"]
    assert not evaluate(case, [{"page": 2, "excerpt": "invented W-17"}], ["a", "b"])["pass"]
    assert not evaluate(case, [{"page": 2, "excerpt": "invented W-17"}], pages)["pass"]
    assert not evaluate(case, [{"page": 3, "excerpt": "W-17"}], pages)["citation_page_valid"]


def test_unsupported_topic_is_only_a_retrieval_check():
    evaluate = scorer()
    case = {"expected_absent": "earthquake"}
    result = evaluate(case, [{"page": 1, "excerpt": "wind damage"}], ["wind damage"])
    assert result["pass"] is True
    assert result["answer_abstention"] is None
    assert evaluate(case, [], ["wind damage"])["pass"] is None
    assert not evaluate(case, [{"page": 1, "excerpt": "earthquake covered"}], ["wind damage"])[
        "pass"
    ]


def test_dataset_rejects_duplicate_and_contradictory_labels():
    module = load_suite()
    case = {"id": "test", "question": "What?", "page": 1, "expected_text": "wind"}
    module.validate_cases([case], ["wind"])
    with pytest.raises(ValueError, match="unique"):
        module.validate_cases([case, case], ["wind"])
    with pytest.raises(ValueError, match="not on"):
        module.validate_cases([case], ["rain"])
    with pytest.raises(ValueError, match="present"):
        module.validate_cases(
            [{"id": "test", "question": "What?", "expected_absent": "wind"}], ["wind"]
        )


def test_embedding_checks_reject_empty_nonfinite_and_mismatched_vectors():
    evaluate = load_suite().embedding_metrics
    assert evaluate([1.0, 0.0], [1.0, 0.0])["repeat_max_abs_difference"] == 0
    assert not evaluate([], [])["dimensions_match"]
    assert not evaluate([1.0, 2.0], [1.0])["dimensions_match"]
    assert not evaluate([float("nan")], [float("nan")])["finite"]
    assert not evaluate([0.0], [0.0])["nonzero"]
    assert evaluate(["invalid"], ["invalid"])["repeat_max_abs_difference"] is None
