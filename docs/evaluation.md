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

- Evaluation coverage meets the configured threshold.
- Overall precision meets the configured threshold.
- Every material view meets minimum coverage, decisive-example, and precision thresholds, unless a waiver is explicit in configuration.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

## Skill behavior evals

The skill eval bank lives in `skills/curate-apple-photos/evals/evals.json`. It tests the production failures that can survive a superficially successful run: equal-count source drift, reused evidence presented as fresh, corrupt previews, aggregate metrics masking a weak view, unsafe clearance, cascading replacements, cross-UUID duplicates, candidate drift after evaluation, interrupted writes, publication-boundary leakage, private-data offloading, identity inference, destructive catalog plans, and prior-version overwrite. A positive control requires the skill to proceed when every production-write gate is actually closed.

`eval-contract.json` maps every case to a decision oracle, required dimensions, anti-shortcuts, and a counterfactual pass condition. Audit the bank with:

```bash
make evals
```

Hill-climb the bank recursively:

1. Run the same prompt against the current skill and the previous revision.
2. Grade each expectation from artifact or transcript evidence, not from tone or stated confidence.
3. Remove or weaken one case and confirm the meta-evaluation fails.
4. Flip every oracle to `BLOCK` and confirm the positive control detects refusal-only behavior.
5. Add newly observed field failures without deleting protected prior regressions.
6. Re-run the whole bank after any source, safety, evaluation, planning, writing, verification, or publication-contract change.

The deterministic audit checks eval design. Model runs and human review still establish whether the skill satisfies the cases.

## Closing a round

Evaluation is not complete when a report is written. Apply explicit feedback to the full candidate pool, rebuild deterministically, and review every newly admitted or reassigned asset. A rejected sampled item often causes an unreviewed lower-ranked item to enter the master; the replacement manifest makes that consequence visible.

Diagnostic rounds may be preserved without being represented as scored release rounds. Never lower a threshold merely to finish.
