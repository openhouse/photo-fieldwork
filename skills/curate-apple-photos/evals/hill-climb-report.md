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

## Stop condition

The bank reached a full pass, exposed regressions on a complete repeat, and
then reached 40/40 again after targeted hardening. Every implementation defect
surfaced by the evals has a regression test. Remaining human decisions about
rights, consent, safety, editorial selection, and publication are intentionally
not automated.
