# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

The evaluation CSV is a frozen manifest, not an informal collection of returned rows. Every sampled row carries the same `evaluation_sample_sha256` and `evaluation_sample_count`. The digest binds each canonical UUID to its `primary_view`; missing, substituted, duplicate, or relabeled rows invalidate the evaluation before quality metrics are considered.

When `require_per_view_sufficiency` is enabled, every configured nonzero view must meet `minimum_decisive_per_view`. Aggregate precision cannot waive a missing, underpowered, or weak view.

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

## Tuning, canaries, and final holdout

Do not use the final holdout to tune retrieval, scoring, assignments, thresholds, or labels. Regression canaries may be known hard cases, but they are not independent evidence. Before release, `audit-holdout` checks canonical UUID overlap and shared duplicate, perceptual, or burst clusters across tuning, canary, and holdout manifests. `release-audit` recomputes that audit from the current manifests and requires the supplied report to match exactly, so membership or cluster drift in any split fails the release.

## Release gates

- Evaluation coverage meets the configured threshold.
- Overall precision meets the configured threshold.
- No sufficiently sampled material view falls below the configured view threshold.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.
- The decision ledger is intact and any safety clearance came from an identified human.
- The decision ledger belongs to the catalog plan's run, and every changed safety state is reconciled to an asset-specific human clearance from the frozen baseline.
- The final holdout is independent at both asset and cluster level, as recomputed from the current tuning, holdout, and canary manifests.
- The exact config, feedback, master membership, assignments, HOLD, source, and catalog plan are candidate-bound.

Passing the gate produces an editor-field release seal. It means the bound corpus is ready for editors. It does not mean every category assignment is factually proven, that rights are cleared, or that any image is approved for publication.
