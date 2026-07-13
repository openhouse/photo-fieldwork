# Threat model

Photo Fieldwork operates on archives that may expose private relationships,
homes, records, locations, identities, and vulnerable contexts. Local-only does
not mean risk-free.

## Protected assets

- original photographs and videos;
- exported previews and contact sheets;
- raw or derived OCR;
- existing People associations and co-presence patterns;
- exact coordinates and private location names;
- HOLD membership and generalized hold reasons;
- stable Photos identifiers and local paths;
- rights, consent, and publication decisions;
- helper permissions and writer plans.

## Trust boundaries

### Apple Photos library

The library is authoritative for assets and existing human metadata. Readers and
verifiers use immutable, query-only access. No component writes Photos SQLite.

### Private run workspace

The workspace contains previews, manifests, and decisions. It is created with
mode `0700`; writer ID files use `0600`. It must not live in a public repository,
shared cloud folder, or web root.

### Local helper and Photos automation

PhotoKit and AppleScript can mutate album structure. They receive a frozen,
membership-only plan, run a ten-item test first, fail on unexpected state, emit
receipts, and remain untrusted until an independent read-only verifier passes.

### Review workbench

The generated workbench has no external scripts, fonts, analytics, or network
connections. Its optional server binds only to loopback. Browser local storage
and exported feedback remain private artifacts and need the same handling as the
run workspace.

### Public handoff

The public handoff is built from an allowlist of fields and cleared rows. It uses
salted opaque IDs and excludes archive UUIDs, People, albums, paths, locations,
OCR, safety reasons, and HOLD membership.

## Principal risks and controls

| Risk | Control |
| --- | --- |
| Private pixels leave the machine | Network disabled in plans; no cloud inspection; offline workbench |
| Generated albums become circular evidence | Explicit album lineage; generated/private/audit lineages excluded |
| People metadata becomes identity or consent | Existing associations are retrieval-only; no new face identification |
| A document evades automated flags | HOLD before ranking, risk-stratified safety audit, human review |
| A tuning sample is reported as independent | Locked final master and untouched final-holdout role |
| Catalog state changes during a run | Frozen source count, plan hashes, exact writer checks, independent verification |
| TCC failure causes unsafe improvisation | Live preflight and explicit, contract-tested writer backend selection |
| Public export leaks private columns | Allowlisted projection schema and clearance gates |
| Temporary scripts or ID files persist | Private run location, restrictive permissions, explicit retention review |
| A collaborator assumes album membership is permission | Separate rights, consent, claim, and publication states |

## Retention

The archive owner should decide how long to retain previews, contact sheets,
writer ID files, review local storage, and HOLD manifests. Keep frozen configs,
aggregate reports, plan hashes, writer receipts, and independent verification
when an audit trail is needed. Delete private working derivatives only through an
explicit owner-approved process; Photo Fieldwork never deletes them automatically.

## Non-goals

The system does not establish legal ownership, infer consent, identify unnamed
people, determine sensitive traits, or certify that a photograph is safe to
publish. It structures review and makes unresolved states visible.
