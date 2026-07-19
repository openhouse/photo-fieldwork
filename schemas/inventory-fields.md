# Inventory fields

The selector accepts UTF-8 CSV. Unknown columns are preserved. Boolean values may be `true`, `false`, `1`, or `0`.

## Required

| Field | Meaning |
| --- | --- |
| `uuid` | Stable catalog or file identifier. |
| `filename` | Human-readable original filename. |
| `assigned_view` | Explicit reviewed editorial assignment. The selector never derives this from `candidate_views`. |

## Recommended

| Field | Meaning |
| --- | --- |
| `candidate_views` | Semicolon-separated view IDs suggested by metadata retrieval. These remain hypotheses. |
| `retrieval_basis` | Aggregate signal classes by view, without private matched terms. |
| `assigned_view` | Optional explicit editorial assignment. If omitted for every eligible row, deterministic constrained assignment supplies it. Never mix assigned and unassigned rows. |
| `assignment_status` | `assigned`, `unclassified`, or `sparse-hypothesis`. |
| `assignment_reason` | Public-safe reason for the frozen assignment. |
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `visible_observation` | Short reviewer-authored statement about what is actually visible. |
| `observation_source` | `human`, `reviewer`, `delegated-editorial-inference`, `unreviewed`, or `none`. |
| `machine_visible_signals` | Local machine labels used for retrieval, not human observation or factual provenance. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `automated_safety_state` | Local detector result such as `clear-automated`, `hold`, or `unavailable`. |
| `safety_status` | `clear-automated`, `human-needs-review`, or `hold`. Holds can never enter the master. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `perceptual_cluster_id` | Local pixel-derived near-duplicate cluster identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `event_cluster` | Event identifier used to limit concentration. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |
| `provenance_status` | Defaults to `retrieval-only`; separate from visible observation. |
| `publication_state` | Defaults to `publication-review-required`; selection never grants permission. |

The selector writes `primary_view`, `score_total`, `selection_tier`,
`selection_reason`, `config_sha256`, `master_sha256`, and `proposal_id` into the
proposed master. Evaluation rows additionally bind `round_id`, `sample_sha256`,
`inspection_path`, `inspection_sha256`, `inspection_round_id`, and
`inspection_sample_sha256` to real local artifacts for the deterministic review
sample.
