# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Sample at least three items per view: low, middle, and high score.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason, an identified human reviewer, reviewer kind, and round ID.
5. Compute overall and per-view precision.
6. Read every rejection and a sample of uncertainties.
7. Revise one part of the system and rerun deterministically.
8. Persist known rejects and historical holds as regression controls.
9. Audit the actual frozen field, including every replacement introduced after an earlier pass.
10. Bind the report to the exact proposal and master identity. A changed membership or view assignment requires a new final-field audit.
11. Bind the report to the exact config and feedback content. A changed threshold, judgment, visible reason, safety state, reviewer, round, or replacement state requires reevaluation.
12. Keep tuning and canaries outside an untouched final holdout, including duplicate, perceptual-match, and burst relations. Run `photo-fieldwork audit-split` before scoring the holdout.

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
- Every material view meets its configured decisive-precision and minimum-decision thresholds.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.
- Every replacement appears in the final-field feedback.
- Every final decision has visible reasoning and identified-human provenance.
- The holdout leakage audit passes without inspecting its outcomes during tuning.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

## Recursive eval bank

Run `make evals` while changing selection, release, safety, or run-state behavior. The executable bank begins with known field failures and adds adversarial variants after each repair. It includes a production-shaped 4,000-item overlap assignment so exactness and determinism remain ordinary regression checks rather than occasional demonstrations.

The companion `evals/evals.json` uses typed `BLOCK` and `PROCEED` oracles, severity, unsafe shortcuts, and counterfactual pass conditions. The bank validator requires both decisions and complete coverage of the critical contract dimensions. Mutation tests remove controls and dimensions to prove that the validator detects a weakened bank.
