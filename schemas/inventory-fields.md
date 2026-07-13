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
| `retrieval_basis` | Controlled summary of the metadata signals that retrieved the candidate. |
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `visible_context` | Local machine observation. Do not present it as a human-reviewed fact. |
| `human_visible_context` | Short reviewer-authored observation of visible objects, setting, or activity. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | `clear`, `machine-suspected`, or `human-confirmed-hold`. Holds can never enter the master. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `event_cluster` | Event identifier used to limit concentration. |
| `evaluation_exclusion` | A human-reviewed hard negative excluded from later selection. |
| `evaluation_reason` | Visible reason for the exclusion, without raw private text. |
| `previously_selected` | Whether an earlier referenced field contained the item. This is not visual evidence. |
| `freshly_inspected` | Whether local pixels were inspected in this run. |
| `publication_status` | Defaults to `not-approved`; field selection never grants publication approval. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |

The selector writes `primary_view`, `score_total`, `selection_tier`, and `selection_reason` into the proposed master.
