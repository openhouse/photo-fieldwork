# Evaluation bank

Photo Fieldwork uses two complementary kinds of evaluation:

1. `evals.json` contains realistic operator prompts and semantic assertions for testing the bundled skill with an agent or human reviewer.
2. `test_release_contracts.py` executes the release invariants that code can prove without private photographs or a live Photos mutation.

The prompt bank concentrates on consequential failures rather than happy-path wording: interrupted runs, source drift, protected material, unsupported views, stale evaluations, false freshness, and publication pressure.

Run the executable bank with:

```bash
make evals
```

Run it before and after changing the skill or workflow. A useful hill climb turns a failure into a general contract, adds an adversarial variant, and reruns the whole bank. Do not weaken an assertion merely to improve the score. Record iteration results in `evals/iterations/` when a change is being proposed.

The recorded `revision-A` climb includes both deterministic contract tests and paired read-only agent responses. The agent comparison uses identical prompts for the pre-revision and revised skill, grades only the saved responses, and records limitations alongside scores.

These synthetic evals do not establish live macOS compatibility, editorial quality, consent, rights, or publication clearance. Production still requires local pixel inspection, a bounded write test, and independent verification against Apple Photos.
