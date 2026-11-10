"""Human review labels must not survive edits without a matching artifact binding."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from annotation_validation import validate_annotation

FINGERPRINT = "ab" * 32


def annotation(labels=None, **changes):
    return {
        "artifact_version": 2,
        "result_fingerprint": FINGERPRINT,
        "labels": {"citation_support_human": True} if labels is None else labels,
        **changes,
    }


def validate(value, **target_changes):
    target = {"artifact_version": 2, "result_fingerprint": FINGERPRINT}
    return validate_annotation(value, **(target | target_changes))


def test_absence_is_unscored_and_never_creates_human_labels():
    assert validate(None) is None
    assert validate(annotation(labels={})) == {}


def test_matching_labels_preserve_false_and_allow_partial_review():
    supplied = annotation(labels={"explanation_correct_human": False})
    labels = validate(supplied)
    assert labels == {"explanation_correct_human": False}
    assert labels is not supplied["labels"]
    assert validate(annotation(result_fingerprint=FINGERPRINT.upper())) == {
        "citation_support_human": True
    }


@pytest.mark.parametrize(
    "supplied",
    [
        {},
        {"citation_support_human": True},
        True,
        [],
        "reviewed",
        {"artifact_version": 2, "labels": {}},
        {"artifact_version": 2, "result_fingerprint": FINGERPRINT},
        annotation(unexpected=True),
    ],
)
def test_legacy_unbound_or_malformed_envelopes_are_rejected(supplied):
    with pytest.raises(ValueError, match="must contain"):
        validate(supplied)


@pytest.mark.parametrize("version", [True, False, "2", 2.0, None])
def test_version_requires_an_integer_not_a_boolean_or_coercion(version):
    with pytest.raises(TypeError, match="must be an integer"):
        validate(annotation(artifact_version=version))


def test_same_run_after_edit_cannot_reuse_previous_human_review():
    with pytest.raises(ValueError, match="different artifact version"):
        validate(annotation(), artifact_version=3)
    with pytest.raises(ValueError, match="different saved result"):
        validate(annotation(), result_fingerprint="cd" * 32)


@pytest.mark.parametrize("digest", [None, 12, "", "a" * 63, "g" * 64, "a" * 65])
def test_fingerprint_requires_a_complete_sha256_hex_digest(digest):
    with pytest.raises(ValueError, match="SHA-256"):
        validate(annotation(result_fingerprint=digest))


@pytest.mark.parametrize(
    "labels",
    [
        [],
        True,
        {"unapproved_metric": True},
        {"citation_support_human": 1},
        {"citation_support_human": "true"},
        {"explanation_correct_human": None},
    ],
)
def test_labels_accept_only_the_existing_boolean_metric_set(labels):
    with pytest.raises(ValueError, match="supported boolean labels"):
        validate(annotation(labels=labels))


def test_invalid_target_binding_fails_closed():
    with pytest.raises(TypeError, match="must be an integer"):
        validate(annotation(), artifact_version=True)
    with pytest.raises(ValueError, match="SHA-256"):
        validate(annotation(), result_fingerprint=None)
