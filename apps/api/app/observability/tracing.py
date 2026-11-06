"""Local JSON tracing fallback. Policy text, prompts, and credentials are not logged."""

import logging
from contextvars import ContextVar

current_run_id: ContextVar[str | None] = ContextVar("jeeves_run_id", default=None)


def configure_tracing() -> None:
    logger = logging.getLogger("jeeves")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
