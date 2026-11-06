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

    def with_structured_output(self, output_type):
        self.output_type = output_type
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        return self.result


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
