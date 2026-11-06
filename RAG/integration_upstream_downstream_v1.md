# policy_rag Integration Guide (Upstream and Downstream)

Package version: **v2**. Owner: Srikanth. Read this before wiring your component to `policy_rag`.

`policy_rag` answers "is this covered, and how much will be paid?" questions about home insurance policy PDFs. It uses LangChain, Chroma (local vector store) and OpenAI (`text-embedding-3-small`, `gpt-4o-mini`).

## 1. Who Is Who

| S.No | Component | Role | Talks to policy_rag through |
|---|---|---|---|
| 1 | **Upstream**: front end / auth / upload service | Authenticates users, receives uploads, sends questions | `ingest_policy()`, `answer_question()`, `delete_policy()` |
| 2 | **policy_rag** (this package) | Parses, chunks, stores, retrieves, answers | n/a |
| 3 | **Downstream**: UI rendering, API responses, monitoring / analytics | Shows answers, stores results, reads trace logs | `IngestResult`, `QueryResult`, `logs/` folder |

```text
 1  UPSTREAM (front end, auth)                POLICY_RAG                              DOWNSTREAM
 2  -------------------------                 ----------                              ----------
 3  user logs in
 4  user uploads PDF ──save file──> policy_documents/
 5                   ──ingest_policy(IngestRequest)──> parse > verify > chunk > Chroma
 6                                                     returns IngestResult ─────────> UI: "upload done"
 7                                                     writes logs/ingestion/... ───> monitoring
 8  user asks question ──answer_question(QueryRequest)──> retrieve > LLM > calculator
 9                                                     returns QueryResult ──────────> UI: answer card
10                                                     writes logs/queries/... ─────> monitoring / support
```

## 2. Setup (everyone)

| S.No | Item | Requirement |
|---|---|---|
| 1 | Python | 3.12. Python 3.14 failed to install the dependencies (PyMuPDF / chromadb) |
| 2 | Install | `pip install -r requirements.txt` |
| 3 | API key | `OPENAI_API_KEY` in the environment, or in `.env` at the project root (copy `.env.example`). Never commit `.env` |
| 4 | Import | `from policy_rag.api import ...` only. Other modules are internal and may change |

Optional environment variables (defaults are folders inside the project root):

| S.No | Variable | Default | Purpose |
|---|---|---|---|
| 1 | `POLICY_RAG_UPLOAD_DIR` | `policy_documents/` | Where upstream saves uploaded PDFs |
| 2 | `POLICY_RAG_CHROMA_DIR` | `chroma_store/` | Vector store data |
| 3 | `POLICY_RAG_LOG_DIR` | `logs/` | Trace files |
| 4 | `POLICY_RAG_TRACE` | `1` | Set to `0` to switch trace files off |

## 3. Upstream Instructions (front end, auth, upload)

### 3.1 Responsibilities that stay with you

| S.No | Responsibility | Why |
|---|---|---|
| 1 | Authenticate the user | policy_rag trusts `user_id` completely |
| 2 | Confirm the user owns the policy number | policy_rag only checks that the PDF's printed policy number matches what you send |
| 3 | Validate the upload is a PDF and has a sensible size | policy_rag does not check file type or size |
| 4 | Take `user_id` from the session and `policy_number` from the user's selection | **Never** take either from the question text |
| 5 | Run ingestion off the request thread if the UI must not block | Ingestion embeds about 50 to 60 chunks via OpenAI and takes a few seconds |

### 3.2 Upload a policy

1. Save the uploaded file into `POLICY_RAG_UPLOAD_DIR`.
2. Call `ingest_policy` with the **file name only** (no folders). Names that escape the upload folder are rejected.

```python
1  from policy_rag.api import ingest_policy, IngestRequest
2
3  result = ingest_policy(IngestRequest(
4      user_id="u-1029",                                  # required: authenticated user id
5      policy_number="MCM-HO3-CA-100231",                 # required: policy the user selected
6      file_name="MCM_Policy_01_Okafor-Raman_HO3_v1.pdf", # required: file inside POLICY_RAG_UPLOAD_DIR
7      insured_name="Priya Okafor-Raman",                 # optional: read from the PDF if omitted
8      doc_version="v1",                                  # optional: default "v1"
9  ))
```

| S.No | Field | Type | Required | Notes |
|---|---|---|---|---|
| 1 | `user_id` | str | Yes | Stable id; used for access control and stored on every chunk |
| 2 | `policy_number` | str | Yes | Case-insensitive; stored upper-case |
| 3 | `file_name` | str | Yes | File name only |
| 4 | `insured_name` | str | No | Display name stored as metadata |
| 5 | `doc_version` | str | No | Tag of the uploaded document |

Re-uploading the same policy for the same user **replaces** the old chunks (`replaced_existing=True`).

### 3.3 Ask a question

```python
1  from policy_rag.api import answer_question, QueryRequest
2
3  result = answer_question(QueryRequest(
4      user_id="u-1029",                       # from the session
5      policy_number="MCM-HO3-CA-100231",      # from the user's selection
6      question="Jewelry worth $9,200 was stolen. How much is paid?",
7  ))
```

The policy must have been ingested first by the **same** `user_id`, otherwise `PolicyNotIngestedError`.

### 3.4 Remove a policy

```python
1  from policy_rag.api import delete_policy
2
3  removed_chunks = delete_policy(user_id="u-1029", policy_number="MCM-HO3-CA-100231")
```

Deleting the PDF from the upload folder is your job; `delete_policy` only removes the stored chunks.

### 3.5 Errors to catch

All errors inherit from `PolicyRagError`. Suggested HTTP mapping if you wrap this in an API:

| S.No | Exception | Raised when | Suggested HTTP status | Suggested user message |
|---|---|---|---|---|
| 1 | `InvalidRequestError` | Missing field, or bad file name | 400 | "Something is missing from the request." |
| 2 | `DocumentNotFoundError` | File not in the upload folder | 404 | "We could not find the uploaded file." |
| 3 | `PolicyMismatchError` | PDF's policy number differs from the request | 422 | "This document does not match the selected policy." |
| 4 | `PolicyNotIngestedError` | Question for a policy this user has not uploaded | 409 | "Please upload this policy first." |
| 5 | Other `PolicyRagError` (e.g. model output could not be parsed) | Rare | 502 | "We could not answer right now. Please try again." |
| 6 | OpenAI client errors (network, rate limit, bad key) | Not wrapped | 503 | "The answer service is unavailable." |

### 3.6 Deployment constraints

| S.No | Constraint | What to do |
|---|---|---|
| 1 | Chroma runs as a local persistent store | Run policy_rag in **one** process (one worker). Multiple processes writing the same `chroma_store/` is not supported |
| 2 | Calls are synchronous | Use a thread pool or task queue for ingestion if needed |
| 3 | Changing `EMBEDDING_MODEL`, `CHUNK_SIZE_CHARS` or the collection name in `config.py` | Re-ingest every policy |

### 3.7 Example wrapper (FastAPI, for reference only)

```python
 1  from dataclasses import asdict
 2  from fastapi import Depends, FastAPI, HTTPException
 3  from policy_rag.api import (answer_question, QueryRequest, PolicyNotIngestedError,
 4                              InvalidRequestError, PolicyRagError)
 5
 6  app = FastAPI()
 7
 8  @app.post("/policies/{policy_number}/questions")
 9  def ask(policy_number: str, body: dict, user=Depends(current_user)):   # current_user = your auth
10      try:
11          result = answer_question(QueryRequest(user.id, policy_number, body["question"]))
12      except InvalidRequestError as e:
13          raise HTTPException(400, str(e))
14      except PolicyNotIngestedError as e:
15          raise HTTPException(409, str(e))
16      except PolicyRagError as e:
17          raise HTTPException(502, str(e))
18      return asdict(result)
```

## 4. Downstream Instructions (UI, API consumers, monitoring)

### 4.1 `IngestResult`

| S.No | Field | Type | Meaning |
|---|---|---|---|
| 1 | `policy_number` | str | Upper-case policy number |
| 2 | `file_name` | str | Stored file name |
| 3 | `chunks_stored` | int | Number of chunks saved (about 47 to 57 for the test policies) |
| 4 | `form` | str or None | Policy form read from the PDF, e.g. `HO-3` |
| 5 | `replaced_existing` | bool | True when an earlier upload was replaced |
| 6 | `trace_id` | str or None | Id of the ingestion trace file (None when tracing is off) |

### 4.2 `QueryResult`

| S.No | Field | Type | Meaning | How to show it |
|---|---|---|---|---|
| 1 | `covered` | str | `Yes`, `No`, `Partial`, `N/A`, `Not addressed` | Badge (see 4.3) |
| 2 | `amount_payable` | float or None | Amount computed in Python from the policy rule. **Use this one** | Currency; hide when None |
| 3 | `llm_amount` | float or None | The model's own figure, for audit only | Do not show to end users |
| 4 | `amount_check` | str | `match`, `mismatch` or `n/a` | On `mismatch`, show "needs review" and log it |
| 5 | `answer_summary` | str | One or two sentence answer | Main text |
| 6 | `calculation_explanation` | str | Step-by-step calculation | Expandable "How we calculated this" |
| 7 | `sources` | list of `SourceChunk` | Policy sections the answer used | "Based on: page 6, Section I ..." |
| 8 | `trace_id` | str or None | Id of the query trace file | Show in support / debug views |
| 9 | `policy_number`, `question` | str | Echo of the request | Optional |

`SourceChunk` fields: `chunk_id`, `heading_path`, `page`, `chunk_type`.

Serialise with `dataclasses.asdict(result)`. Example JSON:

```json
 1  {
 2    "policy_number": "MCM-HO3-CA-100231",
 3    "question": "Jewelry worth $9,200 was stolen. How much is paid?",
 4    "covered": "Partial",
 5    "amount_payable": 1500.0,
 6    "llm_amount": 1500.0,
 7    "amount_check": "match",
 8    "answer_summary": "Theft of jewelry is covered but limited to $1,500.",
 9    "calculation_explanation": "$9,200 - $2,500 deductible = $6,700, capped at the $1,500 special limit.",
10    "sources": [{"chunk_id": "u-1029::MCM-HO3-CA-100231::v1::0004", "heading_path": "Declarations Page > Deductibles",
11                 "page": 3, "chunk_type": "declarations"}],
12    "trace_id": "ec9b73f7444e489d8b5813830c2583af"
13  }
```

### 4.3 Meaning of `covered`

| S.No | Value | Meaning | Suggested UI |
|---|---|---|---|
| 1 | `Yes` | Covered; paid in full after the deductible | Green "Covered" |
| 2 | `Partial` | Covered but capped or reduced by a limit | Amber "Partially covered" |
| 3 | `No` | Not covered, excluded, or nothing payable (`amount_payable` = 0) | Red "Not covered" |
| 4 | `N/A` | Factual question with no payment (e.g. "What is my deductible?") | Neutral, text only |
| 5 | `Not addressed` | The policy text does not answer the question | Grey "Not found in your policy" |

Always show a disclaimer such as "Estimate based on your policy text; the final claim decision is made by the insurer."

### 4.4 Trace logs (monitoring, support, analytics)

| S.No | Path | Content |
|---|---|---|
| 1 | `logs/queries/<YYYY-MM-DD>/<HHMMSS>_<policy>_<trace8>.json` | Full trace of one question |
| 2 | `logs/ingestion/<YYYY-MM-DD>/<HHMMSS>_<policy>_<trace8>.json` | Full trace of one upload |
| 3 | `logs/query_index.jsonl` | One line per question: trace_id, started_at, status, duration_ms, file, user_id, policy_number, question, covered, amount_payable, amount_check |
| 4 | `logs/ingestion_index.jsonl` | One line per upload: trace_id, started_at, status, duration_ms, file, user_id, policy_number, file_name, chunks_stored |

Every trace file has these top-level keys: `trace_id`, `kind`, `status` (`ok` / `error`), `started_at`, `ended_at`, `duration_ms`, `context`, `settings`, `steps`, `result`, `error`. Each entry in `steps` has `step_no`, `depth`, `parent_step`, `function`, `started_at`, `ended_at`, `duration_ms`, `status`, `details`.

Useful signals for monitoring:

| S.No | Signal | Where |
|---|---|---|
| 1 | Failed requests | `status = "error"` in the index files |
| 2 | Latency | `duration_ms` (whole request) and per step |
| 3 | Token usage / cost | `steps[function = policy_rag.qa.call_llm].details.token_usage` |
| 4 | Arithmetic disagreements | `amount_check = "mismatch"` |
| 5 | Unanswerable questions | `covered = "Not addressed"` |

**The logs contain user ids, questions and policy text. Treat them as confidential:** restrict access, do not ship them to third-party tools without approval, and agree a retention period. The API key is never logged.

## 5. Compatibility Rules

| S.No | Rule |
|---|---|
| 1 | Only `policy_rag.api` is public. Fields listed in sections 3 and 4 will not be removed or renamed without a version bump |
| 2 | New optional fields may be added to results at any time; downstream code must ignore unknown fields |
| 3 | Breaking changes are announced with a new package version (v3, v4 ...) and a note in `DECISIONS_vN.md` |

## 6. Integration Checklists

**Upstream**

| S.No | Check |
|---|---|
| 1 | Python 3.12 environment with `requirements.txt` installed |
| 2 | `OPENAI_API_KEY` provided through secrets management or `.env` |
| 3 | Upload saved into `POLICY_RAG_UPLOAD_DIR` and only the file name passed |
| 4 | `user_id` from the session; `policy_number` checked against the user's account |
| 5 | All `PolicyRagError` subclasses and OpenAI errors handled |
| 6 | policy_rag runs in a single process |

**Downstream**

| S.No | Check |
|---|---|
| 1 | Display uses `amount_payable`, not `llm_amount` |
| 2 | All five `covered` values handled, including `Not addressed` |
| 3 | `amount_check = "mismatch"` shown as "needs review" |
| 4 | Sources shown with page and heading |
| 5 | `trace_id` stored with any saved answer or support ticket |
| 6 | Log access restricted and retention agreed |
