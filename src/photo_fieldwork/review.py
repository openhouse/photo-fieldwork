from __future__ import annotations

import hashlib
import html
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def preview_name(uuid: str) -> str:
    return f"{uuid.replace('/', '_')}.jpg"


def build_review_workbench(sample: list[dict[str, str]], previews: Path, output: Path) -> None:
    """Build a private, dependency-free review surface with no external requests."""
    records = []
    for row in sample:
        image_path = previews / preview_name(row["uuid"])
        relative = os.path.relpath(image_path, output.parent)
        records.append(
            {
                "uuid": row["uuid"],
                "primary_view": row.get("primary_view", "unknown"),
                "score_total": row.get("score_total", ""),
                "visible_context": row.get("visible_context", ""),
                "sample_role": row.get("sample_role", "working-round"),
                "image": Path(relative).as_posix(),
                "available": image_path.exists(),
            }
        )
    review_id = hashlib.sha256(
        "\n".join(record["uuid"] for record in records).encode()
    ).hexdigest()[:16]
    payload = json.dumps(records, ensure_ascii=True).replace("</", "<\\/")
    title = html.escape(f"Photo Fieldwork review {review_id}")
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' data: blob:; img-src 'self' data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none';">
<title>{title}</title>
<style>
:root {{ color-scheme: light; font: 15px/1.4 system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f5f5f2; color: #171717; }}
header {{ position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: #fff; border-bottom: 1px solid #c9c9c3; }}
button, select, input {{ min-height: 36px; border: 1px solid #8a8a84; border-radius: 4px; background: #fff; color: inherit; padding: 6px 10px; }}
button:focus-visible, input:focus-visible, select:focus-visible {{ outline: 3px solid #1468c4; outline-offset: 2px; }}
.spacer {{ flex: 1; }}
main {{ display: grid; grid-template-columns: minmax(0, 1fr) 340px; min-height: calc(100vh - 58px); }}
.stage {{ display: grid; place-items: center; min-width: 0; padding: 18px; background: #222; }}
.stage img {{ display: block; max-width: 100%; max-height: calc(100vh - 96px); object-fit: contain; }}
.missing {{ color: #fff; border: 1px solid #777; padding: 24px; }}
aside {{ padding: 18px; background: #fff; border-left: 1px solid #c9c9c3; overflow: auto; }}
dl {{ display: grid; grid-template-columns: 92px 1fr; gap: 8px; margin: 0 0 18px; }}
dt {{ color: #666; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
.actions {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }}
.actions button[data-value="fit"] {{ border-color: #287a48; }}
.actions button[data-value="reject"] {{ border-color: #9b3030; }}
.actions button[data-value="uncertain"] {{ border-color: #8c6b16; }}
.actions button[data-value="hold"] {{ border-color: #60388c; }}
label {{ display: grid; gap: 5px; margin-top: 14px; }}
input {{ width: 100%; }}
#grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 6px; padding: 10px; background: #deded8; }}
#grid button {{ padding: 0; border: 3px solid transparent; aspect-ratio: 1; overflow: hidden; background: #333; }}
#grid button.active {{ border-color: #1468c4; }}
#grid img {{ width: 100%; height: 100%; object-fit: cover; }}
@media (max-width: 760px) {{ main {{ grid-template-columns: 1fr; }} aside {{ border: 0; }} .stage img {{ max-height: 62vh; }} }}
</style>
</head>
<body>
<header>
  <button id="previous" type="button" title="Previous image">Previous</button>
  <strong id="position"></strong>
  <button id="next" type="button" title="Next image">Next</button>
  <span class="spacer"></span>
  <span id="progress"></span>
  <button id="export" type="button">Export review CSV</button>
</header>
<main>
  <section class="stage" id="stage"></section>
  <aside>
    <dl id="metadata"></dl>
    <div class="actions">
      <button type="button" data-value="fit">Fit (F)</button>
      <button type="button" data-value="reject">Reject (R)</button>
      <button type="button" data-value="uncertain">Uncertain (U)</button>
      <button type="button" data-value="hold">HOLD (H)</button>
    </div>
    <label>Visible reason<input id="reason" autocomplete="off"></label>
    <label>Error category
      <select id="error">
        <option value="visible-fit">visible-fit</option>
        <option value="retrieval-mismatch">retrieval-mismatch</option>
        <option value="context-collapse">context-collapse</option>
        <option value="taxonomy-coercion">taxonomy-coercion</option>
        <option value="privacy-miss">privacy-miss</option>
        <option value="relationship-loss">relationship-loss</option>
        <option value="temporal-distortion">temporal-distortion</option>
        <option value="redundancy">redundancy</option>
        <option value="aesthetic-overreach">aesthetic-overreach</option>
      </select>
    </label>
  </aside>
</main>
<section id="grid" aria-label="Review sample"></section>
<script>
const records = {payload};
const storageKey = "photo-fieldwork-review-{review_id}";
const saved = JSON.parse(localStorage.getItem(storageKey) || "{{}}");
let index = 0;
const decision = uuid => saved[uuid] || {{judgment:"", visible_reason:"", error_category:"visible-fit"}};
function persist() {{ localStorage.setItem(storageKey, JSON.stringify(saved)); }}
function setDecision(value) {{
  const row = records[index]; const current = decision(row.uuid);
  current.judgment = value; saved[row.uuid] = current; persist(); render();
}}
function render() {{
  const row = records[index]; const current = decision(row.uuid);
  document.getElementById("position").textContent = `${{index + 1}} / ${{records.length}}`;
  document.getElementById("progress").textContent = `${{Object.values(saved).filter(x => x.judgment).length}} judged`;
  const stage = document.getElementById("stage"); stage.replaceChildren();
  if (row.available) {{ const image = document.createElement("img"); image.src = row.image; image.alt = "Private review image"; stage.append(image); }}
  else {{ const message = document.createElement("p"); message.className = "missing"; message.textContent = "Preview unavailable"; stage.append(message); }}
  const metadata = document.getElementById("metadata"); metadata.replaceChildren();
  for (const [label, value] of [["UUID",row.uuid],["View",row.primary_view],["Score",row.score_total],["Visible",row.visible_context],["Sample",row.sample_role],["Decision",current.judgment || "unjudged"]]) {{
    const dt=document.createElement("dt"); dt.textContent=label; const dd=document.createElement("dd"); dd.textContent=value || "-"; metadata.append(dt,dd);
  }}
  document.getElementById("reason").value = current.visible_reason || "";
  document.getElementById("error").value = current.error_category || "visible-fit";
  document.querySelectorAll("#grid button").forEach((button, position) => button.classList.toggle("active", position === index));
}}
function move(delta) {{ index = Math.max(0, Math.min(records.length - 1, index + delta)); render(); }}
document.getElementById("previous").addEventListener("click", () => move(-1));
document.getElementById("next").addEventListener("click", () => move(1));
document.querySelectorAll(".actions button").forEach(button => button.addEventListener("click", () => setDecision(button.dataset.value)));
document.getElementById("reason").addEventListener("input", event => {{ const row=records[index]; const current=decision(row.uuid); current.visible_reason=event.target.value; saved[row.uuid]=current; persist(); }});
document.getElementById("error").addEventListener("change", event => {{ const row=records[index]; const current=decision(row.uuid); current.error_category=event.target.value; saved[row.uuid]=current; persist(); }});
document.addEventListener("keydown", event => {{
  if (event.target.matches("input,select")) return;
  const key=event.key.toLowerCase(); if (key==="arrowleft") move(-1); if (key==="arrowright") move(1);
  if (key==="f") setDecision("fit"); if (key==="r") setDecision("reject"); if (key==="u") setDecision("uncertain"); if (key==="h") setDecision("hold");
}});
const grid=document.getElementById("grid"); records.forEach((row, position) => {{ const button=document.createElement("button"); button.type="button"; button.title=`${{position+1}} ${{row.primary_view}}`; if(row.available){{const image=document.createElement("img");image.src=row.image;image.alt="";button.append(image);}} button.addEventListener("click",()=>{{index=position;render();scrollTo({{top:0,behavior:"smooth"}});}});grid.append(button); }});
document.getElementById("export").addEventListener("click", () => {{
  const fields=["uuid","primary_view","judgment","visible_reason","safety_status","error_category","round_id","reviewer_lens"];
  const quote=value => `"${{String(value ?? "").replaceAll('"','""')}}"`;
  const lines=[fields.join(",")]; for(const row of records){{const current=decision(row.uuid);lines.push([row.uuid,row.primary_view,current.judgment,current.visible_reason,current.judgment==="hold"?"hold":"clear",current.error_category,"local-workbench","human-or-delegated-review"].map(quote).join(","));}}
  const url=URL.createObjectURL(new Blob([lines.join("\\n")+"\\n"],{{type:"text/csv"}})); const link=document.createElement("a");link.href=url;link.download="evaluation-reviewed.csv";link.click();URL.revokeObjectURL(url);
}});
render();
</script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def serve_review(directory: Path, host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("review workbench may bind only to loopback")
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"private review workbench: http://{host}:{server.server_port}")
    server.serve_forever()
