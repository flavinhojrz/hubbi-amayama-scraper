"""T174 — spec_registry_repo persiste e recupera SpecIdentity/DiscoveredSpecEntry.

T028 (002) — list_all_spec_identities() (data-model.md §7, research.md §12):
leitura aditiva independente de stable_key/run_id, usada pelo driver de
coleta para saber quais specs já foram descobertas.
"""

from datetime import date

from amayama_scraper.domain.discovery import DiscoveredSpecEntry
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
    get_spec_identity,
    list_all_spec_identities,
    list_discovered_spec_entries,
    save_discovered_spec_entry,
    save_spec_identity,
)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def _identity(**overrides: object) -> SpecIdentity:
    defaults: dict[str, object] = dict(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="2022.06 - ...",
        source_url="https://x/s7bc8a-62184",
        production_start=date(2022, 6, 1),
    )
    defaults.update(overrides)
    return SpecIdentity(**defaults)  # type: ignore[arg-type]


def test_save_and_get_round_trips():
    conn = _conn()
    identity = _identity()
    stable_key = save_spec_identity(conn, identity)
    assert stable_key == identity.stable_key()

    fetched = get_spec_identity(conn, stable_key)
    assert fetched == identity


def test_get_missing_returns_none():
    conn = _conn()
    assert get_spec_identity(conn, "nonexistent") is None


def test_upsert_updates_non_identity_fields_only():
    conn = _conn()
    identity = _identity(grade="Highline")
    stable_key = save_spec_identity(conn, identity)

    updated = _identity(grade="Comfortline")
    save_spec_identity(conn, updated)

    fetched = get_spec_identity(conn, stable_key)
    assert fetched is not None
    assert fetched.grade == "Comfortline"
    assert fetched.stable_key() == stable_key  # identity tuple unchanged


def test_find_by_model_code_and_catalog_id_disambiguates_same_model_code():
    conn = _conn()
    a = _identity(amayama_catalog_id="62184", production_period_raw="2022.06 - ...")
    b = _identity(amayama_catalog_id="61189", production_period_raw="2019.08 - 2022.05")
    save_spec_identity(conn, a)
    save_spec_identity(conn, b)

    results = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")
    assert len(results) == 1
    assert results[0].amayama_catalog_id == "62184"


def test_discovered_spec_entry_persists_and_lists_by_stable_key():
    conn = _conn()
    identity = _identity()
    stable_key = save_spec_identity(conn, identity)

    entry = DiscoveredSpecEntry(
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        source_url="https://x/s7bc8a-62184",
        source_capture_id="cap-1",
        production_period_raw="2022.06 - ...",
    )
    save_discovered_spec_entry(conn, entry, stable_key)

    fetched = list_discovered_spec_entries(conn, stable_key)
    assert len(fetched) == 1
    assert fetched[0].source_capture_id == "cap-1"


def test_list_all_spec_identities_empty_when_nothing_discovered():
    conn = _conn()
    assert list_all_spec_identities(conn) == []


def test_list_all_spec_identities_returns_every_persisted_identity_regardless_of_run():
    conn = _conn()
    a = _identity(amayama_catalog_id="62184")
    b = _identity(amayama_catalog_id="61189", model_code="S7BC8A")
    save_spec_identity(conn, a)
    save_spec_identity(conn, b)

    all_identities = list_all_spec_identities(conn)
    catalog_ids = {identity.amayama_catalog_id for identity in all_identities}
    assert catalog_ids == {"62184", "61189"}


def test_list_all_spec_identities_reflects_exactly_what_was_saved():
    conn = _conn()
    identity = _identity()
    save_spec_identity(conn, identity)

    (only,) = list_all_spec_identities(conn)
    assert only == identity
