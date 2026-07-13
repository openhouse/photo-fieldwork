#!/usr/bin/env python3
"""Render private contact sheets for a stratified evaluation CSV."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


def preview_path(directories: list[Path], uuid: str) -> Path | None:
    base = uuid.split("/", 1)[0]
    for directory in directories:
        candidates = [directory / f"{base}_L0_001.jpg", directory / f"{base}.jpg", directory / f"{uuid.replace('/', '_')}.jpg"]
        found = next((path for path in candidates if path.exists()), None)
        if found:
            return found
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--previews", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cell-width", type=int, default=360)
    parser.add_argument("--cell-height", type=int, default=310)
    args = parser.parse_args()

    with args.sample.open(newline="", encoding="utf-8-sig") as handle:
        records = list(csv.DictReader(handle))
    args.output.mkdir(parents=True, exist_ok=True)
    per_page = args.columns * args.rows
    pages = math.ceil(len(records) / per_page)
    font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=12)
    manifest_rows = []

    for page_index in range(pages):
        batch = records[page_index * per_page : (page_index + 1) * per_page]
        canvas = Image.new("RGB", (args.columns * args.cell_width, args.rows * args.cell_height), "#f4f4f1")
        draw = ImageDraw.Draw(canvas)
        for index, record in enumerate(batch):
            x = (index % args.columns) * args.cell_width
            y = (index // args.columns) * args.cell_height
            path = preview_path(args.previews, record["uuid"])
            preview_status = "available" if path else "unavailable"
            image_box = (x + 8, y + 8, x + args.cell_width - 8, y + args.cell_height - 62)
            if path:
                try:
                    with Image.open(path) as source:
                        image = ImageOps.exif_transpose(source).convert("RGB")
                        image.thumbnail((args.cell_width - 16, args.cell_height - 70))
                        px = x + (args.cell_width - image.width) // 2
                        py = y + 8 + (args.cell_height - 70 - image.height) // 2
                        canvas.paste(image, (px, py))
                except (UnidentifiedImageError, OSError):
                    preview_status = "corrupt"
                    draw.rectangle(image_box, outline="#a33", width=2)
                    draw.text((x + 18, y + 110), "PREVIEW CORRUPT", fill="#a33", font=font)
            else:
                draw.rectangle(image_box, outline="#a33", width=2)
                draw.text((x + 18, y + 110), "PREVIEW UNAVAILABLE", fill="#a33", font=font)
            view = record.get("primary_view") or record.get("assigned_bucket") or "?"
            score = record.get("score_total") or record.get("editorial_score") or "?"
            draw.text((x + 10, y + args.cell_height - 51), f"{record['uuid'][:12]}  view {view}", fill="#111", font=font)
            draw.text((x + 10, y + args.cell_height - 29), f"score {score}", fill="#444", font=small)
            draw.rectangle((x, y, x + args.cell_width - 1, y + args.cell_height - 1), outline="#bbb", width=1)
            manifest_rows.append(
                {
                    "page": page_index + 1,
                    "row": index // args.columns + 1,
                    "column": index % args.columns + 1,
                    "uuid": record["uuid"],
                    "proposal_id": record.get("proposal_id", ""),
                    "assigned_view": view,
                    "safety_status": record.get("safety_status", ""),
                    "sampling_reason": record.get("sampling_reason", ""),
                    "preview_status": preview_status,
                    "preview_path": str(path) if path else "",
                }
            )
        output = args.output / f"contact-sheet-{page_index + 1:02d}.jpg"
        canvas.save(output, "JPEG", quality=88)
        print(output)
    manifest_path = args.manifest or args.output / "contact-sheet-index.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        fields = list(manifest_rows[0]) if manifest_rows else ["page", "row", "column", "uuid"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(manifest_path)


if __name__ == "__main__":
    main()
