# Curate Apple Photos evals

These synthetic scenarios exercise decisions that failed or required improvised recovery during whole-library production runs. They contain no real Photos identifiers, people, locations, OCR, or run artifacts.

The bank emphasizes fail-closed behavior. A strong response should say how far the evidence permits the run to proceed, name the blocking contract, and identify the next safe action. Producing a plausible completion narrative without the required evidence is a failure.

The fixtures deliberately contain fake sensitive-looking values so privacy and safety responses can be evaluated without exposing private archive material.

Validate the bank with:

```bash
python3 skills/curate-apple-photos/evals/validate_evals.py
```

When changing the skill, compare the candidate skill with a snapshot of the previous version. Review both formal expectation scores and whether the response remains useful, restrained, and legible to an operator.

The first checked-in comparison is documented in [hill-climb-2026-07-19.md](hill-climb-2026-07-19.md).
