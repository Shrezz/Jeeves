"""Provision a named operations dashboard using the Langfuse CLI (no embedded secrets).

Run using the API venv with LANGFUSE_* configured and pnpm on PATH. Reuses named
widgets/dashboard and existing placements. Does not alter the project's default.
The unstable dashboard API is intentionally confined to this provisioning script.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def api(resource, action, *args, body=None):
    env = {**os.environ, "LANGFUSE_HOST": os.environ["LANGFUSE_BASE_URL"]}
    with tempfile.TemporaryDirectory() as d:
        command = [
            "pnpm",
            "dlx",
            "langfuse-cli",
            "api",
            resource,
            action,
            *args,
            "--json",
        ]
        if body is not None:
            p = Path(d) / "body.json"
            p.write_text(json.dumps(body))
            command += ["--body-file", str(p)]
        try:
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            value = json.loads(result.stdout)
        except (subprocess.TimeoutExpired, ValueError) as exc:
            raise RuntimeError(
                f"{resource}/{action}: command did not return valid JSON"
            ) from exc
        status = value.get("status", 500) if isinstance(value, dict) else 500
        if (
            result.returncode
            or not isinstance(status, int)
            or not 200 <= status < 300
            or status == 207
        ):
            # Provider response bodies are not safe operational log messages.
            raise RuntimeError(f"{resource}/{action}: command failed (HTTP {status})")
        return value["body"]


def list_all(resource):
    rows = []
    for page in range(1, 101):
        batch = api(resource, "list", "--page", str(page), "--limit", "50")["data"]
        rows.extend(batch)
        if len(batch) < 50:
            return rows
    raise RuntimeError(
        f"{resource}: pagination limit reached; refusing duplicate creation"
    )


def named(rows, name):
    matches = [row for row in rows if row["name"] == name]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple objects named {name}; resolve before provisioning"
        )
    return matches[0] if matches else None


def widget_definition(widget):
    """Compare authored fields, allowing the documented default chart config.

    API IDs/timestamps and future response-only fields do not change the chart.
    The API fills chartConfig.type from chartType when chartConfig is omitted.
    """
    definition = {
        key: widget.get(key)
        for key in ("name", "view", "dimensions", "metrics", "filters", "chartType")
    }
    definition["description"] = widget.get("description") or ""
    definition["chartConfig"] = {
        "type": widget.get("chartType"),
        **(widget.get("chartConfig") or {}),
    }
    return definition


def placements(detail):
    """Current deployments may expose placements in either or both locations."""
    rows = list((detail.get("definition") or {}).get("widgets") or [])
    rows.extend(detail.get("placements") or [])
    by_id = {}
    for row in rows:
        placement_id = row.get("id")
        if not isinstance(placement_id, str) or not placement_id:
            raise RuntimeError("Dashboard returned a placement without an ID")
        previous = by_id.get(placement_id)
        if previous and previous.get("widgetId") != row.get("widgetId"):
            raise RuntimeError("Dashboard returned conflicting placement IDs")
        by_id[placement_id] = row
    return list(by_id.values())


def allocate_placement_id(widget_id, occupied_ids):
    stem = "jeeves-ops-" + hashlib.sha256(widget_id.encode()).hexdigest()[:16]
    candidate = stem
    suffix = 0
    while candidate in occupied_ids:
        suffix += 1
        candidate = f"{stem}-{suffix}"
    occupied_ids.add(candidate)
    return candidate


def scope_quality_widgets(spec, evaluator_sha256):
    """Keep incompatible evaluator implementations out of the same quality aggregate."""
    if (
        not isinstance(evaluator_sha256, str)
        or len(evaluator_sha256) != 64
        or any(char not in "0123456789abcdef" for char in evaluator_sha256)
    ):
        raise ValueError("Evaluator fingerprint must be a SHA256 hex digest")
    resolved = copy.deepcopy(spec)
    for widget in resolved["widgets"]:
        if not widget["view"].startswith("scores-"):
            continue
        widget["filters"] = [
            item
            for item in widget["filters"]
            if not (
                item.get("column") == "metadata"
                and item.get("key") == "evaluator_sha256"
            )
        ]
        widget["filters"].append(
            {
                "column": "metadata",
                "key": "evaluator_sha256",
                "type": "stringObject",
                "operator": "=",
                "value": evaluator_sha256,
            }
        )
    return resolved


def current_evaluator_fingerprint():
    # Keep this script runnable directly from the API venv, like the eval exporters.
    evals_path = str(Path(__file__).resolve().parents[1])
    sys.path.insert(0, evals_path)
    try:
        from score_export import evaluator_fingerprint

        return evaluator_fingerprint()
    finally:
        sys.path.remove(evals_path)


def provision(spec, *, evaluator_sha256=None):
    spec = scope_quality_widgets(
        spec,
        evaluator_sha256
        if evaluator_sha256 is not None
        else current_evaluator_fingerprint(),
    )
    definitions = spec["widgets"]
    names = [definition["name"] for definition in definitions]
    if len(names) != len(set(names)):
        raise ValueError("Dashboard spec contains duplicate widget names")
    existing = list_all("unstable-dashboards")
    dashboard = named(existing, spec["name"])
    widgets = list_all("unstable-dashboard-widgets")
    # Detect ambiguous names before mutating any dashboard or widget.
    for definition in definitions:
        named(widgets, definition["name"])
    if dashboard is None:
        dashboard = api(
            "unstable-dashboards",
            "create",
            body={k: spec[k] for k in ("name", "description")},
        )
    elif dashboard.get("description") != spec["description"]:
        api(
            "unstable-dashboards",
            "update",
            dashboard["id"],
            body={"description": spec["description"]},
        )
    detail = api("unstable-dashboards", "get", dashboard["id"])
    existing_placements = placements(detail)
    placed = {p.get("widgetId") for p in existing_placements}
    occupied_ids = {p["id"] for p in existing_placements}
    # Add below existing user-arranged content rather than reusing index positions.
    next_y = max(
        (p.get("y", 0) + p.get("height", 0) for p in existing_placements), default=0
    )
    added = 0
    expected = {}
    for definition in definitions:
        widget = named(widgets, definition["name"])
        if widget is None:
            widget = api("unstable-dashboard-widgets", "create", body=definition)
        elif widget_definition(widget) != widget_definition(definition):
            widget = api(
                "unstable-dashboard-widgets", "update", widget["id"], body=definition
            )
        expected[widget["id"]] = widget_definition(definition)
        if widget["id"] not in placed:
            api(
                "unstable-dashboards",
                "add-placement",
                dashboard["id"],
                body={
                    "type": "widget",
                    "widgetId": widget["id"],
                    "id": allocate_placement_id(widget["id"], occupied_ids),
                    "x": (added % 2) * 6,
                    "y": next_y + (added // 2) * 6,
                    "width": 6,
                    "height": 6,
                },
            )
            placed.add(widget["id"])
            added += 1
    saved = api("unstable-dashboards", "get", dashboard["id"])
    actual_ids = {item.get("widgetId") for item in placements(saved)}
    if not expected.keys() <= actual_ids:
        raise RuntimeError("Dashboard did not persist all required widget placements")
    if saved.get("description") != spec["description"]:
        raise RuntimeError("Dashboard did not persist its description")
    for widget_id, definition in expected.items():
        saved_widget = api("unstable-dashboard-widgets", "get", widget_id)
        if widget_definition(saved_widget) != definition:
            raise RuntimeError("Dashboard widget definition did not persist")
    return {"dashboard_id": dashboard["id"], "widgets": len(expected), "verified": True}


def main():
    spec = json.loads(Path(__file__).with_name("dashboard.json").read_text())
    print(json.dumps(provision(spec)))


if __name__ == "__main__":
    main()
