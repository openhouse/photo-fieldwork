# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Working-round loop

1. Sample at least three items per view: low, middle, and high score.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Compute overall and per-view decisive fit rate.
6. Read every rejection and a sample of uncertainties.
7. Revise one part of the system and rerun deterministically.

Working rounds are diagnostic. Their examples have influenced the system and
must not later be presented as an independent estimate of the final field.

## Metric names

- **Review completion:** judged sample rows divided by assigned sample rows.
- **View sampling coverage:** sampled active views divided by active configured views.
- **Decisive fit rate:** fits divided by fits plus rejects. Uncertainty is reported separately.
- **Field audit rate:** final-holdout rows divided by final-master rows.

Earlier reports called review completion `coverage` and decisive fit rate
`precision`. Version 0.2 retains those aliases for compatibility but does not
use them as the primary language.

## Final holdout

After all retrieval rules, quotas, replacements, and labels are frozen:

1. Exclude every row used in tuning rounds.
2. Draw a new uniform deterministic random sample for estimation.
3. Add clearly labeled supplemental rows only where needed to reach a per-view review floor.
4. For a 4,000-photo field, begin with at least 200 estimation rows and review at least 15 per material view.
5. Inspect the pixels without changing the frozen field.
6. Calculate the Wilson interval from the uniform estimation sample only; use supplemental rows for per-view diagnostics, not the aggregate interval.
7. Record whether the reviewer built the field, performed a separate pass, or was independent.

An observed 71/71 fit rate has a 95% Wilson lower bound of about 0.949. The
point estimate is useful, but it is not certainty. A final holdout that is made
from surviving tuning examples or hand-selected replacements is a conformance
audit, not an independent estimate.

## Safety audit

Editorial fit cannot estimate safety recall. Run a separate risk-stratified
audit across the master, HOLD boundary, prior false negatives, document-like
images, domestic contexts, and other brief-specific risks. Safety release still
requires zero known high-risk regressions.

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

- Review completion meets the configured threshold.
- View sampling coverage meets the configured threshold.
- Decisive fit rate meets the configured threshold.
- The final Wilson lower bound meets its configured threshold when a final holdout is used.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.
