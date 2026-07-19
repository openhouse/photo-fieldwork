# Curate Apple Photos evals

These evals exercise the failure modes most likely to turn an apparently successful photo-fieldwork run into an unsafe or irreproducible one. All fixtures use synthetic identifiers and generated pixels. No Apple Photos UUID, private path, preview, OCR, face data, or archive metadata belongs in this directory.

Run the suite from the repository root:

```bash
make eval
```

The ten executable contracts cover:

- same-count source membership drift;
- deterministic exact quotas with overlapping views;
- aggregate metrics concealing uncertainty or a weak view;
- UUID-addressed feedback and stale-sample rejection;
- safety propagation across duplicate and burst relationships;
- exact master, config, and evaluation-report binding before plan generation;
- actual JPEG decoding, coverage, and filename ambiguity;
- final-holdout freshness against prior tuning rounds;
- event-ledger recovery, compare-and-swap, and artifact checksums;
- a synthetic 4,000-item exact-quota benchmark.

## Hill-climb record

The suite was developed recursively on 2026-07-19:

| Iteration | Result | What changed next |
| --- | ---: | --- |
| Initial contracts against revision F | 6/10 | Added relational safety propagation, evaluation seals, preview verification, and holdout freshness. |
| First implementation | 10/10 | Strengthened the evaluator instead of accepting the score. |
| Harder evaluator | 8/10 | Required the actual evaluation report at planning and a real JPEG decode rather than marker inspection. |
| Final implementation | 10/10 | Added report-to-seal verification and Pillow-backed decode checks. |

`make check` runs the evals after the unit tests. A passing synthetic suite is a code-quality gate, not proof that a real archive run is editorially sound, publicly safe, or approved for production.
