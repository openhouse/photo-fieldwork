# Recursive eval hill climb

Date: 2026-07-19

This report records the aggregate results of recursively evaluating the
`curate-apple-photos` skill. The raw model outputs and grader evidence remained
in a private temporary workspace because they can include local execution
context. No Apple Photos library was read or changed during these evals.

## Results

| Round | Scope | Result | What it established |
| --- | --- | --- | --- |
| Baseline | 10 evals, 40 expectations | 33/40 (82.5%) | Exposed missing contracts for protected album recursion, unsupported-view gaps, and default-closed public projection. |
| Revised | 10 evals, 40 expectations | 40/40 (100%) | Confirmed that the first repairs addressed every recorded failure. |
| Robustness repeat | 10 evals, 40 expectations | 37/40 (92.5%) | Found three retrieval-sensitive omissions in the release dependency chain. |
| Targeted repair | 3 evals, 12 expectations | 12/12 (100%) | Verified resumed inspection, holdout identity, and post-freeze invalidation repairs. |
| Final repeat | 10 evals, 40 expectations | 40/40 (100%) | Repeated a complete pass after hardening the shared contracts. |

## Composite extension

Revision L then added evals 11-19 for joint assignment, append-only recovery,
relational holdout freshness, candidate-bound release, distinct execution
evidence, eval governance, and a valid `PROCEED` control.

| Round | Scope | Result | What it established |
| --- | --- | --- | --- |
| Frozen pre-composite baseline | New evals 11-18, 32 expectations | 21/32 (65.625%) | Quantified the missing production contracts without using the revised skill as its own baseline. |
| First composite | Evals 11-19, 36 expectations | 32/36 (88.89%) | Added broad coverage but left recovery, replacement provenance, and verification details underspecified. |
| Strict full repeat | Evals 11-19, 36 expectations | 32/36 (88.89%) | Reproduced four explicit omissions under a fresh generation and strict operational grader. |
| Targeted repair | Evals 11, 13, 14, and 15, 16 expectations | 16/16 (100%) | Confirmed the repaired hypothesis, recovery, replacement, and verifier contracts. |
| Final full repeat | Evals 11-19, 36 expectations | 36/36 (100%) | Passed every composite expectation with valid transition ordering and explicit evidence scope. |
| Independent review | Candidate implementation | 8 release and compatibility findings | Exposed legacy migration, holdout-export, candidate-binding, launch-drift, auxiliary-membership, receipt-outcome, supersession, and eval-audit gaps. |
| Post-review extension | Evals 20-21, 8 expectations | 8/8 (100%) | A fresh operator response and strict grader passed the new release-bypass and compatibility cases. |
| Second independent review | Repaired candidate implementation | 6 findings | Exposed relation loss in reviewed exports, sequential floor infeasibility, stale nonce authorization, duplicate catalog keys, adapter-plan drift across idempotence attempts, and production solver cost. |
| Second post-review extension | Evals 22-27, 24 expectations | 24/24 (100%) | A fresh operator response and separate strict grader passed every new expectation with no failure cluster. |
| Third independent review | Repaired candidate implementation | 5 findings | Exposed a status-only write-test gate, collapsed equal-membership album roles, relation identifiers omitted from holdout identity, incomplete prior-feedback schemas, and adapter validation/hash time-of-check gaps. |
| Third post-review extension | Evals 28-32, 20 expectations | 20/20 (100%) | A fresh operator response and separate strict grader passed every new expectation with no failure cluster. |
| Closure review | Repaired candidate implementation | 2 high findings | Found that bridge validation still reopened adapter bytes and that a nonce-bearing runtime plan could be replaced before the writer or verifier opened its pathname. |
| Fourth post-review extension | Eval 33, 4 expectations | 4/4 (100%) | A fresh operator response and separate strict grader passed the end-to-end runtime-plan substitution case. |

## Changes driven by failures

- Made source count and sorted membership fingerprint drift explicit, including
  recursive exclusion of generated, private-review, and write-audit albums.
- Required cumulative inspection receipts when a Swift inspection resumes.
- Preserved final-holdout identity and run-lock context through offline review.
- Enforced event caps while satisfying diversity floors.
- Required explicit unsupported-view gap reports and distinguished an
  unrecovered view from evidence that no relevant photograph exists.
- Centralized the release dependency chain from frozen master through final
  holdout, safety review, test write, production write, and verification.
- Invalidated downstream approvals whenever a frozen master changes.
- Kept public projection default-closed, allowlisted, and limited to opaque
  identifiers and approved editorial fields.
- Replaced first-match overlap handling with globally optimized deterministic
  assignment under exact quotas and event caps.
- Added append-only artifact invalidation and numeric-revision recovery.
- Bound release to relation-clean holdout evidence, the current run lock and
  source, one exact adapter plan, distinct nonces, and a verified write-test gate.
- Added a pre-mutation helper capability handshake and fresh read-only source,
  topology, and exact-membership verification.
- Migrated pre-ledger schema-v2 workspaces into an explicitly marked genesis
  event without inventing historical transitions.
- Recomputed locked master, config, evaluation, leakage, and validation
  identities at registration and every execution gate.
- Restricted every adapter album to a catalog membership or locked,
  candidate-derived auxiliary set and required exact receipt outcomes.
- Added append-only plan supersession after governed invalidation and refreeze.
- Made every eval case individually runnable so weakened cases cannot disappear
  behind overlapping dimension coverage.
- Preserved perceptual, duplicate, and burst identities through offline review
  alongside the candidate master and proposal identities.
- Replaced sequential floor swaps with deterministic alternating-path
  backtracking that can reconsider an already-satisfied floor.
- Revoked writer-facing nonces after candidate invalidation or registration
  supersession and rejected duplicate catalog album keys before map conversion.
- Required idempotence attempts to execute identical adapter-plan bytes.
- Added exact dominance pruning for uncapped assignment edges while retaining
  every capped-view edge and all floor-repair candidates. On the recorded
  6,000-candidate, 4,000-target synthetic benchmark, solver edges fell from
  6,000 to 4,000 and elapsed time fell from 57.458 seconds to 32.957 seconds.
- Required production authorization to join the current plan to a completed
  write-test nonce, immutable receipt, and independently produced read-only
  verification report with zero membership discrepancies.
- Replaced membership-set equivalence with an exact semantic
  role-to-membership map, preserving distinct master, view, and auxiliary
  albums even when their memberships happen to be equal.
- Included perceptual, duplicate, and burst identifiers in final-holdout sample
  identity and rejected prior-feedback inputs that omit any relation column.
- Parsed, validated, and hashed one immutable adapter byte buffer at release
  begin, then required the writer bridge to execute those same authorized bytes.
- Content-addressed the generated runtime plan out of band, required each writer
  to verify one captured read before mutation, recorded that digest in the
  receipt, and made independent verification rehash the plan against it. The
  AppleScript path executes an in-memory script with identifiers embedded from
  the verified runtime content rather than reopening mutable membership files.

## Stop condition

The original bank reached a full pass, exposed regressions on a complete
repeat, and then reached 40/40 again after targeted hardening. The composite
extension independently climbed from 65.625% to a strict 36/36 full pass. The
post-review extension then passed 8/8 under a fresh generation and strict
grader. The second review extension passed 24/24 under another fresh generation
and independent strict grader. The third review extension passed 20/20 under a
third fresh generation and independent strict grader. The closure review then
found two runtime handoff defects beneath that score; eval 33 passed 4/4 after
their repair under a fourth fresh generation and independent strict grader.
Every implementation defect surfaced by the evals and independent review has a regression test.
Remaining human decisions about rights, consent, safety, editorial selection,
and publication are intentionally not automated.
