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

## Evaluate the workflow itself

The bundled skill has an adversarial bank at
`skills/curate-apple-photos/evals/evals.json`. These cases test whether an operator or agent
blocks plausible shortcuts involving source substitution, reused evidence, unsupported views,
safety clearance, interrupted state, candidate drift, helper compatibility, write
disagreement, public-data leakage, and publication permission.

Run candidate and previous-skill responses under the same model and permissions. Preserve
failed outputs, grade consequential actions rather than cautionary language, and add newly
discovered failures as regression cases. After tuning, use an unseen holdout; do not count
tuning examples, targeted supplements, or regression canaries as fresh evidence of quality.

Before opening a visual holdout, run `audit_eval_split.py`. It compares canonical UUIDs and
local perceptual, duplicate, and burst clusters across tuning, canary, and holdout manifests.
The default report exposes counts and membership digests rather than private identifiers.

This workflow-level holdout is distinct from the full-master audit. The holdout estimates
whether the operating instructions generalize. The full-master audit authorizes an exact,
already-frozen master for a membership-only write.
