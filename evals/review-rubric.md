# Human evidence-review rubric

Review only fictional scenarios and preserve the supplied held-out split. Inspect the actual answer and the exact retrieved policy passage, including its section, page, exclusions, and limits. Record two independent booleans for each answer case:

- `citation_support_human`: `true` only if the cited passage supports the material coverage claims and relevant limiting provisions are represented. A missing, invented, unrelated, or contradictory citation is `false`.
- `explanation_correct_human`: `true` only if the explanation matches the fixture facts and policy, distinguishes uncertainty, and states the deductible correctly where applicable. If facts are missing, a justified clarification is acceptable.

Mark a field `false` when the answer is unsupported or materially incorrect. If a reviewer cannot determine the answer, omit that field; it remains unscored. Reviewer agreement alone is not ground truth.

Save annotations as a JSON object keyed by scenario ID, for example after a human has reviewed that actual run:

```json
{
  "dev_01_covered_question": {
    "citation_support_human": true,
    "explanation_correct_human": false
  }
}
```

The values above illustrate the format; they are not an actual review. Pass the file to `fixture_suite.py` with `--annotations path/to/annotations.json`. Current answer cases are `dev_01_covered_question`, `dev_04_exclusion`, and `dev_07_unsupported_evidence`.
