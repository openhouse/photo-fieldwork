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
| `candidate_view_scores` | Optional JSON object mapping view IDs to retrieval scores. Equal scores break by stable view ID, not CSV order. |
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `visible_context` | Short controlled description such as `people`, `apparatus`, `place`, or `document`. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | Explicit safety state. `hold_automated`, `review_sensitive`, and `restricted_private` cannot enter the general master. Legacy values are normalized. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `event_cluster` | Event identifier used to limit concentration. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |

Supported safety states are `clear_automated`, `hold_automated`, `review_sensitive`, `cleared_editor_private`, `cleared_public_candidate`, and `restricted_private`. Legacy `clear`, `hold`, and `needs-review` values are normalized. Only a human editor may grant a clearance state.

The selector writes `primary_view`, `secondary_views`, `score_total`, `selection_tier`, and `selection_reason` into the proposed master.
