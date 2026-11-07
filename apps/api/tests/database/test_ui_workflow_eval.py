"""The UI evaluation adapter reads only explicit synthetic claims and policy files."""

import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.db.migrate import migrate
from tests.database.test_ui_identity_status import MIGRATIONS

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "evals"))

from ui_workflow_eval import FIXTURE, load_observation


def test_ui_evaluation_refuses_other_claims_and_nonfixture_policies(database_factory):
    policy, claim, message, run_id = (str(uuid4()) for _ in range(4))
    owner = "user_SyntheticEvaluator"
    with database_factory() as url:
        migrate(url, directory=MIGRATIONS)
        with psycopg.connect(url) as db:
            db.execute("INSERT INTO users(id) VALUES (%s)", (owner,))
            db.execute(
                "INSERT INTO policies(id,owner_id,file_name,size,object_path,label,status) VALUES (%s,%s,'fixture.pdf',100,'fixture','Fixture','saved')",
                (policy, owner),
            )
            db.execute(
                "INSERT INTO policy_documents(policy_id,content) VALUES (%s,%s)",
                (policy, FIXTURE.read_bytes()),
            )
            db.execute(
                "INSERT INTO claims(id,owner_id,policy_id,title) VALUES (%s,%s,%s,'Synthetic')",
                (claim, owner, policy),
            )
            db.execute(
                "INSERT INTO claim_messages(id,claim_id,content,kind,processing_status) VALUES (%s,%s,'Window claim','ask','saved_for_processing')",
                (message, claim),
            )
            db.execute(
                "INSERT INTO claim_guidance(id,claim_id,message_id,lease_id) VALUES (%s,%s,%s,%s)",
                (run_id, claim, message, run_id),
            )
        with pytest.raises(ValueError, match="allowlisted"):
            load_observation(url, run_id, {str(uuid4())})
        row, pdf = load_observation(url, run_id, {claim})
        assert row["policy_id"] == policy and pdf == FIXTURE.read_bytes()
        with psycopg.connect(url) as db:
            db.execute(
                "UPDATE policy_documents SET content=%s WHERE policy_id=%s",
                (b"not the fictional fixture", policy),
            )
        with pytest.raises(ValueError, match="fictional fixture"):
            load_observation(url, run_id, {claim})
