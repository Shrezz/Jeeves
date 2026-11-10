"""Final boundary for one-shot stdin/stdout workers, never an API lifespan hook."""

import os
import sys
from collections.abc import Callable
from typing import NoReturn


def run_worker(main: Callable[[], object], *, flush: Callable[[], None] | None = None) -> NoReturn:
    """Close application contexts, drain bounded telemetry, and preserve the exit status.

    Call only at a worker's CLI entrypoint. Application resources must be released
    by main before it returns. Langfuse/OTel register atexit handlers that can
    flush a second time without honoring our timeout; skip those handlers after
    our explicit drain, rather than letting telemetry hold a completed response.
    """
    status = 0
    try:
        main()
    except SystemExit as exc:
        status = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        if status:
            print("worker_failed", file=sys.stderr)
    except KeyboardInterrupt:
        status = 130
        print("worker_interrupted", file=sys.stderr)
    except BaseException:  # noqa: BLE001 - CLI boundary preserves failure without private details
        status = 1
        # Exception messages and tracebacks can contain policy text or credentials.
        print("worker_failed", file=sys.stderr)
    finally:
        if flush is not None:
            try:
                flush()
            except BaseException:  # noqa: BLE001 - export cannot replace application status
                print("telemetry_flush_failed", file=sys.stderr)
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (OSError, ValueError):
                status = 1
    os._exit(status)
