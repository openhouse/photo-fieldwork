# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Freeze the proposal hash. Sample fresh low, middle, and high scores plus stable regression canaries.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Validate and apply structured feedback, then compute decisive precision, coverage, uncertainty, and sample sufficiency.
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
- No known safety regression appears in the master.
- Every view has been sampled.
- Every material view meets its configured decisive-sample and precision gates.
- Rejected and uncertain judgments include an error category.
- Every judged image records a visible reason and evaluation safety state.
- Every selected row has a reason.
- Retrieval hypotheses and reviewed assignments remain separate.
- Uncertainty is represented explicitly.
- The final write-authorizing evaluation covers every row in the frozen master and carries its hash.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

Use `photo-fieldwork sample --view VIEW --round-id ROUND` to create a targeted follow-up
sample without relabeling already-reviewed views.

After the last revision, create a final sample large enough to include every selected row.
Pass the frozen master to `evaluate --master`. Only a report with `full_master_audit: true`
and the matching audited UUID-set hash can be used to generate a catalog plan.
