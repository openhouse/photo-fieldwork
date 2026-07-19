# Evaluation practice

The goal is not to prove the selector is intelligent. The goal is to discover where it is wrong before its outputs become editorial assumptions or public claims.

## Minimum loop

1. Sample at least three items per view: low, middle, and high score.
2. Inspect the actual pixels, not filenames or metadata alone.
3. Label each item `fit`, `reject`, or `uncertain`.
4. Record one visible reason.
5. Compute overall and per-view coverage, decisive precision, fit, rejection, and uncertainty rates.
6. Read every rejection and a sample of uncertainties.
7. Revise one part of the system and rerun deterministically.
8. After tuning stops, evaluate a fresh holdout against all prior tuning and regression-canary UUIDs and relationship clusters.

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
- Overall decisive precision meets the configured threshold.
- Overall uncertainty stays below its configured maximum.
- Every material view meets minimum decisive-count, precision, and uncertainty gates.
- No known safety regression appears in the master.
- Every view has been sampled.
- Every selected row has a reason.
- Uncertainty is represented explicitly.
- A human editor is told that project views remain hypotheses where provenance is incomplete.
- The final holdout meets its fresh-evidence floor and is disjoint from tuning evidence when that gate is required.
- The final holdout shares no perceptual, duplicate, or burst cluster with tuning or regression canaries.
- The passing evaluation seals the exact master, view assignments, safety states, config, and evaluation report used for planning.

Passing the gate means the corpus is ready for editors. It does not mean every category assignment is factually proven.

## Denominators

- `coverage = judged / sampled`
- `decisive precision = fit / (fit + reject)`
- `fit rate = fit / judged`
- `reject rate = reject / judged`
- `uncertainty rate = uncertain / judged`

Never describe decisive precision as the percent of the sample confirmed fit. A run can have high decisive precision and a high uncertainty burden at the same time.

Every decision must name its UUID and carry the sample hash, visible reason, safety state, error category, round ID, and reviewer lens. Positional joins are prohibited.

Run `make eval` for the synthetic failure-mode suite. Its fixtures exercise drift, quota overlap, metric traps, feedback integrity, relational safety, preview decoding, cluster contamination, release identity, idempotence, closed public handoff, ledger recovery, and 4,000-item assignment. Passing those contracts is necessary code evidence, not a substitute for pixel inspection or human editorial approval.
