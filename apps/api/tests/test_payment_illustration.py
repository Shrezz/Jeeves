from types import SimpleNamespace

from app.schemas.agents import ReviewResult, ReviewVerdict
from app.services.payment_illustration import flat_deductible
from app.services.rag.types import Citation
from app.services.ui_workflow import project
from tests.fakes import make_context, packet_draft


def test_ambiguous_or_nonflat_deductibles_are_not_assumed():
    assert flat_deductible([{"excerpt": "A deductible of $1,000 may apply."}]) is None
    assert flat_deductible([{"excerpt": "Flat deductible $1,00 per covered occurrence"}]) is None
    assert (
        flat_deductible(
            [
                {"excerpt": "Flat deductible $1,000 per covered occurrence"},
                {"excerpt": "Flat deductible $2,000 per covered occurrence"},
            ]
        )
        is None
    )


def test_review_packet_shows_qualified_illustration_without_inventing_eligibility():
    ctx = make_context()
    draft = packet_draft(ctx)
    draft = draft.model_copy(
        update={
            "coverage": draft.coverage.model_copy(
                update={"covered_amount": None, "deductible": None}
            )
        }
    )
    evidence = [
        Citation(
            "C0",
            "demo-policy",
            "v1",
            1,
            "Declarations",
            "Flat deductible $1,000 per covered occurrence",
            0,
        )
    ]
    snapshot = SimpleNamespace(
        values={
            "phase": "human_review",
            "route": SimpleNamespace(route="file_claim"),
            "artifact_version": 1,
            "review": ReviewResult(
                route="file_claim", artifact_version=1, verdict=ReviewVerdict(outcome="pass")
            ),
            "draft": draft,
            "evidence": evidence,
            "estimate": None,
        },
        interrupts=[SimpleNamespace(id="review")],
    )
    result = project(snapshot, {"receipt-1": "receipt.pdf"}, "150")
    fields = {item["label"]: item["value"] for item in result["workflow"]["fields"]}
    assert fields["Illustrative payment if fully eligible"] == "$0.00"
    assert "Assumes" in fields["Illustration basis"]
    assert "Estimated payment" not in fields
    assert result["sources"][0]["excerpt"] == "Flat deductible $1,000 per covered occurrence"
    assert "Illustrative payment if fully eligible" not in {
        item["label"]
        for item in project(snapshot, {"receipt-1": "receipt.pdf"}, "151")["workflow"]["fields"]
    }
    snapshot.values["draft"] = draft.model_copy(
        update={"coverage": draft.coverage.model_copy(update={"conclusion": "likely_not_covered"})}
    )
    assert "Illustrative payment if fully eligible" not in {
        item["label"]
        for item in project(snapshot, {"receipt-1": "receipt.pdf"}, "150")["workflow"]["fields"]
    }
