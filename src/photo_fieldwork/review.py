from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .pipeline import ensure_private_directory


HOLDOUT_CONTEXT_FIELDS = (
    "sample_role",
    "estimate_included",
    "sample_seed",
    "population_count",
    "full_master_count",
    "view_population_count",
)


def read_review_sample(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if "uuid" not in (reader.fieldnames or []):
            raise ValueError("review sample lacks uuid column")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("review sample is empty")
    return rows


def _source_preview(directory: Path, uuid: str) -> Path | None:
    base = uuid.split("/", 1)[0]
    candidates = (
        directory / f"{base}_L0_001.jpg",
        directory / f"{base}.jpg",
        directory / f"{uuid.replace('/', '_')}.jpg",
    )
    return next(
        (
            path
            for path in candidates
            if path.is_file() and not path.is_symlink() and path.stat().st_size > 0
        ),
        None,
    )


def build_review_workbench(sample: list[dict[str, str]], previews: Path, output: Path) -> dict:
    """Build a private, dependency-free review surface with no network requests."""

    if not sample:
        raise ValueError("review sample is empty")
    ensure_private_directory(output.parent)
    review_assets = output.parent / "review-assets"
    ensure_private_directory(review_assets)

    records: list[dict[str, object]] = []
    for row in sample:
        uuid = str(row.get("uuid") or "").strip()
        if not uuid:
            raise ValueError("review sample contains a blank uuid")
        source = _source_preview(previews, uuid)
        relative = ""
        if source:
            copied = review_assets / f"{hashlib.sha256(uuid.encode()).hexdigest()[:24]}.jpg"
            if source.resolve() != copied.resolve():
                shutil.copy2(source, copied)
            copied.chmod(0o600)
            relative = Path(os.path.relpath(copied, output.parent)).as_posix()
        records.append(
            {
                "uuid": uuid,
                "primary_view": row.get("primary_view") or row.get("assigned_view") or "unknown",
                "score_total": row.get("score_total", ""),
                "visible_context": row.get("visible_context", ""),
                **{field: row.get(field, "") for field in HOLDOUT_CONTEXT_FIELDS},
                "image": relative,
                "available": bool(source),
            }
        )

    review_id = hashlib.sha256(
        "\n".join(str(record["uuid"]) for record in records).encode("utf-8")
    ).hexdigest()[:16]
    payload = json.dumps(records, ensure_ascii=True).replace("</", "<\\/")
    title = html.escape(f"Photo Fieldwork review {review_id}")
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none';">
<title>{title}</title>
<style>
:root {{ color-scheme: light; font: 15px/1.45 system-ui, sans-serif; }}
* {{ box-sizing: border-box; }} body {{ margin: 0; color: #181818; background: #ededeb; }}
header {{ position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 10px; padding: 10px 16px; background: #fff; border-bottom: 1px solid #bbb; }}
button, select, input {{ min-height: 38px; border: 1px solid #777; border-radius: 4px; background: #fff; color: inherit; padding: 7px 10px; }}
button:focus-visible, input:focus-visible, select:focus-visible {{ outline: 3px solid #1667b1; outline-offset: 2px; }}
button:disabled {{ opacity: .4; }} .spacer {{ flex: 1; }}
main {{ display: grid; grid-template-columns: minmax(0, 1fr) 340px; min-height: calc(100vh - 59px); }}
.stage {{ display: grid; place-items: center; min-width: 0; padding: 18px; background: #202020; }}
.stage img {{ display: block; max-width: 100%; max-height: calc(100vh - 96px); object-fit: contain; }}
.missing {{ color: #fff; border: 1px solid #888; padding: 24px; }}
aside {{ padding: 18px; background: #fff; border-left: 1px solid #bbb; overflow: auto; }}
dl {{ display: grid; grid-template-columns: 88px 1fr; gap: 8px; margin: 0 0 18px; }} dt {{ color: #666; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
.actions {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }}
.actions button[data-value="fit"] {{ border-color: #287a48; }} .actions button[data-value="reject"] {{ border-color: #9b3030; }}
.actions button[data-value="uncertain"] {{ border-color: #8c6b16; }} .actions button[data-value="hold"] {{ border-color: #60388c; }}
label {{ display: grid; gap: 5px; margin-top: 14px; }} input, select {{ width: 100%; }}
#grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 6px; padding: 10px; }}
#grid button {{ padding: 0; border: 3px solid transparent; aspect-ratio: 1; overflow: hidden; background: #333; }} #grid button.active {{ border-color: #1667b1; }} #grid img {{ width: 100%; height: 100%; object-fit: cover; }}
@media (max-width: 760px) {{ header {{ flex-wrap: wrap; }} main {{ grid-template-columns: 1fr; }} aside {{ border: 0; }} .stage img {{ max-height: 58vh; }} }}
</style>
</head>
<body>
<header><button id="previous" type="button">Previous</button><strong id="position"></strong><button id="next" type="button">Next</button><span class="spacer"></span><span id="progress"></span><button id="export" type="button">Export CSV</button></header>
<main><section class="stage" id="stage"></section><aside><dl id="metadata"></dl><div class="actions"><button type="button" data-value="fit">Fit</button><button type="button" data-value="reject">Reject</button><button type="button" data-value="uncertain">Uncertain</button><button type="button" data-value="hold">HOLD</button></div><label>Visible reason<input id="reason" autocomplete="off"></label><label>Error category<select id="error"><option>visible-fit</option><option>retrieval-mismatch</option><option>context-collapse</option><option>taxonomy-coercion</option><option>privacy-miss</option><option>relationship-loss</option><option>temporal-distortion</option><option>redundancy</option><option>aesthetic-overreach</option></select></label></aside></main>
<section id="grid" aria-label="Review sample"></section>
<script>
const records={payload}; const storageKey="photo-fieldwork-review-{review_id}"; const saved=JSON.parse(localStorage.getItem(storageKey)||"{{}}"); let index=0;
const decision=uuid=>saved[uuid]||{{judgment:"",visible_reason:"",error_category:"visible-fit"}}; const persist=()=>localStorage.setItem(storageKey,JSON.stringify(saved));
function setDecision(value){{const row=records[index];if(!row.available&&value!=="hold")return;const current=decision(row.uuid);current.judgment=value;saved[row.uuid]=current;persist();render();}}
function render(){{const row=records[index],current=decision(row.uuid);document.getElementById("position").textContent=`${{index+1}} / ${{records.length}}`;document.getElementById("progress").textContent=`${{Object.values(saved).filter(x=>x.judgment).length}} judged`;
const stage=document.getElementById("stage");stage.replaceChildren();if(row.available){{const image=document.createElement("img");image.src=row.image;image.alt="Private review image";stage.append(image);}}else{{const message=document.createElement("p");message.className="missing";message.textContent="Preview unavailable: HOLD only";stage.append(message);}}
const metadata=document.getElementById("metadata");metadata.replaceChildren();for(const [label,value] of [["UUID",row.uuid],["View",row.primary_view],["Score",row.score_total],["Visible",row.visible_context],["Sample",row.sample_role],["Decision",current.judgment||"unjudged"]]){{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=value||"-";metadata.append(dt,dd);}}
document.getElementById("reason").value=current.visible_reason||"";document.getElementById("error").value=current.error_category||"visible-fit";document.querySelectorAll(".actions button").forEach(button=>button.disabled=!row.available&&button.dataset.value!=="hold");document.querySelectorAll("#grid button").forEach((button,position)=>button.classList.toggle("active",position===index));}}
function move(delta){{index=Math.max(0,Math.min(records.length-1,index+delta));render();}} document.getElementById("previous").onclick=()=>move(-1);document.getElementById("next").onclick=()=>move(1);document.querySelectorAll(".actions button").forEach(button=>button.onclick=()=>setDecision(button.dataset.value));
document.getElementById("reason").oninput=event=>{{const row=records[index],current=decision(row.uuid);current.visible_reason=event.target.value;saved[row.uuid]=current;persist();}};document.getElementById("error").onchange=event=>{{const row=records[index],current=decision(row.uuid);current.error_category=event.target.value;saved[row.uuid]=current;persist();}};
document.addEventListener("keydown",event=>{{if(event.target.matches("input,select"))return;const key=event.key.toLowerCase();if(key==="arrowleft")move(-1);if(key==="arrowright")move(1);if(key==="f")setDecision("fit");if(key==="r")setDecision("reject");if(key==="u")setDecision("uncertain");if(key==="h")setDecision("hold");}});
const grid=document.getElementById("grid");records.forEach((row,position)=>{{const button=document.createElement("button");button.type="button";button.title=`${{position+1}} ${{row.primary_view}}`;if(row.available){{const image=document.createElement("img");image.src=row.image;image.alt="";button.append(image);}}button.onclick=()=>{{index=position;render();scrollTo({{top:0,behavior:"smooth"}});}};grid.append(button);}});
document.getElementById("export").onclick=()=>{{const fields=["uuid","primary_view","sample_role","estimate_included","sample_seed","population_count","full_master_count","view_population_count","judgment","visible_reason","safety_status","error_category","round_id","reviewer_lens"],quote=value=>`"${{String(value??"").replaceAll('"','""')}}"`,lines=[fields.join(",")];for(const row of records){{const current=decision(row.uuid),values=fields.map(field=>{{if(field==="judgment")return row.available?current.judgment:"hold";if(field==="visible_reason")return row.available?current.visible_reason:"Preview unavailable";if(field==="safety_status")return row.available?(current.judgment==="hold"?"hold":"clear"):"unavailable";if(field==="error_category")return current.error_category;if(field==="round_id")return "local-workbench";if(field==="reviewer_lens")return "human-or-delegated-review";return row[field]??"";}});lines.push(values.map(quote).join(","));}}const url=URL.createObjectURL(new Blob([lines.join("\n")+"\n"],{{type:"text/csv"}})),link=document.createElement("a");link.href=url;link.download="evaluation-reviewed.csv";link.click();URL.revokeObjectURL(url);}}; render();
</script></body></html>"""
    output.write_text(document, encoding="utf-8")
    output.chmod(0o600)
    return {
        "review_id": review_id,
        "rows": len(records),
        "available": sum(bool(record["available"]) for record in records),
        "unavailable": sum(not bool(record["available"]) for record in records),
        "output": str(output),
    }


def serve_review(directory: Path, host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("review workbench may bind only to loopback")
    if not directory.is_dir():
        raise ValueError("review directory does not exist")
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"private review workbench: http://{host}:{server.server_port}")
    server.serve_forever()
