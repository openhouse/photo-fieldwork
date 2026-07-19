# Revision H composite

Revision H is a selective composite of the `feature/revision-*` family. It uses
Revision M as the production spine and adds only contracts that strengthen a
distinct boundary. It does not combine competing run ledgers, selectors, or
Photos writers.

## Production spine

Revision M supplies the candidate-bound operating chain:

- exact source and proposal identities;
- actual local inspection artifact digests;
- deterministic selection and per-view evaluation;
- fail-closed safety and relation propagation;
- ordered, evidence-backed run phases;
- sealed membership-only plans;
- test-write and production receipts with distinct execution nonces;
- WAL-aware, read-only independent verification;
- 24 structural scenarios and executable production canaries.

## Composite additions

- **Private review workbench:** A static, dependency-free surface copies only
  local previews into a mode-`0700` workspace, makes no network requests, binds
  only to loopback, preserves sampling context, and makes unavailable previews
  HOLD-only.
- **Holdout independence:** `audit-holdout` checks canonical UUIDs plus
  perceptual, duplicate, and burst relations across tuning, canary, and holdout
  manifests. Default reports expose counts and set digests, not identifiers.
- **Public handoff:** `public-handoff` requires destination-scoped rights,
  consent, claim, safety, and editorial gates. Its public JSON is an allowlist
  under salted opaque IDs; blocked reasons and source IDs remain private.
- **Evaluation of the evaluation:** A separate 12-case composite bank requires
  positive production and publication controls, adversarial blocking cases,
  concrete counterfactuals, anti-shortcuts, complete dimension coverage, and
  executable canaries.

## Deliberate boundaries

- The production pipeline does not automate taste, provenance research,
  consent, rights, or public meaning.
- The review workbench is private operational infrastructure, not a public
  gallery or a publication preview.
- A holdout audit establishes split independence only for the identifiers and
  relation fields supplied to it.
- A public handoff records completed human gates; it does not determine those
  gates.
- Passing automated checks does not substitute for actual visual inspection,
  permissioned Photos access, authorized publication review, or final human
  approval.

Read [the composite design](composite.md),
[the recorded eval hill climb](composite-eval-hill-climb.md),
[the operator runbook](operator-runbook.md), and
[the production protocol](production-protocol.md) before a live run.
