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
| `excluded_views` | Semicolon-separated view IDs rejected for this item. The selector must not reassign them. |
| `retrieval_provenance_json` | Structured local retrieval channels, terms, weights, and view hypotheses. |
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `visible_context` | Short controlled description such as `people`, `apparatus`, `place`, or `document`. |
| `vision_labels_all` | Semicolon-separated local machine-classification labels. These are automated evidence, not editorial review. |
| `pixel_available` | Whether local PhotoKit inspection returned pixels. |
| `preview_exported` | Whether a local preview was exported; decode verification is a separate gate. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | `clear` or `hold`. Holds can never enter the master. |
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

The selector writes `primary_view`, `score_total`, `selection_tier`, and `selection_reason` into the proposed master. Evaluation adds `judgment`, `visible_reason`, `error_category`, `editorial_safety_status`, `provenance_status`, `reviewer_actor`, `reviewer_lens`, and `round_id`. These fields keep catalog indexing, automated processing, editorial judgment, and publication clearance distinct.
