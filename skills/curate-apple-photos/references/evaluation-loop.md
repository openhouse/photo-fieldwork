# Recursive visual evaluation

## Round structure

1. Freeze the proposed master and record its `proposal_id` and `master_sha256`.
2. Sample fresh low, median, and high scores from every view. Inspect every item in a view smaller than the configured sample floor.
3. Add a stable canary set of known safety regressions and prior false positives without counting canaries as fresh coverage.
4. Render contact sheets with stable UUID labels and a page/row/column manifest.
5. Inspect all sheets with `view_image`; open individual previews when needed.
6. Record decisions in CSV.
7. Compute fresh sample completion, fresh decisive precision, master review fraction, and per-view results. Report canaries separately.
8. Read every rejection and representative uncertainty.
9. State the observed failure pattern and one system change.
10. Rebuild deterministically and repeat.

## Required feedback fields

- `uuid`
- `proposal_id`
- `master_sha256`
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
- Fresh decisive precision at or above configured minimum.
- Every material view meets its configured decisive precision, sample-size, coverage, and uncertainty gates.
- A weak view is explicitly relabeled `sparse-hypothesis` or returned to unclassified; its quota is never filled by lowering the evidence standard.
- Exact target, unique IDs, stills only, HOLD disjoint, all pixels locally available unless historically exceptional and explicitly recorded.
- Generic social scenes do not dominate work evidence.
- Named relationships and person-free material context both remain visible.

## Stop conditions

Run up to five substantial learning rounds, then freeze the master and declare the final evaluation scope. An `editor-field-verified` release may use a passing final stratified sample; describe its master review fraction honestly. A `master-human-reviewed` release requires every master item. A targeted edge audit may supplement but cannot impersonate either scope. Do not lower thresholds merely to finish.
