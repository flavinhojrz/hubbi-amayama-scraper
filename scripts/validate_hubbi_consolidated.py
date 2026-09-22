"""Read-only final validation for the consolidated Volkswagen Hubbi CSV."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "exports" / "hubbi_volkswagen_full.csv"
CONFLICT_PATH = ROOT / "exports" / "hubbi_volkswagen_consolidation_conflicts.json"
SAMPLE_PATH = ROOT / "exports" / "hubbi_volkswagen_final_sample.csv"
REPORT_PATH = ROOT / "exports" / "hubbi_volkswagen_validation_report.json"
COLUMNS = [
    "manufacturer_ref", "search_ref", "name", "brand", "application", "position", "ncm", "barcode",
    "gross_weight", "net_weight", "width", "depth", "height", "born_at", "deprecated_at", "similarity",
    "notes", "catalog_id", "file_high", "file_medium", "file_low", "file_water_mark",
]
VALID_POSITIONS = {"", "DIANTEIRO", "TRASEIRO", "ESQUERDO", "DIREITO", "DIANTEIRO ESQUERDO", "DIANTEIRO DIREITO", "TRASEIRO ESQUERDO", "TRASEIRO DIREITO", "INTERNO", "EXTERNO"}
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def deterministic_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    def app_count(row: dict[str, str]) -> int: return len(row["application"].split("; "))
    selected: dict[tuple[str, str], dict[str, str]] = {}
    def choose(candidates: list[dict[str, str]], count: int) -> None:
        added = 0
        for row in sorted(candidates, key=lambda r: (hashlib.sha1(r["search_ref"].encode()).hexdigest(), r["search_ref"])):
            if len(selected) >= 200: return
            key = (row["brand"], row["search_ref"])
            if key not in selected:
                selected[key] = row
                added += 1
            if added >= count: return
    choose([r for r in rows if app_count(r) == 1], 30)
    choose(sorted(rows, key=lambda r: (-app_count(r), r["search_ref"]))[:50], 50)
    choose([r for r in rows if r["file_high"]], 40)
    choose([r for r in rows if not any(r[f] for f in ("file_high", "file_medium", "file_low", "file_water_mark"))], 30)
    for position in sorted(VALID_POSITIONS - {""}): choose([r for r in rows if r["position"] == position], 10)
    choose(rows, 200)
    return list(selected.values())[:200]


def main() -> None:
    report: dict = {"files": {"csv": str(CSV_PATH), "conflicts": str(CONFLICT_PATH)}}
    required_empty = Counter()
    positions = Counter()
    image_fields = Counter()
    malformed_urls = Counter()
    file_inconsistencies = 0
    application_empty = application_duplicate = separator_inconsistent = 0
    application_counts: list[int] = []
    multi_examples: list[dict] = []
    invalid_positions: list[dict] = []
    invalid_similarity = similarity_not_array = control_rows = malformed_rows = 0
    period_out_of_range: list[dict] = []
    period_inverted: list[dict] = []
    duplicate_keys = 0
    keys: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []

    with CSV_PATH.open("r", encoding="utf-8", newline="") as source:
        raw = csv.reader(source)
        header = next(raw, None)
        report["schema"] = {"columns": header, "column_count": len(header or []), "matches_expected": header == COLUMNS, "forbidden_present": [x for x in ("image_part_number", "marked_image_filename") if x in (header or [])]}
        for row_number, raw_row in enumerate(raw, start=2):
            if len(raw_row) != len(COLUMNS): malformed_rows += 1
    with CSV_PATH.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        for line_number, row in enumerate(reader, start=2):
            rows.append(row)
            key = (row["brand"], row["search_ref"])
            if key in keys: duplicate_keys += 1
            keys.add(key)
            for field in ("manufacturer_ref", "search_ref", "name", "brand"):
                required_empty[field] += not bool(row[field])
            if row["brand"] != "VOLKSWAGEN": required_empty["brand_not_volkswagen"] += 1
            normalized = re.sub(r"[^A-Z0-9]", "", row["manufacturer_ref"].upper()).lstrip("0") or re.sub(r"[^A-Z0-9]", "", row["manufacturer_ref"].upper())
            if row["search_ref"] != normalized: required_empty["search_ref_not_normalized"] += 1
            application_empty += not bool(row["application"])
            apps = row["application"].split("; ") if row["application"] else []
            application_counts.append(len(apps))
            application_duplicate += len(apps) != len(set(apps))
            separator_inconsistent += bool(row["application"]) and ";" in row["application"] and "; " not in row["application"]
            if len(apps) > 1 and len(multi_examples) < 20:
                multi_examples.append({"oem": row["manufacturer_ref"], "applications": len(apps), "examples": apps[:3]})
            positions[row["position"]] += 1
            if row["position"] not in VALID_POSITIONS or re.fullmatch(r"\d+(?:-\d+)+", row["position"]): invalid_positions.append({"line": line_number, "value": row["position"]})
            for field in ("born_at", "deprecated_at"):
                value = row[field]
                if value and (not value.isdigit() or not 1900 <= int(value) <= 2030): period_out_of_range.append({"line": line_number, "field": field, "value": value})
            if row["born_at"] and row["deprecated_at"] and row["born_at"] > row["deprecated_at"]: period_inverted.append({"line": line_number, "born_at": row["born_at"], "deprecated_at": row["deprecated_at"]})
            try:
                value = json.loads(row["similarity"])
                similarity_not_array += not isinstance(value, list)
            except json.JSONDecodeError: invalid_similarity += 1
            for field in ("file_high", "file_medium", "file_low", "file_water_mark"):
                image_fields[field] += bool(row[field])
                if row[field] and not is_valid_url(row[field]): malformed_urls[field] += 1
            file_inconsistencies += bool(any(row[f] for f in ("file_medium", "file_low", "file_water_mark")) and not row["file_high"])
            control_rows += any(CONTROL.search(value or "") for value in row.values())

    # Full pandas parse independently verifies decoding and row structure.
    pandas_rows = sum(len(chunk) for chunk in pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False, chunksize=100_000, on_bad_lines="error"))
    with CONFLICT_PATH.open("r", encoding="utf-8") as source:
        conflicts = json.load(source)
    conflict_counts = Counter()
    policy_mismatches = []
    by_key = {(r["brand"], r["search_ref"]): r for r in rows}
    for conflict in conflicts["conflicting_pieces"]:
        for field in ("names", "positions", "periods", "catalog_ids", "image_candidates", "notes"):
            conflict_counts[field] += field in conflict
        row = by_key[(conflict["brand"], conflict["search_ref"])]
        if "positions" in conflict and len(conflict["positions"]) > 1 and row["position"]: policy_mismatches.append({"key": conflict["search_ref"], "field": "position", "actual": row["position"]})
        if "periods" in conflict:
            for field in ("born_at", "deprecated_at"):
                if len(conflict["periods"][field]) > 1 and row[field]: policy_mismatches.append({"key": conflict["search_ref"], "field": field, "actual": row[field]})
        if "catalog_ids" in conflict and row["catalog_id"]: policy_mismatches.append({"key": conflict["search_ref"], "field": "catalog_id", "actual": row["catalog_id"]})
        if "notes" in conflict and row["notes"]: policy_mismatches.append({"key": conflict["search_ref"], "field": "notes", "actual": row["notes"]})
        if "image_candidates" in conflict:
            chosen = sorted(conflict["image_candidates"], key=lambda item: (-item["occurrences"], item["file_high"], item["file_medium"], item["file_low"], item["file_water_mark"]))[0]
            if any(row[field] != chosen[field] for field in ("file_high", "file_medium", "file_low", "file_water_mark")): policy_mismatches.append({"key": conflict["search_ref"], "field": "image"})

    sample = deterministic_rows(rows)
    with SAMPLE_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=COLUMNS)
        writer.writeheader(); writer.writerows(sample)
    report.update({
        "rows": len(rows), "unique_brand_search_ref": len(keys), "duplicate_keys": duplicate_keys,
        "required_empty": dict(required_empty), "application": {"empty": application_empty, "duplicate_cells": application_duplicate, "separator_inconsistent": separator_inconsistent, "total_unique_applications": sum(application_counts), "average": sum(application_counts) / len(application_counts), "maximum": max(application_counts), "multi_application_examples": multi_examples},
        "position": {"distinct_counts": dict(sorted(positions.items())), "filled": len(rows) - positions[""], "empty": positions[""], "invalid": len(invalid_positions), "invalid_examples": invalid_positions[:20]},
        "periods": {"born_filled": sum(bool(r["born_at"]) for r in rows), "born_empty": sum(not r["born_at"] for r in rows), "deprecated_filled": sum(bool(r["deprecated_at"]) for r in rows), "deprecated_empty": sum(not r["deprecated_at"] for r in rows), "out_of_range": period_out_of_range[:100], "born_after_deprecated": period_inverted[:100]},
        "similarity": {"invalid_json": invalid_similarity, "not_array": similarity_not_array},
        "images": {**dict(image_fields), "without_any": sum(not any(r[f] for f in ("file_high", "file_medium", "file_low", "file_water_mark")) for r in rows), "coverage": image_fields["file_high"] / len(rows), "malformed_urls": dict(malformed_urls), "inconsistent_fields": file_inconsistencies},
        "conflicts": {"declared": conflicts["count"], **dict(conflict_counts), "policy_mismatches": policy_mismatches[:100], "policy_mismatch_count": len(policy_mismatches)},
        "csv": {"pandas_rows": pandas_rows, "malformed_rows": malformed_rows, "control_character_rows": control_rows, "bytes": CSV_PATH.stat().st_size},
        "artifacts": {"conflict_bytes": CONFLICT_PATH.stat().st_size, "sample_rows": len(sample), "sample_bytes": SAMPLE_PATH.stat().st_size},
    })
    report["status"] = "OK" if not any((not report["schema"]["matches_expected"], report["duplicate_keys"], malformed_rows, sum(required_empty.values()), application_empty, application_duplicate, invalid_positions, invalid_similarity, similarity_not_array, malformed_urls, file_inconsistencies, control_rows, policy_mismatches)) else "FALHOU"
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "rows": report["rows"], "duplicates": duplicate_keys, "sample": len(sample)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
