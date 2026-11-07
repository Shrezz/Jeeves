"""Account-scoped adapters for the local Claimwise database and policy index."""

import asyncio
import json
import os
from pathlib import Path

from psycopg.types.json import Jsonb

from app.schemas.agents import ActionResult, ClaimSnapshot, IncidentFacts, PacketDraft
from app.services.rag.types import Citation


class ClaimChanged(ValueError):
    pass


class WebClaimStore:
    def __init__(self, db, owner, claim_id, run_id):
        self.db, self.owner, self.claim_id, self.run_id = db, owner, claim_id, run_id

    async def record(self, *, lock=False):
        row = await (
            await self.db.execute(
                """SELECT c.*, extract(epoch from c.updated_at)*1000000 AS version,
                p.label AS policy_label, p.ingestion_status, p.object_path
               FROM public.claims c LEFT JOIN public.policies p ON p.id=c.policy_id
                 AND p.owner_id=c.owner_id AND p.status='saved'
               WHERE c.id=%s AND c.owner_id=%s"""
                + (" FOR UPDATE OF c" if lock else ""),
                (self.claim_id, self.owner),
            )
        ).fetchone()
        if not row:
            raise PermissionError("Claim not found")
        return row

    async def load_claim(self, *, user_id, claim_id):
        if (user_id, claim_id) != (self.owner, self.claim_id):
            raise PermissionError("Claim not found")
        c = await self.record()
        rows = await (
            await self.db.execute(
                """SELECT m.content,m.expense,g.content AS reply,g.sources,g.workflow FROM public.claim_messages m
               LEFT JOIN public.claim_guidance g ON g.message_id=m.id AND g.state='ready'
               WHERE m.claim_id=%s AND m.created_at <= (SELECT s.created_at FROM public.claim_messages s
                   JOIN public.claim_guidance target ON target.message_id=s.id WHERE target.id=%s)
               ORDER BY m.created_at DESC,m.id DESC LIMIT 24""",
                (claim_id, self.run_id),
            )
        ).fetchall()
        self.history = [
            {
                "homeowner": r["content"][:1000],
                "expense": str(r["expense"]) if r["expense"] is not None else None,
                "priorReply": (r["reply"] or "")[:600],
            }
            for r in reversed(rows[:5])
        ]
        self.notes = [
            r["content"][:1200]
            + (f" | Recorded expense: ${r['expense']}" if r["expense"] is not None else "")
            for r in reversed(rows)
            if r["content"] or r["expense"] is not None
        ]
        self.notes = list(dict.fromkeys(self.notes))
        # Carry forward the most recent reviewed evidence-backed answer on this policy.
        # Historical workflow/clarification messages are not coverage evidence.
        policy_prefix = str(c["policy_id"]) + ":"
        self.prior_coverage = None
        for row in rows:
            hits = row["sources"] or []
            if (
                hits
                and row["reply"]
                and (not row["workflow"] or row["workflow"].get("route") == "answer_claim")
                and all(h["chunkId"].startswith(policy_prefix) for h in hits)
            ):
                self.prior_coverage = {
                    "answer": row["reply"][:1800],
                    "citations": [
                        {
                            "chunk_id": "C" + h["chunkId"].split(":")[-1],
                            "page": h["page"],
                            "quote": h["excerpt"][:600],
                        }
                        for h in hits[:4]
                    ],
                }
                break
        files = await (
            await self.db.execute(
                "SELECT id,file_name FROM public.claim_evidence WHERE claim_id=%s AND status='saved' ORDER BY created_at",
                (claim_id,),
            )
        ).fetchall()
        self.files = {str(f["id"]): f["file_name"] for f in files}
        self.policy = str(c["policy_id"] or "unlinked")
        self.label = c["policy_label"]
        self.searchable = (
            c["ingestion_status"] == "ready" and c["object_path"] == "local-db:" + self.policy
        )
        return ClaimSnapshot(
            claim_id=claim_id,
            user_id=user_id,
            policy_id=self.policy,
            policy_version="1",
            version=int(c["version"]),
            facts=IncidentFacts.model_validate(c["incident_json"]),
            status=c["status"],
            insurer_outcome=c["insurer_outcome"],
            insurer_outcome_source=c["insurer_outcome_source"],
            notes=self.notes,
            attachment_ids=list(self.files),
        )

    async def retrieve_evidence(self, *, user_id, policy_id, question, limit):
        if (user_id, policy_id) != (self.owner, self.policy):
            raise PermissionError("Policy not found")
        if not self.searchable:
            return []
        root = Path(os.environ["LOCAL_RAG_ROOT"])
        python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        proc = await asyncio.create_subprocess_exec(
            str(python),
            "-m",
            "policy_rag.local_worker",
            cwd=root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                k: os.environ[k] for k in ("PATH", "HOME", "LOCAL_RAG_DATA_DIR") if k in os.environ
            }
            | {
                "ANONYMIZED_TELEMETRY": "False",
                "POLICY_RAG_TRACE": "0",
                "TOKENIZERS_PARALLELISM": "false",
            },
        )
        query = question[:1000] + "\n" + "\n".join(self.notes[-6:])[-1800:]
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(
                    json.dumps(
                        {
                            "operation": "search",
                            "owner": user_id,
                            "policy": policy_id,
                            "question": query,
                            "forChat": True,
                        }
                    ).encode()
                ),
                60,
            )
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        if proc.returncode:
            raise RuntimeError("Policy search unavailable")
        hits = json.loads(out)["passages"]
        result = []
        for h in hits:
            prefix, index = h["chunkId"].rsplit(":", 1)
            if prefix != self.policy or not index.isdecimal():
                raise ValueError("Unexpected policy passage")
            # Short, stable references for the model. Bind back to the real UUID on display.
            result.append(
                Citation("C" + index, self.policy, "1", h["page"], h["section"], h["excerpt"], 0.0)
            )
        return result[:limit]

    async def commit(self, *, user_id, claim, proposal, evidence, request_key):
        if user_id != self.owner or claim.claim_id != self.claim_id:
            raise PermissionError("Claim not found")
        async with self.db.transaction():
            current = await self.record(lock=True)
            previous = await (
                await self.db.execute(
                    "SELECT request_key,result FROM public.claim_workflow_commits WHERE run_id=%s",
                    (self.run_id,),
                )
            ).fetchone()
            if previous:
                if previous["request_key"] != request_key:
                    raise ClaimChanged("Another version was approved.")
                return ActionResult.model_validate(previous["result"])
            if int(current["version"]) != claim.version:
                raise ClaimChanged("Claim changed before approval.")
            packet = isinstance(proposal, PacketDraft)
            # Approval prepares a local artifact. There is no insurer submission operation.
            status = "prepared" if packet else proposal.status or claim.status
            facts = proposal.facts.model_dump(mode="json", exclude_none=True)
            outcome = None if packet else proposal.insurer_outcome
            row = await (
                await self.db.execute(
                    """UPDATE public.claims SET status=%s,incident_json=incident_json || %s,
                insurer_outcome=coalesce(%s,insurer_outcome),
                insurer_outcome_source=CASE WHEN %s::text IS NOT NULL THEN 'user_reported' ELSE insurer_outcome_source END,
                latest_update=%s,updated_at=clock_timestamp() WHERE id=%s AND owner_id=%s
                RETURNING extract(epoch from updated_at)*1000000 AS version""",
                    (
                        status,
                        Jsonb(facts),
                        outcome,
                        outcome,
                        "Packet approved and prepared. Not submitted." if packet else proposal.note,
                        self.claim_id,
                        user_id,
                    ),
                )
            ).fetchone()
            result = ActionResult(
                outcome="prepared" if packet else "saved",
                claim_id=self.claim_id,
                claim_version=int(row["version"]),
                artifact_id=self.run_id if packet else None,
                mode="integrated",
            )
            await self.db.execute(
                "INSERT INTO public.claim_workflow_commits VALUES (%s,%s,%s)",
                (self.run_id, request_key, Jsonb(result.model_dump(mode="json"))),
            )
            return result
