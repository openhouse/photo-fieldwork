# Operator runbook

Complete `make demo`, `make check`, and `make evals` before touching a private
archive. Keep the private machine profile, run workspace, holdout details, and
publication salt outside Git with restrictive permissions.

## 1. Preflight

- Confirm the frozen source count and exact membership digest.
- Confirm the permissioned helper identity and supported mutation contract.
- Confirm the run root is local and mode `0700`.
- Confirm network upload, direct SQLite writes, face identification, and
  sensitive-trait inference remain prohibited.

## 2. Retrieve and inspect

- Retrieve broadly from metadata hypotheses.
- Export previews locally through the permissioned helper.
- Independently decode previews before review.
- Keep missing, corrupt, symlinked, metadata-bearing, or over-permissioned
  previews outside evaluation-ready manifests.

## 3. Review and evaluate

Build the private review surface:

```bash
photo-fieldwork build-review \
  --sample RUN/manifests/eval-sample.csv \
  --previews RUN/previews/evaluation \
  --output RUN/review/index.html

photo-fieldwork serve-review --directory RUN/review
```

Inspect actual pixels and record visible reasons. Read all rejections and a
stratified uncertainty sample. Revise retrieval or assignment logic and repeat
without lowering quality or freshness requirements.

## 4. Protect the holdout

```bash
photo-fieldwork audit-holdout \
  --tuning RUN/manifests/tuning.csv \
  --canary RUN/manifests/canaries.csv \
  --holdout RUN/manifests/holdout.csv \
  --output RUN/reports/holdout-audit.json
```

Release requires zero canonical UUID and relation-cluster leakage. Use
`--include-identifiers` only for a private remediation report.

## 5. Freeze, write, and verify

- Validate the exact final field and HOLD set.
- Generate sealed test and production plans from the same release bundle.
- Verify the test write before production.
- Preserve the first production receipt, rerun once under a distinct nonce,
  and preserve the second receipt.
- Compare both receipts to the plan and verify exact catalog membership from a
  fresh WAL-aware read-only snapshot.

## 6. Prepare a public handoff

This step is optional and separate from production. Create a private salt file
with mode `0600`; never commit it.

```bash
photo-fieldwork public-handoff \
  --input RUN/manifests/publication-review.csv \
  --destination portfolio-case-study \
  --salt-file PRIVATE/publication-salt.txt \
  --output RUN/public/handoff.json \
  --blocked-report RUN/private/publication-blocked.json
```

Exit code `2` means at least one row claimed clearance but failed a required
gate. The public JSON may still contain independently cleared rows; inspect the
private blocked report before any release. Final publication remains an
authorized human decision.
