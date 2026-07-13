# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Sample at least three items per view: low, middle, and high score.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Compute decisive precision, fit rate, uncertainty rate, and per-view results.
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
- Uncertainty remains below the configured maximum.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

## Metric names

`decisive_precision` is `fit / (fit + reject)`. It excludes uncertain judgments. Always report it beside `fit_rate` (`fit / all judged`) and `uncertainty_rate` (`uncertain / all judged`). Reports include 95 percent Wilson intervals for decisive precision and fit rate. A score-stratified sample balanced across views is useful for diagnosis, but its unweighted aggregate is not automatically an estimate of the full field. The report therefore also emits population-weighted rates when sample rows contain `view_population`.

Bind each evaluation to one `proposal_id` and `master_sha256`. A passing report for one membership and view assignment must not authorize a different catalog plan.
