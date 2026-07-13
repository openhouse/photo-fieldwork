# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Freeze the proposal hash. Sample at least three fresh items per view across low, middle, and high scores, plus stable regression canaries.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Validate and apply structured feedback, then compute overall and per-view coverage, decisive precision with 95% Wilson intervals, uncertainty, and sample sufficiency.
6. Read every rejection and a sample of uncertainties.
7. Revise one part of the system and rerun deterministically.

## Error taxonomy

- **Retrieval mismatch:** Metadata suggests a project but pixels do not.
- **Context collapse:** A social photograph is mistaken for professional evidence.
- **Taxonomy coercion:** An image is forced into the least-wrong project.
- **Privacy miss:** Sensitive visible content reaches the proposed master.
- **Relationship loss:** Named people or collective context are underrepresented.
- **Temporal distortion:** Import dates are treated as capture truth.
- **Redundancy:** One event or burst crowds out range.
- **Aesthetic overreach:** A score substitutes for editorial judgment.

## Release gates

- Evaluation coverage meets the configured threshold.
- Overall precision meets the configured threshold.
- Every material view meets its own precision, coverage, sample-size, and uncertainty thresholds.
- No known safety regression appears in the master.
- Every view has been sampled.
- Sparse evidence is labeled `sparse-hypothesis` or returned to unclassified instead of being quota-filled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- The fully audited final proposal hash is the hash embedded in the write plan.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.
