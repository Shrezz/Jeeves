from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from policy_rag.local_index import LocalPolicyIndex

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf"


def embed(texts):
    # Tiny deterministic vectors for the isolation/idempotency tests only.
    return [[float("boarding" in text.lower()), 0.1] for text in texts]


def test_persistent_citations_are_scoped_to_both_owner_and_upload(tmp_path):
    index = LocalPolicyIndex(tmp_path, embed)
    policy, other_policy = uuid4(), uuid4()
    count = index.index("user_A", policy, FIXTURE)
    assert count > 1 and index.index("user_A", policy, FIXTURE) == count
    assert index.index("user_B", other_policy, FIXTURE) == count
    reopened = LocalPolicyIndex(tmp_path, embed)
    hits = reopened.search("user_A", policy, "boarding")
    assert any(hit["page"] == 2 and "$275" in hit["excerpt"] for hit in hits)
    assert all(hit["chunkId"].startswith(str(policy) + ":") for hit in hits)
    assert not reopened.search("user_A", other_policy, "boarding")
    assert not reopened.search("user_B", policy, "boarding")


def test_blank_document_is_not_reported_as_indexed(tmp_path):
    pdf = tmp_path / "blank.pdf"
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(pdf)
    with pytest.raises(ValueError, match="no_text"):
        LocalPolicyIndex(tmp_path / "index", embed).index("user_A", uuid4(), pdf)
