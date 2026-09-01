"""T068 — plan_operation() contra SQLite real pré-populado produz zero
diferença observável no banco e no filesystem de raw (SC-014, DEC-009)."""

from __future__ import annotations

import hashlib
from datetime import date
from functools import partial
from pathlib import Path

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.checkpoint.resume import get_pending_groups
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.dry_run import ReadOnlyRepos, plan_operation
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    list_incomplete_runs,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    list_all_spec_identities,
    save_spec_identity,
)


def _dump_db(db_path: str) -> str:
    conn = connect(db_path)
    lines = []
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()  # noqa: S608
        for row in rows:
            lines.append(f"{table}:{dict(row)}")
    conn.close()
    return "\n".join(lines)


def _populate(db_path: str) -> None:
    conn = connect(db_path)
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    identity = SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="2022.06 - ...",
        source_url="https://x/62184",
        production_start=date(2022, 6, 1),
    )
    save_spec_identity(conn, identity)
    conn.close()


def _repos(conn) -> ReadOnlyRepos:
    return ReadOnlyRepos(
        get_collection_run=partial(get_collection_run, conn),
        list_incomplete_runs=partial(list_incomplete_runs, conn),
        list_all_spec_identities=partial(list_all_spec_identities, conn),
        get_current_state=partial(get_current_state, conn),
        get_authoritative_manifest=partial(get_authoritative, conn),
        get_pending_groups=partial(get_pending_groups, conn),
    )


def test_plan_operation_produces_zero_observable_diff(tmp_path: Path) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    (raw_root / "marker.txt").write_bytes(b"pre-existing raw content")

    _populate(db_path)
    before_db = _dump_db(db_path)
    before_raw = sorted(
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in raw_root.rglob("*")
        if p.is_file()
    )

    conn = connect(db_path)
    plan = plan_operation(
        _repos(conn),
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        limit_specs=None,
        limit_groups=None,
        spec_filter=None,
        force=None,
    )
    conn.close()

    after_db = _dump_db(db_path)
    after_raw = sorted(
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in raw_root.rglob("*")
        if p.is_file()
    )

    assert before_db == after_db
    assert before_raw == after_raw
    assert plan.discovered_spec_count == 1
    assert plan.run_decision  # produced a real answer, not a crash
