"""Evaluate observable evidence; missing measurements remain unscored."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool | None
    expected: Any
    actual: Any


def evaluate(expected: dict[str, Any], actual: dict[str, Any]) -> list[Check]:
    checks = []
    for name, expected_value in expected.items():
        key = {
            "citation_required": "citations",
            "human_approval_required": "approval_required",
        }.get(name, name)
        if key not in actual or actual[key] is None:
            checks.append(Check(name, None, expected_value, None))
            continue
        observed = actual[key]
        if name == "citation_required":
            observed = bool(observed)
        if name == "estimated_payment":
            try:
                equal = Decimal(str(observed)) == Decimal(str(expected_value))
            except InvalidOperation:
                equal = False
        else:
            equal = observed == expected_value
        checks.append(Check(name, equal, expected_value, observed))
    return checks
