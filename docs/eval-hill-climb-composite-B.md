# Composite B eval hill climb

Date: 2026-07-19

The preferred composite was evaluated with synthetic identifiers and generated state only. No Apple Photos library, private pixel, OCR, People association, location, or production receipt was read or changed.

## Frozen comparison

The pre-composite Revision B skill and implementation were frozen at commit `456a246`. The candidate used the same decision prompts, response schema, and executable oracles.

## Decision-behavior climb

Eight new cases cover exact quota scarcity, relational safety closure, holdout independence, stale run-state revisions, substituted upstream evidence, copied idempotence receipts, protected-source contamination, and a fully cleared publication shortlist.

The first four-case run gave both baseline and candidate 2/4 deterministic control passes. Two failures came from ambiguous facts about whether new inspection and replacement work remained required. The prompts were clarified without weakening their gates. Both versions then passed the corrected cases, and both passed the four untouched cases.

This is a useful result, not a superiority claim. Explicit synthetic prompts plus a typed response schema let a strong general model infer many safe decisions. These cases remain regression canaries, but they do not distinguish whether the repository can enforce its advice.

The model comparison used one local Codex CLI run per condition. It is diagnostic, not a variance estimate. Raw transcripts remained in a private temporary workspace and are not committed.

## Executable climb

The next iteration translated the highest-consequence claims into repository-executable oracles.

| Iteration | Frozen baseline | Composite candidate | Added pressure |
| --- | ---: | ---: | --- |
| Single-mutation bank | 0/8 | 8/8 | Exact quota scarcity, transitive HOLD, count-preserving quota drift, UUID and relation holdout leakage, stale state, evaluation substitution, validation substitution |
| Recursive expansion | 0/12 | 12/12 | HOLD plus quota scarcity, simultaneous UUID and relation leakage, double artifact substitution, event-ahead crash recovery |

The recursive expansion combines contracts that had passed separately. The candidate retained a complete pass without weakening an assertion. The frozen baseline lacks these executable capabilities and failed every oracle.

## What changed

- Selection now reports structured per-view deficits and never pads a deficient view from another assignment.
- Direct HOLD states propagate through connected perceptual, duplicate, and burst relations.
- Final holdouts are audited for canonical UUID and relation leakage with identifier-minimized reports.
- Run transitions use locked revisions and an append-only hash-linked event ledger with event-ahead recovery.
- Membership plans embed complete evaluation and validation artifacts and bind each by canonical digest.
- The eval contract requires risk coverage and separate positive controls for editor-field and publication completion.

## Stop rule

Stop expanding when the full single and compound frontier passes, the existing suite remains green, and a proposed new case does not expose a distinct observable failure. Keep prose-only cases as safety canaries. Add executable cases when the repository owns the behavior. Keep visual quality, rights, consent, dignity, collective credit, and publication approval as explicit human gates.
