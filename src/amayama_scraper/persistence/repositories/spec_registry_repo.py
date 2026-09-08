"""spec_registry_repo / discovered_spec_entry_repo — data-model.md §1, §14.

Upsert por `stable_key` (SpecIdentity é imutável na tupla de identidade —
um upsert aqui é sempre idempotente sobre os mesmos 6 campos normativos,
mas os campos não-identidade, como grade/período, podem ser atualizados).
"""

from __future__ import annotations

import sqlite3
from datetime import date

from amayama_scraper.domain.discovery import DiscoveredSpecEntry
from amayama_scraper.domain.identity import SpecIdentity


def _date_to_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date_from_str(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def save_spec_identity(conn: sqlite3.Connection, identity: SpecIdentity) -> str:
    stable_key = identity.stable_key()
    conn.execute(
        """
        INSERT INTO spec_registry (
            stable_key, source, manufacturer, vehicle_model, market, model_code,
            amayama_catalog_id, production_period_raw, source_url,
            production_start, production_end, grade, configuration
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (stable_key) DO UPDATE SET
            production_period_raw = excluded.production_period_raw,
            source_url = excluded.source_url,
            production_start = excluded.production_start,
            production_end = excluded.production_end,
            grade = excluded.grade,
            configuration = excluded.configuration
        """,
        (
            stable_key,
            identity.source,
            identity.manufacturer,
            identity.vehicle_model,
            identity.market,
            identity.model_code,
            identity.amayama_catalog_id,
            identity.production_period_raw,
            identity.source_url,
            _date_to_str(identity.production_start),
            _date_to_str(identity.production_end),
            identity.grade,
            identity.configuration,
        ),
    )
    return stable_key


def get_spec_identity(conn: sqlite3.Connection, stable_key: str) -> SpecIdentity | None:
    row = conn.execute("SELECT * FROM spec_registry WHERE stable_key = ?", (stable_key,)).fetchone()
    if row is None:
        return None
    return SpecIdentity(
        source=row["source"],
        manufacturer=row["manufacturer"],
        vehicle_model=row["vehicle_model"],
        market=row["market"],
        model_code=row["model_code"],
        amayama_catalog_id=row["amayama_catalog_id"],
        production_period_raw=row["production_period_raw"],
        source_url=row["source_url"],
        production_start=_date_from_str(row["production_start"]),
        production_end=_date_from_str(row["production_end"]),
        grade=row["grade"],
        configuration=row["configuration"],
    )


def list_all_spec_identities(conn: sqlite3.Connection) -> list[SpecIdentity]:
    """Todas as SpecIdentity já persistidas, independente de run_id (T028/T029, 002).

    data-model.md §7, research.md §12 — leitura aditiva sobre spec_registry
    já existente. Usada pelo driver de coleta (orchestration/collection_driver.py)
    para saber quais specs já foram descobertas (nesta ou em execuções
    anteriores) e decidir o que navegar a seguir.
    """
    rows = conn.execute("SELECT * FROM spec_registry ORDER BY stable_key").fetchall()
    return [
        SpecIdentity(
            source=row["source"],
            manufacturer=row["manufacturer"],
            vehicle_model=row["vehicle_model"],
            market=row["market"],
            model_code=row["model_code"],
            amayama_catalog_id=row["amayama_catalog_id"],
            production_period_raw=row["production_period_raw"],
            source_url=row["source_url"],
            production_start=_date_from_str(row["production_start"]),
            production_end=_date_from_str(row["production_end"]),
            grade=row["grade"],
            configuration=row["configuration"],
        )
        for row in rows
    ]


def list_by_scope(
    conn: sqlite3.Connection, *, manufacturer: str, vehicle_model: str, market: str
) -> list[SpecIdentity]:
    """Todas as SpecIdentity de um escopo (manufacturer/vehicle_model/market), case-insensitive.

    003-corpus-analysis-tool — leitura aditiva sobre spec_registry já existente,
    usada pela ferramenta de análise para restringir a um escopo como
    "VOLKSWAGEN / AMAROK / AMA-BR" sem exigir SQL manual do operador.
    """
    rows = conn.execute(
        "SELECT * FROM spec_registry "
        "WHERE UPPER(manufacturer) = UPPER(?) AND UPPER(vehicle_model) = UPPER(?) "
        "AND UPPER(market) = UPPER(?) ORDER BY stable_key",
        (manufacturer, vehicle_model, market),
    ).fetchall()
    return [
        SpecIdentity(
            source=row["source"],
            manufacturer=row["manufacturer"],
            vehicle_model=row["vehicle_model"],
            market=row["market"],
            model_code=row["model_code"],
            amayama_catalog_id=row["amayama_catalog_id"],
            production_period_raw=row["production_period_raw"],
            source_url=row["source_url"],
            production_start=_date_from_str(row["production_start"]),
            production_end=_date_from_str(row["production_end"]),
            grade=row["grade"],
            configuration=row["configuration"],
        )
        for row in rows
    ]


def find_by_model_code_and_catalog_id(
    conn: sqlite3.Connection, model_code: str, amayama_catalog_id: str
) -> list[SpecIdentity]:
    """model_code isolado nunca identifica — retorna todos os candidatos (FR-003)."""
    rows = conn.execute(
        "SELECT * FROM spec_registry WHERE model_code = ? AND amayama_catalog_id = ?",
        (model_code, amayama_catalog_id),
    ).fetchall()
    return [
        SpecIdentity(
            source=row["source"],
            manufacturer=row["manufacturer"],
            vehicle_model=row["vehicle_model"],
            market=row["market"],
            model_code=row["model_code"],
            amayama_catalog_id=row["amayama_catalog_id"],
            production_period_raw=row["production_period_raw"],
            source_url=row["source_url"],
            production_start=_date_from_str(row["production_start"]),
            production_end=_date_from_str(row["production_end"]),
            grade=row["grade"],
            configuration=row["configuration"],
        )
        for row in rows
    ]


def save_discovered_spec_entry(
    conn: sqlite3.Connection, entry: DiscoveredSpecEntry, stable_key: str
) -> None:
    conn.execute(
        """
        INSERT INTO discovered_spec_entry (
            stable_key, market, model_code, amayama_catalog_id, source_url,
            source_capture_id, production_period_raw, production_start,
            production_end, grade, configuration
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stable_key,
            entry.market,
            entry.model_code,
            entry.amayama_catalog_id,
            entry.source_url,
            entry.source_capture_id,
            entry.production_period_raw,
            _date_to_str(entry.production_start),
            _date_to_str(entry.production_end),
            entry.grade,
            entry.configuration,
        ),
    )


def list_discovered_spec_entries(
    conn: sqlite3.Connection, stable_key: str
) -> list[DiscoveredSpecEntry]:
    rows = conn.execute(
        "SELECT * FROM discovered_spec_entry WHERE stable_key = ? ORDER BY id", (stable_key,)
    ).fetchall()
    return [
        DiscoveredSpecEntry(
            market=row["market"],
            model_code=row["model_code"],
            amayama_catalog_id=row["amayama_catalog_id"],
            source_url=row["source_url"],
            source_capture_id=row["source_capture_id"],
            production_period_raw=row["production_period_raw"],
            production_start=_date_from_str(row["production_start"]),
            production_end=_date_from_str(row["production_end"]),
            grade=row["grade"],
            configuration=row["configuration"],
        )
        for row in rows
    ]
