"""Deterministic checks for the claim companion evaluation scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool | None
    expected: Any
    actual: Any


def evaluate(expected: dict[str, Any], actual: dict[str, Any]) -> list[Check]:
    """Compare expected fields against the workflow output's matching fields.

    Use exact code checks for routing, arithmetic, and action gates. Review
    whether cited text supports an explanation with a human rubric.
    """
    checks: list[Check] = []
    for name, expected_value in expected.items():
        if name == "citation_required":
            actual_value = bool(actual.get("citations"))
        elif name == "human_approval_required":
            actual_value = bool(actual.get("approval_required"))
        else:
            actual_value = actual.get(name)
        measured = name in actual or name in {
            "citation_required",
            "human_approval_required",
        }
        checks.append(
            Check(
                name,
                actual_value == expected_value if measured else None,
                expected_value,
                actual_value,
            )
        )
    return checks
