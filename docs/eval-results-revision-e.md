# Revision E skill-eval hill climb

Date: 2026-07-19

Revision E was evaluated as an agent decision protocol, not only as a Python implementation. The synthetic suite asks whether an agent using the skill will preserve evidence, block unsafe transitions, continue when a correction is honestly available, and distinguish a verified private editor field from publication permission.

## Method

- The original Revision E skill was frozen before instruction changes.
- Every executor received only one copied skill and one synthetic fixture in an isolated, read-only workspace.
- Executors could not see the rubric or another skill version.
- The controlled comparison ran the frozen v0 and final v4 skills against the same sanitized fixtures, structured response schema, and final semantic rubric.
- Each finding had to name a disposition, active gate, evidence IDs, required action, and Photos-mutation status.
- Supported claims had to cite attached evidence. Unknown evidence IDs failed.
- The controlled runner cleared stale responses and recorded skill-tree, suite, prompt, and response hashes. The final runner also bounds executor duration.
- No Apple Photos library, private manifest, pixel, OCR, People association, or location was accessed.
- Generated transcripts stayed in a temporary private workspace and were not committed.

The executor was `codex-cli 0.145.0-alpha.18` with its default model. The controlled full-suite scores use one run per configuration and are diagnostic rather than confidence intervals. Intermediate developmental runs changed both the skill and the evals, so they are used to explain the hill climb rather than presented as controlled comparisons.

## Results

| Version | Change | Trials | Expectations | Pass rate |
| --- | --- | ---: | ---: | ---: |
| v0 | Frozen original Revision E skill | 1 per eval | 100 / 116 | 86.21% |
| v4 | Final decision contract and evidence-closed grader | 1 per eval | 116 / 116 | 100% |

The focused v4 regression reran preview integrity, replacement/cluster closure, and assignment scarcity twice each: 78 / 78 expectations passed under the final rubric.

Developmental v1-v3 rounds introduced release dispositions and final holdouts, stabilized report vocabulary, moved essential rules from a reference into the primary skill, and exposed weaknesses in the evals themselves. Their exploratory scores are retained in `history.json` with `benchmark_scope: developmental` but are not directly compared in this table.

## What changed under pressure

The original skill correctly detected source drift, weak views, corrupt previews, replacement leakage, altered receipts, and quota scarcity. Its meaningful failures were at higher-level boundaries:

- it labeled a blocked publication request as `EDITOR_FIELD_VERIFIED` because the private editor field itself was verified;
- it blocked the entire field when an optional project-proof view was unsupported, instead of omitting the view and continuing honestly;
- it reported absent publication evidence as `blocked` during an otherwise complete editor-field release;
- it did not always cite the complete source-to-verification chain when declaring completion.

The hill climb added scoped dispositions, independent editor/publication states, an explicit `hypothesis_resolution` path, untouched final holdouts, complete release-chain citations, allowlisted public projection, and canonical report vocabulary.

The evals also changed. Early grading over-penalized semantically equivalent gate and finding names and ignored evidence cited in structured claims. The final grader accepts documented semantic aliases while retaining strict checks on disposition, evidence closure, unsupported claims, and mutation boundaries. A repairable run may be `in-progress` while its requested transition remains `BLOCKED`.

## Limits

These evals test instruction-following and release judgment over synthetic artifacts. They do not evaluate visual taste, contact-sheet interpretation, PhotoKit behavior, macOS permissions, whole-library throughput, or the truth of claims in a real archive. Those remain separate local integration, visual review, and human approval gates.
