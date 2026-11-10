import asyncio

import pytest

from app.services.chat_guidance import (
    Quote,
    Reply,
    Review,
    guidance,
    unqualified_claim_decision,
    verified_sources,
)

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


def test_definitive_claim_outcomes_need_a_qualifier():
    assert unqualified_claim_decision(
        "Yes, the broken window is a covered loss. The policy does not issue a payment."
    )
    assert not unqualified_claim_decision(
        "If the loss is eligible, the policy may pay nothing after the deductible."
    )
    assert unqualified_claim_decision(
        "If the insurer needs records, provide them. Your claim is covered."
    )
    assert unqualified_claim_decision("Your claim is not covered.")


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
    assert draft.payloads[1]["previous_draft"]["answer"] == "We will pay $1,000."
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


def test_below_deductible_never_tells_homeowner_they_pay_nothing():
    passages = [
        {**HIT, "excerpt": "Flat deductible\n$1,000 per covered occurrence"},
        {
            **HIT,
            "chunkId": "policy-9:1",
            "excerpt": "Sudden impact from windborne debris that breaks an exterior dwelling window is a covered cause of loss.",
        },
    ]
    bad = reply(
        "The deductible exceeds the repair cost, so you pay nothing.",
        quote="$1,000 per covered occurrence",
    )
    reviewer = Responses()
    result = asyncio.run(
        guidance(
            {
                "question": "Is windborne debris breaking my window covered and how does the deductible affect payment?",
                "reportedExpenseTotal": "650",
            },
            passages,
            Responses(bad, bad),
            reviewer,
        )
    )
    assert not reviewer.payloads  # Deterministic guard catches the dangerous wording.
    assert (
        "$0.00" in result["content"] and "$650.00 would be your responsibility" in result["content"]
    )
    assert "if the entire recorded expense" in result["content"].lower()
    assert len(result["sources"]) == 2
    assert all(any(s["excerpt"] in p["excerpt"] for p in passages) for s in result["sources"])


def test_conditional_fallback_never_invents_a_deductible_or_amount():
    from app.services.chat_guidance import conditional_fallback

    assert (
        conditional_fallback(
            {"question": "What is the deductible?", "reportedExpenseTotal": "650"}, [HIT]
        )
        is None
    )
    assert (
        conditional_fallback(
            {"question": "What is the deductible?"},
            [{**HIT, "excerpt": "Flat deductible $1,000 per covered occurrence"}],
        )
        is None
    )


def test_citation_feedback_identifies_the_mismatched_source():
    other = {**HIT, "chunkId": "policy-9:1", "excerpt": "Storm debris can break windows."}
    bad = reply("The deductible is $1,000.", source=2)
    generator = Responses(bad, reply("The deductible is $1,000."))
    result = asyncio.run(
        guidance({}, [HIT, other], generator, Responses(Review(approved=True, feedback="")))
    )
    assert "source 2" in generator.payloads[1]["feedback"]
    assert generator.payloads[1]["previous_draft"]["citations"][0]["source"] == 2
    assert result["sources"][0]["chunkId"] == HIT["chunkId"]


def test_explicit_insurer_payment_promise_requires_a_condition():
    assert unqualified_claim_decision("The insurer will pay $0 for the repair.")
    assert unqualified_claim_decision("The insurer will not pay the expense.")
    assert not unqualified_claim_decision(
        "If eligible, the insurer will pay $0 after the deductible."
    )
