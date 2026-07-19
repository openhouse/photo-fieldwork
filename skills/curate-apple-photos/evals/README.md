# Curate Apple Photos evals

These synthetic decision drills test whether the skill chooses the next safe action under conflicting or incomplete evidence. They never require access to a live Photos library.

The bank emphasizes consequential boundaries:

- source identity rather than count equality;
- interruption and absent-receipt recovery;
- human safety decisions over automated clearance;
- fresh evaluation evidence and canary separation;
- honest treatment of unsupported editorial views;
- helper and plan compatibility;
- preview and checkpoint integrity;
- editor-field versus publication authorization;
- public-report data minimization;
- exact topology and idempotence;
- People metadata without new identification;
- a clean completion control that detects blanket refusal;
- post-evaluation configuration drift;
- circular provenance from generated albums;
- imported-scan date overclaim;
- contradictory duplicate feedback.

`evals.json` contains human-readable expectations and deterministic control checks. `response.schema.json` gives decision-drill agents one comparable output contract. Run `validate_skill_evals.py` without responses in CI; pass a response directory to grade the deterministic controls after a benchmark run.

In the typed response, a `*_required` control is true only when that control remains outstanding after considering the scenario's supplied evidence. It is false when the scenario proves the prerequisite already passed.

The expectations remain the primary rubric. Machine checks cover high-consequence control decisions, but they cannot establish the quality of visual judgment, explanation, or editorial care.

## Revision B hill climb

The bank was developed against a snapshot of the pre-eval Revision B skill. All runs were synthetic and read-only. No photographs or private library data were supplied, and every run prohibited live Photos inspection or mutation.

1. The twelve-case baseline passed 31 of 36 human expectations under an independent strict grading pass. Misses concerned permission-preserving helper replacement, complete publication checks, exact topology language, person-free context, and explicit preservation of prior versions.
2. The skill was revised at those general boundaries, not with case-specific answers. Ambiguous machine assertions were corrected when they required evidence that the scenario did not justify.
3. The complete bank passed all 16 deterministic decision/control checks.
4. The independent final grading pass found 48 of 48 human expectations satisfied, including four held-out cases added after the first hill climb.

The final grader still observed occasional broad workflow boilerplate in otherwise correct answers. This is a useful next benchmark dimension: measure whether an answer stays proportional to the immediate decision without weakening downstream safety boundaries.
