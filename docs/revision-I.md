# Revision I composite guide

Revision I composes the strongest compatible parts of the revision family into
one governed path. The operating principle is candidate coherence: the source,
policy, master, review sample, local inspection evidence, evaluation,
validation, write plan, execution receipts, and live catalog verification must
describe the same unchanged candidate.

It is intentionally capable of a bounded `PROCEED`. When every artifact needed
for the requested next step is coherent, the system advances to that step. It
does not use a technical pass to claim human inspection, editorial quality,
production completion, rights clearance, consent, or publication approval.

## Source and proposal identity

Configure a private machine profile, then freeze the source count and digest.
Both a Photos album and `visible-library-stills://v1` are supported. Same-count
membership drift is still drift.

The selector binds `config_sha256`, `master_sha256`, and `proposal_id` to the
selected rows. Complete explicit `assigned_view` values are preserved. When no
explicit assignments exist, deterministic constrained assignment fills every
configured quota exactly from `candidate_views`. A partially assigned field or
an infeasible quota blocks with capacity diagnostics.

## Fresh evaluation rounds

Create a private history file using the schema in
`schemas/sampling-history.schema.json`:

```json
{
  "excluded_ids": ["LOCAL-ID-REVIEWED-IN-ROUND-01"],
  "canary_ids": ["LOCAL-ID-REGRESSION-CANARY"]
}
```

Then use the same file for both commands:

```bash
photo-fieldwork sample \
  --master RUN/manifests/proposed-master.csv \
  --config RUN/config.json \
  --round-id round-02 \
  --sampling-history RUN/manifests/sampling-history.json \
  --output RUN/manifests/eval-sample-round-02.csv

photo-fieldwork evaluate \
  --feedback RUN/manifests/eval-sample-round-02-labeled.csv \
  --master RUN/manifests/proposed-master.csv \
  --config RUN/config.json \
  --sampling-history RUN/manifests/sampling-history.json \
  --output RUN/reports/round-02
```

Ordinary previously reviewed IDs are excluded so coverage remains fresh.
Canaries are included deliberately, marked `sample_kind=canary`, and scored
separately. They cannot inflate fresh coverage or precision, but any canary
regression blocks release. The normalized history digest is part of the sample
identity, so changing either list makes the old feedback stale.

Every judgment must point to a regular, non-symlink local inspection artifact
whose digest, round, and sample identity match. This proves the evidence file
was available and candidate-bound; it cannot prove the quality of attention.

## Release chain

Plan generation recomputes evaluation and validation from the current private
artifacts. The ten-item test and production plan are membership-only. Each
helper launch carries a nonce, each receipt must reconcile against the exact
plan and source, and the production rerun must be a distinct execution.

Independent verification uses a fresh WAL-aware read-only Photos snapshot and
checks identifiers, membership, collection types, and hierarchy. A copied
receipt, supplied PASS document, stale snapshot, or matching count without
matching identity cannot complete the phase.

## Publication is another gate

Editor-field membership never supplies publication permission. First create a
private publication-review CSV with independent item-specific fields:

- `publication_status`;
- `publication_destination`;
- `rights_status`;
- `consent_status`;
- `claim_status`;
- optional editorial fields such as caption, credit, crop, and alt text.

After human review, create a minimized derivative:

```bash
photo-fieldwork public-handoff \
  --manifest RUN/private/publication-review.csv \
  --destination portfolio-case-study \
  --salt-file /private/path/public-id-salt.txt \
  --output RUN/public/portfolio-case-study.json
```

The salt must contain at least 16 characters, be a regular file with mode
`0600`, and remain private. The output follows
`schemas/public-handoff.schema.json`: private UUIDs and operational fields are
replaced by salted public IDs and an explicit allowlist. Unreviewed rows are
omitted. A row claiming publication readiness blocks the whole handoff if its
rights, consent, claim, or destination gate is incomplete.

## Evals

Run `make check` for unit, structural, privacy-boundary, JSON, and Swift checks.
Run `make evals` for every allowlisted executable canary. The public bank must
contain both adversarial blocking cases and at least one coherent proceed
control; otherwise a blanket-refusal system could appear safe.

Passing these checks means the implementation satisfies its synthetic
contract. It does not attest to a real photo run, rights or consent, editorial
approval, or publication readiness.
