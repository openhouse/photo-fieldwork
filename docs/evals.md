# Evaluation bank

Photo Fieldwork evaluates release claims, not just command completion. The skill bank in
`skills/curate-apple-photos/evals/evals.json` uses adversarial operator prompts to test the
workflow at the points where a plausible-looking run can become unsafe or irreproducible.

## Coverage

| Risk | Eval | Observable release fact |
| --- | --- | --- |
| Whole-library completion | 1 | Exact quotas, passing views, sealed plans, verified membership |
| Interrupted operation | 2 | Receipt-aware resume without premature mutation |
| Sensitive material | 3 | Human clearance, permanent HOLD, local-only handling |
| Count-preserving source drift | 4 | Sorted-membership SHA-256 mismatch blocks release |
| Weak or infeasible view | 5 | Per-view failure remains visible; quotas are not padded |
| Reused evaluation evidence | 6 | Fresh metrics exclude stable regression canaries |
| Feedback ambiguity | 7 | Image-view decisions, reasons, and duplicate-row rejection |
| Missing or corrupt pixels | 8 | Only verified previews count as visual inspection |
| Post-evaluation tampering | 9 | Evaluation, master, plan, seal, and receipt remain hash-bound |
| Public/private collapse | 10 | Data-minimized report plus separate publication clearance |
| Stale permissioned helper | 11 | Capability mismatch fails closed |
| Receipt-only completion | 12 | Independent exact verification and idempotence |
| Holdout contamination | 13 | UUID and related-cluster split audit before judgments |
| Partial public clearance | 14 | Five independent gates and a minimized projection |
| Config or sample drift | 15 | Candidate, config, and sample hashes remain aligned |
| Reflexive refusal | 16 | A fully closed synthetic case receives bounded PROCEED |

## Recursive hill climb

1. Start with realistic end-to-end prompts and identify claims that could pass from prose alone.
2. Split those claims into observable artifacts, hashes, counts, states, or explicit refusal conditions.
3. Add deterministic regression tests for the underlying contracts whenever the repository owns them.
4. Run the complete synthetic workflow after each change; a new eval must not weaken an older safety gate.
5. When a field run discovers a new failure mode, add the smallest case that would have caught it before changing implementation.
6. Run `make evals`. The contract auditor checks one-to-one case mapping, required risk coverage, concrete anti-shortcuts and counterfactuals, blocking cases, and a positive control.
7. Mutate the auditor in tests: remove required coverage, replace every outcome with refusal, add an orphan contract case, and weaken an expectation. Each mutation must fail.

Regression canaries are deliberately separate from fresh evaluation rows. They can block release,
but they cannot increase fresh coverage, decisive precision, or per-view sample sufficiency. A lint
PASS likewise proves only that known operational fields were not detected; it never grants rights,
consent, factual provenance, or publication permission.
