# Revision L composite

This revision composes the branch family by contract rather than by wholesale
merge. It retains Revision L's reproducibility, bounded-absence language,
private review surface, and default-closed public projection, then adds five
complementary production guarantees.

## Composite contracts

1. **Exact assignment.** Candidate views remain retrieval hypotheses. A
   deterministic minimum-cost capacity solve assigns every selected asset at most once while
   preserving exact active-view quotas and per-view event caps. Infeasibility is
   reported; intent is never silently rebalanced. The base assignment maximizes
   total deterministic candidate benefit globally. For uncapped views, a
   proven top-target dominance rule reduces the solver graph; capped views keep
   all edges. Diversity floors are then satisfied jointly through deterministic
   alternating-path backtracking rather than irreversible greedy swaps.
2. **Recoverable ordered state.** `run-events.jsonl` is append-only,
   hash-linked, revisioned, and authoritative. `run-state.json` is an atomic
   materialization that can be recovered. Completed artifacts are rehashed
   before later transitions. A CAS-guarded invalidation event records artifact
   drift and resets dependent phases without rewriting history. Required phases
   cannot be skipped.
   Pre-ledger schema-v2 workspaces migrate into an explicitly marked genesis
   event that preserves their materialized state without inventing transitions.
3. **Relation-clean evaluation.** Final-holdout freshness is audited across
   UUID, perceptual cluster, duplicate group, and burst group. Regression
   canaries stay separate from fresh estimates, duplicate image-view judgments
   fail, and a failed material view blocks release. Offline review exports
   retain those opaque relation identifiers plus master and proposal identity.
   Relation identifiers participate in the sample digest, and prior-feedback
   files without the complete relation schema fail closed.
4. **Candidate-bound release.** Source membership, configuration, master
   assignments and safety state, evaluation, relation-clean holdout report,
   validation, run lock, catalog plan, and exact adapter plan are
   content-addressed as one candidate. Mixed identities and
   post-registration plan changes fail closed. Empty or duplicate catalog album
   keys are rejected before membership comparison.
5. **Distinct execution evidence.** Each writer launch receives a distinct
   nonce against one registered plan and exact adapter plan. Production remains
   blocked until the independently verified write-test phase completes. Two immutable production attempts are
   required for idempotence, and both must execute identical adapter-plan bytes.
   A nonce is revoked by candidate invalidation or registration supersession.
   Writer receipts never substitute for fresh read-only verification.

Registration and every execution gate rehash the frozen lock and recorded phase
evidence. Every adapter album has a unique semantic role, and the exact
role-to-membership map must match catalog and locked auxiliary roles. Validation
and hashing consume the same immutable adapter bytes. The nonce-bearing runtime
plan is separately hashed, passed to the writer out of band, verified from one
read before mutation, and rebound through the immutable receipt to independent
verification. Completion receipts must
enumerate the exact folder and album outcomes. A repaired candidate supersedes an earlier
registration only through post-registration invalidation, refreeze, fresh
evaluation and validation, and an append-only supersession event.

## Eval governance

The expanded bank contains adversarial cases for all five contracts plus a
valid production `PROCEED` control. Its executable contract requires decision
oracles, unsafe-shortcut descriptions, runnable coverage for every critical
dimension, and at least one positive control. Mutation tests ensure that an
orphaned dimension, removed case, or refusal-only bank cannot pass.

Synthetic evals and regression tests establish contract behavior only. They do
not establish live Photos compatibility, visual quality, safety clearance,
rights, consent, publication permission, or completion of a real run.
