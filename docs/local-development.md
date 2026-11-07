# Local UI, Clerk and PostgreSQL

This setup runs the existing Claimwise React UI and Express API with real Clerk
development sessions and a dedicated local database using the shared UI schema.
Local policy uploads use the RAG parser, chunker and vector search. Local claim chat uses the LangGraph router, the linked policy index and a persistent human review step.

The combined dashboard and shared-identity workflow require UI migration
`0006_review_chat_integration.sql`. A local Claimwise submission is not an insurer
filing. Earlier identity migrations deliberately stop on unrecognized historical
statuses; reconcile existing data explicitly before migrating. This migration has
not been validated against an existing populated deployment.

## Configuration from you

In the [Clerk dashboard](https://dashboard.clerk.com/), select or create an
application's **Development** instance. Use email sign-in/sign-up, which the current
UI exposes. Copy its two API keys into `apps/web/.env.local`:

```dotenv
CLERK_PUBLISHABLE_KEY=pk_test_your_development_key
CLERK_SECRET_KEY=sk_test_your_development_secret
```

Both keys must belong to the same development instance. Keep the secret in this
Git-ignored file, not in chat or a variable beginning with `VITE_`. The launcher
passes only the publishable key to Vite. It supplies the matching frontend key,
local URLs, and database URL itself. Production keys are rejected by this launcher.

No database account, OpenAI/Nebius key, or Replit credential is needed for this step.
See [Clerk's key configuration](https://clerk.com/docs/guides/development/clerk-environment-variables).

## First-time dependencies

Use Node.js 22+, pnpm 10+, Python 3.11+ and a running Docker Desktop.
From the repository root, if the dependencies have not already been installed:

```sh
cd apps/api
python3 -m venv .venv
.venv/bin/python -m pip install -e . -r requirements-db.txt
cd ../../RAG
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd ../apps/web
pnpm install --frozen-lockfile
```

On Windows, use `.venv\Scripts\python.exe` instead. If `apps/api/.venv` already
exists for the agent service, reuse it with the same install command.
Copy `.env.local.example` to `.env.local` if that file has not been created yet.

## Start

From `apps/web`:

```sh
pnpm run check:local
pnpm run dev:local
```

The config check validates presence/shape without printing key values; sign-in
still needs live verification. The launcher:

1. Starts the `jeeves-local` PostgreSQL Compose project and waits for readiness.
2. Applies only `apps/web/lib/db/migrations`, preserving data and checking history.
3. Initializes the LangGraph checkpoint tables in the local database, then builds and starts Express on `127.0.0.1:8080`.
4. Starts Vite and serves the UI at **http://localhost:5173**.

Always open `localhost:5173` for this setup: that origin is allowed in Clerk's
backend session validation. Vite proxies `/api` to Express, so browser cookies and
requests stay on the same origin. The development instance talks directly to
Clerk; the Replit Clerk proxy is unused.

PostgreSQL is bound to `127.0.0.1:54329`, database/user `jeeves_local` / `jeeves`,
with the local-only password in `compose.local.yml`. The named Docker volume
`jeeves-local_local_postgres` preserves records across restarts. This is separate
from the older prototype Compose project and any other local applications.

## What you can verify

- Sign up or sign in: the first authenticated API request mirrors the Clerk ID in `users`.
- Open the dashboard and create a claim (a policy is optional).
- Add a message or expense; reopen the claim or refresh to confirm it is saved.
- Record a status and comment; confirm the friendly label and saved history.
- Sign out/in and confirm the same account still sees its records.

These are real database writes. No fabricated user or auth bypass is used.

### Upload and verify a policy

1. Open **Upload Policy** and select `data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf`.
2. Name the policy and select **Save policy**. The first local index downloads Chroma's
   MiniLM model (about 80 MB); subsequent indexing and searches use the cached model.
3. Look for **Indexed** and the passage count. Open **Search this policy** on the success
   screen or dashboard. Ask: “How much is allowed for temporary window boarding?”
   The sample returns clause W-17 on **page 2**, with a **$275** limit. Results are
   excerpts from the PDF, not a coverage verdict.
4. A failed index leaves the original downloadable and offers **Retry indexing**;
   image-only PDFs need OCR, which is not included. Repeated retries reuse the policy UUID.

From **Upload Policy → Recently saved**, choose **View policy details** to reopen any
saved local policy. The details view reads explicitly labeled entries on declarations
pages within the first eight pages of the original PDF. It shows the source wording and
page, independently of RAG indexing. Unsupported layouts and scans can still be
downloaded. The optional deductible entered at upload stays separate from the PDF.

PostgreSQL stores the original bytes in `policy_documents`; policy metadata tracks upload and
index status separately. The local content endpoint accepts only the owner's unexpired,
pending upload and validates PDF bytes and size (20 MB maximum). Once received, bytes
cannot be replaced. Nonlocal deployments keep their existing object-storage path.

Express passes the verified owner and policy UUID to a private Python process. It runs the
existing layout parser and section chunker, embeds each passage with local MiniLM, and upserts
into a separate persistent Chroma collection. Every search filters both owner and policy UUID;
a matching printed policy number is not an authorization key. CPU model and index files live
under Git-ignored `data/generated/local-rag/`. Keep that directory as well as the PostgreSQL
volume across restarts. The local launcher serializes vector operations for one API instance;
it is not a production job queue. A retry can resume an interrupted index.

### Ask about a linked policy in chat

Run Ollama locally with `gemma4:12b` installed (`ollama pull gemma4:12b` if needed).
The desktop app or `ollama serve` must listen on 127.0.0.1:11434. No model key is
required. To use a different installed model that supports structured output,
set `OLLAMA_MODEL` in `apps/web/.env.local` and restart the launcher.
The selected runtime must support JSON-schema structured output. If it returns
HTTP 501, use a compatible Ollama build/model; the worker does not silently fall
back to unconstrained output. Some Homebrew/MLX builds have had a missing grammar
library: https://github.com/ollama/ollama/issues/18597

Open **File Your Claim**, select the indexed policy under **Saved policy**, create
a draft, then use **Ask**. First ask “A window broke. Is the repair covered?”
Then supply the cause and cost. The answer should explain any deductible separately
from coverage. Expand **Policy evidence** to see the original quotes and page numbers.
The policy dashboard’s **Find passages** is a direct search without a model.

To test packet preparation, use a claim that already includes the incident date,
cause, repair description and cost, then type **lets file the claim** in the conversation.
The LangGraph router selects the filing node. It reads the homeowner’s saved notes,
searches their linked policy, and asks a second model call to review the draft.
A zero payment estimate does not prevent preparation. A reported receipt is not
marked as an uploaded attachment. Missing material facts can be supplied through
**Provide missing details**.

Choose **Review claim packet** to see the narrative, amounts, evidence and decision.
The packet remains a draft until the homeowner approves that exact version. The reviewer
can request a revision before the human sees it; the homeowner can request changes or
decline. Approval saves a downloadable local packet marked **Prepared — not submitted**.
There is no outbound filing integration. Asking to update a status in chat similarly
produces a proposal; the explicit manual status form remains a direct manual update.

The web API binds each run to a saved message and the authenticated Clerk owner.
The local Python worker uses the compiled graph and PostgreSQL checkpoints under
`claim_graph`. Chat/review projections and approved local actions live in the shared
UI database; closing the tab or restarting the worker does not approve or lose a review.
Retry a failed generation on the saved message to avoid recording an expense twice.

Ollama is the default. There is no provider fallback. To explicitly send chat context
and retrieved passages to Nebius instead, set `CLAIM_CHAT_PROVIDER=nebius`,
`NEBIUS_API_KEY`, `NEBIUS_GENERATOR_MODEL`, and `NEBIUS_REVIEWER_MODEL` in the
server-side `.env.local` and restart. The local test does not use those credentials.

### Langfuse observability

Optionally set `LANGFUSE_TRACING_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` in the ignored server-side
`apps/web/.env.local`, and restart the local launcher. The UI claim worker exports
metadata-only workflow, model, and retrieval observations; the policy worker
exports ingestion, embedding and vector-search observations. Claim-driven policy
search carries trace context into the child process; independent uploads create
their own trace. Raw questions, prompts, policy excerpts, credentials, and vectors
are not included by default. Never put secrets in VITE_ variables. For an explicitly
fictional local claim only, set `LANGFUSE_CAPTURE_SYNTHETIC_CONTENT=true` and
`JEEVES_SYNTHETIC_TRACE_CLAIM_IDS` to a comma-separated allowlist of claim UUIDs.
For those claims model inputs and outputs are sent to Langfuse; best-effort redaction
does not remove all personal data. Never include real policyholder data or secrets in
those claims. Clear both settings after the synthetic test and restart the launcher.

To enable the optional separate public-search field set
`KEENABLE_SEARCH_ENABLED=true` and optionally a server-side `KEENABLE_API_KEY`.
Only the separate query the user enters is sent to Keenable; the claim message,
documents and attachments are not automatically sent. Public results are displayed
separately and are not used to establish coverage or as policy citations.

### Claim-topic guardrail

The claim agent checks the user's message and any public-search query before
calling the router, a model, or web search. Jeev chat and the hosted fallback
perform the same check before their model calls. Out-of-scope messages receive
a fixed response and are excluded from later model conversation history. The
claim review endpoints also check clarification and edit text before resuming.
The guard is a conservative English keyword and pattern heuristic, not a semantic
classifier or security boundary: it can reject relevant wording and can miss
irrelevant requests that use insurance terms. Ask users to rephrase ambiguous
questions and review the shared cases in `evals/datasets/prompt_scope_cases.json`
when changing either implementation. A short answer such as `yes` or `$650` is
allowed in a claim or clarification context. Guarded messages are still saved in
the local conversation; avoiding a model call does not delete the message.

See `evals/README.md` for synthetic workflow, retrieval, and embedding experiments.

## Stop and restart

Ctrl+C in the launcher stops the UI/API. PostgreSQL remains running. From the repo
root, stop it without deleting data:

```sh
docker compose -f compose.local.yml stop
```

Run `pnpm run dev:local` from `apps/web` to restart. Do not use `down -v` if you want
to keep records. Restart the launcher after changing Clerk keys.

The Python synthetic agent demo, if separately running on port 8000, remains
independent of this UI/database.
