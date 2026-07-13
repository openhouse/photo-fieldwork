# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Sample at least three items per view: low, middle, and high score.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Record safety, public suitability, and provenance separately from category fit.
6. Compute overall and per-view precision with decisive denominators and Wilson intervals.
7. Read every rejection and a sample of uncertainties.
8. Apply rejects as hard negatives and confirmed safety findings as HOLD.
9. Revise one part of the system and rerun deterministically.

## Error taxonomy

- **Retrieval mismatch:** Metadata suggests a project but pixels do not.
- **Context collapse:** A social photograph is mistaken for professional evidence.
- **Taxonomy coercion:** An image is forced into the least-wrong project.
- **Privacy miss:** Sensitive visible content reaches the proposed master.
- **Relationship loss:** Named people or collective context are underrepresented.
- **Temporal distortion:** Import dates are treated as capture truth.
- **Redundancy:** One event or burst crowds out range.
- **Aesthetic overreach:** A score substitutes for editorial judgment.

## Measurement boundary

`fit` and `reject` measure visible fit to the assigned editor view. `uncertain` remains outside decisive precision. Every report includes the decisive numerator and denominator, a 95% Wilson interval, and a small-sample warning when a view has fewer than the configured decisive minimum.

Evaluation does not merge these distinct questions:

- Is the assignment visibly fitting?
- Does the image require a safety hold?
- Is it suitable for public consideration?
- Is external provenance sufficient for a claim?

Passing means ready for an editor. It does not mean factually proven or ready to publish.

## Release gates

- Evaluation coverage meets the configured threshold.
- Overall precision meets the configured threshold.
- No sufficiently sampled material view falls below the configured view threshold.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.
