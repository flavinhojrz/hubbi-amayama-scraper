"""T016 — build_redundancy_report(): cluster de tamanho 2 + isolada, distintos por hash,
taxa de redução, exclusão de snapshot INCOMPLETE/INVALID (Constitution §11)."""

from datetime import UTC, datetime

from amayama_scraper.analysis.redundancy import build_redundancy_report
from amayama_scraper.analysis.types import ScopeIdentifier
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.persistence.repositories.snapshot_repo import UNAVAILABLE_HASH
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

SCOPE = ScopeIdentifier(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")

SHARED_PARTS_HASH = "a" * 64
UNIQUE_PARTS_HASH = "b" * 64


def _identity(
    model_code: str,
    *,
    amayama_catalog_id: str = "999",
    production_period_raw: str = "2020-2021",
    grade: str | None = None,
    configuration: str | None = None,
    market: str = "AMA-BR",
) -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market=market,
        model_code=model_code,
        amayama_catalog_id=amayama_catalog_id,
        production_period_raw=production_period_raw,
        source_url=f"https://amayama.example/{model_code}-{market}",
        grade=grade,
        configuration=configuration,
    )


def _snapshot(
    spec_ref: str,
    *,
    spec_parts_hash: str,
    structure_hash: str = "s" * 64,
    schema_semantic_hash: str = "c" * 64,
    image_hash: str = "i" * 64,
    state: SnapshotState = SnapshotState.VALID,
    collection_complete: bool = True,
    counts: dict[str, int] | None = None,
) -> SpecSnapshot:
    return SpecSnapshot(
        snapshot_id=f"snap-{spec_ref[:8]}",
        spec_identity_ref=spec_ref,
        idempotency_key=f"idem-{spec_ref[:8]}",
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="p1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=collection_complete,
        structure_hash=structure_hash,
        spec_parts_hash=spec_parts_hash,
        schema_semantic_hash=schema_semantic_hash,
        image_hash=image_hash,
        state=state,
        counts=counts or {"categories": 1, "groups": 1, "schemas": 1, "parts": 1},
    )


def test_two_identical_and_one_distinct_spec_parts_hash_forms_one_cluster_and_one_isolated():
    spec_1 = _identity("R1")
    spec_2 = _identity("R2")
    spec_3 = _identity("R3")
    latest = {
        spec_1.stable_key(): _snapshot(spec_1.stable_key(), spec_parts_hash=SHARED_PARTS_HASH),
        spec_2.stable_key(): _snapshot(spec_2.stable_key(), spec_parts_hash=SHARED_PARTS_HASH),
        spec_3.stable_key(): _snapshot(spec_3.stable_key(), spec_parts_hash=UNIQUE_PARTS_HASH),
    }

    report = build_redundancy_report(SCOPE, [spec_1, spec_2, spec_3], latest)

    assert report.specs_considered == 3
    assert report.distinct_spec_parts_hash == 2
    assert len(report.clusters) == 1
    assert report.clusters[0].size == 2
    assert {m.stable_key for m in report.clusters[0].members} == {
        spec_1.stable_key(),
        spec_2.stable_key(),
    }
    assert report.isolated_spec_count == 1
    assert report.largest_cluster_size == 2
    assert report.potential_reduction_ratio == (3 - 2) / 3


def test_incomplete_snapshot_is_excluded_from_redundancy_calculation():
    spec_valid = _identity("R4")
    spec_incomplete = _identity("R5")
    latest = {
        spec_valid.stable_key(): _snapshot(
            spec_valid.stable_key(), spec_parts_hash=SHARED_PARTS_HASH
        ),
        spec_incomplete.stable_key(): _snapshot(
            spec_incomplete.stable_key(),
            spec_parts_hash=SHARED_PARTS_HASH,
            state=SnapshotState.INCOMPLETE,
            collection_complete=False,
        ),
    }

    report = build_redundancy_report(SCOPE, [spec_valid, spec_incomplete], latest)

    assert report.specs_considered == 1
    assert report.distinct_spec_parts_hash == 1
    assert report.clusters == ()
    assert report.isolated_spec_count == 1


def test_distinct_hash_counts_cover_all_four_fingerprint_fields():
    spec_1 = _identity("R6")
    spec_2 = _identity("R7")
    latest = {
        spec_1.stable_key(): _snapshot(
            spec_1.stable_key(),
            spec_parts_hash=SHARED_PARTS_HASH,
            structure_hash="s1" * 32,
            schema_semantic_hash="c1" * 32,
            image_hash="i1" * 32,
        ),
        spec_2.stable_key(): _snapshot(
            spec_2.stable_key(),
            spec_parts_hash=SHARED_PARTS_HASH,
            structure_hash="s2" * 32,
            schema_semantic_hash="c2" * 32,
            image_hash="i2" * 32,
        ),
    }

    report = build_redundancy_report(SCOPE, [spec_1, spec_2], latest)

    assert report.distinct_spec_parts_hash == 1
    assert report.distinct_structure_hash == 2
    assert report.distinct_schema_semantic_hash == 2
    assert report.distinct_image_hash == 2


def test_empty_scope_returns_zeros_without_division_by_zero():
    report = build_redundancy_report(SCOPE, [], {})

    assert report.specs_considered == 0
    assert report.potential_reduction_ratio == 0.0
    assert report.clusters == ()


def test_unavailable_fingerprint_is_excluded_and_never_clustered():
    """Codex finding #5 — duas specs com o MESMO valor de spec_parts_hash
    UNAVAILABLE_HASH (hash NULL no banco, mesmo sentinel para ambas) nunca
    podem ser tratadas como um cluster de equivalência técnica."""
    spec_valid = _identity("R8")
    spec_unavailable_a = _identity("R9")
    spec_unavailable_b = _identity("R10")
    latest = {
        spec_valid.stable_key(): _snapshot(
            spec_valid.stable_key(), spec_parts_hash=SHARED_PARTS_HASH
        ),
        spec_unavailable_a.stable_key(): _snapshot(
            spec_unavailable_a.stable_key(), spec_parts_hash=UNAVAILABLE_HASH
        ),
        spec_unavailable_b.stable_key(): _snapshot(
            spec_unavailable_b.stable_key(), spec_parts_hash=UNAVAILABLE_HASH
        ),
    }

    report = build_redundancy_report(
        SCOPE, [spec_valid, spec_unavailable_a, spec_unavailable_b], latest
    )

    assert report.specs_considered == 1
    assert report.distinct_spec_parts_hash == 1
    assert report.clusters == ()
    assert report.isolated_spec_count == 1


def test_cluster_members_expose_human_readable_spec_registry_and_snapshot_fields():
    """PO follow-up — stable_key sozinho não basta para ler um cluster; cada
    membro deve trazer model_code/amayama_catalog_id/production_period_raw/
    grade/configuration (de SpecIdentity, já disponível) e parts_count (de
    SpecSnapshot.counts, já disponível) — nenhuma leitura nova de repositório."""
    spec = _identity(
        "S7BA53",
        amayama_catalog_id="61156",
        production_period_raw="2016.06-2019.08",
        grade="Highline",
        configuration="4Motion",
    )
    twin = _identity("S7BA54", amayama_catalog_id="61157")
    latest = {
        spec.stable_key(): _snapshot(
            spec.stable_key(),
            spec_parts_hash=SHARED_PARTS_HASH,
            counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 5432},
        ),
        twin.stable_key(): _snapshot(twin.stable_key(), spec_parts_hash=SHARED_PARTS_HASH),
    }

    report = build_redundancy_report(SCOPE, [spec, twin], latest)

    member = next(m for m in report.clusters[0].members if m.stable_key == spec.stable_key())
    assert member.model_code == "S7BA53"
    assert member.amayama_catalog_id == "61156"
    assert member.production_period_raw == "2016.06-2019.08"
    assert member.grade == "Highline"
    assert member.configuration == "4Motion"
    assert member.parts_count == 5432


def test_cluster_members_are_sorted_by_model_code_then_catalog_id_then_stable_key():
    """Prova os 3 níveis de desempate de (model_code, amayama_catalog_id,
    stable_key), não apenas o primeiro:

    - nível 1 (model_code): "A" < "B" decide entre spec_a200 e o grupo "B";
    - nível 2 (amayama_catalog_id): dentro de model_code "B", catalog "050"
      vem antes de "100";
    - nível 3 (stable_key): duas specs com o MESMO model_code ("B") E o MESMO
      amayama_catalog_id ("100") só podem coexistir com stable_key diferente
      se outro campo de identidade também diferir — aqui usamos `market`, que
      participa do stable_key (domain/identity.py) mas não da formação do
      cluster (a clusterização usa o `scope` externo via
      equivalence/cluster.py::cluster_key(), nunca spec.market).
    """
    spec_a200 = _identity("A", amayama_catalog_id="200")
    spec_b050 = _identity("B", amayama_catalog_id="050")
    spec_b100_x = _identity("B", amayama_catalog_id="100", market="AMA-BR")
    spec_b100_y = _identity("B", amayama_catalog_id="100", market="AMA-OTHER")

    assert spec_b100_x.model_code == spec_b100_y.model_code == "B"
    assert spec_b100_x.amayama_catalog_id == spec_b100_y.amayama_catalog_id == "100"
    assert spec_b100_x.stable_key() != spec_b100_y.stable_key()  # pré-condição da fixture

    specs = [spec_b100_y, spec_b050, spec_b100_x, spec_a200]  # ordem de entrada embaralhada
    latest = {
        spec.stable_key(): _snapshot(spec.stable_key(), spec_parts_hash=SHARED_PARTS_HASH)
        for spec in specs
    }

    # Executado com duas ordens de entrada distintas — a saída nunca deve
    # depender da ordem de iteração de dict/set.
    report_1 = build_redundancy_report(SCOPE, specs, latest)
    report_2 = build_redundancy_report(SCOPE, list(reversed(specs)), latest)

    expected_stable_key_order = [
        spec_a200.stable_key(),
        spec_b050.stable_key(),
        *sorted([spec_b100_x.stable_key(), spec_b100_y.stable_key()]),
    ]

    for report in (report_1, report_2):
        assert len(report.clusters) == 1
        members = report.clusters[0].members
        assert len(members) == 4

        # Nível 1: model_code manda primeiro ("A" antes de qualquer "B").
        assert [m.model_code for m in members] == ["A", "B", "B", "B"]

        # Nível 2: dentro do mesmo model_code "B", amayama_catalog_id decide
        # ("050" antes de "100").
        assert [m.amayama_catalog_id for m in members] == ["200", "050", "100", "100"]

        # Nível 3: entre os dois "B"/"100" (empate nos dois primeiros
        # critérios), o desempate final é stable_key, ordem alfabética.
        assert [m.stable_key for m in members] == expected_stable_key_order
