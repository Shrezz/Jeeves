import pytest
from policy_rag import observability


def test_disabled_tracing_is_noop(monkeypatch):
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    with observability.span("retrieval") as current:
        assert current is None


def test_error_status_does_not_export_exception_details(monkeypatch):
    updates = []

    class Current:
        def update(self, **kw):
            updates.append(kw)

    class Manager:
        def __enter__(self):
            return Current()

        def __exit__(self, *args):
            return False

    class Client:
        def start_as_current_observation(self, **kw):
            return Manager()

    monkeypatch.setattr(observability, "client", lambda: Client())
    with pytest.raises(ValueError), observability.span("retrieval"):
        raise ValueError("private policy contents")
    assert updates == [{"level": "ERROR", "status_message": "Policy operation failed"}]
