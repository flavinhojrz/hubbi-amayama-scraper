"""Read-only audit of the direct Volkswagen Hubbi consolidation input."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from export_hubbi_sample import build_row, load_html, parse_area_geometry
from amayama_scraper.parsing.group_detail import parse_group_detail

DB_PATH = ROOT / "amayama.db"
OUT_PATH = ROOT / "exports" / "hubbi_volkswagen_consolidation_audit.json"
CONFLICT_FIELDS = (
    "manufacturer_ref", "name", "position", "born_at", "deprecated_at", "catalog_id",
    "file_high", "notes", "similarity",
)


def list_specs(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT DISTINCT s.stable_key, s.vehicle_model, s.model_code, s.amayama_catalog_id,
               s.production_period_raw, s.production_start, s.production_end, s.grade, s.configuration
        FROM spec_registry s
        WHERE s.manufacturer = 'VOLKSWAGEN'
          AND EXISTS (SELECT 1 FROM checkpoint_entry ce WHERE ce.spec_key=s.stable_key AND ce.status='ACCEPTED')
        ORDER BY s.vehicle_model, s.market, s.model_code, s.stable_key
        """
    ).fetchall()


def list_groups(connection: sqlite3.Connection, spec_key: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT DISTINCT category_slug, group_id, raw_capture_id
        FROM checkpoint_entry
        WHERE spec_key=? AND status='ACCEPTED'
        ORDER BY category_slug, group_id
        """,
        (spec_key,),
    ).fetchall()


def values_summary(values: set[str]) -> list[str]:
    return sorted(values)[:8]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--limit-specs", type=int, default=None)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    specs = list_specs(connection)
    if args.limit_specs is not None:
        specs = specs[: args.limit_specs]
    pieces: dict[tuple[str, str], dict] = {}
    occurrences = 0
    skipped = 0
    groups = 0

    for spec_number, spec in enumerate(specs, start=1):
        if spec_number % 50 == 0 or spec_number == len(specs):
            print(f"AUDIT_PROGRESS specs={spec_number}/{len(specs)} groups={groups} occurrences={occurrences}")
        for group in list_groups(connection, spec["stable_key"]):
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
                        vehicle_model=spec["vehicle_model"], spec=spec,
                        category_slug=group["category_slug"], group_id=group["group_id"],
                        schema_id=schema.schema_id, part=part, area_coords=area_coords,
                        declared_sizes=declared_sizes, materialize_images=False,
                    )
                    if row is None:
                        skipped += 1
                        continue
                    occurrences += 1
                    key = (row["brand"], row["search_ref"])
                    piece = pieces.setdefault(
                        key,
                        {"occurrences": 0, "applications": set(), "values": defaultdict(set)},
                    )
                    piece["occurrences"] += 1
                    piece["applications"].add(row["application"])
                    for field in CONFLICT_FIELDS:
                        piece["values"][field].add(row[field])

    applications_per_piece = [len(piece["applications"]) for piece in pieces.values()]
    conflict_counts: dict[str, int] = {}
    conflict_samples: dict[str, list[dict]] = {}
    for field in CONFLICT_FIELDS:
        conflicts = []
        for (brand, search_ref), piece in pieces.items():
            values = piece["values"][field]
            meaningful = {value for value in values if value}
            if len(meaningful) > 1:
                conflicts.append({
                    "brand": brand, "search_ref": search_ref, "occurrences": piece["occurrences"],
                    "applications": len(piece["applications"]), "values": values_summary(meaningful),
                })
        conflict_counts[field] = len(conflicts)
        conflict_samples[field] = conflicts[:20]

    position_missing_and_present = sum(
        bool(piece["values"]["position"] - {""}) and "" in piece["values"]["position"]
        for piece in pieces.values()
    )
    report = {
        "source": "direct normalized rows from amayama.db; no image materialization or downloads",
        "specs": len(specs), "groups": groups, "occurrences": occurrences, "skipped_invalid_rows": skipped,
        "unique_brand_search_ref": len(pieces),
        "line_reduction": occurrences - len(pieces),
        "line_reduction_fraction": (occurrences - len(pieces)) / occurrences if occurrences else 0,
        "applications_per_piece": {
            "average": sum(applications_per_piece) / len(applications_per_piece) if applications_per_piece else 0,
            "maximum": max(applications_per_piece, default=0),
        },
        "conflict_counts_nonempty_distinct": conflict_counts,
        "position_missing_and_present": position_missing_and_present,
        "conflict_samples": conflict_samples,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("AUDIT_RESULT_JSON=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
