# Curate Apple Photos evals

These evals exercise the failure modes most likely to turn an apparently successful photo-fieldwork run into an unsafe or irreproducible one. All fixtures use synthetic identifiers and generated pixels. No Apple Photos UUID, private path, preview, OCR, face data, or archive metadata belongs in this directory.

Run the suite from the repository root:

```bash
make eval
```

The sixteen executable contracts cover:

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
- UUID- and cluster-clean separation of tuning, holdout, and regression canaries;
- ordered release attempts with prior-artifact revalidation;
- helper identity and capability negotiation;
- exact plan, helper, source, and catalog-topology receipt binding;
- distinct-execution idempotence evidence;
- a closed, allowlisted public handoff with opaque IDs.

## Hill-climb record

The suite was developed recursively on 2026-07-19:

| Iteration | Result | What changed next |
| --- | ---: | --- |
| Initial contracts against revision F | 6/10 | Added relational safety propagation, evaluation seals, preview verification, and holdout freshness. |
| First implementation | 10/10 | Strengthened the evaluator instead of accepting the score. |
| Harder evaluator | 8/10 | Required the actual evaluation report at planning and a real JPEG decode rather than marker inspection. |
| Final implementation | 10/10 | Added report-to-seal verification and Pillow-backed decode checks. |
| Expanded composite against unchanged revision F | 10/16 | Added cluster isolation, ordered release, helper/receipt, idempotence, and public-handoff contracts. |
| First composite implementation | 16/16 | Strengthened the new evaluators with post-completion drift, helper substitution, and allowlisted-value attacks. |
| Harder composite evaluator | 13/16 | Rehashed completed artifacts, authorized the exact helper binary, and linted values inside public fields. |
| Preferred composite | 16/16 | Added raw plan-byte binding and retained all stricter adversarial cases. |

`make check` runs the evals after the unit tests. A passing synthetic suite is a code-quality gate, not proof that a real archive run is editorially sound, publicly safe, or approved for production.
