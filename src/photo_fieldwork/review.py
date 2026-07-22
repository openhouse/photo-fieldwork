from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
from pathlib import Path

from .pipeline import file_sha256


REVIEW_FIELDS = (
    "uuid",
    "primary_view",
    "assigned_view",
    "score_total",
    "sampling_reason",
    "view_selected_count",
    "proposal_id",
    "master_sha256",
    "config_sha256",
    "round_id",
    "sample_sha256",
)

BLOCKED_SAFETY_STATES = {"hold", "needs-review", "human-needs-review"}


def _canonical_uuid(value: object) -> str:
    return str(value or "").strip().split("/", 1)[0]


def verified_preview_records(
    sample: list[dict[str, str]],
    preview_index: list[dict[str, str]],
    preview_root: Path,
    asset_root: Path,
) -> list[dict[str, str]]:
    """Copy and bind verified preview evidence through a strict field allowlist."""
    sample_ids = [_canonical_uuid(row.get("uuid")) for row in sample]
    if "" in sample_ids or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("review sample requires unique non-empty UUIDs")
    index_ids = [_canonical_uuid(row.get("uuid")) for row in preview_index]
    if "" in index_ids or len(index_ids) != len(set(index_ids)):
        raise ValueError("preview index requires unique non-empty UUIDs")
    by_id = dict(zip(index_ids, preview_index, strict=True))
    missing = sorted(set(sample_ids) - set(by_id))
    if missing:
        raise ValueError("every sampled UUID requires a verified preview index row")

    if preview_root.is_symlink():
        raise ValueError("preview root must not be a symlink")
    preview_root = preview_root.resolve(strict=True)
    if asset_root.is_symlink():
        raise ValueError("review asset root must not be a symlink")
    asset_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    asset_root.chmod(0o700)
    records: list[dict[str, str]] = []
    for row, uuid in zip(sample, sample_ids, strict=True):
        safety = str(row.get("safety_status") or "").strip().lower()
        if safety in BLOCKED_SAFETY_STATES:
            raise ValueError("blocked safety rows cannot enter the review workbench")
        index_row = by_id[uuid]
        if str(index_row.get("decode_status") or "").strip().lower() != "ok":
            raise ValueError(f"sampled UUID lacks a verified decodable preview: {uuid}")
        source_value = str(index_row.get("preview_path") or "").strip()
        source = Path(source_value)
        if not source.is_absolute() or source.is_symlink():
            raise ValueError("preview index paths must be absolute non-symlink files")
        resolved = source.resolve(strict=True)
        if preview_root not in resolved.parents or not resolved.is_file():
            raise ValueError("preview index path resolves outside the declared preview root")
        if os.stat(resolved).st_mode & 0o077:
            raise ValueError("preview permissions are broader than 0600")
        expected_digest = str(index_row.get("preview_sha256") or "").strip()
        actual_digest = file_sha256(resolved)
        if expected_digest != actual_digest:
            raise ValueError("preview digest differs from the verified index")
        suffix = resolved.suffix.lower() if resolved.suffix else ".jpg"
        asset_name = actual_digest[:24] + suffix
        copied = asset_root / asset_name
        if copied.is_symlink():
            raise ValueError("review asset destination must not be a symlink")
        shutil.copyfile(resolved, copied)
        copied.chmod(0o600)
        record = {field: str(row.get(field) or "") for field in REVIEW_FIELDS}
        record.update(
            {
                "uuid": uuid,
                "image": asset_name,
                "inspection_path": str(copied.resolve()),
                "inspection_sha256": actual_digest,
                "inspection_round_id": str(row.get("round_id") or ""),
                "inspection_sample_sha256": str(row.get("sample_sha256") or ""),
            }
        )
        records.append(record)
    return records


def build_review_workbench(
    sample: list[dict[str, str]],
    preview_index: list[dict[str, str]],
    preview_root: Path,
    output: Path,
) -> str:
    """Build a private, offline review field from verified preview evidence."""
    if output.is_symlink() or output.parent.is_symlink():
        raise ValueError("review output and its private parent must not be symlinks")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    asset_root = output.parent / "review-assets"
    records = verified_preview_records(sample, preview_index, preview_root, asset_root)
    review_id = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    payload = json.dumps(records, ensure_ascii=True).replace("</", "<\\/")
    title = html.escape(f"Photo Fieldwork review {review_id}")
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{title}</title>
<style>
:root {{ color-scheme: light; font: 15px/1.45 system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #efefeb; color: #171717; }}
button, select, input {{ min-height: 38px; border: 1px solid #777; border-radius: 4px; background: #fff; color: inherit; padding: 7px 10px; }}
button:focus-visible, input:focus-visible, select:focus-visible {{ outline: 3px solid #0868ac; outline-offset: 2px; }}
header {{ position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 10px; min-height: 58px; padding: 10px 14px; background: #fff; border-bottom: 1px solid #bbb; }}
.spacer {{ flex: 1; }}
main {{ display: grid; grid-template-columns: minmax(0, 1fr) 360px; min-height: calc(100vh - 58px); }}
.stage {{ display: grid; place-items: center; min-width: 0; padding: 18px; background: #202020; }}
.stage img {{ display: block; max-width: 100%; max-height: calc(100vh - 94px); object-fit: contain; }}
aside {{ padding: 18px; background: #fff; border-left: 1px solid #bbb; overflow: auto; }}
dl {{ display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 7px; margin: 0 0 16px; }}
dt {{ color: #666; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
.actions {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
.actions button[data-value="fit"] {{ border-color: #257344; }}
.actions button[data-value="reject"] {{ border-color: #9a3030; }}
.actions button[data-value="uncertain"] {{ border-color: #856410; }}
.actions button[data-value="hold"] {{ border-color: #693b84; }}
label {{ display: grid; gap: 5px; margin-top: 13px; }} input, select {{ width: 100%; }}
#grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 6px; padding: 10px; background: #d7d7d1; }}
#grid button {{ padding: 0; border: 3px solid transparent; aspect-ratio: 1; overflow: hidden; background: #292929; }}
#grid button.active {{ border-color: #0868ac; }} #grid img {{ width: 100%; height: 100%; object-fit: cover; }}
@media (max-width: 760px) {{ main {{ grid-template-columns: 1fr; }} aside {{ border: 0; }} .stage img {{ max-height: 60vh; }} header {{ flex-wrap: wrap; }} }}
</style>
</head>
<body>
<header>
  <button id="previous" type="button" title="Previous image">Previous</button>
  <strong id="position"></strong>
  <button id="next" type="button" title="Next image">Next</button>
  <span class="spacer"></span><span id="progress"></span>
  <button id="export" type="button">Export review CSV</button>
</header>
<main>
  <section class="stage" id="stage" aria-live="polite"></section>
  <aside>
    <dl id="metadata"></dl>
    <div class="actions">
      <button type="button" data-value="fit">Fit (F)</button>
      <button type="button" data-value="reject">Reject (R)</button>
      <button type="button" data-value="uncertain">Uncertain (U)</button>
      <button type="button" data-value="hold">HOLD (H)</button>
    </div>
    <label>Visible reason<input id="reason" autocomplete="off"></label>
    <label>Error category<select id="error">
      <option value="visible-fit">visible-fit</option><option value="retrieval-mismatch">retrieval-mismatch</option>
      <option value="context-collapse">context-collapse</option><option value="taxonomy-coercion">taxonomy-coercion</option>
      <option value="privacy-miss">privacy-miss</option><option value="relationship-loss">relationship-loss</option>
      <option value="temporal-distortion">temporal-distortion</option><option value="redundancy">redundancy</option>
      <option value="aesthetic-overreach">aesthetic-overreach</option>
    </select></label>
    <label>Reviewer name<input id="actor" autocomplete="name"></label>
    <label>Review authority<select id="lens"><option value="">Choose authority</option><option value="human-review">Human review</option><option value="delegated-editorial-inference">Delegated editorial inference</option></select></label>
  </aside>
</main>
<section id="grid" aria-label="Review sample"></section>
<script>
const records = {payload};
const storageKey = "photo-fieldwork-review-{review_id}";
const saved = JSON.parse(localStorage.getItem(storageKey) || "{{}}");
let index = 0;
const decision = uuid => saved[uuid] || {{judgment:"",visible_reason:"",error_category:"visible-fit"}};
function persist() {{ localStorage.setItem(storageKey, JSON.stringify(saved)); }}
function setDecision(value) {{ const row=records[index]; const current=decision(row.uuid); current.judgment=value; saved[row.uuid]=current; persist(); render(); }}
function render() {{
  const row=records[index], current=decision(row.uuid);
  document.getElementById("position").textContent=`${{index+1}} / ${{records.length}}`;
  document.getElementById("progress").textContent=`${{Object.values(saved).filter(value=>value.judgment).length}} judged`;
  const stage=document.getElementById("stage"); stage.replaceChildren(); const image=document.createElement("img"); image.src=`review-assets/${{row.image}}`; image.alt="Private review image"; stage.append(image);
  const metadata=document.getElementById("metadata"); metadata.replaceChildren();
  for(const [label,value] of [["UUID",row.uuid],["View",row.primary_view],["Score",row.score_total],["Sample",row.sampling_reason],["Decision",current.judgment||"unjudged"]]){{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=value||"-";metadata.append(dt,dd);}}
  document.getElementById("reason").value=current.visible_reason||""; document.getElementById("error").value=current.error_category||"visible-fit";
  document.querySelectorAll("#grid button").forEach((button,position)=>button.classList.toggle("active",position===index));
}}
function move(delta) {{ index=Math.max(0,Math.min(records.length-1,index+delta)); render(); }}
document.getElementById("previous").addEventListener("click",()=>move(-1)); document.getElementById("next").addEventListener("click",()=>move(1));
document.querySelectorAll(".actions button").forEach(button=>button.addEventListener("click",()=>setDecision(button.dataset.value)));
document.getElementById("reason").addEventListener("input",event=>{{const row=records[index],current=decision(row.uuid);current.visible_reason=event.target.value;saved[row.uuid]=current;persist();}});
document.getElementById("error").addEventListener("change",event=>{{const row=records[index],current=decision(row.uuid);current.error_category=event.target.value;saved[row.uuid]=current;persist();}});
document.addEventListener("keydown",event=>{{if(event.target.matches("input,select"))return;const key=event.key.toLowerCase();if(key==="arrowleft")move(-1);if(key==="arrowright")move(1);if(key==="f")setDecision("fit");if(key==="r")setDecision("reject");if(key==="u")setDecision("uncertain");if(key==="h")setDecision("hold");}});
const grid=document.getElementById("grid"); records.forEach((row,position)=>{{const button=document.createElement("button"),image=document.createElement("img");button.type="button";button.title=`${{position+1}} ${{row.primary_view}}`;image.src=`review-assets/${{row.image}}`;image.alt="";button.append(image);button.addEventListener("click",()=>{{index=position;render();scrollTo({{top:0,behavior:"smooth"}});}});grid.append(button);}});
document.getElementById("export").addEventListener("click",()=>{{
  const actor=document.getElementById("actor").value.trim(), lens=document.getElementById("lens").value;
  const incomplete=records.filter(row=>!decision(row.uuid).judgment||!decision(row.uuid).visible_reason.trim());
  if(!actor||!lens||incomplete.length){{alert("Name the reviewer, choose review authority, and judge every row with a visible reason before export.");return;}}
  const fields=["uuid","primary_view","assigned_view","proposal_id","master_sha256","config_sha256","view_selected_count","judgment","visible_reason","evaluation_note","error_category","round_id","reviewer_actor","reviewer_lens","sample_sha256","inspection_path","inspection_sha256","inspection_round_id","inspection_sample_sha256","safety_status","hidden","missing"];
  const quote=value=>`"${{String(value??"").replaceAll('"','""')}}"`; const lines=[fields.join(",")];
  for(const row of records){{const current=decision(row.uuid);const safety=current.judgment==="hold"?"hold":lens==="human-review"?"clear":"human-needs-review";const values=fields.map(field=>{{if(field==="judgment")return current.judgment;if(field==="visible_reason")return current.visible_reason;if(field==="evaluation_note")return "";if(field==="error_category")return current.error_category;if(field==="reviewer_actor")return actor;if(field==="reviewer_lens")return lens;if(field==="safety_status")return safety;if(field==="hidden"||field==="missing")return "false";return row[field]??"";}});lines.push(values.map(quote).join(","));}}
  const url=URL.createObjectURL(new Blob([lines.join("\\n")+"\\n"],{{type:"text/csv"}})),link=document.createElement("a");link.href=url;link.download="evaluation-reviewed.csv";link.click();URL.revokeObjectURL(url);
}});
render();
</script>
</body>
</html>
"""
    output.write_text(document, encoding="utf-8")
    output.chmod(0o600)
    return review_id
