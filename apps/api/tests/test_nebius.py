import asyncio

import httpx
import pytest

from app.schemas.agents import RouteDecision
from app.services.nebius import ModelUnavailable, NebiusModel


def request_model(handler, model_id="test-model", **options):
    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://api.tokenfactory.nebius.com/v1/",
            transport=httpx.MockTransport(handler),
        ) as client:
            model = NebiusModel(client, model_id, **options)
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


def test_truncated_deepseek_generation_reserves_retry_budget_for_the_answer():
    import json

    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "length", "message": {"content": None}}]}
            )
        return valid_response()

    result = request_model(respond, "deepseek-ai/DeepSeek-V4.1-Flash-1017", reasoning_effort="low")
    assert result.route == "answer_claim"
    assert [r["reasoning_effort"] for r in requests] == ["low", "none"]
    assert requests[0]["max_tokens"] == requests[1]["max_tokens"]


def test_packet_and_reviewer_can_only_cite_current_retrieved_chunks():
    from app.schemas.agents import PacketDraft, ReviewVerdict
    from app.services.nebius import response_schema

    for model, nested in ((PacketDraft, "CoverageDraft"), (ReviewVerdict, "ReviewIssue")):
        for ids in (["C4", "C9"], []):
            schema = response_schema(model, {"evidence": [{"chunk_id": i} for i in ids]})
            refs = schema["$defs"][nested]["properties"]["citation_ids"]
            if ids:
                assert refs["items"]["enum"] == ids
            else:
                assert refs["maxItems"] == 0


def test_invalid_generation_retries_once_without_replaying_the_output():
    import json

    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": "invalid-private-output"}}
                    ]
                },
            )
        return valid_response()

    assert request_model(handler).route == "answer_claim"
    assert len(requests) == 2
    assert "invalid-private-output" not in str(requests[1])


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


def test_nebius_roles_use_distinct_model_ids_for_structured_requests():
    import json

    from app.services.nebius import nebius_pair

    seen = []

    def record(request):
        seen.append(json.loads(request.content)["model"])
        return valid_response()

    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://example.test/v1/", transport=httpx.MockTransport(record)
        ) as client:
            with pytest.raises(ValueError, match="distinct"):
                nebius_pair(client, "same", "same")
            gen, rev = nebius_pair(client, "test-generator", "test-reviewer")
            assert (gen.role, rev.role) == ("generator", "reviewer")
            for model in (gen, rev):
                await model.generate(
                    prompt="Test", payload={"message": "Synthetic"}, output_type=RouteDecision
                )

    asyncio.run(scenario())
    assert seen == ["test-generator", "test-reviewer"]


@pytest.mark.parametrize(
    ("provider_usage", "expected_usage"),
    [
        (
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "provider_note": "private-policy-content",
                "prompt_tokens_details": {"note": "private-policy-content"},
            },
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        ),
        (
            {
                "prompt_tokens": "private-policy-content",
                "completion_tokens": True,
                "total_tokens": -1,
            },
            {},
        ),
        ("private-policy-content", {}),
    ],
)
def test_model_completion_logs_only_validated_token_counts(
    caplog, provider_usage, expected_usage
):
    import json
    import logging

    response = valid_response().json()
    response["usage"] = provider_usage
    with caplog.at_level(logging.INFO, logger="jeeves.models"):
        assert request_model(
            lambda request: httpx.Response(200, json=response)
        ).route == "answer_claim"

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "jeeves.models"
    ]
    assert len(events) == 1
    assert events[0]["event"] == "model_completed"
    assert events[0]["usage"] == expected_usage
    assert "private-policy-content" not in caplog.text
