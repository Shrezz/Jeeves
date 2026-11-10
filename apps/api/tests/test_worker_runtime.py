"""Exercise the real CLI exit boundary in disposable child processes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNTIMES = [ROOT / "apps/api/app/services/worker_runtime.py", ROOT / "RAG/policy_rag/worker_runtime.py"]


def child(code, *, timeout=5):
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        env={
            "PATH": os.environ["PATH"],
            "PYTHONPATH": os.pathsep.join([str(ROOT / "apps/api"), str(ROOT / "RAG")]),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True, capture_output=True, timeout=timeout,
    )


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_completed_worker_flushes_output_and_skips_stuck_atexit(runtime):
    result = child(f"""
import asyncio, atexit, json, sys, time
from contextlib import asynccontextmanager
import runpy
run_worker = runpy.run_path({str(runtime)!r})["run_worker"]
atexit.register(lambda: time.sleep(60))
@asynccontextmanager
async def resource():
    try:
        yield
    finally:
        print("resource_closed", file=sys.stderr)
async def main():
    async with resource():
        print(json.dumps({{"ok": True}}))
def drain():
    print("telemetry_drained", file=sys.stderr)
run_worker(lambda: asyncio.run(main()), flush=drain)
""")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"ok": True}
    assert result.stderr.splitlines() == ["resource_closed", "telemetry_drained"]


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_worker_failure_exits_nonzero_without_private_exception(runtime):
    result = child(f"""
import atexit, time
import runpy
run_worker = runpy.run_path({str(runtime)!r})["run_worker"]
atexit.register(lambda: time.sleep(60))
def main():
    raise ValueError("private-policy-content")
run_worker(main)
""")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "worker_failed\n"


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_flush_failure_does_not_fail_completed_application(runtime):
    result = child(f"""
import runpy
run_worker = runpy.run_path({str(runtime)!r})["run_worker"]
def main():
    print('{{"ok": true}}')
def drain():
    raise RuntimeError("private-export-response")
run_worker(main, flush=drain)
""")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"ok": True}
    assert result.stderr == "telemetry_flush_failed\n"


def test_ui_setup_branch_closes_saver_and_exits_successfully():
    result = child("""
import asyncio, atexit, os, sys, time
from app.services import ui_workflow
from app.services.worker_runtime import run_worker
atexit.register(lambda: time.sleep(60))
class Saver:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        print("saver_closed", file=sys.stderr)
    async def setup(self):
        print("setup_complete", file=sys.stderr)
ui_workflow.AsyncPostgresSaver.from_conn_string = lambda *a, **kw: Saver()
os.environ["DATABASE_URL"] = "postgresql://example.invalid/test"
sys.argv = ["worker", "--setup"]
run_worker(lambda: asyncio.run(ui_workflow.main()))
""")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.splitlines() == ["setup_complete", "saver_closed"]
