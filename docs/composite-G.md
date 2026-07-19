# Preferred revision composite

This revision keeps G's deterministic weighted min-cost assignment as the selection spine. It
integrates a narrow set of complementary controls from the revision family without replacing
benefit-aware assignment with a capacity-only solver.

## Adopted

- **Candidate identity:** the exact master, configuration, and evaluation sample are separately
  hashed. Evaluation and write plans must bind all three.
- **Independent final evidence:** final holdouts exclude tuning UUIDs, distinguish unbiased estimate
  rows from per-view supplements, and fail when UUID, perceptual, duplicate, or burst groups leak.
  The passing split audit is digest-bound to the evaluated holdout and carried into production plans.
- **Publication boundary:** the private review surface records rights, consent, claim support, public
  safety, and publication status separately. The public handoff emits only fully cleared allowlisted
  fields under salted public IDs.
- **Eval self-audit:** sixteen cases map one-to-one to decision oracles, risk dimensions,
  anti-shortcuts, and concrete counterfactual pass conditions. A positive PROCEED control prevents
  refusal from masquerading as judgment.
- **Mutation pressure:** tests prove the auditor detects missing coverage, refusal-only outcomes,
  orphan cases, vague expectations, cluster leakage, partial clearance, config drift, and sample
  substitution.

## Deliberate boundaries

The fast capacity-only assignment variant is not substituted for G's weighted solver because doing
so would discard edge-benefit optimization. Publication clearance remains a human decision. No eval,
hash, linter, or completed Apple Photos write can grant rights, consent, testimonial status, or
permission for public use.

## Hill-climb result

Deterministic mutation tests first removed four evaluator shortcuts: missing required risk coverage,
refusal-only outcomes, orphan contract cases, and vague expectations. A separate read-only model probe
then tested cluster leakage, incomplete claim clearance, and a positive production decision. The first
positive prompt was ambiguous because it described work after production verification; the model
reasonably interpreted publication as the remaining decision. The prompt was moved to the exact
pre-production boundary. On rerun it returned `PROCEED`, named the candidate/config/sample/plan
bindings and membership-only scope, and kept publication out of that authorization.
