"""Exporta TODOS os dados já coletados de um modelo Volkswagen (não uma
amostra) para o padrão Hubbi — `exports/hubbi_volkswagen_{model}_full.csv`
+ imagens marcadas em `exports/images_marked/{brand}/`.

Reaproveita toda a lógica já validada em `export_hubbi_sample.py`
(mapeamento de colunas, normalização, geração das duas imagens, nome de
arquivo Hubbi) — a única diferença é que aqui NÃO há amostragem: todo
spec, toda categoria, todo grupo, toda peça ACCEPTED do modelo entram.

Escala: modelos grandes (GOL, SAVEIRO, AMAROK) podem passar de dezenas de
milhares de combinações spec×categoria×grupo — e cada grupo tem várias
peças, então o CSV final pode chegar a 100 mil+ linhas. Por isso:
  - as imagens são baixadas em paralelo (--workers, padrão 8) antes de
    montar as linhas, não uma por vez durante o loop principal;
  - o CSV é escrito incrementalmente (linha por linha, com flush
    periódico), não tudo de uma vez no final — uma trava no meio não
    perde o que já foi processado;
  - arquivos de imagem já existentes em disco são reaproveitados (nunca
    baixados/gerados de novo) — rodar de novo depois de uma interrupção
    retoma rápido nas imagens já prontas.

Uso:
    uv run --with pillow python scripts/export_hubbi_full.py --model EOS
    uv run --with pillow python scripts/export_hubbi_full.py --model GOL --workers 8
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import csv  # noqa: E402

from export_hubbi_sample import (  # noqa: E402
    _REAL_PART_IMAGE_HOST,
    HUBBI_COLUMNS,
    _download_image_bytes,
    build_row,
    load_html,
    parse_area_geometry,
    plain_image_path,
)

from amayama_scraper.parsing.group_detail import parse_group_detail  # noqa: E402

DB_PATH = ROOT / "amayama.db"


def resolve_market(conn: sqlite3.Connection, manufacturer: str, vehicle_model: str) -> str:
    rows = conn.execute(
        "SELECT DISTINCT market FROM spec_registry WHERE manufacturer=? AND vehicle_model=?",
        (manufacturer, vehicle_model),
    ).fetchall()
    markets = [r["market"] for r in rows]
    if len(markets) == 1:
        return markets[0]
    if not markets:
        raise SystemExit(f"error: nenhum spec encontrado para {manufacturer}/{vehicle_model}")
    raise SystemExit(
        f"error: {len(markets)} mercados encontrados para {vehicle_model} ({markets}) "
        "— passe --market explicitamente"
    )


def list_all_specs(
    conn: sqlite3.Connection, manufacturer: str, vehicle_model: str, market: str | None
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT DISTINCT s.stable_key, s.model_code, s.amayama_catalog_id,
               s.production_period_raw, s.production_start, s.production_end,
               s.grade, s.configuration
        FROM spec_registry s
        JOIN checkpoint_entry ce ON ce.spec_key = s.stable_key AND ce.status = 'ACCEPTED'
        WHERE s.manufacturer = ? AND s.vehicle_model = ?
          AND (? IS NULL OR s.market = ?)
        ORDER BY s.model_code ASC
        """,
        (manufacturer, vehicle_model, market, market),
    ).fetchall()


def list_all_groups(conn: sqlite3.Connection, spec_key: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT DISTINCT category_slug, group_id, raw_capture_id
        FROM checkpoint_entry
        WHERE spec_key = ? AND status = 'ACCEPTED'
        ORDER BY category_slug ASC, group_id ASC
        """,
        (spec_key,),
    ).fetchall()


def main() -> None:
    # Rodadas longas (horas): sem isso, print() fica preso no buffer do
    # processo até ele terminar quando a saída não é um terminal (ex.
    # redirecionada pra arquivo/pipe) — progresso só aparecia no final.
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="vehicle_model, ex: EOS, GOL, AMAROK")
    parser.add_argument("--market", default=None, help="opcional — detectado sozinho se único")
    parser.add_argument("--manufacturer", default="VOLKSWAGEN")
    parser.add_argument("--workers", type=int, default=8, help="downloads de imagem em paralelo")
    parser.add_argument(
        "--out",
        default=None,
        help="caminho do CSV (padrão: exports/hubbi_volkswagen_{model}_full.csv)",
    )
    args = parser.parse_args()

    vehicle_model = args.model.upper()
    out_path = (
        Path(args.out)
        if args.out
        else ROOT / "exports" / f"hubbi_volkswagen_{vehicle_model.lower()}_full.csv"
    )

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    markets = (
        [args.market]
        if args.market
        else [
            row["market"]
            for row in conn.execute(
                "SELECT DISTINCT market FROM spec_registry "
                "WHERE manufacturer=? AND vehicle_model=? ORDER BY market",
                (args.manufacturer, vehicle_model),
            ).fetchall()
        ]
    )
    specs = list_all_specs(conn, args.manufacturer, vehicle_model, args.market)
    if not specs:
        raise SystemExit(
            f"error: nenhum spec ACCEPTED para {args.manufacturer}/{vehicle_model}/{markets}"
        )
    print(f"modelo={vehicle_model} mercados={','.join(markets)} specs={len(specs)}")

    t0 = time.monotonic()

    # --- Fase 1: enumera tudo (spec x categoria x grupo x peça), lendo só
    # HTML já em disco (rápido, sem rede) — monta a lista de linhas a
    # gerar + o conjunto de URLs de imagem realmente precisadas.
    pending: list[dict] = []
    image_urls_needed: set[str] = set()
    groups_seen = 0
    for spec_index, spec in enumerate(specs, start=1):
        if spec_index % 50 == 0:
            print(
                f"  ... enumerando spec {spec_index}/{len(specs)} "
                f"({groups_seen} grupos até agora)"
            )
        for group in list_all_groups(conn, spec["stable_key"]):
            groups_seen += 1
            html = load_html(conn, group["raw_capture_id"])
            if html is None:
                continue
            parsed = parse_group_detail(
                html, category_slug=group["category_slug"], group_id=group["group_id"]
            )
            if parsed.critical_error is not None:
                continue
            area_coords, declared_sizes = parse_area_geometry(html)
            for schema in parsed.schemas:
                for part in schema.parts:
                    pending.append(
                        {
                            "vehicle_model": vehicle_model,
                            "spec": spec,
                            "category_slug": group["category_slug"],
                            "group_id": group["group_id"],
                            "schema_id": schema.schema_id,
                            "part": part,
                            "area_coords": area_coords,
                            "declared_sizes": declared_sizes,
                        }
                    )
                    if part.image_url and part.image_url.startswith(_REAL_PART_IMAGE_HOST):
                        image_urls_needed.add(part.image_url)
    print(
        f"fase 1 (enumeração): {len(pending)} linhas candidatas, "
        f"{len(image_urls_needed)} imagens únicas, {groups_seen} grupos — "
        f"{time.monotonic() - t0:.1f}s"
    )

    # --- Fase 2: baixa todas as imagens únicas em paralelo (aquece o
    # cache de export_hubbi_sample — build_row() só vai bater cache local
    # depois disso, nunca esperar rede peça por peça).
    t1 = time.monotonic()
    ok = 0
    fail = 0
    urls = list(image_urls_needed)
    cached_urls = {url for url in urls if plain_image_path(url).exists()}
    reused = 0
    downloaded = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for url, content in zip(urls, pool.map(_download_image_bytes, urls), strict=True):
            if content is None:
                fail += 1
            else:
                ok += 1
                if url in cached_urls:
                    reused += 1
                else:
                    downloaded += 1
    print(f"fase 2 (download paralelo): {ok} ok, {fail} falharam — {time.monotonic() - t1:.1f}s")

    # --- Fase 3: monta e escreve as linhas (agora sem esperar rede —
    # build_row() gera a imagem marcada a partir do cache já aquecido).
    t2 = time.monotonic()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    by_model_count: dict[str, int] = defaultdict(int)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HUBBI_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for i, item in enumerate(pending):
            row = build_row(
                vehicle_model=item["vehicle_model"],
                spec=item["spec"],
                category_slug=item["category_slug"],
                group_id=item["group_id"],
                schema_id=item["schema_id"],
                part=item["part"],
                area_coords=item["area_coords"],
                declared_sizes=item["declared_sizes"],
            )
            if row is None:
                continue
            writer.writerow(row)
            written += 1
            by_model_count[row["application"].split(" - ")[0]] += 1
            if written % 500 == 0:
                f.flush()
                print(f"  ... {written} linhas escritas ({i + 1}/{len(pending)} processadas)")

    print(
        f"fase 3 (escrita): {written} linhas em {out_path} — {time.monotonic() - t2:.1f}s"
    )
    print(
        "EXPORT_METRICS_JSON="
        + json.dumps(
            {
                "model": vehicle_model,
                "markets": markets,
                "specs": len(specs),
                "groups": groups_seen,
                "rows_enumerated": len(pending),
                "rows_written": written,
                "images_found": len(urls),
                "images_new_downloaded": downloaded,
                "images_reused_cache": reused,
                "images_failed": fail,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print(f"total: {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
