# Inventory fields

The selector accepts UTF-8 CSV. Unknown columns are preserved. Boolean values may be `true`, `false`, `1`, or `0`.

## Required

| Field | Meaning |
| --- | --- |
| `uuid` | Stable catalog or file identifier. |
| `filename` | Human-readable original filename. |

## Recommended

| Field | Meaning |
| --- | --- |
| `candidate_views` | Semicolon-separated view IDs suggested by metadata retrieval. These remain hypotheses. |
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `visible_context` | Short controlled description such as `people`, `apparatus`, `place`, or `document`. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | Provenance-aware safety state. Blocking states can never enter the master. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `safety_actor` | `automated`, `human`, or another generalized review role. |
| `safety_reviewed_at` | Optional review timestamp. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |

The selector writes `primary_view`, `score_total`, `selection_tier`, and `selection_reason` into the proposed master.

## Safety states

Blocking states are `hold`, `auto-hold`, `needs-human-review`, `human-added-hold`,
`confirmed-sensitive`, `unavailable`, and `corrupt`. `clear` and
`cleared-false-positive` are eligible only when the rest of the selection contract
also passes. A cleared false positive requires a human review record; it is not a
global detector exception.
