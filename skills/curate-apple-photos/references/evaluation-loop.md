# Recursive visual evaluation

## Round structure

1. Freeze the proposed master and assign a round ID.
2. Sample low, median, and high scores from every view.
3. Add known safety regressions and prior false positives.
4. Render contact sheets with stable UUID labels.
5. Inspect all sheets with `view_image`; open individual previews when needed.
6. Record decisions in CSV.
7. Compute coverage and precision.
8. Read every rejection and representative uncertainty.
9. State the observed failure pattern and one system change.
10. Rebuild deterministically and repeat.

Iterative rounds can be targeted. After the last change, run a separate final audit that
contains every selected UUID. Only this audit may authorize catalog plan generation.

## Required feedback fields

- `uuid`
- `primary_view`
- `judgment`: `fit`, `reject`, or `uncertain`
- `visible_reason`
- `evaluation_safety_state`: `clear`, a `hold-*` state, or `unavailable`
- `error_category`
- `round_id`
- `reviewer_lens`
- `proposal_id` and `master_sha256`

## Error categories

- `retrieval-mismatch`
- `context-collapse`
- `taxonomy-coercion`
- `privacy-miss`
- `relationship-loss`
- `temporal-distortion`
- `redundancy`
- `aesthetic-overreach`
- `visible-fit`

## Gates

- Zero known identity-document or private-record regressions in the master.
- Every view sampled.
- Coverage at or above configured minimum.
- Overall decisive precision at or above configured minimum.
- Every material view meets its configured decisive-sample and precision thresholds; a weak
  view gets a targeted follow-up round or is relabeled as uncertain/editor hypothesis.
- Missing visible reasons, missing reject/uncertain error categories, and any safety regression fail the gate.
- The final write-authorizing report has `full_master_audit: true` and matches the frozen master hash.
- Exact target, unique IDs, stills only, HOLD disjoint, all pixels locally available unless historically exceptional and explicitly recorded.
- Generic social scenes do not dominate work evidence.
- Named relationships and person-free material context both remain visible.

## Stop conditions

Run up to five substantial rounds. Stop earlier when all gates pass and failure review reveals no new systematic issue. Do not lower thresholds merely to finish. If the same genuine blocker recurs, preserve the run and explain exactly what input or permission is missing.
