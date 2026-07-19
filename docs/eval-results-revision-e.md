# Revision E composite skill-eval hill climb

Date: 2026-07-19

Revision E was evaluated as an agent decision protocol, not only as a Python implementation. The synthetic suite asks whether an agent using the skill will preserve evidence, block unsafe transitions, continue when a correction is honestly available, and distinguish a verified private editor field from publication permission.

The composite pass expanded the suite from nine to fourteen cases after reviewing the complete `feature/revision-A` through `feature/revision-N` family. The five new cases target exact candidate binding, ledger recovery, relationship-level holdout leakage, receipt self-authorization, and helper capability negotiation.

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

## Composite expansion

The frozen v4 skill and every composite iteration received the same five new fixtures and final rubric. The rubric remained hidden from executors.

| Version | Change | Expectations | Pass rate |
| --- | --- | ---: | ---: |
| Frozen v4 | Pre-composite skill on five new hostile cases | 54 / 65 | 83.08% |
| v5 composite | Initial composite instructions | 57 / 65 | 87.69% |
| v6 composite | Exact contradiction codes and evidence facts | 63 / 65 | 96.92% |
| v7 composite | Requested-transition disposition and calibrated semantic aliases | 65 / 65 | 100% |
| v7 robustness repeat | Two fresh runs per new case | 129 / 130 | 99.23% |
| v8 targeted repair | Run-integrity dependency ordering, three fresh runs | 39 / 39 | 100% |
| v8 source regression | Count-versus-membership distinction, two fresh runs | 26 / 26 | 100% |
| v8 full suite | Fourteen cases, one fresh run each | 181 / 181 | 100% |
| v9 final composite | Exact pull-request skill after final public-audit and report-recomputation edits | 181 / 181 | 100% |

The robustness repeat exposed one case where the agent found every underlying problem but selected `production_verification` instead of the earlier `run_integrity` gate. The repair made the dependency ordering explicit and passed three fresh targeted runs.

The final full-suite response initially scored 180 / 181 because the grader accepted the literal phrase `zero missing` but not the semantically identical `no missing`. The assertion was corrected to accept both forms, and the unchanged fourteen responses regraded at 181 / 181. No product rule or agent output was weakened to obtain that point.

After the final instruction and implementation edits, a fresh fourteen-case run passed 181 / 181 expectations without regrading. Its skill-tree SHA-256 is `64b1a0b2ea918baa569026e7557bf462771e7c745416acb45fcab1a2fc517de3`; its suite SHA-256 is `729df3055b9df9b3607e7b9198d71f8af525b0717ecc82e5e846c67bc68ae823`. The generated responses and transcripts remain in the private evaluation workspace rather than the repository.

These are single-model synthetic decision trials, not statistical confidence intervals. The repeated subsets are robustness checks, not evidence about visual judgment or live catalog behavior.

## What changed under pressure

The original skill correctly detected source drift, weak views, corrupt previews, replacement leakage, altered receipts, and quota scarcity. Its meaningful failures were at higher-level boundaries:

- it labeled a blocked publication request as `EDITOR_FIELD_VERIFIED` because the private editor field itself was verified;
- it blocked the entire field when an optional project-proof view was unsupported, instead of omitting the view and continuing honestly;
- it reported absent publication evidence as `blocked` during an otherwise complete editor-field release;
- it did not always cite the complete source-to-verification chain when declaring completion.

The hill climb added scoped dispositions, independent editor/publication states, an explicit `hypothesis_resolution` path, untouched final holdouts, complete release-chain citations, allowlisted public projection, canonical report vocabulary, exact release-candidate identity, event-ledger precedence, relationship-level split isolation, helper capability negotiation, and receipt anti-self-authorization.

The evals also changed. Early grading over-penalized semantically equivalent gate and finding names and ignored evidence cited in structured claims. The final grader accepts documented semantic aliases while retaining strict checks on disposition, evidence closure, unsupported claims, and mutation boundaries. A repairable run may be `in-progress` while its requested transition remains `BLOCKED`.

## Limits

These evals test instruction-following and release judgment over synthetic artifacts. They do not evaluate visual taste, contact-sheet interpretation, PhotoKit behavior, macOS permissions, whole-library throughput, or the truth of claims in a real archive. Those remain separate local integration, visual review, and human approval gates.
