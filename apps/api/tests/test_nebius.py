import asyncio

import httpx
import pytest

from app.schemas.agents import RouteDecision
from app.services.nebius import ModelUnavailable, NebiusModel


def request_model(handler):
    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://api.tokenfactory.nebius.com/v1/",
            transport=httpx.MockTransport(handler),
        ) as client:
            model = NebiusModel(client, "test-model")
            return await model.generate(
                prompt="Route", payload={"message": "Is it covered?"}, output_type=RouteDecision
            )

    return asyncio.run(scenario())


def valid_response():
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"route":"answer_claim","clarification":null}'},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def test_nebius_schema_request_and_response():
    import json

    def handler(request):
        body = json.loads(request.content)
        assert str(request.url).endswith("/v1/chat/completions")
        assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        assert body["model"] == "test-model"
        return valid_response()

    assert request_model(handler).route == "answer_claim"


def test_nebius_retries_transient_failure_once():
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(503) if len(attempts) == 1 else valid_response()

    assert request_model(handler).route == "answer_claim"
    assert len(attempts) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, text="private provider details"),
        httpx.Response(
            200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        ),
        httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}]}
        ),
    ],
)
def test_nebius_fails_closed_without_leaking_response(response):
    with pytest.raises(ModelUnavailable, match="unavailable or invalid"):
        request_model(lambda request: response)
