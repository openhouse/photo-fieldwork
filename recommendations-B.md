# Recommendations B for Photo Fieldwork

**Prepared:** July 15, 2026

**Basis:** Hands-on review of the completed v04-B Apple Photos run and close reading of Revision I.

**Status:** The trust-chain recommendations are implemented in Revision B. Longer-horizon editorial and ecosystem work remains sequenced below.

## Product judgment

Photo Fieldwork should be a local-first, resumable evidence system, not merely a collection of scripts that creates albums. Its strongest contribution is keeping retrieval hypotheses, visible evidence, provenance, editorial judgment, safety review, technical verification, and publication approval distinct.

The v04-B run demonstrated real scale: 603,137 visible stills, 8,000 locally inspected candidates, an exact 4,000-image master, 2,106 holds outside the master, a ten-image write test, an idempotent production write, and independent membership verification. It also showed where expert memory still carried the workflow.

## Simulated discussion

These are imagined product lenses, not quotations or endorsements.

**Jamie Burkart:** I think structure should continue to grow from the material, but another person must be able to enter after an interruption and understand what is settled, what is inferred, and what remains alive.

**Cyd Harrell:** I think status must say what happened, what did not happen, what proves it, and the next safe action.

**Hamel Husain:** I think every evaluation metric needs an explicit denominator. Canaries must detect regressions without improving fresh precision.

**Sara Hendren:** I think unresolved human-sensitive material needs a real state and a real consequence without becoming a declaration about a person.

**Maggie Appleton:** I think source, candidate, preview, observation, judgment, proposal, plan, receipt, and verification should form one inspectable provenance graph.

**Deborah Treisman:** I think `editor-field-verified`, `master-human-reviewed`, and `publication-ready` must remain different statements.

## Implemented in Revision B

1. A versioned source manifest with count-preserving drift detection.
2. Evaluation bound to the exact source, master, and sample.
3. Separate sample completion, fresh precision, master review fraction, and canary results.
4. Explicit evaluation scopes and release classes.
5. Typed safety states with unresolved human review excluded by default.
6. Source, configuration, master, hold, plan, helper, receipt, and verifier hash continuity.
7. Schema-version-2 Python and Swift plan contracts with keyed albums.
8. Helper capability and revision handshake before Photos mutation.
9. Resume totals recomputed from prior inspection rows.
10. Duplicate and corrupt inspection checkpoint rejection.
11. Atomic run phase records, next actions, `resume`, and `mark-phase`.
12. Owner-only run workspaces and a gitignored local deployment profile.
13. Pillow declared as an optional review dependency and installed in CI.
14. Complete-link perceptual clustering with method, medoid, and distance fields.
15. Regression tests for unresolved safety, duplicate judgments, canary inflation, source binding, plan integrity, and receipt mismatch.

## Next editorial milestone

Build a network-disabled local review console over the new ledger contracts. It should show the image, event neighbors, retrieval hypothesis, visible evidence, provenance, safety state, prior judgment, and proposal identity. Keyboard decisions should append events instead of mutating canonical rows.

Add set-level diagnostics for event repetition, perceptual concentration, named-person concentration, person-free context, time and safe-granularity place range, uncertainty, and project evidence strength. These are composition diagnostics, not identity or fairness claims.

Measure retrieval breadth as well as selected precision. Track fresh-candidate fraction, audit excluded boundaries, sample unretrieved source strata, and preserve negative knowledge so later rounds do not repeatedly rediscover the same failures.

## Next infrastructure milestone

Move canonical run data from mutable CSV toward typed SQLite or JSONL ledgers while retaining CSV as interchange. Add migrations for every contract. Build a fake catalog adapter and a golden source-to-verification CI run, then add a small macOS PhotoKit integration suite.

Separate the reusable protocol, catalog adapters, and private deployment profile fully. The public repository should require no personal path or identifier.

## Publication milestone

Keep field creation separate from publication selection. A downstream shortlist should review rights, consent, caption provenance, public safety, crop suitability, accessibility description, credit, final human approval, and revisit date. No image should become public merely because it scored highly or appeared in a project album.

## Do not build yet

Defer cloud image analysis, automatic naming of unidentified people, hosted collaborative review, generative factual captions, autonomous publication selection, and a plugin marketplace until the trust chain and local review experience are mature.

## Final view

Many systems can rank files. Photo Fieldwork is valuable when it makes a large personal archive navigable without pretending that ranking is truth, recognition is consent, a project hypothesis is a caption, or technical verification is editorial approval.
