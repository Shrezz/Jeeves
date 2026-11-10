"""Live synthetic readiness probe. Never runs against the application database.

Requires TEST_DATABASE_URL ending in _test with CREATEDB privileges, installed
RAG runtime, and configured model/telemetry. Creates and removes a private test
DB and vector index. Does not create Clerk accounts or submit insurer claims.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import AsyncConnection, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from app.agents.checkpoints import checkpoint_serializer
from app.db.migrate import migrate
from app.observability.tracing import result_fingerprint, worker_trace
from app.services.chat_worker import chat_models
from app.services.dashboard_workflow import ChatContext, build_dashboard_graph
from app.services.local_policy_search import search_passages
from app.services.ui_workflow import AsyncPostgresSaver, ClaimChanged, execute

ROOT = Path(__file__).resolve().parents[3]


async def probe(url, directory, *, demo=False):
    owner = "user_SyntheticReadiness"
    policy, claim, message, run = (str(uuid4()) for _ in range(4))
    os.environ["LOCAL_RAG_ROOT"] = str(ROOT / "RAG")
    os.environ["LOCAL_RAG_DATA_DIR"] = directory
    question = (
        "Windborne debris broke my exterior dwelling window on November 3, 2026. "
        "The repair is pending and the estimate is $650. No files are attached. "
        "Please prepare a claim packet."
    )
    pdf = ROOT / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf"
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        in {
            "PATH",
            "HOME",
            "LOCAL_RAG_DATA_DIR",
            "LANGFUSE_TRACING_ENABLED",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_BASE_URL",
            "LANGFUSE_RELEASE",
            "LANGFUSE_TRACING_ENVIRONMENT",
        }
    }
    env["ANONYMIZED_TELEMETRY"] = "False"
    result = await asyncio.to_thread(
        subprocess.run,
        [str(ROOT / "RAG/.venv/bin/python"), "-m", "policy_rag.local_worker"],
        input=json.dumps({"operation": "index", "owner": owner, "policy": policy, "pdf": str(pdf)}),
        text=True,
        capture_output=True,
        cwd=ROOT / "RAG",
        env=env,
        timeout=240,
    )
    if result.returncode:
        raise RuntimeError("Synthetic policy indexing failed")
    count = json.loads(result.stdout)["count"]
    with worker_trace("readiness-retrieval", run):
        passages = await search_passages(owner, policy, "temporary window boarding limit")
        assert passages and all(p["chunkId"].startswith(policy + ":") for p in passages)
        assert not await search_passages("user_OtherSynthetic", policy, "window")
    migrate(url, directory=ROOT / "apps/web/lib/db/migrations")
    with psycopg.connect(url) as db:
        db.execute("INSERT INTO users(id) VALUES (%s)", (owner,))
        db.execute(
            "INSERT INTO policies(id,owner_id,file_name,size,object_path,label,status,ingestion_status,indexed_chunks) VALUES (%s,%s,'synthetic.pdf',%s,%s,'Synthetic','saved','ready',%s)",
            (policy, owner, pdf.stat().st_size, "local-db:" + policy, count),
        )
        db.execute(
            "INSERT INTO policy_documents(policy_id,content) VALUES (%s,%s)",
            (policy, pdf.read_bytes()),
        )
        db.execute(
            "INSERT INTO claims(id,owner_id,policy_id,title,total_expenses) VALUES (%s,%s,%s,'Synthetic readiness',650)",
            (claim, owner, policy),
        )
        db.execute(
            "INSERT INTO claim_messages(id,claim_id,content,expense,kind,processing_status) VALUES (%s,%s,%s,650,'preparation_request','saved_for_processing')",
            (message, claim, question),
        )
        db.execute(
            "INSERT INTO claim_guidance(id,claim_id,message_id,lease_id) VALUES (%s,%s,%s,%s)",
            (run, claim, message, run),
        )

    async def call(response=None, setup=False, actor=owner):
        # Reconnect each call to verify durable checkpoints across worker lifetimes.
        with worker_trace("ui-claim-workflow", run) as span:
            async with (
                AsyncPostgresSaver.from_conn_string(
                    make_conninfo(url, options="-c search_path=claim_graph"),
                    serde=checkpoint_serializer(),
                ) as saver,
                await AsyncConnection.connect(url, autocommit=True, row_factory=dict_row) as db,
                chat_models() as (generator, reviewer),
            ):
                if setup:
                    await saver.setup()
                result = await execute(
                    db,
                    saver,
                    {"owner": actor, "claimId": claim, "runId": run, "response": response},
                    generator,
                    reviewer,
                )
                span.update(
                    output={
                        "route": result["workflow"]["route"],
                        "status": result["workflow"]["phase"],
                        "artifact_version": result["workflow"]["version"],
                        "result_fingerprint": result_fingerprint(result),
                    }
                )
                if result["workflow"]["phase"] == "blocked":
                    span.update(level="WARNING", status_message="Draft did not pass review")
                return result

    async with chat_models() as (generator, reviewer):
        with worker_trace("dashboard-chat", run) as span:
            dashboard = await build_dashboard_graph().ainvoke(
                {
                    "request": __import__(
                        "app.schemas.agents", fromlist=["AgentRequest"]
                    ).AgentRequest(
                        message=(
                            "What is the flat deductible in this policy?"
                            if demo
                            else "What does the policy say about temporary window boarding?"
                        )
                    ),
                    "recent_turns": [],
                },
                context=ChatContext(owner, policy, generator, reviewer),
            )
            print("Synthetic dashboard:", json.dumps(dashboard["chat_reply"]), flush=True)
            dashboard_ok = bool(dashboard["chat_reply"]["sources"])
            span.update(
                output={
                    "route": dashboard["route"].route,
                    "source_count": len(dashboard["chat_reply"]["sources"]),
                }
            )
    packet = await call(setup=True)
    # A clarification is a legitimate safe pause. Supply only predeclared fictional facts.
    for _ in range(2):
        if packet["workflow"]["phase"] != "needs_information":
            break
        packet = await call(
            {
                "action": "clarify",
                "interruptId": packet["workflow"]["interruptId"],
                "feedback": "The window was intact before the November 3, 2026 storm. Windborne debris broke it. The repair is pending, the estimate is $650, no boarding has been done and no files have been uploaded.",
            }
        )
    flow = packet["workflow"]
    print("Synthetic packet:", json.dumps(packet), flush=True)
    sys.path.insert(0, str(ROOT / "evals"))
    from ui_workflow_eval import evaluate_ui, publish_scores

    case = next(
        json.loads(line)
        for line in (ROOT / "evals/datasets/ui_dev.jsonl").read_text().splitlines()
        if json.loads(line)["id"] == "ui_below_deductible_packet"
    )
    observed = {**packet, "state": "ready", "policy_id": policy}
    checks = evaluate_ui(case, observed, pdf.read_bytes())
    export = None
    if os.getenv("LANGFUSE_TRACING_ENABLED") == "true":
        # Includes bounded ingestion visibility polling and a hard process deadline.
        export = await asyncio.to_thread(
            publish_scores, run, case["id"], checks, observed, case_definition=case
        )
    print(
        "Evaluation:",
        json.dumps(
            {
                "export": export,
                "failed": [c.name for c in checks if c.passed is False],
                "unscored": [c.name for c in checks if c.passed is None],
            }
        ),
        flush=True,
    )
    report = {
        "session_id": run,
        "indexed_chunks": count,
        "dashboard_citations": len(dashboard["chat_reply"]["sources"]),
        "dashboard_verified": dashboard_ok,
        "eval_export": export,
        "failed_checks": [c.name for c in checks if c.passed is False],
        "packet_phase": flow["phase"],
        "stale_approval_rejected": None,
        "cross_owner_rejected": None,
        "result_fingerprint": result_fingerprint(packet),
    }
    # Failed preparations are measured too. Never attempt approval without a
    # real review interrupt; unexercised approval checks remain unknown.
    if flow["phase"] != "human_review":
        return report
    decision = {"interruptId": flow["interruptId"], "version": flow["version"], "action": "approve"}
    try:
        await call({**decision, "version": flow["version"] + 1})
    except ClaimChanged:
        pass
    else:
        raise AssertionError("Stale approval accepted")
    try:
        await call(decision, actor="user_OtherSynthetic")
    except PermissionError:
        pass
    else:
        raise AssertionError("Cross-owner approval accepted")
    final = await call(decision)
    assert final["workflow"]["phase"] == "completed"
    with psycopg.connect(url) as db:
        assert db.execute("SELECT count(*) FROM claim_workflow_commits").fetchone()[0] == 1
    return {
        **report,
        "packet_phase": final["workflow"]["phase"],
        "stale_approval_rejected": True,
        "cross_owner_rejected": True,
        "result_fingerprint": result_fingerprint(final),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-rehearsal",
        action="store_true",
        help="Use the demo coverage question; default boarding probe remains unchanged",
    )
    args = parser.parse_args()
    target = os.environ["TEST_DATABASE_URL"]
    if not conninfo_to_dict(target).get("dbname", "").endswith("_test"):
        raise ValueError("Disposable TEST_DATABASE_URL must end in _test")
    name = "jeeves_probe_" + uuid4().hex + "_test"
    with psycopg.connect(target, autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with tempfile.TemporaryDirectory(prefix="jeeves-readiness-") as directory:
            report = asyncio.run(
                probe(make_conninfo(target, dbname=name), directory, demo=args.demo_rehearsal)
            )
            print(json.dumps(report, indent=2))
            if args.demo_rehearsal and not report["dashboard_verified"]:
                raise SystemExit("Demo coverage answer abstained; rehearsal is incomplete")
            if report["failed_checks"] or (
                report["eval_export"] and report["eval_export"]["status"] != "verified"
            ):
                raise SystemExit(1)
    finally:
        with psycopg.connect(target, autocommit=True) as db:
            db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
