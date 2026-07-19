# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Skill behavior suite

The bundled skill includes fourteen adversarial synthetic behavior evals under `skills/curate-apple-photos/evals/`. They test source drift and same-count substitution, local versus aggregate failure, preview integrity, replacement and safety closure, ledger recovery, relationship-level holdout leakage, receipt self-authorization, helper compatibility, publication boundaries, unsupported hypotheses, assignment scarcity, and a genuinely green completion case.

Run the deterministic suite check with:

```bash
make evals-check
```

Agent benchmarks are optional and require a local `codex` executable. See [the Revision E hill climb](eval-results-revision-e.md) for method, results, and limitations. Generated transcripts belong in a private temporary workspace, not this repository.

## Minimum loop

1. Sample at least three items per view: low, middle, and high score.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Compute overall and per-view precision.
6. Read every rejection and a sample of uncertainties.
7. Revise one part of the system and rerun deterministically.
8. Freeze a final holdout disjoint from tuning and canaries by UUID, duplicate group, perceptual cluster, and burst group.

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
- Every configured nonzero-quota view has at least `minimum_decisive_per_view` fit/reject judgments.
- Every such view meets its configured or global per-view precision threshold.
- No known safety regression appears in the master.
- Every view has been sampled.
- The final holdout passes the split audit, and canaries do not contribute to quality metrics.
- The final report is bound to the exact source, config, master, and sample that will be planned.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

`uncertain` contributes to coverage but not decisive precision. A view with too little decisive evidence is reported as `insufficient-evidence`; it cannot borrow confidence from stronger views or from the overall average.
