# Curate Apple Photos evals

These synthetic evals test whether the skill preserves its operating contract
under plausible pressure. They do not contain photographs, private identifiers,
real People associations, OCR, locations, or production receipts.

## What the bank measures

Each case names a concrete failure mode, severity, capability tags, an
observable oracle, and both positive and refusal expectations. The bank favors
cases where fluent prose could otherwise look successful while the underlying
run is unsafe, stale, unsupported, or unverifiable.

## Run the structural check

```bash
python3 skills/curate-apple-photos/scripts/check_evals.py
```

The check reports `STRUCTURAL-PASS` after validating the skill-creator fields,
unique cases, fixture boundaries, critical capability coverage, fail-closed
expectations, and recomputable fixture canaries. It does not grade model
behavior.

Run every allowlisted executable canary, including the synthetic end-to-end
workflow, with:

```bash
make evals
```

This reports `EXECUTABLE-PASS` separately. Required-artifact and
forbidden-action oracles still need an actual skill run and evidence-based human
or model grading. Neither pass proves that real pixels were freshly inspected
or that rights, consent, claims, or publication were approved.

## Hill-climb record

- **Iteration 1:** 8 cases, 7 critical, 34 expectations. Independent critics
  found prose-only oracles, incorrect phase fixtures, unrecomputable digests,
  aggregate-only evaluation, relation safety leakage, weak receipt checks, and
  missing freshness, event-range, and public-handoff pressure cases.
- **Iteration 2:** 12 cases, 10 critical, 50 expectations, 8 fixture canaries.
  The fixes closed per-view evaluation, proposal drift, transitive duplicate and
  burst holds, and empty receipts, but an independent critic found four
  false-pass seams between locally valid artifacts and release.
- **Iteration 3:** 16 cases, 13 critical, 66 expectations, 11 fixture canaries,
  and 21 executable canaries. Release planning now recomputes feedback and
  validation bundles, phase completion requires a passing candidate-bound
  plan and receipt, receipts reconcile with the catalog, and structural and
  executable results are reported separately.
- **Iteration 4:** 20 cases, 17 critical, 82 expectations, 11 fixture canaries,
  and 26 executable canaries. Independent red-team counterexamples now bind
  source and policy to the proposal, enforce the deterministic fresh-inspection
  sample, reject unsafe master mutations, require two production executions,
  verify collection hierarchy, and make fresh live-catalog verification an
  explicit lifecycle gate.
- **Iteration 5:** 24 cases, 21 critical, 98 expectations, 11 fixture canaries,
  and 30 executable canaries. A fresh hostile rerun exposed self-attested
  inspection, whitespace safety evasion, mutable write plans, partial receipts,
  forged verification documents, copied rerun receipts, and unchecked root
  parentage. The repaired contract requires real local inspection artifacts,
  registered plan hashes, full receipt reconciliation, governed live
  verification, launch nonces, and unconditional hierarchy checks.
- **Iteration 6:** 28 cases, 25 critical, 114 expectations, 11 fixture canaries,
  and 40 executable canaries. Cross-variant comparison added relation-aware
  holdout auditing, bounded retrieval, a verified offline review field, and a
  default-closed publication projection. It explicitly rejected duplicate
  assignment, writer, ledger, and receipt architectures.
- **Iteration 7:** 30 cases, 27 critical, 122 expectations, 11 fixture canaries,
  and 43 executable canaries. A hostile composite pass found symlinked review
  roots, identifier-derived path traversal, cross-destination ID correlation,
  and spreadsheet-active public text. Review assets now use content-derived
  names, private roots reject symlinks, public IDs bind the destination, and
  any unsafe claimed-clearance row blocks the complete projection.
- **Iteration 8:** 35 cases, 31 critical, 142 expectations, 11 fixture canaries,
  and 55 executable canaries. A live nested-workspace audit found that the
  external-anchor exception could be copied onto a governed descendant and
  that a same-title collection could substitute for the exact declared anchor.
  The verifier now limits the exception to the existing `workspace_parent`,
  binds receipt identifiers to the plan, and preserves strict hierarchy checks
  for every governed descendant.
- **Iteration 9:** 36 cases, 32 critical, 146 expectations, 11 fixture canaries,
  and 56 executable canaries. A live 76-preview run found 29 safe JPEGs with
  matching encoder dimensions but no optional color-space tag. The verifier
  now accepts dimensions-only encoder metadata while continuing to reject
  unexpected source tags, false dimensions, and explicit non-sRGB values.

## Recursive hill climb

1. Run every case against the current skill and the previous released skill.
2. Grade each expectation from durable output evidence, not confident prose.
3. Inspect false passes first. Strengthen the oracle or fixture before changing
   the skill.
4. Classify failures by source, retrieval, inspection, assignment, evaluation,
   safety, mutation, verification, privacy, or handoff.
5. Add the smallest adversarial case that distinguishes the failure.
6. Rerun the full bank, including unchanged safety canaries.
7. Promote a new skill only when no critical case regresses. A lower score on a
   hard case is more informative than a perfect score on a non-discriminating
   assertion.

Do not tune prompts to private run details. Durable evals should survive a new
library, brief, target size, and operator.
