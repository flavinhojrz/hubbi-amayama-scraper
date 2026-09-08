"""T025 — cli/analyze.py::main() ponta a ponta sobre fixture SQLite em arquivo temporário.

Cobre: corpus saudável, manifest divergente, snapshot incompleto, spec
zero-peças legítima, banco inexistente/escopo inexistente, saída texto vs JSON.
"""

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from amayama_scraper.cli.analyze import main
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest
from amayama_scraper.persistence.repositories.snapshot_repo import save_snapshot
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot


def _identity(model_code: str) -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code=model_code,
        amayama_catalog_id="999",
        production_period_raw="2020-2021",
        source_url=f"https://amayama.example/{model_code}",
    )


def _snapshot(spec_ref: str, snapshot_id: str, **overrides) -> SpecSnapshot:
    base = dict(
        snapshot_id=snapshot_id,
        spec_identity_ref=spec_ref,
        idempotency_key=f"idem-{snapshot_id}",
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="p1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=True,
        structure_hash="s" * 64,
        spec_parts_hash="h" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="i" * 64,
        state=SnapshotState.VALID,
        counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 10},
    )
    base.update(overrides)
    return SpecSnapshot(**base)


@pytest.fixture
def fixture_db(tmp_path):
    db_path = tmp_path / "fixture.db"
    conn = connect(str(db_path))
    run_migrations(conn)

    healthy = _identity("HEALTHY1")
    save_spec_identity(conn, healthy)
    save_snapshot(conn, _snapshot(healthy.stable_key(), "snap-healthy", spec_parts_hash="p1" * 32))
    save_manifest(
        conn,
        SpecGroupManifest(
            spec_key=healthy.stable_key(),
            source_capture_id="cap-healthy",
            discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
            categories=(ManifestCategory("engine", (ManifestGroupRef("1", "https://x/1"),)),),
            manifest_complete=True,
        ),
        run_id="run-1",
    )

    divergent = _identity("DIVERGENT1")
    save_spec_identity(conn, divergent)
    save_snapshot(
        conn,
        _snapshot(
            divergent.stable_key(),
            "snap-divergent",
            counts={"categories": 1, "groups": 5, "schemas": 5, "parts": 10},
            spec_parts_hash="p2" * 32,
        ),
    )
    save_manifest(
        conn,
        SpecGroupManifest(
            spec_key=divergent.stable_key(),
            source_capture_id="cap-divergent",
            discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
            categories=(
                ManifestCategory("engine", (ManifestGroupRef("1", "https://x/1"),)),
            ),  # manifest says 1, snapshot says 5
            manifest_complete=True,
        ),
        run_id="run-1",
    )

    incomplete = _identity("INCOMPLETE1")
    save_spec_identity(conn, incomplete)
    save_snapshot(
        conn,
        _snapshot(
            incomplete.stable_key(),
            "snap-incomplete",
            state=SnapshotState.INCOMPLETE,
            collection_complete=False,
            spec_parts_hash="p3" * 32,
        ),
    )

    zero_parts = _identity("2HBC34")
    save_spec_identity(conn, zero_parts)
    save_snapshot(
        conn,
        _snapshot(
            zero_parts.stable_key(),
            "snap-zero",
            counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 0},
            spec_parts_hash="p4" * 32,
        ),
    )

    conn.close()
    return db_path, {
        "healthy": healthy.stable_key(),
        "divergent": divergent.stable_key(),
        "incomplete": incomplete.stable_key(),
        "zero_parts": zero_parts.stable_key(),
    }


SCOPE_ARGS = ["--manufacturer", "VOLKSWAGEN", "--vehicle-model", "AMAROK", "--market", "AMA-BR"]


def test_summary_text_output(fixture_db, capsys):
    db_path, _ = fixture_db
    exit_code = main(["summary", *SCOPE_ARGS, "--db-path", str(db_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "specs descobertas: 4" in out


def test_summary_json_output_is_valid_json(fixture_db, capsys):
    db_path, _ = fixture_db
    exit_code = main(["summary", *SCOPE_ARGS, "--db-path", str(db_path), "--json"])
    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    assert payload["specs_discovered"] == 4
    assert payload["specs_with_zero_parts"] == 1


def test_quality_flags_manifest_divergence_and_incomplete_snapshot_and_zero_parts_as_info(
    fixture_db, capsys
):
    db_path, keys = fixture_db
    exit_code = main(["quality", *SCOPE_ARGS, "--db-path", str(db_path), "--json"])
    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    findings_by_spec: dict[str, list[str]] = {}
    for finding in payload["findings"]:
        findings_by_spec.setdefault(finding["spec_stable_key"], []).append(finding["code"])

    assert "MANIFEST_SNAPSHOT_GROUP_COUNT_MISMATCH" in findings_by_spec[keys["divergent"]]
    assert "SNAPSHOT_NOT_VALID" in findings_by_spec[keys["incomplete"]]
    assert "COLLECTION_NOT_COMPLETE" in findings_by_spec[keys["incomplete"]]

    zero_parts_finding = next(
        f
        for f in payload["findings"]
        if f["spec_stable_key"] == keys["zero_parts"] and f["code"] == "SPEC_WITH_ZERO_PARTS"
    )
    assert zero_parts_finding["severity"] == "INFO"


def test_quality_text_output(fixture_db, capsys):
    db_path, _ = fixture_db
    exit_code = main(["quality", *SCOPE_ARGS, "--db-path", str(db_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Qualidade da coleta" in out
    assert "MANIFEST_SNAPSHOT_GROUP_COUNT_MISMATCH" in out


def test_redundancy_json_output(fixture_db, capsys):
    db_path, _ = fixture_db
    exit_code = main(["redundancy", *SCOPE_ARGS, "--db-path", str(db_path), "--json"])
    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    # 4 specs distinct hashes each (p1/p2/p4 VALID+complete; p3 INCOMPLETE excluded)
    assert payload["specs_considered"] == 3
    assert payload["distinct_spec_parts_hash"] == 3


def test_redundancy_text_output_with_a_cluster_shows_human_readable_members(fixture_db, capsys):
    db_path, keys = fixture_db
    # Reuse the fixture db but insert a second spec sharing HEALTHY1's hash to exercise
    # the "clusters redundantes" rendering branch (fixture_db alone has no duplicate hash).
    conn = connect(str(db_path))
    twin = _identity("HEALTHYTWIN")
    save_spec_identity(conn, twin)
    save_snapshot(conn, _snapshot(twin.stable_key(), "snap-twin", spec_parts_hash="p1" * 32))
    conn.close()

    exit_code = main(["redundancy", *SCOPE_ARGS, "--db-path", str(db_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Redundância" in out
    assert "clusters redundantes (tamanho >= 2): 1" in out
    assert "Cluster — 2 specs" in out
    # model_code (não só o stable_key gigante) aparece na linha do membro.
    assert "HEALTHY1 | catalog 999 | 2020-2021" in out
    assert "HEALTHYTWIN | catalog 999 | 2020-2021" in out
    assert f"key={keys['healthy']}" in out


def test_redundancy_json_output_includes_structured_cluster_members(fixture_db, capsys):
    db_path, keys = fixture_db
    conn = connect(str(db_path))
    twin = _identity("HEALTHYTWIN")
    save_spec_identity(conn, twin)
    save_snapshot(conn, _snapshot(twin.stable_key(), "snap-twin", spec_parts_hash="p1" * 32))
    conn.close()

    exit_code = main(["redundancy", *SCOPE_ARGS, "--db-path", str(db_path), "--json"])
    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    cluster = payload["clusters"][0]
    assert cluster["size"] == 2
    healthy_member = next(m for m in cluster["members"] if m["stable_key"] == keys["healthy"])
    assert healthy_member["model_code"] == "HEALTHY1"
    assert healthy_member["amayama_catalog_id"] == "999"
    assert healthy_member["production_period_raw"] == "2020-2021"
    assert healthy_member["parts_count"] == 10
    # members ordenados por model_code -> determinístico
    assert [m["model_code"] for m in cluster["members"]] == ["HEALTHY1", "HEALTHYTWIN"]


def test_compare_two_specs(fixture_db, capsys):
    db_path, keys = fixture_db
    exit_code = main(
        [
            "compare",
            "--spec-a",
            keys["healthy"],
            "--spec-b",
            keys["divergent"],
            "--db-path",
            str(db_path),
            "--json",
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    assert payload["equivalence"]["parts_relation"] == "DIFFERENT"
    assert payload["hash_comparison"]["spec_parts_hash"] == "DIFFERENT"
    assert payload["group_diff"]["shared"] == ["engine/1"]
    assert payload["parts_diff_available"] is False


def test_compare_cross_market_specs_with_identical_hash_is_unknown_not_equal(fixture_db, capsys):
    """Codex finding #1 — a CLI deriva `scope` do spec A (_run_compare); este
    teste prova que isso não faz compare_specs() tratar erroneamente specs de
    mercados diferentes como comparáveis, mesmo com hash idêntico."""
    db_path, keys = fixture_db
    conn = connect(str(db_path))
    other_market = SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-OTHER",
        model_code="OTHERMARKET1",
        amayama_catalog_id="999",
        production_period_raw="2020-2021",
        source_url="https://amayama.example/OTHERMARKET1",
    )
    save_spec_identity(conn, other_market)
    save_snapshot(
        conn,
        _snapshot(other_market.stable_key(), "snap-other-market", spec_parts_hash="p1" * 32),
    )
    conn.close()

    exit_code = main(
        [
            "compare",
            "--spec-a",
            keys["healthy"],
            "--spec-b",
            other_market.stable_key(),
            "--db-path",
            str(db_path),
            "--json",
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    assert payload["equivalence"]["comparison_valid"] is False
    assert payload["equivalence"]["parts_relation"] == "UNKNOWN"
    assert payload["hash_comparison"]["spec_parts_hash"] == "UNAVAILABLE"


def test_compare_two_specs_text_output(fixture_db, capsys):
    db_path, keys = fixture_db
    exit_code = main(
        [
            "compare",
            "--spec-a",
            keys["healthy"],
            "--spec-b",
            keys["divergent"],
            "--db-path",
            str(db_path),
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Comparação" in out
    assert "diff de OEMs/peças: indisponível" in out


def test_compare_unknown_stable_key_returns_error_exit_code(fixture_db, capsys):
    db_path, keys = fixture_db
    exit_code = main(
        [
            "compare",
            "--spec-a",
            keys["healthy"],
            "--spec-b",
            "does-not-exist",
            "--db-path",
            str(db_path),
        ]
    )
    assert exit_code == 2
    assert "não encontrado" in capsys.readouterr().err


def test_nonexistent_db_path_returns_error_without_creating_file(tmp_path, capsys):
    missing_path = tmp_path / "missing.db"
    exit_code = main(["summary", *SCOPE_ARGS, "--db-path", str(missing_path)])
    assert exit_code == 2
    assert not missing_path.exists()
    assert "não encontrado" in capsys.readouterr().err


def test_invalid_sqlite_file_returns_short_stderr_message_no_traceback(tmp_path, capsys):
    """Codex finding #4 — arquivo existe mas não é um SQLite válido."""
    garbage_path = tmp_path / "garbage.db"
    garbage_path.write_bytes(b"this is not a sqlite database\x00\x01\x02")

    exit_code = main(["summary", *SCOPE_ARGS, "--db-path", str(garbage_path)])

    err = capsys.readouterr().err
    assert exit_code == 2
    assert err.strip()
    assert "Traceback" not in err


def test_empty_sqlite_db_without_schema_returns_short_stderr_message_no_traceback(tmp_path, capsys):
    """Codex finding #4 — SQLite válido, mas sem nenhuma migration aplicada."""
    empty_db_path = tmp_path / "empty.db"
    sqlite3.connect(str(empty_db_path)).close()

    exit_code = main(["summary", *SCOPE_ARGS, "--db-path", str(empty_db_path)])

    err = capsys.readouterr().err
    assert exit_code == 2
    assert err.strip()
    assert "Traceback" not in err
    assert "no such table" in err or "spec_registry" in err


def test_nonexistent_scope_returns_zeroed_summary_not_exception(fixture_db, capsys):
    db_path, _ = fixture_db
    exit_code = main(
        [
            "summary",
            "--manufacturer",
            "TOYOTA",
            "--vehicle-model",
            "HILUX",
            "--market",
            "BR",
            "--db-path",
            str(db_path),
            "--json",
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    assert payload["specs_discovered"] == 0
