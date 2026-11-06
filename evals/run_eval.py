"""Evaluation runner scaffold; connect `run_case` to the API workflow service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluators import evaluate


def run_case(case_input: dict[str, Any]) -> dict[str, Any]:
    """Call the same request/workflow service used by the web API.

    Replace this placeholder once the backend workflow contract is agreed.
    """
    raise NotImplementedError("Wire run_case to the backend workflow service")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path, help="Path to a JSONL dataset")
    args = parser.parse_args()

    total = passed = 0
    with args.dataset.open(encoding="utf-8") as dataset_file:
        for line in dataset_file:
            if not line.strip():
                continue
            case = json.loads(line)
            actual = run_case(case["input"])
            checks = evaluate(case["expected"], actual)
            total += len(checks)
            passed += sum(check.passed for check in checks)
            print(case["id"], [(check.name, check.passed) for check in checks])
    print(f"Passed {passed}/{total} checks")


if __name__ == "__main__":
    main()
