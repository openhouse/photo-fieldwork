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

## Required feedback fields

- `uuid`
- `primary_view`
- `judgment`: `fit`, `reject`, or `uncertain`
- `visible_reason`
- `safety_status`: `clear`, `hold`, or `needs-review`
- `error_category`
- `round_id`
- `reviewer_lens`

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
- No material view remains below 0.65 decisive precision without being relabeled as uncertain/editor hypothesis.
- Exact target, unique IDs, stills only, HOLD disjoint, all pixels locally available unless historically exceptional and explicitly recorded.
- Generic social scenes do not dominate work evidence.
- Named relationships and person-free material context both remain visible.

## Stop conditions

Run up to five substantial rounds. Stop earlier when all gates pass and failure review reveals no new systematic issue. Do not lower thresholds merely to finish. If the same genuine blocker recurs, preserve the run and explain exactly what input or permission is missing.

