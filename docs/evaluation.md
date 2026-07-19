# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Freeze the proposal hash. Sample at least three fresh items per view across low, middle, and high scores, plus stable regression canaries.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Validate and apply structured feedback, then compute fresh sample completion, fresh decisive precision with 95% Wilson intervals, uncertainty, master review fraction, and per-view sample sufficiency.
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

## Evaluation scopes

- `learning-sample`: informs another iteration and cannot authorize a write.
- `final-stratified-sample`: can qualify an `editor-field-verified` release when bound to the exact master and source.
- `full-master`: required for `master-human-reviewed` and must cover every master row.
- `publication-shortlist`: required for `publication-ready`, together with rights, consent, caption, and accessibility fields.

`sample_completion` reports judgments divided by sampled rows. `master_review_fraction` reports fresh judged rows divided by master rows. These denominators must never be described interchangeably. Regression canaries are reported separately and never improve fresh precision.

## Release gates

- Fresh sample completion meets the configured threshold.
- Fresh decisive precision meets the configured threshold.
- Every material view meets its own precision, coverage, sample-size, and uncertainty thresholds.
- No known safety regression appears in the master.
- Every view has been sampled.
- Sparse evidence is labeled `sparse-hypothesis` or returned to unclassified instead of being quota-filled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- The source manifest, sample, fully evaluated proposal, holds, and exact plan are hash-bound.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

## Composite evaluation layers

The preferred composite keeps four layers separate:

1. `evals/evals.json` tests skill decisions under synthetic pressure.
2. `evals/eval-contract.json` requires risk-dimension coverage, explicit decision oracles, and both editor-field and publication positive controls.
3. `make evals` executes product contracts for exact quotas, relational HOLD closure, holdout independence, run-state concurrency, and artifact-chain binding.
4. Local field evaluation still inspects real pixels, runs the bounded write test, and independently verifies Apple Photos.

The final holdout must be disjoint from tuning and canaries by canonical UUID and by perceptual, duplicate, and burst relations. Run `audit_eval_split.py` before using holdout results as release evidence. Its default report contains counts and membership digests, not private identifiers.
