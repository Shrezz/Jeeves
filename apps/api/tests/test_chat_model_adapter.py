"""Check structured-output validation for an injected chat model."""

import asyncio

import pytest
from pydantic import ValidationError

from app.agents.model import ChatModelAdapter
from app.schemas.agents import RouteDecision


class SyntheticChatModel:
    model_name = "synthetic-model"

    def __init__(self, result):
        self.result = result
        self.messages = []
        self.output_type = None

    def with_structured_output(self, output_type, *, include_raw=False):
        assert include_raw
        self.output_type = output_type
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        return {"raw": None, "parsed": self.result, "parsing_error": None}


def test_structured_chat_output_is_validated():
    model = SyntheticChatModel({"route": "answer_claim", "clarification": None})
    result = asyncio.run(
        ChatModelAdapter(model).generate(
            prompt="synthetic prompt",
            payload={"request": "synthetic message"},
            output_type=RouteDecision,
        )
    )
    assert result.route == "answer_claim"
    assert model.output_type is RouteDecision
    assert "synthetic message" in model.messages[1].content


def test_invalid_structured_chat_output_is_rejected():
    model = SyntheticChatModel({"route": "invented_route"})
    with pytest.raises(ValidationError):
        asyncio.run(
            ChatModelAdapter(model).generate(
                prompt="synthetic", payload={}, output_type=RouteDecision
            )
        )


def test_adapter_records_usage_without_raw_model_content(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    updates = []

    @contextmanager
    def observation(*args, **kwargs):
        class Span:
            def update(self, **values):
                updates.append(values)

        yield Span()

    class Model(SyntheticChatModel):
        async def ainvoke(self, messages):
            return {
                "raw": SimpleNamespace(
                    content="private reply",
                    usage_metadata={"input_tokens": 8, "output_tokens": 3, "total_tokens": 11},
                ),
                "parsed": self.result,
                "parsing_error": None,
            }

    monkeypatch.setattr("app.agents.model.observation", observation)
    monkeypatch.setattr("app.agents.model.capture_synthetic_content", lambda: False)
    asyncio.run(
        ChatModelAdapter(Model({"route": "answer_claim"})).generate(
            prompt="private prompt", payload={"private": "data"}, output_type=RouteDecision
        )
    )
    assert {"usage_details": {"input": 8, "output": 3, "total": 11}} in updates
    assert "private" not in repr(updates)
