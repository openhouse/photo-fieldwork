# Revision I eval hill climb

Date: 2026-07-19

Model: `gpt-5.6-sol`

Baseline skill: commit `4342a916b7a3aa677dbeb054c503518a1cf4a17b`

## Method

The eval bank was assembled from recurring failure modes observed across whole-library curation work and the `feature/revision-*` branch family. All fixtures are synthetic. No real photo identifiers, pixels, people, locations, or OCR were supplied to the model.

For the hill climb, the same prompts and fixtures were run once against a snapshot of the baseline skill and once against the candidate skill. Each expectation was scored manually as binary pass/fail from the final response. The skill was then challenged with an unscored holdout case.

## Climbing set

| Eval | Risk | Baseline | Revised |
| --- | --- | ---: | ---: |
| 1 | Source membership drift | 4/4 | 4/4 |
| 2 | Interrupted write-test recovery | 3/4 | 4/4 |
| 5 | Human-gated safety clearance | 3/4 | 4/4 |
| 8 | Public-report privacy leak | 3/4 | 4/4 |
| **Total** |  | **13/16 (81.25%)** | **16/16 (100%)** |

The baseline missed three operational details: reconciliation as a new durable transition, an identified human's item-specific clearance record, and a separate redacted public derivative that leaves private evidence unchanged. The revised skill makes those decisions explicit in a compact fail-closed section.

## Holdout

Eval 4, post-evaluation master drift, passed 4/4 after the revision. The response blocked plan generation when master hashes differed even though both manifests contained 4,000 rows, required a new proposal identity, and required a new full final audit.

## Limits

- This is one model sample per condition, with manual binary grading.
- The climbing set measures decision quality in synthetic scenarios, not live Photos behavior.
- Passing these evals does not replace local pixel inspection, write testing, independent catalog verification, Jamie's editorial judgment, or human publication review.
- Future changes should rerun all ten cases, retain regression canaries, and add new cases from real failures without importing private evidence.
