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

## Interpretation

This is a small paired run, not a universal model benchmark. Its purpose is to
improve the tests and expose missing contracts. Future changes should rerun the
whole bank, preserve the prior skill as a baseline, and challenge every pass
with its anti-pattern before accepting an apparent improvement.
