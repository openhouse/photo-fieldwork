# Composite eval hill climb

Date: 2026-07-19

The hill climb used synthetic fixtures only. No Apple Photos library, preview,
People association, OCR, location, or private manifest entered the repository or
test outputs.

## Baseline

Revision M was adopted as the unchanged production spine. Its baseline passed
52 unit tests, Python compilation, JSON validation, Swift typechecking, and the
24-case production bank with 21 critical cases, 98 expectations, 16 capability
tags, and 11 recomputable fixture canaries.

## Round 1: cross-boundary implementation

Added executable contracts for holdout independence, private offline review,
and destination-scoped public handoff. The first 13 targeted tests produced two
failures:

- a CLI test invoked the shell launcher through the Python interpreter rather
  than executing the launcher directly;
- a privacy assertion searched for a one-letter identifier that also appeared
  inside ordinary report words.

Both were test-oracle defects. The CLI canary was corrected to exercise the real
entry point, and the privacy canary now uses distinctive synthetic secrets and
asserts each is absent from the default report. All 13 then passed.

## Round 2: eval-of-eval governance

Added a 12-case, 15-dimension behavioral bank with six `BLOCK`, three
`REMEDIATE_THEN_PROCEED`, two `PROCEED`, and one `PUBLICATION_BLOCKED` oracle.
Mutation tests confirmed that the bank fails when:

- the holdout case is orphaned;
- every decision becomes refusal-only;
- every decision becomes permissive-only;
- an expectation becomes vague;
- a counterfactual pass condition disappears;
- the contract attempts to escape its eval directory.

The full structural suite then passed 73 unit tests plus both eval-bank
validators and Swift typechecking.

## Round 3: full executable bank

`make evals` passed all 30 allowlisted production canaries, the dependency-free
synthetic end-to-end practice run, and 21 cross-boundary executable tests.

## Round 4: publication boundary attack

Adversarial review identified two untested paths: a symlinked public output and
the public package sharing a path with the private blocked-row report. The
implementation now rejects both, requires the salt to be a regular private
file, and tests the permission boundary directly.

The hardened candidate passed:

- 75 unit tests;
- Python compilation and tracked JSON validation;
- macOS Swift helper typechecking;
- all 30 production executable canaries and synthetic practice;
- all 23 composite executable tests;
- both structural banks, including both positive controls.

## Stop condition

The climb stops when the unchanged candidate passes structural, executable,
positive, adversarial, privacy-boundary, and synthetic end-to-end checks without
weakening a source, human-review, safety, publication, or verification gate.
This establishes code-review readiness only. Live Photos access, real visual
inspection, publication clearance, and final human approval remain open gates.
