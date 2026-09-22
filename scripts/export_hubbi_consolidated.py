"""Build the single, deduplicated Volkswagen Hubbi CSV without downloading images."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audit_hubbi_consolidation import DB_PATH, list_groups, list_specs
from export_hubbi_sample import HUBBI_COLUMNS, _REAL_PART_IMAGE_HOST, build_row, load_html, parse_area_geometry
from amayama_scraper.parsing.group_detail import parse_group_detail

OUT_PATH = ROOT / "exports" / "hubbi_volkswagen_full.csv"
SAMPLE_PATH = ROOT / "exports" / "hubbi_volkswagen_full_sample.csv"
CONFLICT_PATH = ROOT / "exports" / "hubbi_volkswagen_consolidation_conflicts.json"


def squash_whitespace(value: str) -> str:
    return " ".join(value.split())


def new_piece() -> dict:
    return {
        "occurrences": 0, "applications": set(), "manufacturer_ref": set(),
        "names": Counter(), "positions": set(), "position_empty": False,
        "born_at": set(), "deprecated_at": set(), "catalog_ids": set(), "notes": set(),
        "similarity": set(), "images": Counter(),
    }


def add_row(piece: dict, row: dict[str, str]) -> None:
    piece["occurrences"] += 1
    piece["applications"].add(row["application"])
    piece["manufacturer_ref"].add(row["manufacturer_ref"])
    name = squash_whitespace(row["name"])
    if name:
        piece["names"][name] += 1
    if row["position"]:
        piece["positions"].add(row["position"])
    else:
        piece["position_empty"] = True
    for field in ("born_at", "deprecated_at", "catalog_id", "notes", "similarity"):
        if row[field]:
            piece[{"born_at": "born_at", "deprecated_at": "deprecated_at", "catalog_id": "catalog_ids", "notes": "notes", "similarity": "similarity"}[field]].add(row[field])
    image = (row["file_high"], row["file_medium"], row["file_low"], row["file_water_mark"])
    if row["file_high"].startswith(_REAL_PART_IMAGE_HOST):
        piece["images"][image] += 1


def scan_spec(spec: dict[str, str | None]) -> dict:
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    pieces: dict[tuple[str, str], dict] = {}
    groups = occurrences = skipped = 0
    for group in list_groups(connection, str(spec["stable_key"])):
        groups += 1
        html = load_html(connection, group["raw_capture_id"])
        if html is None:
            continue
        parsed = parse_group_detail(html, category_slug=group["category_slug"], group_id=group["group_id"])
        if parsed.critical_error is not None:
            continue
        area_coords, declared_sizes = parse_area_geometry(html)
        for schema in parsed.schemas:
            for part in schema.parts:
                row = build_row(
                    vehicle_model=str(spec["vehicle_model"]), spec=spec,
                    category_slug=group["category_slug"], group_id=group["group_id"],
                    schema_id=schema.schema_id, part=part, area_coords=area_coords,
                    declared_sizes=declared_sizes, materialize_images=False,
                )
                if row is None:
                    skipped += 1
                    continue
                occurrences += 1
                piece = pieces.setdefault((row["brand"], row["search_ref"]), new_piece())
                add_row(piece, row)
    connection.close()
    return {"groups": groups, "occurrences": occurrences, "skipped": skipped, "pieces": pieces}


def merge_piece(target: dict, source: dict) -> None:
    target["occurrences"] += source["occurrences"]
    target["applications"].update(source["applications"])
    target["manufacturer_ref"].update(source["manufacturer_ref"])
    target["names"].update(source["names"])
    target["positions"].update(source["positions"])
    target["position_empty"] = target["position_empty"] or source["position_empty"]
    for field in ("born_at", "deprecated_at", "catalog_ids", "notes", "similarity"):
        target[field].update(source[field])
    target["images"].update(source["images"])


def pick_name(names: Counter[str]) -> str:
    if not names:
        return ""
    return sorted(names, key=lambda value: (-names[value], -len(value), value))[0]


def pick_image(images: Counter[tuple[str, str, str, str]]) -> tuple[str, str, str, str]:
    if not images:
        return ("", "", "", "")
    return sorted(images, key=lambda value: (-images[value], value))[0]


def only_value(values: set[str]) -> str:
    return next(iter(values)) if len(values) == 1 else ""


def consolidate(brand: str, search_ref: str, piece: dict) -> tuple[dict[str, str], dict | None]:
    manufacturer_ref = only_value(piece["manufacturer_ref"])
    if not manufacturer_ref:
        raise ValueError(f"manufacturer_ref conflict for {brand}/{search_ref}")
    similarity = only_value(piece["similarity"]) or "[]"
    parsed_similarity = json.loads(similarity)
    if not isinstance(parsed_similarity, list):
        raise ValueError(f"similarity is not an array for {brand}/{search_ref}")
    image = pick_image(piece["images"])
    position = only_value(piece["positions"])
    row = {
        "manufacturer_ref": manufacturer_ref, "search_ref": search_ref, "name": pick_name(piece["names"]),
        "brand": brand, "application": "; ".join(sorted(piece["applications"])), "position": position,
        "ncm": "", "barcode": "", "gross_weight": "", "net_weight": "", "width": "", "depth": "", "height": "",
        "born_at": only_value(piece["born_at"]), "deprecated_at": only_value(piece["deprecated_at"]),
        "similarity": similarity, "notes": only_value(piece["notes"]), "catalog_id": only_value(piece["catalog_ids"]),
        "file_high": image[0], "file_medium": image[1], "file_low": image[2], "file_water_mark": image[3],
    }
    conflict = {}
    if len(piece["names"]) > 1: conflict["names"] = sorted(piece["names"])
    if len(piece["positions"]) > 1 or (piece["position_empty"] and piece["positions"]):
        conflict["positions"] = sorted(piece["positions"])
        conflict["position_partially_absent"] = piece["position_empty"]
    if len(piece["born_at"]) > 1 or len(piece["deprecated_at"]) > 1:
        conflict["periods"] = {"born_at": sorted(piece["born_at"]), "deprecated_at": sorted(piece["deprecated_at"])}
    if len(piece["catalog_ids"]) > 1: conflict["catalog_ids"] = sorted(piece["catalog_ids"])
    if len(piece["images"]) > 1:
        conflict["image_candidates"] = [
            {"file_high": value[0], "file_medium": value[1], "file_low": value[2], "file_water_mark": value[3], "occurrences": count}
            for value, count in sorted(piece["images"].items(), key=lambda item: (-item[1], item[0]))
        ]
    if len(piece["notes"]) > 1: conflict["notes"] = sorted(piece["notes"])
    return row, ({"brand": brand, "search_ref": search_ref, "occurrences": piece["occurrences"], "applications": len(piece["applications"]), **conflict} if conflict else None)


def validate(path: Path) -> dict[str, int | float]:
    with path.open("r", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != HUBBI_COLUMNS:
            raise ValueError("invalid CSV schema")
        keys = set()
        rows = image_rows = application_total = 0
        for row in reader:
            rows += 1
            key = (row["brand"], row["search_ref"])
            if key in keys: raise ValueError(f"duplicate key: {key}")
            keys.add(key)
            if not all(row[field] for field in ("manufacturer_ref", "search_ref", "name", "brand", "application")):
                raise ValueError(f"empty required field at row {rows}")
            apps = row["application"].split("; ")
            if apps != sorted(set(apps)): raise ValueError(f"non-deterministic applications at row {rows}")
            if row["position"] and re.fullmatch(r"\d+-\d+(?:-\d+)?", row["position"]): raise ValueError(f"invalid position at row {rows}")
            if not isinstance(json.loads(row["similarity"]), list): raise ValueError(f"invalid similarity at row {rows}")
            application_total += len(apps)
            image_rows += bool(row["file_high"])
    pandas_columns = list(pd.read_csv(path, nrows=100, dtype=str, keep_default_na=False).columns)
    if pandas_columns != HUBBI_COLUMNS: raise ValueError("pandas schema mismatch")
    return {"rows": rows, "applications": application_total, "image_rows": image_rows, "image_coverage": image_rows / rows if rows else 0}


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=HUBBI_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit-specs", type=int, default=None)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--sample-out", type=Path, default=SAMPLE_PATH)
    parser.add_argument("--conflicts-out", type=Path, default=CONFLICT_PATH)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
    started = time.monotonic()
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        specs = [dict(row) for row in list_specs(connection)]
    if args.limit_specs is not None:
        specs = specs[: args.limit_specs]
    pieces: dict[tuple[str, str], dict] = {}
    groups = occurrences = skipped = done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(scan_spec, spec) for spec in specs]
        for future in as_completed(futures):
            result = future.result()
            done += 1; groups += result["groups"]; occurrences += result["occurrences"]; skipped += result["skipped"]
            for key, source in result["pieces"].items():
                merge_piece(pieces.setdefault(key, new_piece()), source)
            if done % 25 == 0 or done == len(specs): print(f"CONSOLIDATE_PROGRESS specs={done}/{len(specs)} groups={groups} occurrences={occurrences}")
    rows: list[dict[str, str]] = []
    conflicts = []
    for (brand, search_ref), piece in sorted(pieces.items()):
        row, conflict = consolidate(brand, search_ref, piece)
        rows.append(row)
        if conflict: conflicts.append(conflict)
    args.sample_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.conflicts_out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.sample_out, rows[:100])
    sample_validation = validate(args.sample_out)
    write_csv(args.out, rows)
    final_validation = validate(args.out)
    conflict_report = {"policy": "consolidation policy supplied by user", "conflicting_pieces": conflicts, "count": len(conflicts)}
    args.conflicts_out.write_text(json.dumps(conflict_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {"specs": len(specs), "groups": groups, "occurrences": occurrences, "skipped": skipped, "pieces": len(rows), "reduction_fraction": 1 - len(rows) / occurrences, "sample_validation": sample_validation, "final_validation": final_validation, "conflicts": len(conflicts), "csv_bytes": args.out.stat().st_size, "conflict_bytes": args.conflicts_out.stat().st_size, "elapsed_seconds": time.monotonic() - started}
    print("CONSOLIDATION_RESULT_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
