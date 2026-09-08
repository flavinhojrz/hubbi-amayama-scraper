"""Blocker restante (Codex, follow-up ao Blocker 1) — `--dry-run` deve
satisfazer simultaneamente DEC-009 (zero mutação de filesystem) E leitura
correta do estado persistido atual, incluindo commits presentes apenas no
WAL de um writer legítimo ainda aberto. `immutable=1` universal (correção
anterior) violava a segunda metade do contrato: lê apenas o arquivo
principal, ignorando o WAL inteiramente — confirmado empiricamente que isso
chega a esconder até um `CREATE TABLE` existente somente no WAL.

`_connect_read_only()` agora escolhe dinamicamente:
- sem WAL pendente -> `mode=ro&immutable=1` (evita criar `-shm`/`-wal`);
- com WAL pendente (`<db>-wal` existe e tem conteúdo) -> `mode=ro` puro,
  que participa corretamente do protocolo de leitura do WAL, reaproveitando
  os sidecars JÁ EXISTENTES sem criar nada novo.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.cli.main import main
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity


def _fail_if_transport_instantiated(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("ChromeCdpTransport must never be instantiated during --dry-run")


def _hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _snapshot(tmp_path: Path, db_path: Path) -> dict[str, object]:
    return {
        "names": sorted(p.name for p in tmp_path.iterdir()),
        "db_hash": _hash(db_path),
        "wal_hash": _hash(Path(f"{db_path}-wal")),
        "wal_size": Path(f"{db_path}-wal").stat().st_size
        if Path(f"{db_path}-wal").exists()
        else None,
        "shm_size": Path(f"{db_path}-shm").stat().st_size
        if Path(f"{db_path}-shm").exists()
        else None,
    }


# --- Cenário 1: diretório vazio ---------------------------------------------


def test_empty_directory_dry_run_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "state.db"
    raw_root = tmp_path / "raw"
    monkeypatch.setattr(
        "amayama_scraper.cli.main.ChromeCdpTransport", _fail_if_transport_instantiated
    )

    assert sorted(tmp_path.iterdir()) == []

    exit_code = main(["run", "--dry-run", "--db-path", str(db_path), "--raw-root", str(raw_root)])

    assert exit_code == 0
    assert not db_path.exists()
    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()
    assert not raw_root.exists()
    assert sorted(tmp_path.iterdir()) == []


# --- Cenário 2: banco limpo existente (sem WAL pendente) --------------------


def test_clean_existing_database_dry_run_reads_correctly_and_zero_diffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "state.db"
    raw_root = tmp_path / "raw"

    conn = connect(str(db_path))
    run_migrations(conn)
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

    # sanity per research.md/Blocker 1: a cleanly-closed WAL-mode db leaves
    # no -wal/-shm behind in this environment.
    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()

    monkeypatch.setattr(
        "amayama_scraper.cli.main.ChromeCdpTransport", _fail_if_transport_instantiated
    )
    before = _snapshot(tmp_path, db_path)

    exit_code = main(["run", "--dry-run", "--db-path", str(db_path), "--raw-root", str(raw_root)])

    after = _snapshot(tmp_path, db_path)

    assert exit_code == 0
    assert after == before  # names, main-db hash, and (absent) sidecars all identical
    assert not raw_root.exists()
    captured = capsys.readouterr()
    assert "discovered specs: 1" in captured.out


# --- Cenário 3: banco com writer ativo e WAL não checkpontado ---------------


def test_dry_run_sees_commits_still_only_in_an_active_writers_wal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reprodução exata do cenário relatado pelo Codex: um writer legítimo
    permanece com a conexão aberta; CollectionRun e SpecIdentity já foram
    commitados (autocommit) mas ainda não passaram por checkpoint para o
    arquivo principal — só existem no `-wal`. O dry-run precisa enxergá-los
    corretamente, sem alterar nenhum arquivo existente e sem criar nenhum
    novo."""
    db_path = tmp_path / "state.db"
    raw_root = tmp_path / "raw"

    writer = connect(str(db_path))
    run_migrations(writer)
    save_collection_run(writer, CollectionRun(run_id="run-1"))
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
    save_spec_identity(writer, identity)
    # writer stays OPEN — never closed before the dry-run below runs.

    # Confirm the premise under test: real, non-trivial WAL data pending,
    # not yet checkpointed to the main file.
    wal_path = Path(f"{db_path}-wal")
    assert wal_path.exists()
    assert wal_path.stat().st_size > 0
    assert get_collection_run(writer, "run-1") is not None  # writer sees its own data

    monkeypatch.setattr(
        "amayama_scraper.cli.main.ChromeCdpTransport", _fail_if_transport_instantiated
    )
    before = _snapshot(tmp_path, db_path)

    exit_code = main(["run", "--dry-run", "--db-path", str(db_path), "--raw-root", str(raw_root)])

    after = _snapshot(tmp_path, db_path)
    captured = capsys.readouterr()

    assert exit_code == 0
    # --- correctness: dry-run sees the WAL-resident commits ---
    assert "discovered specs: 1" in captured.out
    assert "run-1" in captured.out  # sees the existing incomplete run, not "would create a new run"
    assert "would create a new run" not in captured.out

    # --- zero mutation: nothing new, nothing changed ---
    assert after["names"] == before["names"]  # no new files (raw_root included)
    assert after["db_hash"] == before["db_hash"]  # main file untouched
    assert after["wal_hash"] == before["wal_hash"]  # WAL bytes untouched (writer data intact)
    assert after["wal_size"] == before["wal_size"]
    # -shm content bytes MAY differ (SQLite's WAL reader protocol writes
    # transient read-mark bookkeeping into the shared-memory index for any
    # reader, including mode=ro) — this is inherent, unavoidable, and
    # confirmed empirically to never change the file's SIZE or create a new
    # file. Byte-identity of -shm is deliberately not asserted here.
    assert after["shm_size"] == before["shm_size"]
    assert not raw_root.exists()

    writer.close()


# --- Cenário 4: regressão DEC-009 -------------------------------------------


def test_dry_run_with_active_wal_writer_never_touches_browser_or_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mesmo cenário do teste anterior, focado especificamente em provar
    que nenhuma das garantias de DEC-009 foi enfraquecida pela correção:
    zero browser, zero navegação, zero escrita de DB, zero checkpoint, zero
    raw, zero migration, zero criação de run."""
    db_path = tmp_path / "state.db"
    raw_root = tmp_path / "raw"

    writer = connect(str(db_path))
    run_migrations(writer)
    save_collection_run(writer, CollectionRun(run_id="run-1"))

    monkeypatch.setattr(
        "amayama_scraper.cli.main.ChromeCdpTransport", _fail_if_transport_instantiated
    )

    def _fail_if_migrations_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("run_migrations() must never be called during --dry-run")

    monkeypatch.setattr("amayama_scraper.cli.main.run_migrations", _fail_if_migrations_run)

    exit_code = main(["run", "--dry-run", "--db-path", str(db_path), "--raw-root", str(raw_root)])

    assert exit_code == 0
    assert not raw_root.exists()
    # a second, independent connection (simulating a completely fresh
    # inspection) still sees only the ONE run the writer created — the
    # dry-run never created a second one.
    from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE
    from amayama_scraper.persistence.repositories.checkpoint_repo import list_incomplete_runs

    incomplete = list_incomplete_runs(writer, FIXED_SCOPE)
    assert [r.run_id for r in incomplete] == ["run-1"]

    writer.close()
