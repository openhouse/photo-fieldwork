# Revision K eval hill climb

Revision K's skill was evaluated without Apple Photos access, private images, or catalog
mutation. The previous skill directory was frozen before editing and used as the baseline.

## Eval bank

Ten adversarial cases cover source substitution, recycled evidence, unsupported project
views, automated safety clearance, interrupted state, assignment drift, incompatible helper
execution, receipt/verification disagreement, public-data leakage, and publication permission.

## Iteration results

1. **Natural-language calibration:** candidate and baseline both passed 16/16 expectations
   across fresh-evidence planning, safety clearance, resume, and public handoff. These cases
   remain useful regression canaries, but they did not distinguish the candidate.
2. **Executable split audit:** the candidate produced a correct failing report for a holdout
   with perceptual-cluster leakage and a passing report for a clean replacement. It scored 3/4;
   the baseline scored 0/4. The missing candidate point exposed an under-specified prompt.
3. **Aligned contract:** after the prompt explicitly requested the evidence-layer distinctions,
   the candidate passed 5/5 and the baseline passed 2/5. The baseline correctly refused to
   invent reports and correctly described canary and full-master semantics, but it had no
   executable split auditor. The candidate's unrelated human-safety canary remained 4/4.

The executable auditor catches canonical-UUID reuse, duplicate holdout rows, and local
perceptual, duplicate-group, and burst-cluster leakage. Its default JSON contains counts and
membership digests rather than private identifiers.

## Interpretation

The hill climb improved both the skill and the eval. The useful gain is not that the revised
skill sounds more cautious. It can now prove that a proposed visual holdout is independent of
the evidence used to tune the field. Refusal, gaps, and blocked releases remain successful
outcomes when the required evidence is absent.

These were single paired runs under one model, not repeated trials or a variance estimate.
Full local grading artifacts remain outside the repository; only synthetic fixtures and this
aggregate, public-safe account are committed.
