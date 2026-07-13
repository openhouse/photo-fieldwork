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
| `retrieval_basis` | Machine-readable or concise human explanation of the metadata fields and terms that surfaced the item. |
| `visible_observation` | What a reviewer can actually see, kept separate from project inference. |
| `provenance_basis` | Why a project, event, or sequence association is plausible. |
| `claim_boundary` | What the photograph and its metadata do not establish. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | `clear` or `hold`. Holds can never enter the master. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `historical_hold` | Excludes an item previously placed in HOLD, even if current metadata changes. |
| `known_reject` | Excludes a prior visible false positive from future selections. |
| `prior_judgment` | Prior `fit`, `reject`, or `uncertain` judgment used for regression control. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `event_cluster` | Event identifier used to limit concentration. |
| `replacement` | Marks an item introduced after an evaluation pass; every replacement must enter the final-field audit. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |

The selector writes `primary_view`, `score_total`, `selection_tier`, and `selection_reason` into the proposed master.
