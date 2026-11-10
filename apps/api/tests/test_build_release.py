"""Release identities cover source paths/bytes while excluding secrets and runtime data."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import build_release as release_module
from build_release import REQUIRED_MANIFESTS, SOURCE_TREES, build_release


def write(root, relative, content="source"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


@pytest.fixture
def repo(tmp_path):
    for relative, extensions in SOURCE_TREES:
        suffix = ".py" if extensions == frozenset({".py"}) else ".ts"
        write(tmp_path, relative + "/entry" + suffix)
    write(tmp_path, "apps/web/lib/example/src/index.ts")
    write(tmp_path, "apps/web/lib/example/package.json", "{}")
    write(tmp_path, "apps/web/scripts/dev-local.mjs")
    for relative in REQUIRED_MANIFESTS:
        write(tmp_path, relative, "dependency manifest")
    return tmp_path


def test_hash_is_deterministic_and_manifest_contains_hashes_not_contents(repo):
    first = build_release(repo)
    assert first == build_release(repo)
    assert first["release"] == "jeeves-" + first["sha256"][:20]
    assert first["file_count"] == len(first["files"])
    assert [item["path"] for item in first["files"]] == sorted(
        item["path"] for item in first["files"]
    )
    assert "dependency manifest" not in json.dumps(first)
    assert str(repo) not in json.dumps(first)


@pytest.mark.parametrize(
    "relative",
    [
        "apps/api/app/entry.py",
        "RAG/policy_rag/entry.py",
        "apps/web/artifacts/api-server/src/entry.ts",
        "apps/web/artifacts/claimwise/src/entry.ts",
        "apps/web/lib/example/src/index.ts",
        "apps/web/scripts/dev-local.mjs",
        "apps/api/uv.lock",
        "apps/web/pnpm-lock.yaml",
    ],
)
def test_source_or_lockfile_change_changes_release(repo, relative):
    before = build_release(repo)["release"]
    write(repo, relative, "changed bytes")
    assert build_release(repo)["release"] != before


def test_renames_affect_hash_and_generated_runtime_code_is_included(repo):
    initial = build_release(repo)["release"]
    source = repo / "apps/web/lib/example/src/index.ts"
    source.rename(source.with_name("renamed.ts"))
    assert build_release(repo)["release"] != initial
    before = build_release(repo)["release"]
    write(repo, "apps/web/lib/example/src/generated/api.ts", "export const generated = true")
    assert build_release(repo)["release"] != before


def test_environment_customer_data_dependencies_and_build_outputs_are_excluded(repo):
    before = build_release(repo)
    for relative in [
        ".env",
        "apps/web/.env.local",
        "apps/api/app/.env",
        "data/customer/policy.pdf",
        "reports/customer.json",
        "apps/web/node_modules/vendor/index.ts",
        "apps/api/.venv/vendor.py",
        "apps/web/artifacts/api-server/dist/index.js",
        "apps/web/artifacts/claimwise/src/.cache/cached.ts",
        "apps/api/app/__pycache__/unexpected.py",
        ".git/config",
    ]:
        write(repo, relative, "private credential or customer data")
    assert build_release(repo) == before


@pytest.mark.parametrize(
    "relative",
    [
        "apps/api/app",
        "RAG/policy_rag",
        "apps/web/artifacts/api-server/src",
        "apps/web/artifacts/claimwise/src",
        "apps/web/lib",
        "apps/web/scripts",
    ],
)
def test_missing_expected_source_root_fails(repo, relative):
    path = repo / relative
    path.rename(path.with_name(path.name + "-missing"))
    with pytest.raises(ValueError, match="missing"):
        build_release(repo)


def test_missing_dependency_lock_fails(repo):
    (repo / "apps/api/uv.lock").unlink()
    with pytest.raises(ValueError, match="manifest is missing"):
        build_release(repo)


@pytest.mark.parametrize("directory", [False, True])
def test_symlinked_source_is_rejected_without_reading_target(repo, tmp_path, directory):
    target = tmp_path / "outside"
    if directory:
        target.mkdir()
        write(target, "secret.py", "never read this")
        (repo / "apps/api/app/external").symlink_to(target, target_is_directory=True)
    else:
        target.write_text("never read this")
        (repo / "apps/api/app/external.py").symlink_to(target)
    with pytest.raises(ValueError, match="Symlinked source"):
        build_release(repo)


def test_cli_writes_separate_manifest_and_only_prints_release(repo, monkeypatch, capsys):
    destination = repo / "reports/release.json"
    monkeypatch.setattr(
        sys, "argv", ["build_release", "--root", str(repo), "--output", str(destination)]
    )
    assert release_module.main() == 0
    manifest = json.loads(destination.read_text())
    assert capsys.readouterr().out.strip() == manifest["release"]
    assert build_release(repo)["release"] == manifest["release"]


def test_cli_refuses_overwriting_a_dependency_manifest(repo, monkeypatch, capsys):
    target = repo / "apps/web/package.json"
    before = target.read_bytes()
    monkeypatch.setattr(
        sys, "argv", ["build_release", "--root", str(repo), "--output", str(target)]
    )
    assert release_module.main() == 1
    assert target.read_bytes() == before
    assert "Release identification failed" in capsys.readouterr().err


def test_directory_scan_failures_cannot_silently_omit_source(repo, monkeypatch):
    def failed_walk(directory, *, followlinks, onerror=None):
        if onerror:
            onerror(PermissionError("Cannot scan source"))
        return iter(())

    monkeypatch.setattr(release_module.os, "walk", failed_walk)
    with pytest.raises(PermissionError, match="Cannot scan source"):
        build_release(repo)


def test_cli_refuses_output_path_alias_of_dependency_manifest(repo, monkeypatch, capsys):
    target = repo / "apps/web/package.json"
    before = target.read_bytes()
    alias = repo / "reports/../apps/web/package.json"
    monkeypatch.setattr(sys, "argv", ["build_release", "--root", str(repo), "--output", str(alias)])
    assert release_module.main() == 1
    assert target.read_bytes() == before
    assert "Release identification failed" in capsys.readouterr().err


def test_cli_refuses_output_through_symlink_directory(repo, monkeypatch, capsys):
    destination = repo / "outside"
    destination.mkdir()
    (repo / "output-link").symlink_to(destination, target_is_directory=True)
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_release", "--root", str(repo), "--output", str(repo / "output-link/release.json")],
    )
    assert release_module.main() == 1
    assert not (destination / "release.json").exists()
    assert "Release identification failed" in capsys.readouterr().err
