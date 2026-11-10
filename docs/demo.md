# Jeeves demo rehearsal

Use the local single-host stack and the checked-in fictional policy. Keep the laptop
plugged in, Docker Desktop and Ollama running, and allow the model to finish each turn.
Clerk sign-in and the Langfuse dashboard require internet access.

## Start or check

From the repository root:

```sh
bash scripts/start-demo.sh --check
bash scripts/start-demo.sh
```

The startup script reuses installed dependencies, checks the configured Ollama model,
and launches the local database, API, and UI. It does not download anything or overwrite
credentials. If the app is already running, use the `--check` command only. Open
[the application](http://localhost:5173). Sign in ahead of the presentation; verify
[Langfuse](https://us.cloud.langfuse.com) sign-in as well.

## Suggested walkthrough

1. Upload `data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf`. Label it “Demo homeowners policy”; the fixture deductible is $1,000. Wait until saving/indexing completes.
2. Use “Search this policy” with `windborne debris` and show that excerpts include page references. This step retrieves exact passages without waiting for a model answer.
3. With that policy selected, ask:

   > What is the flat deductible in this policy?

   Tested answer: $1,000 per covered occurrence, with page citations (10.9 seconds in the signed-in browser rehearsal). Show the conditional $0 estimate later in the reviewed packet.
4. In the claim workspace, include these fictional incident facts and request preparation:

   > Windborne debris broke my exterior dwelling window on November 3, 2026. The window was intact before the storm. The repair is pending and the estimate is $650. No boarding has been done and no files are attached. Please prepare a claim packet.

   Record `650` in the optional expense field **once**; amounts add to the running total. Do not re-enter it on retries. Use “Prepare claim”, acknowledge that no insurer submission occurs, then “Confirm request”. The dashboard-to-claim handoff preserves the message, but text mentioning a cost does not itself add a recorded expense.
5. If the graph asks for clarification, answer truthfully from those same fictional facts. It is an expected review boundary, not an error. Review the narrative, page citations, repair estimate, deductible, and conditional payment before selecting “Approve local packet”. Show “Prepared · Not submitted” and download the approved packet.
6. Open the corresponding Langfuse trace. Explain the request root, agent nodes, retrieval, generator/reviewer calls, available token counts, and approval/resume traces grouped by session. Use `development` for the live app and `verification` for rehearsals. Raw customer content is intentionally absent from normal app traces.

## Langfuse talking points

- A trace records one execution; a session groups related turns/resumes.
- Generations show model calls; retrieval/embedding spans show where policy evidence came from.
- Token usage is reported by the provider. Local Ollama monetary cost is not available.
- Scores come from explicit evaluation runs. The signed-in packet has 11 passing Boolean checks plus an unscored-count record of 2. Those two checks need human semantic review.
- “Jeeves Operations” shows request volume, p95 latency, errors, model tokens, measured pass rates, unscored checks, warnings, blocked packets, and abstained answers.
  Quality charts select the current v2 evaluator implementation; the earlier signed-in
  packet scores remain available on their original trace. Verification includes intentionally rejected stale/cross-owner approvals, so filter before interpreting error rates.

## If something pauses or fails

- Wait for the active response; do not repeatedly click submit. A retry is safe after the UI reports failure; saved messages remain stored.
- If indexing fails, use the policy’s retry control after confirming Ollama/Docker and the app are running.
- If a model answer abstains, show the exact policy passages and explain the verification boundary. Do not present abstention as a correct cited answer. The temporary-boarding and longer pre-claim payment questions both abstained in rehearsal; do not use those as the opening success example.
- If Langfuse ingestion is delayed, refresh later or show the verified rehearsal trace linked in `docs/observability.md`. Do not mistake delayed telemetry for a missing database commit.
- If the app stops, restart with `bash scripts/start-demo.sh`. Do not delete Docker volumes or run `docker compose down -v`; that erases local data.

The signed-in browser rehearsal completed upload, indexing, cited answer, packet review,
and local approval on November 9, 2026. The final packet took 29 seconds and one automatic
revision. Earlier attempts were blocked by inconsistent model reviews. Including the
server-calculated estimate inside the review artifact was followed by a passing browser attempt.
A subsequent clean backend rehearsal still blocked on redundant payment-wording requests.
Fresh packet generation is therefore **not yet reliable enough to promise a seamless live demo**.
Use the saved approved packet as the presentation fallback; failed attempts are retained.
No real claim is filed and alerts are disabled.

Keep the [approved packet](http://localhost:5173/workspace/review?claim=eb6fa6bd-732a-4e65-8c5d-cc6fd174b233&run=2169450d-3c35-44b8-9e2f-773de663fa0c)
open before presenting. It shows “Prepared · Not submitted”. The export link contains the
complete approved text. Browser automation blocked its data-URL download, and the owner
then **confirmed a successful manual download**. Upload through local approval and file
download are now verified in the signed-in journey.


## Recorded fallback and rehearsal evidence

An earlier combined backend rehearsal indexed the policy, returned a cited deductible
answer, and reached packet review and approval with all 10 automated Boolean checks
passing. Two semantic checks remain unscored for human review. This is evidence
of one real execution, not a guarantee of identical model behavior on every attempt.

- [Cited deductible answer](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/b1c45adf6403af742384987376917d2f)
- [Signed-in packet: 11 measured passes, 2 unscored](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/1b58c27f7d4da59b08d526360b14be3a)
- [Signed-in approval and local commit](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/6589bacd8e4e8a830c2e78699191c0b4)
- [Earlier isolated packet and scores](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/daef772f227a16796dd1946e0009feea)
- [Jeeves Operations](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/dashboards/cmwa97l5504x7ad0dae5bruea)
- Signed-in reports: `reports/demo-signed-in-review.json`, `reports/demo-signed-in-approved.json`; session `2169450d-3c35-44b8-9e2f-773de663fa0c`.
- Local backup: `reports/demo-packet-backup.txt`; structured results: `reports/demo-chat.json`, `reports/demo-packet-rehearsal.json`, and `reports/demo-full-flow.json`.

If you show a saved result, say that it is a recorded rehearsal. Keep it open before
presenting so you can explain the workflow even if the model or network pauses.

## Reading the verified trace during the demo

Open the signed-in packet trace above. The **Tree** tab shows a 29.02-second root,
retrieval and query embedding, then six **model-generation** observations. Each
model-generation has provider-reported input/output tokens; the total is 12,459.
The first **agent-reviewer** has a warning because it requested a revision; the second
passed. A warning does not mean the final workflow failed: inspect the root output.

At the top, open **Show 12 more details** to see the eleven `ui_eval_...` Boolean
scores and `ui_eval_unscored_count = 2`. These scores measure this reviewable version,
not every conversation. The **session** link groups preparation and approval; the
approval trace ends with `agent-commit_action` and root status `completed`.
The database verified exactly one commit, with an exact result fingerprint match.
Normal traces omit raw policy and homeowner text, so metadata-only inputs are expected.

## Known reliability issue before production

A later clean rehearsal returned the correct cited deductible answer but blocked packet
preparation because the reviewer requested redundant narrative arithmetic. Its retained
[failed trace](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/30852de863e31bdd2427b5325dcc1347)
has six failed workflow/citation-availability checks, one passing route check, and five
unscored checks. This does not invalidate the saved approved packet. It does mean that
fresh generation still needs model/reviewer calibration before a production readiness claim.
Reports: `reports/demo-clean-retest-failure.json` and `reports/demo-clean-retest-eval.json`.
The probe now exports failed preparations too, without attempting approval or treating
unexercised safety checks as passes.
