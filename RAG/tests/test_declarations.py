from pathlib import Path

import pymupdf

from policy_rag.declarations import extract_declarations


def test_stacked_cedar_cove_declarations_preserve_qualifiers():
    fixture = Path(__file__).resolve().parents[2] / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf"
    fields = extract_declarations(fixture.read_bytes())
    assert {f["kind"]: f["value"] for f in fields} == {
        "number": "CCV-HO3-CA-100731",
        "location": "Fictional residence, California",
        "term": "January 1 to December 31, 2026",
        "deductible": "$1,000 per covered occurrence",
    }
    assert {f["page"] for f in fields} == {1}


def test_table_on_second_page_keeps_source_wording_and_ignores_claim_examples():
    with pymupdf.open() as doc:
        cover = doc.new_page()
        cover.insert_text((50, 50), "Illustration only")
        cover.insert_text((50, 90), "Deductible: $25")
        page = doc.new_page()
        page.insert_text((50, 50), "1 Declarations")
        page.insert_text((50, 90), "Applicable deductible")
        page.insert_text((220, 90), "$1,000 per covered occurrence")
        page.insert_text((50, 135), "Eligible-expense limit")
        page.insert_text((220, 135), "$10,000 per covered occurrence,\nbefore the deductible")
        page.insert_text((50, 200), "Payment examples")
        page.insert_text((50, 230), "Deductible: $150")
        fields = extract_declarations(doc.tobytes())
    assert [(f["value"], f["page"]) for f in fields] == [
        ("$1,000 per covered occurrence", 2), ("$10,000 per covered occurrence, before the deductible", 2),
    ]


def test_no_declarations_returns_no_guessed_values():
    with pymupdf.open() as doc:
        doc.new_page()
        doc.new_page().insert_text((50, 100), "See declarations\nDeductible: $0")
        assert extract_declarations(doc.tobytes()) == []
