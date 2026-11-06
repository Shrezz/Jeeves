# Claim Companion

MVP workspace for a synthetic homeowners insurance claim assistant.

## Layout

- `apps/web/` — user interface.
- `apps/api/` — API, workflow, and policy RAG service.
- `packages/contracts/` — shared API contracts.
- `evals/` — synthetic scenarios and evaluation runner.
- `data/fixtures/` — fictional demo policy materials only.
- `docs/` — architecture and team contracts.

The backend now includes an executable agent workflow and UI-facing API. Login, UI,
real policy indexing, and database adapters remain separate integrations.

## RAG core

The API includes page-aware policy PDF extraction and chunking, with injected interfaces for embeddings and pgvector storage. See `apps/api/app/services/rag/README.md`.

## Run the backend locally

Copy `.env.example` to `.env`, set a local `JEEVES_DEMO_TOKEN`, and keep
`MODEL_MODE=fixture` for a no-credit synthetic demo. Then, from the repository root:

```bash
cd apps/api
uv sync --locked --group dev
uv run --locked uvicorn app.main:app --env-file ../../.env --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` and use **Authorize** with the demo token.
Seeded selections are `demo-policy` and `demo-window`. The demo uses scripted model
responses and synthetic evidence; it is not a live RAG or model-quality demonstration.
All demo state, pending approvals, and artifacts reset on restart. Use one worker.

Set `MODEL_MODE=nebius` and configure the API key and two model IDs to use real models
with the synthetic adapters. This consumes Nebius credits. No OpenAI fallback is enabled.

See [backend integration](docs/backend-integration.md) for the execution checklist,
[API contracts](docs/api-contracts.md) for UI examples, and
[node review guide](docs/agent-nodes-review.md) for the reading order.
