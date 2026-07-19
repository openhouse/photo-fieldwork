# Evaluation hill climb

Date: 2026-07-19

This revision expanded the behavioral eval bank after comparing the failure
contracts developed across the `feature/revision-*` family. The work used only
synthetic scenarios. It did not access or mutate Apple Photos.

## Iteration 0: audit the original bank

The original bank contained four useful prompts but no explicit expectations,
required evidence, risk coverage, or adversarial shortcuts. A prudent answer
could appear successful without naming the artifact or state transition that
made it safe.

## Iteration 1: broaden and challenge

The bank grew to twelve distinct risks. Every case now includes:

- evidence required for a passing judgment;
- four or more observable expectations;
- unsafe shortcuts that must fail;
- a stable name and one primary risk category.

Six high-risk cases were run with the current skill and without project skill
instructions: run recovery, same-count source substitution, aggregate metric
masking, receipt-versus-verification, public handoff, and role-play provenance.
Conservative manual grading gave the skill 30/30 expectations and the no-skill
baseline 21/30. The baseline's strength was useful: it showed that generic
caution could pass many release-decision checks.

The comparison found two weak discriminators:

1. The evaluation case did not require the exact run config and allowed a model
   to substitute a documented production default.
2. The verification case did not test the mutation boundary; a generic answer
   proposed removing membership and moving an existing album.

## Iteration 2: tighten and promote

The two cases gained config-bound threshold, membership-only correction, and
idempotence expectations. The skill now states that missing config blocks a
numeric gate claim. The rerun passed all 33 expectations across the six-case
slice; the unchanged no-skill responses conservatively satisfy 21/33.

Five model-eval findings were also promoted into deterministic regressions:

- reject duplicate evaluation UUIDs;
- fail an unsampled positive-quota view;
- validate exact configured view quotas;
- reject out-of-order phase events and reused attempt IDs;
- reject blank visible reasons or other required editorial evidence.

## Iteration 3: compose and hold out

The updated `feature/revision-*` family exposed six distinct gaps that should
not be collapsed into more prose: global assignment feasibility, candidate
sealing, cluster-aware holdout independence, publication clearance, replay-safe
idempotence evidence, and a positive control.

Six held-out scenarios raised the bank from 12 to 18 cases. A separate oracle
contract now maps every case to an expected release decision, covered
dimensions, anti-shortcuts, and a concrete condition under which the blocked
case could later proceed. Its first mutation test revealed that removing the
dedicated holdout-leakage case still left incidental positive-control coverage;
the contract was tightened to require both success and failure coverage for
holdout independence.

Product regressions were then written before implementation. The current
selector failed both overlapping-quota tests: it returned A=4/B=2 for a feasible
A=3/B=3 request, and it did not fail an infeasible event-capped request. Seven
additional tests initially failed because release sealing, publication
clearance, split audit, and distinct-execution verification did not exist.

The composite implementation made those red cases pass without importing a
second pipeline: deterministic exact-capacity assignment was added to the J
selector, while the other boundaries became small standard-library modules.
The operational path now requires a release seal before plan generation,
publication starts closed, holdouts are cluster-disjoint, and idempotence needs
two helper-attested execution nonces, one stable app-binary identity, and two
independent verification reports.

A local synthetic scale smoke test assigned 4,000 unique photographs from
8,000 two-view candidates across eight exact 500-photo quotas in 0.24 seconds.
This is not a cross-machine benchmark, but it guards against solving correctness
by introducing an obviously impractical editor-field path.

## Interpretation

This is a small paired run, not a universal model benchmark. Its purpose is to
improve the tests and expose missing contracts. Future changes should rerun the
whole bank, preserve the prior skill as a baseline, and challenge every pass
with its anti-pattern before accepting an apparent improvement.
