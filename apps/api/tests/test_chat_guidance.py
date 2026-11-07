import asyncio

import pytest

from app.services.chat_guidance import Quote, Reply, Review, guidance, verified_sources

HIT = {
    "chunkId": "policy-9:0",
    "section": "Payments",
    "page": 3,
    "excerpt": "The deductible is $1,000 per covered occurrence.",
}


class Responses:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.payloads = []

    async def generate(self, *, prompt, payload, output_type):
        self.payloads.append(payload)
        response = next(self.responses)
        assert isinstance(response, output_type)
        return response


def reply(answer, source=1, quote="deductible is $1,000"):
    return Reply(kind="policy", answer=answer, citations=[Quote(source=source, quote=quote)])


def test_actual_passages_reach_both_models_and_only_reviewed_draft_is_published():
    draft = Responses(reply("We will pay $1,000."), reply("The deductible is $1,000 (Source 1)."))
    review = Responses(
        Review(approved=False, feedback="Do not promise payment."),
        Review(approved=True, feedback=""),
    )
    result = asyncio.run(guidance({"question": "What is the deductible?"}, [HIT], draft, review))
    assert result == {
        "content": "The deductible is $1,000.",
        "sources": [{**HIT, "excerpt": "deductible is $1,000"}],
    }
    assert draft.payloads[1]["feedback"] == "Do not promise payment."
    assert (
        draft.payloads[0]["sources"][0]["text"]
        == review.payloads[0]["sources"][0]["text"]
        == HIT["excerpt"]
    )


@pytest.mark.parametrize(
    "draft",
    [
        reply("Unknown source.", source=2),
        reply("Fake quote.", quote="No deductible"),
        Reply(kind="policy", answer="Always covered.", citations=[]),
    ],
)
def test_fabricated_evidence_never_reaches_the_homeowner(draft):
    result = asyncio.run(guidance({}, [HIT], Responses(draft, draft), Responses()))
    assert "couldn’t verify" in result["content"] and result["sources"] == []


def test_no_policy_cannot_supply_a_citation():
    with pytest.raises(ValueError):
        verified_sources(reply("The deductible is $1,000."), [])
