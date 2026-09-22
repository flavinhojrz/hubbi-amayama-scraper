"""Parallel, read-only audit for the final Volkswagen Hubbi consolidation."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audit_hubbi_consolidation import CONFLICT_FIELDS, DB_PATH, OUT_PATH, list_groups, list_specs, values_summary
from export_hubbi_sample import build_row, load_html, parse_area_geometry
from amayama_scraper.parsing.group_detail import parse_group_detail


def audit_one_spec(spec: dict[str, str | None]) -> dict:
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    pieces: dict[tuple[str, str], dict] = {}
    occurrences = skipped = groups = 0
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
                key = (row["brand"], row["search_ref"])
                piece = pieces.setdefault(key, {"occurrences": 0, "applications": set(), "values": defaultdict(set)})
                piece["occurrences"] += 1
                piece["applications"].add(row["application"])
                for field in CONFLICT_FIELDS:
                    piece["values"][field].add(row[field])
    connection.close()
    return {"groups": groups, "occurrences": occurrences, "skipped": skipped, "pieces": pieces}


def merge_piece(target: dict, source: dict) -> None:
    target["occurrences"] += source["occurrences"]
    target["applications"].update(source["applications"])
    for field in CONFLICT_FIELDS:
        target["values"][field].update(source["values"][field])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        specs = [dict(row) for row in list_specs(connection)]

    pieces: dict[tuple[str, str], dict] = {}
    groups = occurrences = skipped = completed = 0
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(audit_one_spec, spec) for spec in specs]
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            groups += result["groups"]
            occurrences += result["occurrences"]
            skipped += result["skipped"]
            for key, source in result["pieces"].items():
                target = pieces.setdefault(key, {"occurrences": 0, "applications": set(), "values": defaultdict(set)})
                merge_piece(target, source)
            if completed % 25 == 0 or completed == len(specs):
                print(f"AUDIT_PROGRESS specs={completed}/{len(specs)} groups={groups} occurrences={occurrences}")

    applications = [len(piece["applications"]) for piece in pieces.values()]
    conflict_counts: dict[str, int] = {}
    conflict_samples: dict[str, list[dict]] = {}
    for field in CONFLICT_FIELDS:
        conflicts = []
        for (brand, search_ref), piece in pieces.items():
            meaningful = {value for value in piece["values"][field] if value}
            if len(meaningful) > 1:
                conflicts.append({"brand": brand, "search_ref": search_ref, "occurrences": piece["occurrences"], "applications": len(piece["applications"]), "values": values_summary(meaningful)})
        conflict_counts[field] = len(conflicts)
        conflict_samples[field] = conflicts[:20]
    report = {
        "source": "direct normalized rows from amayama.db; parallel read-only; no image downloads",
        "workers": args.workers, "specs": len(specs), "groups": groups, "occurrences": occurrences,
        "skipped_invalid_rows": skipped, "unique_brand_search_ref": len(pieces),
        "line_reduction": occurrences - len(pieces),
        "line_reduction_fraction": (occurrences - len(pieces)) / occurrences if occurrences else 0,
        "applications_per_piece": {"average": sum(applications) / len(applications) if applications else 0, "maximum": max(applications, default=0)},
        "conflict_counts_nonempty_distinct": conflict_counts,
        "position_missing_and_present": sum(bool(piece["values"]["position"] - {""}) and "" in piece["values"]["position"] for piece in pieces.values()),
        "conflict_samples": conflict_samples,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("AUDIT_RESULT_JSON=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
