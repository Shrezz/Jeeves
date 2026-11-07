"""The combined app flushes optional observations in both startup modes."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.observability import tracing


@pytest.mark.parametrize("mode", ["unconfigured", "demo"])
def test_shutdown_flushes_langfuse_in_each_mode(monkeypatch, mode):
    client = Mock()
    monkeypatch.setattr(tracing, "_client", client)
    monkeypatch.setenv("JEEVES_MODE", mode)
    monkeypatch.setenv("MODEL_MODE", "fixture")
    monkeypatch.setenv("JEEVES_DEMO_TOKEN", "test-token")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    with TestClient(create_app()) as api:
        assert api.get("/health").json() == {"status": "ok"}
        client.flush.assert_not_called()
    client.flush.assert_called_once_with()
