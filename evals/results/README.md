# Synthetic fixture evaluation results

Recorded November 6, 2026 against the agent feature branch's deterministic in-memory fixture. The full case-by-case outputs, checks, and timings are in `fixture_dev.json` and `fixture_held_out.json`. These are fixture integration results, not live-model quality results or statistically reliable estimates. The scenarios and policy labels still need team review.

| Split | Cases | Passed checks | Failed checks | Unscored checks | Execution errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 8 | 18 | 3 | 7 | 0 |
| Held out | 4 | 3 | 1 | 1 | 0 |

The development failures are the exclusion explanation, status routing, and the unsupported-coverage response. The fixture cannot restore a saved claim and note after a simulated restart, so the held-out persistence check fails. Foreign-user API access is denied in the fixture, but direct pgvector chunk isolation is unscored because a real adapter is not connected. The six human evidence/explanation checks and the status confirmation check are unscored without human annotations or a reachable status-review outcome.

For the two controlled invalid-citation examples, the pre-review drafts referenced an unknown chunk; after one review/refinement, the displayed coverage and packet drafts used the fixture's known chunk. This is a before/after check of citation references, not proof of semantic support. The app's actual provider and reviewer need a separate evaluation using a reviewed policy and live model access.

Langfuse SDK tracing and experiments were tested with an in-memory exporter. These results were not uploaded to a live Langfuse project because project credentials were unavailable.
