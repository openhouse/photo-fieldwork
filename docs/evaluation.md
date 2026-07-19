# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Use low, middle, and high scores for calibration, then collect at least five
   decisive judgments per material view when the view is large enough.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Compute overall and per-view precision, sample size, coverage, uncertainty,
   and 95% Wilson intervals.
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
- Every material view meets its own precision and decisive-sample threshold.
- Sparse hypotheses are labeled explicitly and still require coverage and
  uncertainty review.
- No known safety regression appears in the master.
- Every configured non-empty view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

An evaluation report is bound to the exact source, configuration, master
membership, view assignments, deterministic review sample, and freshly
inspected review rows through `config_sha256`, `master_sha256`, `proposal_id`,
`sample_sha256`, and `feedback_sha256`. A catalog plan recomputes that report
from feedback and recomputes validation from the master and HOLD manifest. It
is refused when any source, policy, sample, inspection, assignment, review, or
safety fact differs.

The sample itself is part of the candidate. It is regenerated from the frozen
configuration, not chosen ad hoc after seeing the result. Each completed row
names an absolute, non-symlink local inspection artifact. Its digest is
recomputed and bound to the exact round and sample. This proves that the named
artifact was present; it does not prove the reviewer looked carefully, that the
judgment is correct, or that publication is approved.

## Skill regression evals

The public synthetic bank at
`skills/curate-apple-photos/evals/evals.json` tests the full operating contract
under adversarial pressure. Run its structural and coverage check with:

```bash
python3 skills/curate-apple-photos/scripts/check_evals.py
```

Run the allowlisted executable canaries with:

```bash
make evals
```

`STRUCTURAL-PASS` covers schema, coverage, fixtures, and recomputable canaries.
`EXECUTABLE-PASS` covers the referenced unit and synthetic end-to-end checks.
Neither result grades a model's required artifacts or proves human inspection,
rights clearance, consent, or publication approval.

Use the recursive protocol in the eval README when changing the skill. Grade
from artifacts and refusal behavior, inspect false passes first, and rerun every
critical safety canary after each revision.

The cross-boundary bank at
`skills/curate-apple-photos/evals/composite-evals.json` is governed by
`eval-contract.json`. It adds positive production and publication controls,
holdout independence, offline review, publication minimization, and explicit
counterfactual pass conditions. Run it with:

```bash
make composite-evals
```

The meta-tests deliberately remove cases, weaken expectations, erase
counterfactuals, and mutate all decisions toward refusal or permissiveness. A
bank that cannot detect those mutations is not accepted as discriminating.
