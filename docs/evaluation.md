# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Sample at least three items per view: low, middle, and high score.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Compute overall and per-view precision.
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

- The report is interpreted against the exact run config, not a remembered
  default from documentation.
- Evaluation coverage meets the configured threshold.
- Overall precision meets the configured threshold.
- Every represented view meets configured precision and decisive-sample thresholds.
- Uncertainty does not exceed the configured maximum.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

Evaluation rows must have unique UUIDs. Every requested positive-quota view
must appear in the sample; a missing view is a failure, not zero-error evidence.
Final validation also checks each configured view's exact quota.

## Fresh evidence

Track how many candidates were newly inspected in each round. Reusing an old
inspection can be legitimate, but it cannot by itself demonstrate that a
retrieval failure was resolved. Preserve each sample, decision file, and report
as a separate round artifact.
