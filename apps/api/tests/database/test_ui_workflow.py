"""Real graph checkpoints and owner-bound approvals against a disposable UI database."""

import asyncio
from uuid import uuid4

import psycopg
import pytest
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from app.agents.checkpoints import checkpoint_serializer
from app.db.migrate import migrate
from app.schemas.agents import IncidentFacts, PacketDraft, ReviewVerdict, RouteDecision
from app.services.rag.types import Citation
from app.services.ui_workflow import AsyncPostgresSaver, ClaimChanged, WebClaimStore, execute
from tests.database.test_ui_identity_status import MIGRATIONS
from tests.fakes import ScriptedModel, coverage_draft


def test_owned_packet_survives_restart_and_only_exact_human_approval_prepares_it(
    database_factory, monkeypatch
):
    policy, claim, message, run_id = (str(uuid4()) for _ in range(4))
    owner = "user_TestReviewer"

    async def evidence(self, *, user_id, policy_id, **_):
        assert (user_id, policy_id) == (owner, policy)
        return [
            Citation(
                "C0", policy, "1", 2, "Window glass", "A covered repair has a $1,000 deductible.", 0
            )
        ]

    monkeypatch.setattr(WebClaimStore, "retrieve_evidence", evidence)
    generator = ScriptedModel()
    reviewer = ScriptedModel()
    generator.outputs.extend(
        [
            RouteDecision(route="file_claim"),
            PacketDraft(
                narrative="Baseball impact, reported repair $150. Not submitted.",
                facts=IncidentFacts(
                    description="Window glass",
                    cause="Baseball impact",
                    occurred_on="2026-11-01",
                    repair_cost="150",
                ),
                coverage=coverage_draft(citation_ids=["C0"]),
            ),
        ]
    )
    reviewer.outputs.append(ReviewVerdict(outcome="pass"))

    with database_factory() as url:
        migrate(url, directory=MIGRATIONS)
        with psycopg.connect(url) as db:
            db.execute("INSERT INTO users(id) VALUES (%s)", (owner,))
            db.execute(
                "INSERT INTO policies(id,owner_id,file_name,size,object_path,label,status) VALUES (%s,%s,'test.pdf',100,%s,'Example','saved')",
                (policy, owner, "local-db:" + policy),
            )
            db.execute(
                "INSERT INTO claims(id,owner_id,policy_id,title) VALUES (%s,%s,%s,'Test')",
                (claim, owner, policy),
            )
            db.execute(
                "INSERT INTO claim_messages(id,claim_id,content,kind,processing_status) VALUES (%s,%s,'lets file the claim','ask','saved_for_processing')",
                (message, claim),
            )
            db.execute(
                "INSERT INTO claim_guidance(id,claim_id,message_id,lease_id) VALUES (%s,%s,%s,%s)",
                (run_id, claim, message, run_id),
            )

        async def call(*, setup=False, **changes):
            # New process-equivalent connections and checkpointer for every call.
            async with (
                AsyncPostgresSaver.from_conn_string(
                    make_conninfo(url, options="-c search_path=claim_graph"),
                    serde=checkpoint_serializer(),
                ) as saver,
                await AsyncConnection.connect(url, autocommit=True, row_factory=dict_row) as db,
            ):
                if setup:
                    await saver.setup()
                await execute(
                    db,
                    saver,
                    {"owner": owner, "claimId": claim, "runId": run_id, **changes},
                    generator,
                    reviewer,
                )
                return await (
                    await db.execute(
                        "SELECT workflow,sources FROM claim_guidance WHERE id=%s", (run_id,)
                    )
                ).fetchone()

        result = asyncio.run(call(setup=True))
        view = result["workflow"]
        assert view["phase"] == "human_review" and view["route"] == "file_claim"
        assert result["sources"][0]["chunkId"] == policy + ":0"
        assert {"label": "Estimated payment", "value": "$0.00"} in view["fields"]
        with psycopg.connect(url) as db:
            assert db.execute("SELECT status FROM claims").fetchone()[0] == "draft"
            assert db.execute("SELECT count(*) FROM claim_workflow_commits").fetchone()[0] == 0
        approval = {
            "interruptId": view["interruptId"],
            "version": view["version"],
            "action": "approve",
        }
        with pytest.raises(PermissionError):
            asyncio.run(call(owner="user_Other", response=approval))
        with pytest.raises(ClaimChanged):
            asyncio.run(call(response={**approval, "interruptId": "outdated"}))
        with pytest.raises(ClaimChanged):
            asyncio.run(call(response={**approval, "version": view["version"] + 1}))
        assert asyncio.run(call(response=approval))["workflow"]["phase"] == "completed"
        with pytest.raises(ClaimChanged):
            asyncio.run(call(response=approval))
        with psycopg.connect(url) as db:
            assert db.execute("SELECT status FROM claims").fetchone()[0] == "prepared"
            assert db.execute("SELECT count(*) FROM claim_workflow_commits").fetchone()[0] == 1
