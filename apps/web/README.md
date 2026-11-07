# Claimwise application source

This directory contains the current Claimwise application as a nested pnpm workspace. The existing source layout is retained so workspace dependencies resolve without modifying the rest of Jeeves.

## Layout

- artifacts/claimwise: React/Vite frontend.
- artifacts/api-server: current Express API for Clerk authentication, user-owned policies, claims, chat and evidence.
- lib: shared API clients, validation, database schema and OpenAI integration.
- scripts: workspace utility scripts.

The Express service is included to preserve the current app functionality. It is **not integrated with or a replacement for** the separate Python service in ../api. No changes outside apps/web are required by this source import.

## Install and build

Use Node.js 22 and pnpm 10. Run commands from this directory:

```sh
pnpm install --frozen-lockfile
pnpm run typecheck
PORT=19584 BASE_PATH=/ pnpm --filter @workspace/claimwise run build
pnpm --filter @workspace/api-server run build
```

## Development

Supply the required environment configuration securely, then run each service in its own terminal:

```sh
PORT=8080 pnpm --filter @workspace/api-server run dev
PORT=19584 BASE_PATH=/ pnpm --filter @workspace/claimwise run dev
```

Configure the reverse proxy to serve the frontend at / and forward /api/* to the Express service. This is how the current Replit app is routed; the Vite config does not provide a local API proxy. The repository folder apps/web is a source location, not a browser base path.

## Required services and configuration

- PostgreSQL: DATABASE_URL. Review database schema changes before applying them; do not use destructive force or truncation against existing data.
- Clerk: CLERK_SECRET_KEY, CLERK_PUBLISHABLE_KEY and VITE_CLERK_PUBLISHABLE_KEY. The current deployment uses Replit-managed Clerk and its same-origin production proxy. Configure a suitable Clerk tenant and allowed domains when hosting elsewhere.
- Private Replit App Storage: DEFAULT_OBJECT_STORAGE_BUCKET_ID, PRIVATE_OBJECT_DIR and PUBLIC_OBJECT_SEARCH_PATHS, plus the Replit runtime storage identity. Storage requires adaptation if hosted outside Replit.
- Replit OpenAI integration: AI_INTEGRATIONS_OPENAI_BASE_URL and AI_INTEGRATIONS_OPENAI_API_KEY. These are runtime-managed credentials; do not commit them.

No credentials, real policy PDFs, evidence uploads, database contents, dependencies, build outputs or design mockup workspace are included. This source import does not provision infrastructure, migrate data or publish a deployment.

## Current functional scope

Authentication, private policy uploads, user-owned dashboard/claims, claim evidence, AI text guidance, and manual status updates are implemented.

- Chat with Jeev is a separate conversational surface with its own persisted history and reply APIs; opening or sending a conversation does not create a claim.
- Dashboard sections organize conversations, claims being prepared, and submitted records. Navigation and action labels reflect Prepare Your Claim and Review Claim.
- Review Claim loads saved incident details, expenses, and basic completeness checks through an owned review API. Users can save comments or include them when submitting. Policy citations remain empty because policy wording is not analyzed.
- Submit Your Claim becomes available after a successful review load. It saves an immutable, dated snapshot and comments, records a single submission event, and marks the record Submitted in Claimwise. Repeat submissions are idempotent; stale edits and foreign-account access are rejected.

Submission is local to Claimwise; nothing is sent to an insurer and no coverage decision is made. Summary email delivery, insurer integration, PDF export, and amendments of submitted snapshots are not implemented.

The schema now includes separate Jeev conversations/messages and claim review records. Apply reviewed, non-destructive schema changes to the target database before running these features. Repository upload does not transfer existing data or run migrations.
