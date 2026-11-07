"""Generate Python/TypeScript domain values. Use --check to detect drift."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("domain.json")


def outputs():
    data = json.loads(SOURCE.read_text())
    python = [
        '"""Generated from packages/contracts/domain.json; do not edit."""',
        "",
        "from typing import Literal",
        "",
        "# fmt: off",
    ]
    typescript = ["// Generated from packages/contracts/domain.json; do not edit.", ""]
    for key, values in data.items():
        if key == "identity":
            continue
        values = list(values)
        name = "".join(word.title() for word in key.split("_"))
        literals = ", ".join(json.dumps(value) for value in values)
        python.append(f"{name} = Literal[{literals}]")
        typescript.extend(
            [
                f"export const {key.upper()}_VALUES = [{literals}] as const;",
                f"export type {name} = (typeof {key.upper()}_VALUES)[number];",
            ]
        )
    labels = json.dumps(data["claim_status"], indent=2)
    python.extend(["", f"CLAIM_STATUS_LABELS: dict[ClaimStatus, str] = {labels}", ""])
    typescript.extend(
        ["", f"export const CLAIM_STATUS_LABELS: Record<ClaimStatus, string> = {labels};", ""]
    )
    return {
        ROOT / "apps/api/app/schemas/domain.py": "\n".join(python),
        ROOT / "apps/web/lib/domain/src/generated.ts": "\n".join(typescript),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Regenerate domain contracts: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


if __name__ == "__main__":
    main()
