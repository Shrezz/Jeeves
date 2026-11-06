# policy_rag: Design Decisions (v2)

Changes from v1: per-request trace logging (D14), API key from `.env` (D15), cosine distance in Chroma (D16), trace ids returned to the caller, test PDFs, answer key and `try_policy_rag_v3.py` bundled.

RAG over home insurance policy PDFs, built with LangChain, Chroma and OpenAI.
Public entry point and the parent-module contract: `policy_rag/api.py`.

## 1. Decisions

| S.No | ID | Decision | Choice | Where in code |
|---|---|---|---|---|
| 1 | D1 | Models | `text-embedding-3-small` for embeddings, `gpt-4o-mini` at temperature 0 for answers | `config.py` |
| 2 | D2 | Metadata per chunk | user_id, policy_number, insured_name, form, source_file, doc_version, heading_path, section, page, chunk_type, is_table, endorsement_code, chunk_id, chunk_index | `ingestion.py`, `chunker.py` |
| 3 | D2 | Identity check | The PDF's printed policy number must match the request, otherwise `PolicyMismatchError` | `policy_identity.py` |
| 4 | D3 | Chunking | Structure-aware: split on H1/H2/H3 font sizes; prefix each chunk with its heading path; one chunk per table (very long tables split by whole rows); strip running header and footer; long prose split at 1,100 chars with 150 overlap | `pdf_parser.py`, `chunker.py` |
| 5 | D4 | K | `TOP_K=6` from `FETCH_K=20`, MMR with lambda 0.6. Tune with the evaluation harness (smallest k with recall of 95% or more) | `config.py`, `retriever.py` |
| 6 | D5 | Pinned context | The policy's Declarations chunks are always added, because limits and deductibles live there | `retriever.py` |
| 7 | D6 | Hybrid search | Implemented (BM25 combined with dense using weighted Reciprocal Rank Fusion, 0.4 / 0.6) but OFF by default. Turn on if evaluation shows keyword misses (form numbers, rare terms) | `config.HYBRID_ENABLED` |
| 8 | D7 | Arithmetic | The LLM returns payment inputs per line; Python computes the amount and flags disagreement with the LLM's own figure | `calculator.py` |
| 9 | D8 | Access control | Every Chroma read is filtered by user_id AND policy_number; both come from the parent's authenticated session, never from the question | `vector_store.py` |
| 10 | D9 | Re-ingestion | Fixed chunk ids (`user::policy::version::index`); old chunks for the same user and policy are deleted before insert | `vector_store.py` |
| 11 | D10 | Output format | Structured `CoverageAnswer` (covered, payment_lines, llm_amount, explanation, sources) matching the answer key columns | `contracts.py` |
| 12 | D11 | Unknown answers | The model must return "Not addressed" rather than guess | `prompts.py` |
| 13 | D12 | Evaluation | Harness over all 125 answer-key questions: covered accuracy, amount accuracy, approximate retrieval recall, LLM arithmetic mismatches; CSV output auto-versioned | `evaluation.py` |
| 14 | D13 | Storage | One persistent Chroma collection (`policy_chunks_v2`), isolated by metadata, not one collection per user | `config.py` |
| 15 | D14 | Trace logging | One JSON file per ingest and per question in `logs/`, with every step's function name, start and end timestamps, duration, status and details (candidates with scores, selected and pinned chunks, exact prompt, token usage, parsed answer, calculation, cited chunks, errors with traceback); plus one-line index files. Switch off with `POLICY_RAG_TRACE=0` | `tracing.py` |
| 16 | D15 | API key | Read from `OPENAI_API_KEY` in the shell or `<project root>/.env` (shell wins). Never logged | `config.py` |
| 17 | D16 | Distance | Chroma collection uses cosine distance so logged scores are readable (0 = identical) | `config.py` |

## 2. Deferred (add only if evaluation shows a need)

| S.No | Item | Trigger to add it |
|---|---|---|
| 1 | Multi-query rewriting (split a question into peril, limit, exclusion and endorsement sub-queries) | Retrieval recall below 95% on multi-section questions |
| 2 | Cross-encoder reranker (for example `bge-reranker-base`, 20 candidates down to 6) | Correct chunk found in the top 20 but not the top 6 |
| 3 | Whole-policy baseline (send the full policy, about 12k to 15k tokens, with no retrieval) | Run once as an accuracy ceiling to compare RAG against |
| 4 | Async / background ingestion | The front end needs non-blocking uploads |

## 3. Setup and Run

| S.No | Step | Command |
|---|---|---|
| 1 | Create a virtual environment (Python 3.10+) | `python3 -m venv .venv` then `source .venv/bin/activate` |
| 2 | Install | `pip install -r requirements.txt` |
| 3 | API key | `cp .env.example .env`, then paste the key after `OPENAI_API_KEY=` |
| 4 | Try one policy interactively | `python try_policy_rag_v3.py` |
| 5 | Ingest all 10 test PDFs and evaluate | `python -m policy_rag.evaluation --ingest` |
| 6 | Re-evaluate after tuning `config.py` | `python -m policy_rag.evaluation` |
| 7 | Read traces | `logs/queries/<date>/*.json`, `logs/query_index.jsonl` |

## 4. Trace File Contents (query)

| S.No | Step (function) | Details logged |
|---|---|---|
| 1 | `qa.run_pipeline` | Parent step; total time |
| 2 | `qa.validate_request` | Chunks stored for the policy |
| 3 | `retriever.retrieve` | Strategy, final ordered list with source tags |
| 4 | `retriever.dense_candidates` | Candidate pool (FETCH_K) with cosine distance and rank |
| 5 | `retriever.mmr_search` or `bm25_rank` + `rrf_fuse` | Selected chunks and their scores |
| 6 | `retriever.pinned_declarations` | Declarations chunks always added |
| 7 | `qa.build_messages` | Chunks sent to the LLM (full text), context size, exact messages |
| 8 | `qa.call_llm` | Model, token usage, finish reason, parsed answer |
| 9 | `calculator.compute_amount` | Payment lines, amount, LLM amount, match or mismatch |
| 10 | `qa.map_sources` | Cited tags and chunks |

Top level of every trace: trace_id, kind, status, started_at, ended_at, duration_ms, context (user, policy, question), settings snapshot, result, error.

## 5. Module Map

| S.No | Module | Responsibility |
|---|---|---|
| 1 | `api.py` | Public functions and the parent-module contract |
| 2 | `contracts.py` | Request, result and LLM output schemas |
| 3 | `errors.py` | Exceptions the parent should catch |
| 4 | `config.py` | Paths, models, chunking and retrieval settings |
| 5 | `pdf_parser.py` | PDF to ordered headings, paragraphs and tables |
| 6 | `policy_identity.py` | Read and verify policy number, form and insured |
| 7 | `chunker.py` | Elements to chunk Documents with metadata |
| 8 | `vector_store.py` | Chroma reads and writes, always filtered |
| 9 | `retriever.py` | MMR or hybrid retrieval plus pinned Declarations |
| 10 | `prompts.py` | System prompt and context formatting |
| 11 | `calculator.py` | Deterministic payment arithmetic |
| 12 | `ingestion.py` | Upload pipeline |
| 13 | `qa.py` | Question pipeline |
| 14 | `evaluation.py` | Scoring against the answer key |
| 15 | `tracing.py` | Per-request trace files and index |
