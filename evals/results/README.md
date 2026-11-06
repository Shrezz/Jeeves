# Synthetic fixture evaluation results

Recorded November 6, 2026 against the deterministic in-memory demo fixture. The case-by-case outputs, checks, reviewer comparison, and timings are in `fixture_dev.json` and `fixture_held_out.json`. These are fixture integration results, not live-model quality results or statistically reliable estimates. The team still needs to review the scenarios and policy labels.

| Split | Cases | Passed checks | Failed checks | Unscored checks | Execution errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 8 | 22 | 0 | 6 | 0 |
| Held out | 4 | 3 | 1 | 1 | 0 |

The development cases now recognize completed repair updates, preserve a wear-and-tear cause rather than mistaking “window” for “wind,” and ask for evidence when the requested coverage is outside the synthetic policy fixture. The six human evidence/explanation checks remain unscored until reviewed annotations are supplied; `human-review.md` collects the outputs for that review.

The fixture cannot restore a saved claim and note after a simulated restart, so the held-out persistence check fails. Foreign-user API access is denied in the fixture, but direct pgvector chunk isolation is unscored because a real adapter is not connected. These two checks must be repeated against the eventual authenticated Postgres-backed application.

For two controlled invalid-citation examples, pre-review drafts referenced an unknown chunk; after review and one refinement, the coverage and packet drafts used the fixture's known chunk. This is a before/after check of citation references, not proof of semantic support. The actual provider and reviewer need a separate evaluation using a reviewed policy and live model access.

Synthetic development and held-out experiments were submitted to the team's Langfuse project. A separate synthetic development run enabled detailed content capture for that process and the exported model inputs and outputs were verified. No live-model or production-data conclusions follow from these fixture runs; project credentials and account identifiers are not stored in this repository.

The local automated run passed 131 tests and skipped 32 PostgreSQL-dependent tests. It measured 87.0% statement coverage and 72.5% branch coverage across `apps/api/app`; those figures exclude execution of the skipped database tests and the standalone `RAG/policy_rag` package, and do not establish end-to-end correctness. A separate [GitHub Actions run](https://github.com/Shrezz/Jeeves/actions/runs/42306403824) on the shared base passed 49 database tests and its database restart probe; this does not prove that the in-memory agent persists its state.
