"""Exercise dashboard reconciliation without writing to the live Langfuse project."""

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO / "evals" / "monitoring" / "provision_dashboard.py"
module_spec = importlib.util.spec_from_file_location("provision_dashboard", MODULE_PATH)
dashboard = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(dashboard)
SPEC = json.loads(MODULE_PATH.with_name("dashboard.json").read_text())
FINGERPRINT = "a" * 64


class DashboardAPI:
    """Server-shaped state; responses can acknowledge writes without persisting them."""

    def __init__(self):
        self.dashboard = {"id": "d1", "name": SPEC["name"], "description": SPEC["description"]}
        self.widgets = {}
        self.placements = []
        self.calls = []
        self.discard_widget_updates = False
        self.discard_placements = False

    def __call__(self, resource, action, *args, body=None):
        self.calls.append((resource, action, args, copy.deepcopy(body)))
        if resource == "unstable-dashboards":
            if action == "list":
                return {"data": [copy.deepcopy(self.dashboard)]}
            if action == "get":
                return {
                    **copy.deepcopy(self.dashboard),
                    "definition": {"widgets": copy.deepcopy(self.placements)},
                    "placements": None,
                }
            if action == "update":
                self.dashboard.update(body)
                return copy.deepcopy(self.dashboard)
            if action == "add-placement":
                assert body["id"] not in {p["id"] for p in self.placements}
                if not self.discard_placements:
                    self.placements.append(copy.deepcopy(body))
                return copy.deepcopy(body)
        if resource == "unstable-dashboard-widgets":
            if action == "list":
                return {"data": copy.deepcopy(list(self.widgets.values()))}
            if action == "create":
                widget_id = f"w{len(self.widgets) + 1}"
                self.widgets[widget_id] = {"id": widget_id, **copy.deepcopy(body)}
                return copy.deepcopy(self.widgets[widget_id])
            if action == "update":
                response = {**self.widgets[args[0]], **copy.deepcopy(body)}
                if not self.discard_widget_updates:
                    self.widgets[args[0]] = response
                return response
            if action == "get":
                saved = copy.deepcopy(self.widgets[args[0]])
                # Documented API default plus unrelated response-only properties.
                saved.setdefault("chartConfig", {"type": saved["chartType"]})
                return {**saved, "createdAt": "2026-01-01T00:00:00Z"}
        raise AssertionError((resource, action))


@pytest.fixture
def api(monkeypatch):
    fake = DashboardAPI()
    monkeypatch.setattr(dashboard, "api", fake)
    return fake


def test_quality_tiles_separate_evaluator_versions_and_implementations():
    original = copy.deepcopy(SPEC)
    first = dashboard.scope_quality_widgets(SPEC, FINGERPRINT)
    changed = dashboard.scope_quality_widgets(first, "b" * 64)
    assert SPEC == original
    quality = [w for w in changed["widgets"] if w["view"].startswith("scores-")]
    assert {w["name"] for w in quality} == {
        "Jeeves · Measured check pass rates",
        "Jeeves · Unscored checks",
    }
    for widget in quality:
        filters = {f.get("key"): f["value"] for f in widget["filters"] if f["column"] == "metadata"}
        assert filters == {"evaluator_version": "jeeves-ui-v2", "evaluator_sha256": "b" * 64}
        assert sum(f.get("key") == "evaluator_sha256" for f in widget["filters"]) == 1


def test_warning_tiles_distinguish_final_outcomes_from_intermediate_warnings():
    widgets = {w["name"]: w for w in SPEC["widgets"]}
    expected_filters = {
        "Jeeves · Warning observations by operation": {"level": "WARNING"},
        "Jeeves · Blocked packet requests": {
            "level": "WARNING",
            "name": "ui-claim-workflow",
            "isRootObservation": True,
        },
        "Jeeves · Abstained answers": {"level": "WARNING", "name": "chat-guidance"},
    }
    for name, filters in expected_filters.items():
        widget = widgets[name]
        assert widget["view"] == "observations"
        assert {f["column"]: f["value"] for f in widget["filters"]} == filters
        assert widget["metrics"] == [{"measure": "count", "agg": "count"}]


def test_reconcile_is_idempotent_and_verifies_every_persisted_definition(api):
    first = dashboard.provision(SPEC, evaluator_sha256=FINGERPRINT)
    initial_writes = [
        call for call in api.calls if call[1] in {"create", "update", "add-placement"}
    ]
    api.calls.clear()
    second = dashboard.provision(SPEC, evaluator_sha256=FINGERPRINT)
    assert first == second == {"dashboard_id": "d1", "widgets": 9, "verified": True}
    assert len(initial_writes) == 18
    assert not [call for call in api.calls if call[1] in {"create", "update", "add-placement"}]
    assert len(api.widgets) == len(api.placements) == 9
    assert {
        call[2][0] for call in api.calls if call[:2] == ("unstable-dashboard-widgets", "get")
    } == set(api.widgets)


def test_successful_update_response_cannot_hide_stale_persisted_definition(api):
    dashboard.provision(SPEC, evaluator_sha256=FINGERPRINT)
    api.widgets["w1"]["metrics"] = [{"measure": "latency", "agg": "avg"}]
    api.discard_widget_updates = True
    with pytest.raises(RuntimeError, match="widget definition did not persist"):
        dashboard.provision(SPEC, evaluator_sha256=FINGERPRINT)


def test_placement_acknowledgement_is_verified_by_readback(api):
    api.discard_placements = True
    with pytest.raises(RuntimeError, match="did not persist all required widget placements"):
        dashboard.provision(SPEC, evaluator_sha256=FINGERPRINT)


def test_new_placement_ids_cannot_replace_user_placements(api):
    collision = "jeeves-ops-" + hashlib.sha256(b"w1").hexdigest()[:16]
    user_placement = {
        "id": collision,
        "widgetId": "user-widget",
        "type": "widget",
        "x": 2,
        "y": 8,
        "width": 5,
        "height": 7,
    }
    api.placements = [copy.deepcopy(user_placement)]
    dashboard.provision(SPEC, evaluator_sha256=FINGERPRINT)
    assert api.placements[0] == user_placement
    first = next(p for p in api.placements if p["widgetId"] == "w1")
    assert first["id"] == collision + "-1"
    assert all(p["y"] >= 15 for p in api.placements[1:])
    assert len({p["id"] for p in api.placements}) == 10


def test_placement_response_locations_are_normalized_and_conflicts_rejected():
    placement = {"id": "p1", "widgetId": "w1"}
    assert dashboard.placements({"definition": {"widgets": None}, "placements": None}) == []
    assert dashboard.placements(
        {"definition": {"widgets": [placement]}, "placements": [placement]}
    ) == [placement]
    with pytest.raises(RuntimeError, match="conflicting placement IDs"):
        dashboard.placements(
            {
                "definition": {"widgets": [placement]},
                "placements": [{"id": "p1", "widgetId": "w2"}],
            }
        )


def test_duplicate_names_fail_before_remote_mutations(api):
    api.widgets = {key: {"id": key, **SPEC["widgets"][0]} for key in ("w1", "w2")}
    api.dashboard["description"] = "outdated"
    with pytest.raises(RuntimeError, match="Multiple objects named"):
        dashboard.provision(SPEC, evaluator_sha256=FINGERPRINT)
    assert not [call for call in api.calls if call[1] in {"create", "update", "add-placement"}]


def test_duplicate_spec_names_fail_before_remote_requests(api):
    spec = copy.deepcopy(SPEC)
    spec["widgets"].append(spec["widgets"][0])
    with pytest.raises(ValueError, match="duplicate widget names"):
        dashboard.provision(spec, evaluator_sha256=FINGERPRINT)
    assert not api.calls


def test_invalid_fingerprint_fails_before_remote_requests(api):
    with pytest.raises(ValueError, match="SHA256"):
        dashboard.provision(SPEC, evaluator_sha256="")
    assert not api.calls


def test_listing_reconciles_names_past_first_page(monkeypatch):
    pages = []

    def fake_api(resource, action, *args):
        page = int(args[1])
        pages.append(page)
        return {"data": [{"id": str(i)} for i in range(50)] if page == 1 else [{"id": "last"}]}

    monkeypatch.setattr(dashboard, "api", fake_api)
    assert dashboard.list_all("unstable-dashboards")[-1] == {"id": "last"}
    assert pages == [1, 2]


@pytest.mark.parametrize("status", [207, 400, "invalid"])
def test_cli_failures_do_not_expose_provider_response_bodies(monkeypatch, status):
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.invalid")
    monkeypatch.setattr(
        dashboard.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"status": status, "body": "private payload"})
        ),
    )
    with pytest.raises(RuntimeError) as error:
        dashboard.api("unstable-dashboard-widgets", "get", "w1")
    assert "private payload" not in str(error.value)
    assert "command failed" in str(error.value)


def test_fingerprint_loader_removes_only_its_own_import_path(monkeypatch):
    original = list(sys.path)
    monkeypatch.setattr(sys, "path", list(original))

    def evaluator_fingerprint():
        sys.path.insert(0, "new-dependency-path")
        return FINGERPRINT

    monkeypatch.setitem(
        sys.modules, "score_export", SimpleNamespace(evaluator_fingerprint=evaluator_fingerprint)
    )
    assert dashboard.current_evaluator_fingerprint() == FINGERPRINT
    assert sys.path == ["new-dependency-path", *original]
