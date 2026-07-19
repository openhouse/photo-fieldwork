# Production protocol

This protocol turns a curatorial brief into a resumable, auditable editor field
while preserving human authority over taste, safety, consent, rights, and
public meaning.

## Evidence chain

1. Preserve the brief and freeze the exact source count and membership digest.
2. Record retrieval hypotheses separately from editorial assignments.
3. Export and independently decode local previews; unavailable evidence enters
   HOLD before ranking.
4. Select a deterministic proposed master and preserve the disjoint HOLD set.
5. Generate the score-stratified review sample from the exact candidate.
6. Inspect locally, preserving visible reasons, safety states, error categories,
   reviewer lens, sampling role, and inspection artifact digests.
7. Evaluate overall and material views; revise and repeat without lowering
   gates to fit available evidence.
8. Audit tuning, canary, and holdout manifests for direct and relation leakage.
9. Validate exact quotas, safety closure, still-photo membership, duplicate
   closure, assignments, and replacement closure.
10. Generate and seal membership-only test and production plans from the same
    source, config, master, feedback, evaluation, and validation identities.
11. Verify the test write; execute production twice under distinct launch
    nonces; preserve every receipt.
12. Independently compare exact catalog membership from fresh WAL-aware,
    read-only snapshots.
13. Derive completion from the unchanged artifact chain.

## Release blockers

- source count or exact membership disagreement;
- candidate, policy, sample, feedback, evaluation, validation, or plan drift;
- missing, corrupt, symlinked, stale, or unbound inspection evidence;
- HOLD, hidden, unavailable, or review-pending rows in the master;
- unresolved duplicate, burst, relation, replacement, or assignment review;
- a failed overall or material-view quality gate;
- holdout UUID or relation-cluster leakage;
- destructive or unsealed catalog operations;
- a missing test verification, incomplete receipt, reused execution nonce, or
  stale or self-attested independent verification;
- mutation of the candidate after evidence was generated.

## Public-use boundary

Production completion creates an editor-ready field. It does not grant public
use. A public package is a separate allowlisted export and requires positive,
destination-specific human review for rights, participant consent, factual
claims, visible safety, editorial approval, alt text, and credit. Rows without
positive publication status remain closed. Rows claiming clearance while a gate
is unresolved fail the handoff and remain in a private remediation report.

## Resumption

Preserve failed and partial attempts. Resume only through the evidence-backed
run ledger and stable plan bindings. A retry adds missing memberships without
creating duplicate folders or albums. It receives a new execution nonce and a
new immutable receipt. Final state is established from a fresh read-only
snapshot, not from writer testimony.
