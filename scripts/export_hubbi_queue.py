"""Run the Volkswagen Hubbi export queue serially with resumable progress."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from export_hubbi_sample import HUBBI_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "amayama.db"
EXPORTS_DIR = ROOT / "exports"
PROGRESS_PATH = EXPORTS_DIR / "export_progress.json"
VALID_POSITIONS = {
    "", "DIANTEIRO", "TRASEIRO", "ESQUERDO", "DIREITO", "DIANTEIRO ESQUERDO",
    "DIANTEIRO DIREITO", "TRASEIRO ESQUERDO", "TRASEIRO DIREITO", "INTERNO", "EXTERNO",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def load_progress(models: list[str]) -> dict:
    if PROGRESS_PATH.exists():
        progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    else:
        progress = {"manufacturer": "VOLKSWAGEN", "models": {}}
    entries = progress.setdefault("models", {})
    for model in models:
        entries.setdefault(model, {"status": "PENDING", "row_count": 0, "csv_path": None})
    return progress


def save_progress(progress: dict) -> None:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    temporary = PROGRESS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(PROGRESS_PATH)


def validate_csv(csv_path: Path) -> dict:
    with csv_path.open("r", newline="", encoding="utf-8") as source:
        reader = csv.reader(source)
        header = next(reader, None)
        if header != HUBBI_COLUMNS:
            raise ValueError(f"schema inválido: {header}")
        malformed = sum(1 for row in reader if len(row) != len(HUBBI_COLUMNS))
    if malformed:
        raise ValueError(f"{malformed} linhas malformadas")

    pandas_header = pd.read_csv(csv_path, nrows=100, dtype=str, keep_default_na=False)
    if list(pandas_header.columns) != HUBBI_COLUMNS:
        raise ValueError("pandas não preservou o schema Hubbi")

    rows = 0
    oems: set[str] = set()
    duplicate_keys: set[tuple[str, str]] = set()
    duplicates = 0
    catalogs: set[str] = set()
    groups: set[str] = set()
    file_high = 0
    any_image = 0
    with csv_path.open("r", newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            rows += 1
            for field in ("manufacturer_ref", "search_ref", "name", "brand"):
                if not row[field]:
                    raise ValueError(f"campo obrigatório vazio na linha {rows}: {field}")
            normalized = re.sub(r"[^A-Z0-9]", "", row["manufacturer_ref"].upper())
            if row["search_ref"] != normalized:
                raise ValueError(f"search_ref não normalizado na linha {rows}")
            if row["position"] not in VALID_POSITIONS or re.fullmatch(r"\d+-\d+(?:-\d+)?", row["position"]):
                raise ValueError(f"position inválido na linha {rows}: {row['position']!r}")
            try:
                json.loads(row["similarity"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"similarity inválido na linha {rows}") from exc
            oems.add(row["manufacturer_ref"])
            key = (row["brand"], row["search_ref"])
            duplicates += key in duplicate_keys
            duplicate_keys.add(key)
            if row["catalog_id"]:
                catalogs.add(row["catalog_id"])
            group = re.search(r"(?:^|; )group=([^;]+)", row["notes"])
            if group:
                groups.add(group.group(1))
            file_high += bool(row["file_high"])
            any_image += any(row[field] for field in ("file_high", "file_medium", "file_low", "file_water_mark"))
    return {
        "row_count": rows, "unique_oems": len(oems), "duplicate_brand_search_ref": duplicates,
        "catalogs_represented": len(catalogs), "groups_represented": len(groups),
        "file_high_coverage": file_high / rows if rows else 0, "image_coverage": any_image / rows if rows else 0,
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as connection:
        models = [row[0] for row in connection.execute(
            "SELECT DISTINCT vehicle_model FROM spec_registry WHERE manufacturer='VOLKSWAGEN' ORDER BY vehicle_model"
        )]
    progress = load_progress(models)
    save_progress(progress)

    for model in models:
        entry = progress["models"][model]
        if entry["status"] == "COMPLETED":
            print(f"QUEUE_SKIP_COMPLETED={model}", flush=True)
            continue
        free = shutil.disk_usage(ROOT).free
        if free < 10 * 1024**3:
            entry.update(status="FAILED", error="menos de 10 GiB livres antes do início", completed_at=now())
            save_progress(progress)
            raise SystemExit(f"espaço insuficiente antes de {model}")
        csv_path = EXPORTS_DIR / f"hubbi_volkswagen_{model.lower()}_full.csv"
        entry.update(status="RUNNING", started_at=now(), csv_path=str(csv_path), error=None)
        save_progress(progress)
        started = time.monotonic()
        command = [sys.executable, str(ROOT / "scripts" / "export_hubbi_full.py"), "--model", model, "--workers", str(args.workers)]
        output: list[str] = []
        metrics: dict = {}
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        assert process.stdout is not None
        for line in process.stdout:
            print(f"[{model}] {line}", end="", flush=True)
            output.append(line)
            if line.startswith("EXPORT_METRICS_JSON="):
                metrics = json.loads(line.split("=", 1)[1])
        result = process.wait()
        elapsed = time.monotonic() - started
        if result:
            entry.update(status="FAILED", completed_at=now(), elapsed_seconds=elapsed, error="".join(output[-40:]))
            save_progress(progress)
            raise SystemExit(f"falha no export de {model}: exit={result}")
        try:
            validation = validate_csv(csv_path)
        except Exception as exc:
            entry.update(status="FAILED", completed_at=now(), elapsed_seconds=elapsed, error=str(exc), metrics=metrics)
            save_progress(progress)
            raise SystemExit(f"falha na validação de {model}: {exc}") from exc
        entry.update(status="COMPLETED", completed_at=now(), elapsed_seconds=elapsed, metrics=metrics, **validation)
        save_progress(progress)
        print("QUEUE_MODEL_JSON=" + json.dumps({"model": model, "status": "COMPLETED", "elapsed_seconds": elapsed, **metrics, **validation, "csv_bytes": csv_path.stat().st_size, "free_bytes": shutil.disk_usage(ROOT).free}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
