# Evaluation bank

Photo Fieldwork uses two complementary kinds of evaluation:

1. `evals.json` contains realistic operator prompts and semantic assertions for testing the bundled skill with an agent or human reviewer.
2. `test_release_contracts.py` executes the release invariants that code can prove without private photographs or a live Photos mutation.

The schema-2 prompt bank contains typed `BLOCK` and `PROCEED` decisions, severities, unsafe shortcuts, and counterfactual pass conditions. It concentrates on consequential failures while retaining positive controls: interrupted runs, source drift, protected relations, unsupported views, stale config and feedback, false freshness, holdout leakage, incomplete receipts, delegated publication pressure, and a clean private release.

Run the executable bank with:

```bash
make evals
```

Run it before and after changing the skill or workflow. A useful hill climb turns a failure into a general contract, adds an adversarial variant, and reruns the whole bank. Do not weaken an assertion merely to improve the score. Record iteration results in `evals/iterations/` when a change is being proposed.

The recorded `revision-A` climb includes both deterministic contract tests and paired read-only agent responses. The composite climb adds evaluator mutation tests: removing every positive control, a critical coverage dimension, or one counterfactual must make the bank fail. This guards against improving a score by making the evaluator easier.

These synthetic evals do not establish live macOS compatibility, editorial quality, consent, rights, or publication clearance. Production still requires local pixel inspection, a bounded write test, and independent verification against Apple Photos.
