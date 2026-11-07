"""Metadata-only tracing for the local policy worker."""

import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def client():
    if (
        os.getenv("LANGFUSE_TRACING_ENABLED", "").lower() != "true"
        or not os.getenv("LANGFUSE_PUBLIC_KEY")
        or not os.getenv("LANGFUSE_SECRET_KEY")
    ):
        return None
    try:
        from langfuse import get_client

        return get_client()
    except Exception:  # noqa: BLE001 - telemetry must not stop policy access
        logger.warning("Unable to initialize policy tracing")
        return None


@contextmanager
def span(name, **metadata):
    lf = client()
    if lf is None:
        yield None
        return
    try:
        manager = lf.start_as_current_observation(
            as_type="span", name=name, input={"operation": name}, metadata=metadata
        )
        current = manager.__enter__()
    except Exception:  # noqa: BLE001 - tracing must not affect policy processing
        logger.warning("Unable to start policy observation")
        yield None
        return
    try:
        yield current
        try:
            current.update(output={"status": "completed"})
        except Exception:  # noqa: BLE001 - tracing must not affect policy processing
            logger.warning("Unable to update policy observation")
    except BaseException:
        try:
            current.update(level="ERROR", status_message="Policy operation failed")
        except Exception:  # noqa: BLE001 - tracing must not mask policy failures
            logger.warning("Unable to report policy observation failure")
        raise
    finally:
        try:
            manager.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 - tracing must not affect policy processing
            logger.warning("Unable to close policy observation")


def flush():
    lf = client()
    if lf:
        try:
            lf.flush()
        except Exception:  # noqa: BLE001 - tracing must not affect policy processing
            logger.warning("Unable to flush policy observations")
