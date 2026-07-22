from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

from .review import _canonical_uuid, verified_preview_records


INLINE_CONTEXT_FIELDS = (
    "candidate_views",
    "retrieval_basis",
    "assigned_view",
    "assignment_status",
    "assignment_reason",
    "evidence_confidence",
    "date",
    "place",
    "persons",
    "favorite",
    "edited",
    "event_cluster",
    "visible_observation",
    "observation_source",
)

ASSET_CONTEXT_FIELDS = (
    "date_created",
    "date_added",
    "date_modified",
    "year",
    "width",
    "height",
    "original_width",
    "original_height",
    "favorite",
    "edited",
    "external_edit",
    "title",
    "description",
    "camera_make",
    "camera_model",
    "original_file_size",
    "face_count",
    "burst",
    "burst_key",
    "duplicate_group_id",
)


def _metadata_by_uuid(metadata: list[dict] | None, expected: set[str]) -> dict[str, dict]:
    if metadata is None:
        return {}
    by_uuid: dict[str, dict] = {}
    for record in metadata:
        uuid = _canonical_uuid(record.get("uuid"))
        if not uuid or uuid in by_uuid:
            raise ValueError("studio metadata requires unique non-empty UUIDs")
        by_uuid[uuid] = record
    if set(by_uuid) != expected:
        raise ValueError("studio metadata UUIDs must exactly match the studio field")
    return by_uuid


def _relationship_values(record: dict, name: str, field: str) -> list[str]:
    relationships = record.get("relationships") or {}
    rows = relationships.get(name) or []
    values = {str(row.get(field) or "").strip() for row in rows if isinstance(row, dict)}
    return sorted(value for value in values if value)


def _private_context(row: dict[str, str], metadata: dict | None) -> dict[str, object]:
    context: dict[str, object] = {
        field: str(row.get(field) or "").strip()
        for field in INLINE_CONTEXT_FIELDS
        if str(row.get(field) or "").strip()
    }
    if metadata is None:
        return context
    asset = metadata.get("asset") or {}
    for field in ASSET_CONTEXT_FIELDS:
        value = asset.get(field)
        if value not in (None, ""):
            context[field] = value
    relation_fields = (
        ("people", "person", "people"),
        ("albums", "album_title", "albums"),
        ("keywords", "keyword", "keywords"),
        ("labels", "label", "labels"),
        ("places", "place", "places"),
    )
    for relation, field, output in relation_fields:
        values = _relationship_values(metadata, relation, field)
        if values:
            context[output] = values
    search_rows = (metadata.get("relationships") or {}).get("search_associations") or []
    search_context = []
    for item in search_rows:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category_name") or "").strip()
        value = str(item.get("content_string") or item.get("normalized_string") or "").strip()
        if category or value:
            search_context.append(" / ".join(part for part in (category, value) if part))
    if search_context:
        context["search_context"] = sorted(set(search_context))
    return context


def build_studio_workbench(
    field: list[dict[str, str]],
    preview_index: list[dict[str, str]],
    preview_root: Path,
    output: Path,
    *,
    metadata: list[dict] | None = None,
    title: str = "Photo Fieldwork Studio",
    seed: int = 0,
) -> str:
    """Build a private offline exploratory studio from verified preview evidence."""
    if not field:
        raise ValueError("studio field contains no rows")
    if output.is_symlink() or output.parent.is_symlink():
        raise ValueError("studio output and its private parent must not be symlinks")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    asset_root = output.parent / "studio-assets"
    records = verified_preview_records(field, preview_index, preview_root, asset_root)
    expected = {record["uuid"] for record in records}
    metadata_index = _metadata_by_uuid(metadata, expected)
    rows_by_uuid = {_canonical_uuid(row.get("uuid")): row for row in field}
    for record in records:
        uuid = record["uuid"]
        record["context"] = _private_context(rows_by_uuid[uuid], metadata_index.get(uuid))
        record.pop("inspection_path", None)

    studio_id = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    payload = json.dumps(records, ensure_ascii=True).replace("</", "<\\/")
    safe_title = html.escape(title.strip() or "Photo Fieldwork Studio")
    effective_seed = seed or int(studio_id[:8], 16)
    template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>__TITLE__</title>
<style>
:root { color-scheme: light; font: 14px/1.45 system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: #e9e9e4; color: #171717; }
button, input, textarea { border: 1px solid #777; border-radius: 4px; background: #fff; color: inherit; font: inherit; }
button { min-height: 38px; padding: 7px 10px; cursor: pointer; }
button:focus-visible, input:focus-visible, textarea:focus-visible { outline: 3px solid #0875b7; outline-offset: 2px; }
header { position: sticky; top: 0; z-index: 4; display: flex; align-items: center; gap: 8px; min-height: 58px; padding: 9px 12px; background: #fff; border-bottom: 1px solid #aaa; }
header strong { white-space: nowrap; }
.spacer { flex: 1; }
.segmented { display: inline-flex; }
.segmented button { border-radius: 0; margin-left: -1px; }
.segmented button:first-child { border-radius: 4px 0 0 4px; margin-left: 0; }
.segmented button:last-child { border-radius: 0 4px 4px 0; }
.segmented button[aria-pressed="true"] { background: #171717; color: #fff; }
main { display: grid; grid-template-columns: minmax(0, 1fr) 390px; min-height: calc(100vh - 58px); }
.stage { display: grid; grid-template-columns: minmax(0, 1fr); align-items: center; gap: 8px; min-width: 0; padding: 14px; background: #202020; }
.stage.compare { grid-template-columns: repeat(2, minmax(0, 1fr)); }
figure { display: grid; place-items: center; min-width: 0; margin: 0; }
figure img { display: block; max-width: 100%; max-height: calc(100vh - 90px); object-fit: contain; }
aside { padding: 16px; background: #fff; border-left: 1px solid #aaa; overflow: auto; }
.toolbar { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin-bottom: 14px; }
.status { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.status button[data-state="gather"] { border-color: #267346; }
.status button[data-state="uncertain"] { border-color: #8b6812; }
.status button[data-state="hold"] { border-color: #713d87; }
.status button[data-state="return-later"] { border-color: #28698a; }
.status button[aria-pressed="true"] { box-shadow: inset 0 0 0 2px currentColor; }
label { display: grid; gap: 4px; margin-top: 11px; color: #444; }
input, textarea { width: 100%; padding: 8px; }
textarea { min-height: 70px; resize: vertical; }
details { margin-top: 14px; border-top: 1px solid #ccc; padding-top: 10px; }
dl { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 6px; }
dt { color: #666; } dd { margin: 0; overflow-wrap: anywhere; }
#light-table { display: grid; gap: 6px; padding: 10px; background: #d2d2cc; }
body[data-density="dense"] #light-table { grid-template-columns: repeat(auto-fill, minmax(78px, 1fr)); }
body[data-density="medium"] #light-table { grid-template-columns: repeat(auto-fill, minmax(126px, 1fr)); }
body[data-density="wide"] #light-table { grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); }
#light-table button { position: relative; padding: 0; border: 3px solid transparent; aspect-ratio: 1; overflow: hidden; background: #292929; }
#light-table button.active { border-color: #0875b7; }
#light-table button.pinned { border-color: #e0b92f; }
#light-table button[data-state="hold"]::after, #light-table button[data-state="return-later"]::after, #light-table button[data-state="uncertain"]::after, #light-table button[data-state="gather"]::after { position: absolute; right: 4px; bottom: 4px; width: 10px; height: 10px; border: 2px solid #fff; border-radius: 50%; content: ""; }
#light-table button[data-state="hold"]::after { background: #713d87; }
#light-table button[data-state="return-later"]::after { background: #28698a; }
#light-table button[data-state="uncertain"]::after { background: #8b6812; }
#light-table button[data-state="gather"]::after { background: #267346; }
#light-table img { width: 100%; height: 100%; object-fit: cover; }
@media (max-width: 820px) { header { flex-wrap: wrap; } main { grid-template-columns: 1fr; } aside { border: 0; } .stage img { max-height: 58vh; } .stage.compare { grid-template-columns: 1fr; } }
</style>
</head>
<body data-density="medium">
<header>
  <button id="previous" type="button" title="Previous image" aria-label="Previous image">Previous</button>
  <strong id="position"></strong>
  <button id="next" type="button" title="Next image" aria-label="Next image">Next</button>
  <button id="chance" type="button">Chance walk</button>
  <span class="spacer"></span>
  <div class="segmented" aria-label="Light table density">
    <button type="button" data-density="dense">Dense</button>
    <button type="button" data-density="medium" aria-pressed="true">Medium</button>
    <button type="button" data-density="wide">Wide</button>
  </div>
  <button id="export" type="button">Export notebook</button>
</header>
<main>
  <section class="stage" id="stage" aria-live="polite"></section>
  <aside>
    <div class="toolbar">
      <button id="pin" type="button">Pin for comparison</button>
      <button id="clear-state" type="button">Clear studio state</button>
    </div>
    <div class="status" aria-label="Studio state">
      <button type="button" data-state="gather">Gather</button>
      <button type="button" data-state="uncertain">Uncertain</button>
      <button type="button" data-state="hold">HOLD</button>
      <button type="button" data-state="return-later">Return later</button>
    </div>
    <label>Observation<textarea id="observation"></textarea></label>
    <label>Association<textarea id="association"></textarea></label>
    <label>Question<textarea id="question"></textarea></label>
    <label>Claim candidate<textarea id="claim"></textarea></label>
    <label>Piles<input id="piles" placeholder="semicolon-separated"></label>
    <details open><summary>Encounter</summary><dl id="encounter"></dl></details>
    <details><summary>Private archive context</summary><dl id="context"></dl></details>
  </aside>
</main>
<section id="light-table" aria-label="Private studio light table"></section>
<script>
const records = __PAYLOAD__;
const studioId = "__STUDIO_ID__";
const studioSeed = __SEED__;
const storageKey = `photo-fieldwork-studio-${studioId}`;
const blankState = () => ({status:"",observation:"",association:"",question:"",claim_candidate:"",piles:"",first_seen:null,visit_count:0,last_surface:""});
let saved;
try { saved = JSON.parse(localStorage.getItem(storageKey) || "{}"); } catch (_) { saved = {}; }
saved.annotations = saved.annotations || {};
saved.session = saved.session || {encounter_counter:0,pinned_index:null,density:"medium",chance_cursor:0};
let index = 0;
let surfaceReason = "opening";
function annotation(uuid) { return saved.annotations[uuid] || blankState(); }
function persist() { localStorage.setItem(storageKey, JSON.stringify(saved)); }
function visit(position, reason) {
  index = Math.max(0, Math.min(records.length - 1, position));
  const row = records[index], state = annotation(row.uuid);
  saved.session.encounter_counter += 1;
  state.first_seen = state.first_seen || saved.session.encounter_counter;
  state.visit_count += 1;
  state.last_surface = reason;
  saved.annotations[row.uuid] = state;
  surfaceReason = reason;
  persist();
  render();
}
function seededOrder() {
  let state = studioSeed >>> 0;
  const values = records.map((_, position) => position);
  const random = () => { state ^= state << 13; state ^= state >>> 17; state ^= state << 5; return (state >>> 0) / 4294967296; };
  for (let cursor = values.length - 1; cursor > 0; cursor -= 1) {
    const swap = Math.floor(random() * (cursor + 1));
    [values[cursor], values[swap]] = [values[swap], values[cursor]];
  }
  return values;
}
const chanceOrder = seededOrder();
function setStatus(value) {
  const row = records[index], state = annotation(row.uuid);
  state.status = state.status === value ? "" : value;
  saved.annotations[row.uuid] = state;
  persist(); render();
}
function updateField(field, value) {
  const row = records[index], state = annotation(row.uuid);
  state[field] = value; saved.annotations[row.uuid] = state; persist();
}
function addDefinition(list, label, value) {
  const dt = document.createElement("dt"), dd = document.createElement("dd");
  dt.textContent = label; dd.textContent = Array.isArray(value) ? value.join("; ") : String(value || "-");
  list.append(dt, dd);
}
function figureFor(row, label) {
  const figure = document.createElement("figure"), image = document.createElement("img");
  image.src = `studio-assets/${row.image}`; image.alt = label; figure.append(image); return figure;
}
function render() {
  const row = records[index], state = annotation(row.uuid), pinned = saved.session.pinned_index;
  document.body.dataset.density = saved.session.density;
  document.getElementById("position").textContent = `${index + 1} / ${records.length}`;
  const stage = document.getElementById("stage"); stage.replaceChildren(); stage.classList.toggle("compare", pinned !== null && pinned !== index);
  stage.append(figureFor(row, "Private studio image"));
  if (pinned !== null && pinned !== index) stage.append(figureFor(records[pinned], "Pinned comparison image"));
  document.getElementById("pin").textContent = pinned === index ? "Unpin comparison" : "Pin for comparison";
  for (const field of ["observation","association","question","claim_candidate","piles"]) {
    const element = document.getElementById(field === "claim_candidate" ? "claim" : field);
    element.value = state[field] || "";
  }
  document.querySelectorAll("[data-state]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.state === state.status)));
  document.querySelectorAll("[data-density]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.density === saved.session.density)));
  const encounter = document.getElementById("encounter"); encounter.replaceChildren();
  addDefinition(encounter, "Surfaced by", surfaceReason);
  addDefinition(encounter, "First seen", state.first_seen || "-");
  addDefinition(encounter, "Visits", state.visit_count);
  addDefinition(encounter, "View", row.primary_view || row.assigned_view);
  addDefinition(encounter, "Sample", row.sampling_reason);
  const context = document.getElementById("context"); context.replaceChildren();
  const entries = Object.entries(row.context || {});
  if (!entries.length) addDefinition(context, "Context", "No context supplied");
  for (const [label, value] of entries) addDefinition(context, label.replaceAll("_", " "), value);
  document.querySelectorAll("#light-table button").forEach((button, position) => {
    button.classList.toggle("active", position === index);
    button.classList.toggle("pinned", position === pinned);
    button.dataset.state = annotation(records[position].uuid).status || "";
  });
}
document.getElementById("previous").addEventListener("click", () => visit(index - 1, "adjacent"));
document.getElementById("next").addEventListener("click", () => visit(index + 1, "adjacent"));
document.getElementById("chance").addEventListener("click", () => {
  const cursor = saved.session.chance_cursor % chanceOrder.length;
  saved.session.chance_cursor += 1; visit(chanceOrder[cursor], "chance walk");
});
document.getElementById("pin").addEventListener("click", () => {
  saved.session.pinned_index = saved.session.pinned_index === index ? null : index; persist(); render();
});
document.getElementById("clear-state").addEventListener("click", () => {
  saved.annotations[records[index].uuid] = blankState(); persist(); render();
});
document.querySelectorAll("[data-state]").forEach(button => button.addEventListener("click", () => setStatus(button.dataset.state)));
document.querySelectorAll("[data-density]").forEach(button => button.addEventListener("click", () => { saved.session.density = button.dataset.density; persist(); render(); }));
for (const [elementId, field] of [["observation","observation"],["association","association"],["question","question"],["claim","claim_candidate"],["piles","piles"]]) {
  document.getElementById(elementId).addEventListener("input", event => updateField(field, event.target.value));
}
document.addEventListener("keydown", event => {
  if (event.target.matches("input,textarea,button")) return;
  if (event.key === "ArrowLeft") visit(index - 1, "adjacent");
  if (event.key === "ArrowRight") visit(index + 1, "adjacent");
});
const table = document.getElementById("light-table");
records.forEach((row, position) => {
  const button = document.createElement("button"), image = document.createElement("img");
  button.type = "button"; button.title = `${position + 1} ${row.primary_view || row.assigned_view || ""}`;
  image.src = `studio-assets/${row.image}`; image.alt = ""; button.append(image);
  button.addEventListener("click", () => { visit(position, "light table"); scrollTo({top:0,behavior:"smooth"}); }); table.append(button);
});
document.getElementById("export").addEventListener("click", () => {
  const notebook = {
    schema_version: 1,
    purpose: "private-exploration",
    studio_id: studioId,
    source_record_count: records.length,
    evaluation_state: "not-evaluation",
    publication_state: "review-required",
    annotations: records.map(row => ({uuid:row.uuid,preview_sha256:row.inspection_sha256,...annotation(row.uuid)})),
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(notebook, null, 2) + "\\n"], {type:"application/json"}));
  const link = document.createElement("a"); link.href = url; link.download = `studio-notebook-${studioId}.json`; link.click(); URL.revokeObjectURL(url);
});
visit(0, "opening");
</script>
</body>
</html>
"""
    document = (
        template.replace("__TITLE__", safe_title)
        .replace("__PAYLOAD__", payload)
        .replace("__STUDIO_ID__", studio_id)
        .replace("__SEED__", str(effective_seed))
    )
    output.write_text(document, encoding="utf-8")
    output.chmod(0o600)
    return studio_id
