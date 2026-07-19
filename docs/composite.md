# Composite design

The preferred composite was chosen by comparing the updated
`feature/revision-A` through `feature/revision-N` branches against one question:
which combination gives an operator the strongest coherent path without
creating parallel sources of truth?

## Selected architecture

Revision M is the production spine because it connects source identity, local
inspection, candidate evaluation, plan integrity, two real execution receipts,
and fresh independent verification in one candidate-bound chain.

Revision H contributes mutation-resistant evaluation governance and positive
controls. Revision K contributes executable holdout leakage checks. Revision L
contributes the private offline review and allowlisted handoff pattern. Revision
E sharpens the publication states kept separate in that handoff. Revision A's
operator framing informs the runbook.

These are integrated as additive boundaries around M. They do not introduce a
second selector, run-state model, receipt format, or Photos writer.

## What each revision taught the composite

| Revision | Strongest contribution | Composite decision |
| --- | --- | --- |
| A | Operator ergonomics, runbook, and release sequencing | Integrated as operator documentation |
| B | Typed chain-of-custody and decision drills | Concepts covered by M identities and composite evals |
| C | Append-only lifecycle and fixture-backed evaluation | Lifecycle principle retained through M's evidence ledger |
| D | Broad adversarial mutation frontier | Informs mutation tests; its separate state machine is not merged |
| E | Explicit epistemic and publication states | Integrated into destination-scoped public gates |
| F | Transactional recovery, release seals, and real image decode | Recovery and decode behavior supplied by M |
| G | Fresh evidence separation and browser-level review QA | Freshness retained; review surface added with offline invariants |
| H | Eval-of-eval governance and positive controls | Integrated as the composite behavioral contract |
| I | Schema migration and assignment separation | Assignment distinction retained; no parallel migration layer added |
| J | Discriminative baselines and event concentration | Retained through M's canaries and diversity checks |
| K | Holdout leakage audit across UUID and relations | Integrated as `audit-holdout` |
| L | Offline review and minimized public handoff | Integrated and tightened around M vocabulary |
| M | End-to-end production and verification spine | Adopted as the canonical operating path |
| N | Exact-quota performance and calibrated statistics | Useful future optimization after behavioral equivalence fixtures |

## Why selective composition matters

Every branch contains valuable work, but merging every implementation would
create competing ledgers, overlapping schemas, incompatible commands, and more
than one definition of release. The composite preserves the strongest
distinctive guarantees while keeping one artifact chain that an operator can
explain and an evaluator can falsify.

## Evaluation layers

1. `evals/evals.json` remains the 24-case production bank with recomputable
   fixtures and allowlisted executable checks.
2. `evals/composite-evals.json` adds 12 cross-boundary judgment cases and a
   mutation-resistant coverage contract.
3. Unit canaries execute positive and adversarial holdout, review, publication,
   receipt, source, safety, and catalog behaviors.
4. `make demo` proves the dependency-free synthetic path still works.

The layers must pass against the same unchanged candidate. Passing them does
not close human-only gates.

See [the recorded hill climb](composite-eval-hill-climb.md) for the synthetic
failure, mutation, hardening, and final verification sequence.
