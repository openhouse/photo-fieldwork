# Revision E composite

Date: 2026-07-19

This composite keeps Revision E's epistemic model as the organizing spine: retrieval, machine processing, visual inspection, editorial judgment, safety, editor-field verification, and publication clearance remain separate states. It incorporates the strongest compatible contracts surfaced across `feature/revision-A` through `feature/revision-N` without merging parallel implementations wholesale.

## Composition choices

| Source strength | Composite implementation |
| --- | --- |
| A: operator workflow and exact assignment | Retains E's deterministic capacity max-flow, offline review surface, explicit run phases, and operator CLI. |
| B: end-to-end custody | Adds frozen source manifests, exact membership fingerprints, content-addressed release candidates, schema-2 plans, and helper-contract identity across Python and Swift. |
| C, F, and J: durable lifecycle | Replaces mutable phase history with a locked, hash-chained append-only event ledger, atomic materialized state, compare-and-swap revisions, explicit recovery, and unique write attempt IDs. |
| D and L: honest evaluation and public boundaries | Audits tuning, final-holdout, and canary splits across UUID, duplicate, perceptual-cluster, and burst relationships; publication remains a separate closed workflow. |
| G, H, and I: evidence-aware evaluation | Keeps image-view judgments, per-view gates, visible reasons, reviewer provenance, uncertainty, Wilson intervals, and canaries that can block but cannot improve final quality metrics. |
| K: capability negotiation and WAL awareness | Requires helper contract version 2 and verifies a read-only SQLite backup containing committed WAL-visible state before immutable queries. |
| M: hostile production verification | Rejects self-authored PASS reports and incomplete receipts; binds plan, candidate, source, helper binary, execution nonce, topology, and counts. |
| N: whole-library scale | Retains the capacity-flow assignment and whole-visible-library source contract while making same-count membership substitution a hard failure. |

## One release candidate

`photo-fieldwork plan` now builds one release candidate from these exact inputs:

- frozen source inventory and source manifest;
- configuration;
- master membership and view assignments;
- HOLD membership;
- untouched final-holdout sample;
- passing candidate-bound final evaluation;
- passing final validation;
- passing evaluation-split audit.

The candidate stores hashes of every input and receives a content-derived `candidate_id`. The catalog plan embeds that candidate and seals its own contents. Any changed source member, assignment, sample, report, HOLD, config, or plan member invalidates authorization and requires a new candidate.

An `editor-field-verified` candidate always carries `publication_clearance: false`. Code refuses to manufacture a `publication-ready` candidate from editor-field evidence.

`photo-fieldwork public-audit` separately checks proposed public JSON, CSV, or Markdown for private fields, archive identifiers, OCR, coordinates, credentials, email addresses, and local machine paths. It reports failures without rewriting the private source artifact.

## Durable execution

The event ledger is authoritative; `run-state.json` is a recoverable projection. Every event has a revision, prior-event hash, and event hash. A divergent, missing, or corrupt projection blocks resume until `run-recover` reconstructs it from a valid ledger. Completed phase artifacts carry both byte size and SHA-256. Write-test and production execution phases require unique attempt IDs.

The bridge requires helper contract version 2. Each launch creates a private attempt plan, a bridge-generated execution nonce, and a preserved receipt path. The helper receipt echoes the authorized candidate, plan, source membership, helper identity, nonce, album topology, and counts. `receipt-verify` validates one attempt; `receipt-compare` requires two distinct nonces over the same plan and topology.

## Independent verification

`verify_photos_commit.py` never writes to Photos SQLite. It opens the live database read-only, uses SQLite's backup API to freeze committed database and WAL-visible state into a private snapshot, closes the live connection, and performs immutable query-only verification against that snapshot. It checks source membership identity and exact album memberships, then emits both Markdown and machine-readable JSON with snapshot, plan, receipt, and candidate hashes.

## Deliberate limits

- Synthetic eval success does not establish visual taste, real PhotoKit compatibility, performance on a particular machine, or completion of a live run.
- Helper installation and Photos permission remain local human-controlled actions.
- Pixel inspection, editorial judgment, sensitive-material review, rights, consent, credit, accessibility, and publication approval remain human gates.
- The composite does not upload photographs or private archive data, identify unnamed people, infer sensitive traits, mutate originals or metadata, or write directly to Photos SQLite.
- Public reports must remain allowlisted projections; operational manifests, IDs, paths, People data, OCR, locations, and HOLD details stay private.

## Review order

1. `src/photo_fieldwork/release.py`
2. `src/photo_fieldwork/runstate.py`
3. `src/photo_fieldwork/evaluation_split.py`
4. `src/photo_fieldwork/receipts.py`
5. `skills/curate-apple-photos/scripts/photo_archive_bridge.py`
6. `skills/curate-apple-photos/scripts/verify_photos_commit.py`
7. `tests/test_composite.py`
8. `docs/eval-results-revision-e.md`
