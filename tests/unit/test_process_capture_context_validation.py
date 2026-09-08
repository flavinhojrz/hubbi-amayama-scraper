"""process_capture() valida CollectionContext contra CollectionRun.scope, e
rejeita MARKET_INDEX cujo market extraído diverge do contexto do run (004 —
item 1/FR-002/FR-005 e item 5/FR-040/FR-041 da correção de robustez
multi-modelo).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT, GOL_CONTEXT

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.collection_context import (
    CaptureRunMismatchError,
    CollectionContext,
    ContextScopeMismatchError,
    UnregisteredSpecIdentityError,
)
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.pipeline import process_capture, try_finalize_spec_entry
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    list_by_scope,
    save_spec_identity,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_bytes()


def _repos(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    return conn, blob_store, capture_repo


def _raw_capture_count(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) AS c FROM raw_capture").fetchone()["c"])


def _market_index_input(run_id: str) -> RawCaptureInput:
    return RawCaptureInput(
        capture_kind=CaptureKind.MARKET_INDEX,
        source_url="https://www.amayama.com/en/x/ama-br",
        collected_at=datetime.now(UTC),
        raw_content=MARKET_INDEX_HTML,
        run_id=run_id,
    )


def _amarok_identity() -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="irrelevant for this test",
        source_url="https://x/s7bc8a-62184",
    )


def test_context_diverging_from_the_runs_persisted_scope_is_rejected_before_any_persistence(
    tmp_path: Path,
):
    """Cenário adversarial de US1: mesmo passando um run_id de um run
    Amarok real, um contexto de GOL nunca é aceito — nem o raw capture é
    persistido (accept_capture nunca é alcançado)."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))

    with pytest.raises(ContextScopeMismatchError):
        process_capture(
            conn,
            blob_store,
            capture_repo,
            "run-1",
            _market_index_input("run-1"),
            context=GOL_CONTEXT,
        )

    # nenhum raw capture foi persistido — a validação de contexto acontece
    # antes de accept_capture()
    assert _raw_capture_count(conn) == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM spec_registry").fetchone()["c"] == 0


def test_unknown_run_id_is_rejected_before_any_persistence(tmp_path: Path):
    conn, blob_store, capture_repo = _repos(tmp_path)

    with pytest.raises(ContextScopeMismatchError):
        process_capture(
            conn,
            blob_store,
            capture_repo,
            "does-not-exist",
            _market_index_input("does-not-exist"),
            context=AMAROK_CONTEXT,
        )
    assert _raw_capture_count(conn) == 0


def test_matching_context_processes_normally(tmp_path: Path):
    conn, blob_store, capture_repo = _repos(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))

    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-1",
        _market_index_input("run-1"),
        context=AMAROK_CONTEXT,
    )
    assert result.critical_error is False
    assert _raw_capture_count(conn) == 1
    discovered = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert len(discovered) == 2


# --- Cenário F: market extraído da página diverge do context.market -------


def test_market_index_with_a_different_market_than_the_context_is_rejected(tmp_path: Path):
    """A fixture real tem breadcrumb "AMA-BR" — um contexto para outro
    market (mesmo manufacturer/vehicle_model) nunca persiste as specs
    descobertas, mas o raw capture continua preservado (Constitution §4)."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    other_market_context = CollectionContext(
        manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-US"
    )
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=other_market_context.scope()))

    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-1",
        _market_index_input("run-1"),
        context=other_market_context,
    )

    assert result.critical_error is True
    assert result.routed_to_parser is True
    assert _raw_capture_count(conn) == 1
    assert conn.execute("SELECT COUNT(*) AS c FROM spec_registry").fetchone()["c"] == 0


# --- Blocker 1 (004): spec_key de outro modelo/mercado ---------------------
#
# Cenário obrigatório: run = GOL/AMA-BR, context = GOL/AMA-BR,
# spec_key = de uma spec real da Amarok/AMA-BR. Resultado exigido: falha
# fechada; zero persistência; zero alteração de current_state; run não
# concluído.


def test_spec_key_belonging_to_another_model_is_rejected_before_manifest_write(tmp_path: Path):
    conn, blob_store, capture_repo = _repos(tmp_path)
    amarok_spec_key = save_spec_identity(conn, _amarok_identity())
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    manifest_input = RawCaptureInput(
        capture_kind=CaptureKind.SPEC_NAVIGATION,
        source_url="https://x/spec-nav",
        collected_at=datetime.now(UTC),
        raw_content=b"<html><body>irrelevant</body></html>",
        run_id="run-gol",
    )

    with pytest.raises(ContextScopeMismatchError):
        process_capture(
            conn,
            blob_store,
            capture_repo,
            "run-gol",
            manifest_input,
            context=GOL_CONTEXT,
            spec_key=amarok_spec_key,
        )

    assert _raw_capture_count(conn) == 0
    assert get_authoritative(conn, amarok_spec_key, "run-gol") is None
    assert get_current_state(conn, amarok_spec_key) is None


def test_spec_key_belonging_to_another_model_is_rejected_before_any_checkpoint_write(
    tmp_path: Path,
):
    """GROUP_DETAIL grava checkpoint_entry já no primeiro evento
    (START_ATTEMPT) — prova que nem esse primeiro registro acontece."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    amarok_spec_key = save_spec_identity(conn, _amarok_identity())
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    group_input = RawCaptureInput(
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url="https://x/engine/1",
        collected_at=datetime.now(UTC),
        raw_content=b"<html><body>irrelevant</body></html>",
        run_id="run-gol",
    )

    with pytest.raises(ContextScopeMismatchError):
        process_capture(
            conn,
            blob_store,
            capture_repo,
            "run-gol",
            group_input,
            context=GOL_CONTEXT,
            spec_key=amarok_spec_key,
            category_slug="engine",
            group_id="1",
        )

    assert _raw_capture_count(conn) == 0
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM checkpoint_entry WHERE spec_key = ?", (amarok_spec_key,)
    ).fetchone()
    assert row["c"] == 0
    assert get_current_state(conn, amarok_spec_key) is None


def test_try_finalize_spec_entry_independently_rejects_a_spec_key_from_another_model(
    tmp_path: Path,
):
    """'Não confie apenas no caller': try_finalize_spec_entry() é o caminho
    que efetivamente cria snapshot/current_state/estado VALID — valida
    spec_key -> context por conta própria, mesmo que process_capture() já
    tivesse (hipoteticamente) deixado passar."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    amarok_spec_key = save_spec_identity(conn, _amarok_identity())
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    with pytest.raises(ContextScopeMismatchError):
        try_finalize_spec_entry(
            conn, blob_store, capture_repo, "run-gol", amarok_spec_key, context=GOL_CONTEXT
        )

    assert get_current_state(conn, amarok_spec_key) is None
    row = conn.execute("SELECT COUNT(*) AS c FROM spec_snapshot").fetchone()
    assert row["c"] == 0


# --- Hardening final (004): identidade ausente falha fechada ---------------
#
# _require_matching_spec_context() não pula mais a validação quando não
# encontra a SpecIdentity — levanta UnregisteredSpecIdentityError. "Spec
# inexistente" e "Finalização inexistente" abaixo cobrem exatamente isso.

_MINIMAL_MANIFEST_HTML = """
<html><body>
  <div class="epcVariation__details">
    <div class="epcVariation__filters">
      <div class="epcVariation__schemaGroups">
        <a class="epcVariation__schemaGroup active" data-id="" href="https://x#">All</a>
        <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
      </div>
    </div>
    <div class="epcVariation__schemas">
      <div class="epcVariation__schema" data-id="407">
        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/407">407</a></div>
      </div>
    </div>
  </div>
</body></html>
"""


def test_scenario_spec_key_does_not_exist_process_capture_fails_before_any_write(
    tmp_path: Path,
):
    """'Spec inexistente': run GOL válido, context GOL válido, spec_key
    nunca registrada. process_capture() deve falhar; nenhum manifest,
    checkpoint, snapshot ou current_state."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    manifest_input = RawCaptureInput(
        capture_kind=CaptureKind.SPEC_NAVIGATION,
        source_url="https://x/spec-nav",
        collected_at=datetime.now(UTC),
        raw_content=_MINIMAL_MANIFEST_HTML.encode("utf-8"),
        run_id="run-gol",
    )

    with pytest.raises(UnregisteredSpecIdentityError):
        process_capture(
            conn,
            blob_store,
            capture_repo,
            "run-gol",
            manifest_input,
            context=GOL_CONTEXT,
            spec_key="never-registered",
        )

    assert _raw_capture_count(conn) == 0
    row = conn.execute("SELECT COUNT(*) AS c FROM spec_group_manifest").fetchone()
    assert row["c"] == 0
    row = conn.execute("SELECT COUNT(*) AS c FROM checkpoint_entry").fetchone()
    assert row["c"] == 0
    row = conn.execute("SELECT COUNT(*) AS c FROM spec_snapshot").fetchone()
    assert row["c"] == 0
    assert get_current_state(conn, "never-registered") is None


def test_scenario_spec_key_does_not_exist_group_detail_fails_before_checkpoint(
    tmp_path: Path,
):
    conn, blob_store, capture_repo = _repos(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    group_input = RawCaptureInput(
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url="https://x/engine/1",
        collected_at=datetime.now(UTC),
        raw_content=b"<html><body>irrelevant</body></html>",
        run_id="run-gol",
    )

    with pytest.raises(UnregisteredSpecIdentityError):
        process_capture(
            conn,
            blob_store,
            capture_repo,
            "run-gol",
            group_input,
            context=GOL_CONTEXT,
            spec_key="never-registered",
            category_slug="engine",
            group_id="1",
        )

    assert _raw_capture_count(conn) == 0
    row = conn.execute("SELECT COUNT(*) AS c FROM checkpoint_entry").fetchone()
    assert row["c"] == 0
    assert get_current_state(conn, "never-registered") is None


def test_scenario_finalization_of_a_nonexistent_spec_key_fails_before_snapshot(
    tmp_path: Path,
):
    """'Finalização inexistente': chamar try_finalize_spec_entry() direto
    com spec_key nunca registrada deve falhar antes de snapshot/
    current_state/VALID."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    with pytest.raises(UnregisteredSpecIdentityError):
        try_finalize_spec_entry(
            conn,
            blob_store,
            capture_repo,
            "run-gol",
            "never-registered",
            context=GOL_CONTEXT,
        )

    assert get_current_state(conn, "never-registered") is None
    row = conn.execute("SELECT COUNT(*) AS c FROM spec_snapshot").fetchone()
    assert row["c"] == 0


def test_scenario_spec_registered_and_belonging_to_context_still_works_normally(
    tmp_path: Path,
):
    """'Spec válida': uma spec registrada pertencente ao context continua
    funcionando normalmente após o hardening — nenhuma regressão para o
    caminho legítimo."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    gol_identity = SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="GOL",
        market="AMA-BR",
        model_code="GOLBR1",
        amayama_catalog_id="10001",
        production_period_raw="irrelevant for this test",
        source_url="https://x/golbr1-10001",
    )
    gol_spec_key = save_spec_identity(conn, gol_identity)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    manifest_input = RawCaptureInput(
        capture_kind=CaptureKind.SPEC_NAVIGATION,
        source_url="https://x/spec-nav",
        collected_at=datetime.now(UTC),
        raw_content=_MINIMAL_MANIFEST_HTML.encode("utf-8"),
        run_id="run-gol",
    )

    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-gol",
        manifest_input,
        context=GOL_CONTEXT,
        spec_key=gol_spec_key,
    )

    assert result.critical_error is False
    assert get_authoritative(conn, gol_spec_key, "run-gol") is not None


# --- Hardening final (004): capture_input.run_id != run_id -----------------
#
# process_capture() valida contexto/spec_key contra `run_id`, mas
# accept_capture() persistiria usando `capture_input.run_id` — sem checagem
# explícita os dois poderiam divergir.


def test_capture_input_run_id_diverging_from_run_id_is_rejected_before_any_persistence(
    tmp_path: Path,
):
    """Cenário adversarial: run_id A pertence a GOL, context = GOL, spec GOL
    válida e registrada — mas capture_input.run_id aponta para o run_id B
    de um run da Amarok. Deve falhar fechado antes de qualquer
    persistência, mesmo com run_id/context/spec_key todos corretos entre
    si."""
    conn, blob_store, capture_repo = _repos(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))
    save_collection_run(conn, CollectionRun(run_id="run-amarok", scope=AMAROK_CONTEXT.scope()))

    gol_identity = SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="GOL",
        market="AMA-BR",
        model_code="GOLBR2",
        amayama_catalog_id="10002",
        production_period_raw="irrelevant for this test",
        source_url="https://x/golbr2-10002",
    )
    gol_spec_key = save_spec_identity(conn, gol_identity)

    manifest_input = RawCaptureInput(
        capture_kind=CaptureKind.SPEC_NAVIGATION,
        source_url="https://x/spec-nav",
        collected_at=datetime.now(UTC),
        raw_content=_MINIMAL_MANIFEST_HTML.encode("utf-8"),
        run_id="run-amarok",  # diverge do run_id="run-gol" passado abaixo
    )

    with pytest.raises(CaptureRunMismatchError):
        process_capture(
            conn,
            blob_store,
            capture_repo,
            "run-gol",
            manifest_input,
            context=GOL_CONTEXT,
            spec_key=gol_spec_key,
        )

    assert _raw_capture_count(conn) == 0
    assert get_authoritative(conn, gol_spec_key, "run-gol") is None
    assert get_authoritative(conn, gol_spec_key, "run-amarok") is None
    row = conn.execute("SELECT COUNT(*) AS c FROM checkpoint_entry").fetchone()
    assert row["c"] == 0
    row = conn.execute("SELECT COUNT(*) AS c FROM spec_snapshot").fetchone()
    assert row["c"] == 0
    assert get_current_state(conn, gol_spec_key) is None


def test_capture_input_run_id_matching_run_id_continues_to_work_normally(tmp_path: Path):
    conn, blob_store, capture_repo = _repos(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    gol_identity = SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="GOL",
        market="AMA-BR",
        model_code="GOLBR3",
        amayama_catalog_id="10003",
        production_period_raw="irrelevant for this test",
        source_url="https://x/golbr3-10003",
    )
    gol_spec_key = save_spec_identity(conn, gol_identity)

    manifest_input = RawCaptureInput(
        capture_kind=CaptureKind.SPEC_NAVIGATION,
        source_url="https://x/spec-nav",
        collected_at=datetime.now(UTC),
        raw_content=_MINIMAL_MANIFEST_HTML.encode("utf-8"),
        run_id="run-gol",  # igual ao run_id passado abaixo
    )

    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-gol",
        manifest_input,
        context=GOL_CONTEXT,
        spec_key=gol_spec_key,
    )

    assert result.critical_error is False
    assert _raw_capture_count(conn) == 1
    assert get_authoritative(conn, gol_spec_key, "run-gol") is not None
