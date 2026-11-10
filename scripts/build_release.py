"""Identify an exact source/dependency-manifest snapshot without reading local secrets.

Imported generated source is included. Dependencies, build output, customer files,
model weights, environment files and Git internals are never part of this manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

WEB_CODE = frozenset(
    {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".mts",
        ".cts",
        ".css",
        ".scss",
        ".html",
    }
)
SOURCE_TREES = (
    ("apps/api/app", frozenset({".py"})),
    ("RAG/policy_rag", frozenset({".py"})),
    ("apps/web/artifacts/api-server/src", WEB_CODE),
    ("apps/web/artifacts/claimwise/src", WEB_CODE),
)
REQUIRED_MANIFESTS = (
    "apps/api/pyproject.toml",
    "apps/api/uv.lock",
    "RAG/requirements.txt",
    "apps/web/package.json",
    "apps/web/pnpm-lock.yaml",
    "apps/web/pnpm-workspace.yaml",
    "apps/web/artifacts/api-server/package.json",
    "apps/web/artifacts/claimwise/package.json",
    "apps/web/scripts/package.json",
)
OPTIONAL_MANIFESTS = ("apps/api/requirements-db.txt",)
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "out",
        ".next",
        ".cache",
        ".vite",
        ".pytest_cache",
        ".ruff_cache",
        "coverage",
    }
)
FORMAT = "jeeves-source-release-v1"


def _safe_stat(root: Path, path: Path):
    """Refuse allowlisted symlinks, including intermediate source directories."""
    relative = path.relative_to(root)
    current = root
    for part in (None, *relative.parts):
        if part is not None:
            current = current / part
        if current.is_symlink():
            raise ValueError("Symlinked source paths are not supported")
    return path.stat(follow_symlinks=False)


def _require_directory(root: Path, relative: str) -> Path:
    path = root / relative
    try:
        info = _safe_stat(root, path)
    except FileNotFoundError as exc:
        raise ValueError(f"Expected source root is missing: {relative}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"Expected source root is not a directory: {relative}")
    return path


def _raise_walk_error(error: OSError) -> None:
    raise error


def _walk_code(root: Path, directory: Path, extensions: frozenset[str]) -> list[Path]:
    selected = []
    for current, directories, files in os.walk(
        directory, followlinks=False, onerror=_raise_walk_error
    ):
        directories[:] = sorted(
            name
            for name in directories
            if name not in EXCLUDED_DIRS and not name.startswith(".")
        )
        for name in directories:
            _safe_stat(root, Path(current) / name)
        for name in sorted(files):
            path = Path(current) / name
            if name.startswith(".") or path.suffix not in extensions:
                continue
            if not stat.S_ISREG(_safe_stat(root, path).st_mode):
                raise ValueError("Allowlisted source must be a regular file")
            selected.append(path)
    if not selected:
        raise ValueError(
            f"Expected source root contains no code: {directory.relative_to(root)}"
        )
    return selected


def _source_paths(root: Path) -> list[Path]:
    selected = set()
    for relative, extensions in SOURCE_TREES:
        directory = _require_directory(root, relative)
        selected.update(_walk_code(root, directory, extensions))
    library_root = _require_directory(root, "apps/web/lib")
    library_sources = 0
    for package in sorted(library_root.iterdir()):
        if package.name.startswith(".") or package.name in EXCLUDED_DIRS:
            continue
        info = _safe_stat(root, package)
        if not stat.S_ISDIR(info.st_mode):
            continue
        manifest = package / "package.json"
        if manifest.exists() or manifest.is_symlink():
            if not stat.S_ISREG(_safe_stat(root, manifest).st_mode):
                raise ValueError("Package manifest must be a regular file")
            selected.add(manifest)
        source = package / "src"
        if source.exists() or source.is_symlink():
            if manifest not in selected:
                raise ValueError("A source package is missing package.json")
            directory = _require_directory(root, str(source.relative_to(root)))
            selected.update(_walk_code(root, directory, WEB_CODE))
            library_sources += 1
    if not library_sources:
        raise ValueError("Expected library source roots are missing")
    scripts = _require_directory(root, "apps/web/scripts")
    launchers = sorted(scripts.glob("*.mjs"))
    if not launchers:
        raise ValueError("Expected web launcher scripts are missing")
    selected.update(launchers)
    for relative in REQUIRED_MANIFESTS:
        path = root / relative
        try:
            info = _safe_stat(root, path)
        except FileNotFoundError as exc:
            raise ValueError(
                f"Required dependency manifest is missing: {relative}"
            ) from exc
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Dependency manifest is not a regular file: {relative}")
        selected.add(path)
    for relative in OPTIONAL_MANIFESTS:
        path = root / relative
        if path.exists() or path.is_symlink():
            selected.add(path)
    return sorted(selected, key=lambda path: path.relative_to(root).as_posix())


def _snapshot(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def build_release(repo_root: Path) -> dict:
    """Hash relative path and bytes with unambiguous framing in stable path order."""
    root = Path(repo_root).absolute()
    paths = _source_paths(root)
    aggregate = hashlib.sha256(FORMAT.encode() + b"\0")
    files, snapshots = [], {}
    for path in paths:
        before = _safe_stat(root, path)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Allowlisted release input must be a regular file")
        relative = path.relative_to(root).as_posix()
        encoded_path = relative.encode("utf-8")
        aggregate.update(len(encoded_path).to_bytes(8, "big"))
        aggregate.update(encoded_path)
        aggregate.update(before.st_size.to_bytes(8, "big"))
        digest = hashlib.sha256()
        with os.fdopen(
            os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb"
        ) as source:
            while chunk := source.read(1024 * 1024):
                aggregate.update(chunk)
                digest.update(chunk)
        after = _safe_stat(root, path)
        if _snapshot(before) != _snapshot(after):
            raise RuntimeError("Source changed while hashing; retry after edits finish")
        snapshots[path] = _snapshot(after)
        files.append(
            {"path": relative, "sha256": digest.hexdigest(), "bytes": before.st_size}
        )
    if paths != _source_paths(root) or any(
        _snapshot(_safe_stat(root, path)) != snapshots[path] for path in paths
    ):
        raise RuntimeError("Source changed while hashing; retry after edits finish")
    content_digest = aggregate.hexdigest()
    return {
        "format": FORMAT,
        "scope": "source-and-dependency-manifests",
        "release": "jeeves-" + content_digest[:20],
        "sha256": content_digest,
        "file_count": len(files),
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--output", type=Path, help="Optional JSON hash manifest; no source contents"
    )
    args = parser.parse_args()
    try:
        manifest = build_release(args.root)
        if args.output:
            destination = args.output.absolute()
            included = {
                (args.root.absolute() / entry["path"]).resolve()
                for entry in manifest["files"]
            }
            if (
                destination.suffix != ".json"
                or destination.resolve() in included
                or any(
                    path.is_symlink() for path in (destination, *destination.parents)
                )
            ):
                raise ValueError(
                    "Manifest output must be a separate nonsymlink JSON file"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            with os.fdopen(
                os.open(
                    destination,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_TRUNC
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                ),
                "w",
            ) as output:
                output.write(json.dumps(manifest, indent=2) + "\n")
        print(manifest["release"])
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Release identification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
