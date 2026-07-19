# Skill behavior evals

These synthetic evals test whether an agent using `curate-apple-photos` makes the right release decision under contradictory evidence. They do not access Apple Photos, contain private archive data, or test visual taste.

The suite intentionally includes one green completion case. A skill that blocks every run is not reliable.

## Failure classes

| Eval | Boundary under test |
| --- | --- |
| 01 | Frozen source identity and live-count drift |
| 02 | Per-view gates and untouched final holdout |
| 03 | Preview decoding versus machine processing and visual review |
| 04 | Replacement, decision, duplicate, and safety closure |
| 05 | Interrupted-run state and receipt integrity |
| 06 | Editor-field inclusion versus destination-specific publication clearance |
| 07 | Unsupported hypotheses, unclassified material, anti-claims, and role-play provenance |
| 08 | Exact assignment feasibility without quota fiction |
| 09 | Evidence-backed editor-field completion without publication overclaim |

Every response must cite evidence IDs from its fixture. `rubric.json` checks scoped disposition, active gate, fixture-specific facts, evidence closure, required failure concepts, role-play provenance where applicable, and whether a Photos mutation was proposed.

## Validate the suite

```bash
python3 skills/curate-apple-photos/evals/validate_response.py --check-suite
```

## Run an agent benchmark

Snapshot the prior skill before editing, then run both configurations against the same eval IDs:

```bash
python3 skills/curate-apple-photos/evals/run_evals.py \
  --skill /path/to/prior-skill-snapshot \
  --workspace /private/tmp/photo-fieldwork-evals \
  --label baseline \
  --evals all

python3 skills/curate-apple-photos/evals/run_evals.py \
  --skill skills/curate-apple-photos \
  --workspace /private/tmp/photo-fieldwork-evals \
  --label candidate \
  --evals all \
  --runs-per-eval 3
```

The runner copies only the skill and one synthetic fixture into each isolated, read-only executor workspace. It does not expose the rubric to the executor. It clears stale responses, bounds executor duration, and records prompt, response, skill-tree, and suite hashes. Use repeated runs when comparing stochastic agents; a one-run score is diagnostic, not a confidence interval. Generated transcripts and responses stay in the requested temporary workspace and must not be committed without reviewing them for local paths or other machine-specific data.
