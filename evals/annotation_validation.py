"""Bind explicit human semantic labels to the exact artifact that was reviewed.

A run can produce several artifact versions, so a run ID alone is not sufficient
provenance for a human annotation. This module validates labels; it never creates them.
"""

from __future__ import annotations

import re

_LABELS = frozenset({"citation_support_human", "explanation_correct_human"})
_ENVELOPE = frozenset({"artifact_version", "result_fingerprint", "labels"})
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")


def validate_annotation(
    annotation: dict | None,
    *,
    artifact_version: int,
    result_fingerprint: str,
) -> dict[str, bool] | None:
    """Return supplied labels only when their version and content binding match.

    No annotation means no measurement. Legacy run-only labels are rejected
    rather than silently transferred to a regenerated or edited artifact.
    """
    if annotation is None:
        return None
    if not isinstance(annotation, dict) or set(annotation) != _ENVELOPE:
        raise ValueError(
            "Human annotation must contain artifact_version, result_fingerprint, and labels"
        )
    version = annotation["artifact_version"]
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or isinstance(artifact_version, bool)
        or not isinstance(artifact_version, int)
    ):
        raise TypeError("Human annotation artifact_version must be an integer")
    if version != artifact_version:
        raise ValueError("Human annotation refers to a different artifact version")
    fingerprint = annotation["result_fingerprint"]
    if (
        not isinstance(fingerprint, str)
        or not _SHA256.fullmatch(fingerprint)
        or not isinstance(result_fingerprint, str)
        or not _SHA256.fullmatch(result_fingerprint)
    ):
        raise ValueError(
            "Human annotation result_fingerprint must be a SHA-256 hex digest"
        )
    if fingerprint.casefold() != result_fingerprint.casefold():
        raise ValueError("Human annotation refers to a different saved result")
    labels = annotation["labels"]
    if (
        not isinstance(labels, dict)
        or set(labels) - _LABELS
        or any(not isinstance(value, bool) for value in labels.values())
    ):
        raise ValueError(
            "Human annotation labels must contain only supported boolean labels"
        )
    return dict(labels)
