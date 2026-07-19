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

### Convergence

The final independent audit was limited to those four defects. It recomputed the
hashes and set differences and returned `CONVERGED`: no remaining
release-blocking contradiction in the synthetic eval scope.

## Stop rule

Keep the bank at twelve cases or fewer. Add or mutate a case only when an
independent adversarial pass demonstrates a distinct critical or high-severity
failure with a stable observable oracle. Do not expand the bank for stylistic
preferences or to simulate every production detail.

## Current result

- 11 skill evals with attached public-safe fixtures.
- 1 executable fake-catalog positive path.
- Exact release-blocking expectations for safety, mutation, verification,
  privacy, and publication boundaries.
- 30 deterministic tests covering the bank, fixture hashes, fake-adapter order,
  idempotence, fallback exclusions, safety states, and structured reconciliation.

Run the full deterministic layer with `make check`.
