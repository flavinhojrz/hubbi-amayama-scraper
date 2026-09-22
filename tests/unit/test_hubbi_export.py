import csv
import io
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import scripts.export_hubbi_sample as exporter
from PIL import Image
from scripts.export_hubbi_sample import HUBBI_COLUMNS, build_row, derive_vehicle_position


def test_derives_explicit_vehicle_positions():
    cases = {
        "front bumper": "DIANTEIRO",
        "rear bumper": "TRASEIRO",
        "front left door": "DIANTEIRO ESQUERDO",
        "front right door": "DIANTEIRO DIREITO",
        "rear left door": "TRASEIRO ESQUERDO",
        "rear right door": "TRASEIRO DIREITO",
        "left door": "ESQUERDO",
        "right door": "DIREITO",
        "left-hand mirror": "ESQUERDO",
        "right-hand mirror": "DIREITO",
        "inner door seal": "INTERNO",
        "outer door seal": "EXTERNO",
    }
    for description, expected in cases.items():
        assert derive_vehicle_position(description) == expected


def test_ambiguous_or_technical_text_has_no_position():
    assert derive_vehicle_position("Sticker 'airbag' attention/replacement date") == ""
    assert derive_vehicle_position("Socket head bolt with inner multipoint head") == ""
    assert derive_vehicle_position("Lambda probe in front of catalyst") == ""
    assert derive_vehicle_position("10000-3") == ""


def test_hubbi_columns_match_the_final_22_column_contract():
    from scripts.export_hubbi_full import HUBBI_COLUMNS as full_hubbi_columns

    assert HUBBI_COLUMNS == [
        "manufacturer_ref",
        "search_ref",
        "name",
        "brand",
        "application",
        "position",
        "ncm",
        "barcode",
        "gross_weight",
        "net_weight",
        "width",
        "depth",
        "height",
        "born_at",
        "deprecated_at",
        "similarity",
        "notes",
        "catalog_id",
        "file_high",
        "file_medium",
        "file_low",
        "file_water_mark",
    ]
    assert len(HUBBI_COLUMNS) == 22
    assert full_hubbi_columns == HUBBI_COLUMNS
    assert "image_part_number" not in HUBBI_COLUMNS
    assert "marked_image_filename" not in HUBBI_COLUMNS

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HUBBI_COLUMNS)
    writer.writeheader()
    assert next(csv.reader(io.StringIO(output.getvalue()))) == HUBBI_COLUMNS


def test_build_row_keeps_image_links_without_exporting_diagram_label(monkeypatch):
    monkeypatch.setattr(exporter, "save_plain_image", lambda _: None)
    part = SimpleNamespace(
        oem_code="5X7010274R",
        description="Sticker airbag",
        details="",
        quantity="1",
        image_url="https://vag-img.amayama.com/VW/Bilder/1/1.TIF.png",
        position_pnc="10000-3",
    )
    spec = {
        "production_start": "2010-01-01",
        "production_end": None,
        "model_code": "SA-BR",
        "amayama_catalog_id": "sa-br-1",
        "grade": "",
        "configuration": "",
        "production_period_raw": "",
    }

    row = build_row(
        vehicle_model="SAVEIRO",
        spec=spec,
        category_slug="access-infotainment-miscell",
        group_id="010",
        schema_id="10000",
        part=part,
        area_coords={},
        declared_sizes={},
    )

    assert row is not None
    assert row["position"] == ""
    assert set(row) == set(HUBBI_COLUMNS)
    assert row["file_high"] == part.image_url
    assert row["file_medium"] == ""
    assert row["file_low"] == ""
    assert row["file_water_mark"] == ""


def test_final_contract_csv_opens_with_pandas_and_has_valid_required_fields(tmp_path: Path):
    part = SimpleNamespace(
        oem_code="5X7010274R",
        description="Front left door",
        details="",
        quantity="1",
        image_url="",
        position_pnc="10000-3",
    )
    spec = {
        "production_start": "2010-01-01",
        "production_end": None,
        "model_code": "SA-BR",
        "amayama_catalog_id": "sa-br-1",
        "grade": "",
        "configuration": "",
        "production_period_raw": "",
    }
    row = build_row(
        vehicle_model="SAVEIRO",
        spec=spec,
        category_slug="access-infotainment-miscell",
        group_id="010",
        schema_id="10000",
        part=part,
        area_coords={},
        declared_sizes={},
    )
    assert row is not None

    csv_path = tmp_path / "hubbi_contract_smoke.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=HUBBI_COLUMNS)
        writer.writeheader()
        writer.writerow(row)

    dataframe = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    assert list(dataframe.columns) == HUBBI_COLUMNS
    assert dataframe.shape == (1, 22)
    exported = dataframe.iloc[0].to_dict()
    assert exported["manufacturer_ref"] == "5X7010274R"
    assert exported["search_ref"] == "5X7010274R"
    assert exported["name"] == "Front left door"
    assert exported["brand"] == "VOLKSWAGEN"
    assert exported["position"] == "DIANTEIRO ESQUERDO"
    assert json.loads(exported["similarity"]) == []


def test_full_export_aggregates_all_markets_when_market_is_not_supplied():
    from scripts.export_hubbi_full import list_all_specs

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE spec_registry (
            stable_key TEXT, manufacturer TEXT, vehicle_model TEXT, market TEXT,
            model_code TEXT, amayama_catalog_id TEXT, production_period_raw TEXT,
            production_start TEXT, production_end TEXT, grade TEXT, configuration TEXT
        );
        CREATE TABLE checkpoint_entry (spec_key TEXT, status TEXT);
        INSERT INTO spec_registry VALUES
            ('go', 'VOLKSWAGEN', 'GOLF', 'GO-BR', 'GO', 'go-1', '', '', '', '', ''),
            ('gob', 'VOLKSWAGEN', 'GOLF', 'GOB-BR', 'GOB', 'gob-1', '', '', '', '', '');
        INSERT INTO checkpoint_entry VALUES ('go', 'ACCEPTED'), ('gob', 'ACCEPTED');
        """
    )

    assert [row["stable_key"] for row in list_all_specs(connection, "VOLKSWAGEN", "GOLF", None)] == [
        "go",
        "gob",
    ]
    assert [
        row["stable_key"] for row in list_all_specs(connection, "VOLKSWAGEN", "GOLF", "GOB-BR")
    ] == ["gob"]


def test_image_download_reuses_plain_disk_cache(tmp_path: Path, monkeypatch):
    url = "https://vag-img.amayama.com/VW/Bilder/1/1.TIF.png"
    monkeypatch.setattr(exporter, "IMAGES_DIR", tmp_path)
    exporter._image_download_cache.clear()
    cached_path = exporter.plain_image_path(url)
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    cached_path.write_bytes(image.getvalue())

    def fail_request(*args, **kwargs):
        raise AssertionError("cache miss triggered a network request")

    monkeypatch.setattr(exporter.requests, "get", fail_request)
    assert exporter._download_image_bytes(url) == image.getvalue()
