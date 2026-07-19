# Preferred composite

This revision composes the strongest interoperable contracts found across the `feature/revision-*` branch family. It is intentionally not a wholesale merge. The selection criterion is simple: prevent a consequential false success while keeping the operator path legible.

## Selected contracts

1. **Candidate and holdout identity:** freeze source membership, seal the evaluated candidate, and keep the final holdout clean at both UUID and perceptual/duplicate/burst-cluster levels. Tuning evidence and regression canaries remain distinct.
2. **Ordered release history:** enforce phase order, compare-and-swap revisions, unique attempt IDs, append-only events, and checksum revalidation of all prior completed artifacts.
3. **Helper and receipt identity:** negotiate capabilities before mutation; authorize an exact bundle and binary; bind receipts to launch nonce, raw plan bytes, canonical plan content, source, and exact folder/album topology.
4. **Real idempotence evidence:** require two distinct executions with equivalent resulting catalog topology. A copied receipt or repeated nonce is not evidence.
5. **Closed public handoff:** keep the editor field private. Emit a separate allowlisted projection with opaque IDs only after independent rights, consent, claim, and publication gates pass.

## Deliberately deferred

The composite does not yet add a review web application, FTS index, or a richer image-view evidence graph. Those may improve editorial throughput, but they are larger product surfaces and are not required to close the release-integrity failures covered here. Statistical sampling beyond the existing stratified and 4,000-item scale contracts also remains future work.

## Human boundary

Passing these contracts means the software has stronger evidence that it executed the reviewed plan faithfully. It does not establish taste, factual provenance, consent, rights, or publication approval. Those remain explicit human decisions.
