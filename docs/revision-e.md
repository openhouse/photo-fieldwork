# Revision E: fieldwork-derived hardening

Revision E turns lessons from a large Apple Photos curation run into reusable product behavior. The central change is epistemic as much as technical: catalog access, machine processing, editorial judgment, selection, and publication permission are separate states.

## What changed

| Fieldwork finding | Implemented response |
| --- | --- |
| Machine processing was too easily described as review. | Selection reports use a strict review-state vocabulary, and automated labels no longer count as editorial judgment. |
| Overall precision could conceal a weak view. | `evaluate` enforces minimum decisive evidence and precision for every configured nonzero-quota view. |
| Rejected images could reappear in later retrieval rounds. | An append-only decision ledger stores reviewer, lens, round, reason, safety, and provenance; `decisions-apply` excludes rejected item/view pairs and propagates cluster holds. |
| Quota repair could break diversity constraints. | One deterministic max-flow assignment solves exact view quotas and global named-people/person-free floors together, failing with scarcity diagnostics when infeasible. |
| Long runs depended on session memory. | A phase state machine advances one legal step at a time and hashes receipt files for resumability and tamper detection. |
| Repeated one-off merge scripts increased risk. | The CLI now provides conflict-safe candidate union/subtraction, manifest diff, inspection merge, compact feedback merge, and replacement-entry audit. |
| Retrieval reasons were flattened into a score. | The Apple retrieval adapter emits structured channel, term, weight, and view provenance for every candidate. |
| Review handoff was split across contact sheets and ad hoc CSV editing. | `photo-fieldwork review` creates an offline local browser surface with stable IDs, filters, fit/reject/uncertain controls, safety fields, and feedback CSV download. |
| The narrow source album was not enough for whole-library requests. | A read-only inventory builder and PhotoKit/verifier virtual source now support every visible still via `visible-library-stills://v1`. |
| Helper preflight needed stronger evidence. | `doctor` checks app identity, executable hash, inventory integrity, source identity/count, live whole-library count, and disk headroom. |
| Preview receipts did not prove files were usable. | `verify_preview_exports.py` decodes every promised preview and fails when any are absent or corrupt; contact sheets mark corrupt files explicitly. |
| Earlier versions needed durable integrity evidence. | The version registry stores manifest, membership, source, album, and verification-receipt hashes and compares overlap across versions. |
| Editor-field inclusion could be mistaken for publication approval. | Publication manifests default closed and require rights, consent, provenance, credit, accessibility, context, destination, and date before clearance passes. |
| Core, local integration, and machine facts were easy to conflate. | Architecture and skill documentation now name the adapter boundary and keep machine-specific facts in the Jamie profile. |
| Regressions needed durable tests. | Synthetic tests cover weak-view masking, insufficient evidence, quota scarcity, joint diversity floors, decision reentry, hold propagation, altered receipts, missing previews, clearance failure, and version tampering. |
| Unit tests did not establish agent release judgment. | Fourteen adversarial synthetic skill evals now grade scoped disposition, factual and referential evidence closure, safe continuation, production identity, publication boundaries, and positive completion; recursive hill climbs improved both the original and expanded controlled suites to 100%. |
| Scale and interruption costs were invisible. | Whole-library inventory, retrieval, helper launch, and run phases now emit elapsed-time and throughput observations alongside count and hash receipts. |
| Parallel revisions exposed compatible production contracts. | The [Revision E composite](composite-revision-e.md) adds exact source and candidate identity, hash-chained run events, relationship-level split audits, capability-negotiated helper receipts, distinct execution attempts, and WAL-visible frozen verification snapshots. |
| A plausible PASS could authorize itself. | Catalog planning recomputes candidate bindings from source, config, master, HOLD, final sample, evaluation, validation, and split-audit artifacts; helper and verifier receipts must carry the same immutable identity. |

## Operational boundaries

- No private photographs, raw OCR, exact private coordinates, or personal manifests are committed to this repository.
- The core remains standard-library Python and does not open pixels or mutate a catalog.
- Apple Photos inspection and writes remain inside the permissioned helper.
- Photos database access remains immutable and query-only.
- The only default catalog mutations remain folder/album creation and addition of existing asset membership.
- Role-play can support editorial interpretation but cannot manufacture provenance or first-hand memory.

## Verification

Run:

```bash
make check
make demo
make check-apple
```

See [the composite design](composite-revision-e.md) and [the skill-eval hill climb](eval-results-revision-e.md) for the implementation map, agent-level method, and limits.

The synthetic demo does not access Apple Photos. Production PhotoKit behavior still requires the stable, permissioned local app plus a test write and independent verification against the user's live library.
