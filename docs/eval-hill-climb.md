# Eval hill climb

This revision treats the eval bank as a compact set of production boundaries,
not a checklist of reassuring phrases. The scenarios are synthetic and public
safe. They do not contain archive pixels, private People data, live catalog
identifiers, or permission to mutate Apple Photos.

## Inputs

The seed cases came from using the skill on a large production curation,
reviewing the `feature/revision-*` branch family, and inspecting Revision C's
open review findings. The highest-risk boundaries were source identity,
fallback exclusion, unresolved safety, resume truth, evaluation integrity,
catalog mutation, independent verification, private derivatives, and public
handoff.

## Recursive climb

### Seed

The first draft had ten broad cases. It covered the right policies but six were
prose-only and most rewarded refusal. A cautious but operationally weak response
could pass by restating the prompt.

### First mutation

The bank became eleven distinct scenarios, including a positive safe path.
Overlapping publication and safety cases were consolidated. Synthetic packets
added exact UUID, state, quota, metric, helper, preview, and verification facts.

### Second mutation

An adversarial pass found self-attestation and two contradictions. The positive
path gained an executable fake catalog adapter and invocation trace. Source,
master, HOLD, resume, holdout, and verification evidence became computable.
Derivative quarantine was separated from asset-level HOLD, and the epistemic
case gained explicit safety and inspection evidence.

### Third mutation

A narrower pass found four remaining oracle gaps. Earlier resume phases gained
attached hash-bound artifacts; sample hashing gained a canonical serialization;
source and prior-version snapshots gained real digests and exact-set
recomputation; helper operations gained one strict vocabulary.

### Composite mutation

Revision C then composed the strongest branch-family contracts into one
executable release path. A first independent critic found nine high-severity
gaps: writer authorization stopped before the real bridge, evaluation samples
were not master-bound, release hashes omitted row-level safety state, exact
assignment optimized cardinality rather than score, rejected image-view edges
were not loaded from the ledger, artifact drift could be laundered by another
reconcile, bridge initialization skipped the event ledger, multi-row sample
hashing failed, and the composite eval did not execute its release mutations.
Each became a regression test before repair.

### Composite holdout mutation

A second critic found four narrower paths: reusing feedback after changing the
sampled master, score-losing diversity-floor swaps, self-checksummed writer
plans that did not re-present release evidence, and silent supersession of a
completed phase artifact. The sample gained a master-bound manifest; swaps now
minimize score loss while preserving completion capacity; writer launch
revalidates the current release bundle and membership scope; phase replacement
requires an explicit compare-and-swap update.

### Final mutation

The next holdout found an unknown-operation fallthrough in both helper layers,
a flexible-view floor-capacity trap, and an API path that allowed an explicit
phase update without a revision. Python and Swift now reject every unknown
operation, floor swaps look ahead to the remaining view capacity, and the state
API itself requires `expected_revision` for phase updates.

### Convergence

The final independent audit was limited to the last three defects and the
previous release contracts. It returned `CONVERGED`: no remaining critical or
high defect with a stable executable counterexample in the reviewed scope.

## Stop rule

Keep the bank at twelve cases or fewer. Add or mutate a case only when an
independent adversarial pass demonstrates a distinct critical or high-severity
failure with a stable observable oracle. Do not expand the bank for stylistic
preferences or to simulate every production detail.

## Current result

- 12 skill evals with attached public-safe fixtures.
- 1 executable fake-catalog positive path.
- 1 executable composite path covering assignment, feedback lineage,
  transactional recovery, release mutations, and zero-call writer preflight.
- Exact release-blocking expectations for safety, mutation, verification,
  privacy, and publication boundaries.
- 44 deterministic tests covering the bank, fixture hashes, fake-adapter order,
  idempotence, fallback exclusions, safety states, sample/master binding,
  overlap-aware assignment, release authorization, and transactional state.

Run the full deterministic layer with `make check`.
