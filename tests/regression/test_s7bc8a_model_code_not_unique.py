"""T248 — S7BC8A-62184 vs S7BC8A-61189: model_code isolado nunca é identidade
suficiente (FR-003, SC-002, SC-006; Constitution §2).

Escopo desta regressão (clarificação pontual da T248, aprovada pelo PO em
2026-08-27): a redação original da task apontava para "manifests" (nível
SPEC_NAVIGATION). Nenhum manifest.html real e nenhum group-detail real
existem no workspace para `S7BC8A-61189` — apenas a evidência real de nível
MARKET_INDEX já aprovada (DEC-001) em
`tests/fixtures/market_index/same_model_code_diff_catalog.html` contém as
duas linhas reais (mesma `model_code`, `catalog_id` distinto). Como a
propriedade sob teste aqui é IDENTIDADE de catálogo — não equivalência
semântica de peças — a evidência MARKET_INDEX é suficiente e mais
diretamente alinhada à regra sendo validada (Constitution §2:
"`model_code` sozinho não identifica uma entrada de catálogo"). Esta
regressão não depende de group-detail nem de SpecSnapshot; exercita
exclusivamente `parse_market_spec_index()` -> `DiscoveredSpecEntry` ->
`SpecIdentity.stable_key()`, sem hardcode de model_code/catalog_id na
lógica de produção — os códigos aparecem apenas como dado de teste.

T245-T247 permanecem bloqueadas até a materialização de manifests
SPEC_NAVIGATION reais completos (ver tests/regression/README.md e a nota
de revisão em tasks.md datada de 2026-08-27).
"""

from __future__ import annotations

from pathlib import Path

from amayama_scraper.parsing.market_index import parse_market_spec_index

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "market_index"


def test_s7bc8a_same_model_code_different_catalog_id_yields_different_identity():
    html = (FIXTURES / "same_model_code_diff_catalog.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-s7bc8a-regression")

    assert result.critical_error is None
    assert len(result.entries) == 2

    by_catalog_id = {entry.amayama_catalog_id: entry for entry in result.entries}
    assert set(by_catalog_id) == {"62184", "61189"}

    entry_62184 = by_catalog_id["62184"]
    entry_61189 = by_catalog_id["61189"]

    # Same model_code on both real rows — the exact condition FR-003 guards against.
    assert entry_62184.model_code == "S7BC8A"
    assert entry_61189.model_code == "S7BC8A"
    assert entry_62184.model_code == entry_61189.model_code

    # catalog_id genuinely differs between the two real entries.
    assert entry_62184.amayama_catalog_id != entry_61189.amayama_catalog_id

    identity_62184 = entry_62184.to_spec_identity(
        source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK"
    )
    identity_61189 = entry_61189.to_spec_identity(
        source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK"
    )

    # Both identities still carry the same model_code...
    assert identity_62184.model_code == identity_61189.model_code == "S7BC8A"
    # ...but the resulting stable_key/display_key are different: model_code
    # alone is never sufficient to identify a spec entry (Constitution §2).
    assert identity_62184.stable_key() != identity_61189.stable_key()
    assert identity_62184.display_key() != identity_61189.display_key()


def test_s7bc8a_stable_key_depends_on_catalog_id_not_only_model_code():
    html = (FIXTURES / "same_model_code_diff_catalog.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-s7bc8a-regression-2")

    entries_by_catalog_id = {e.amayama_catalog_id: e for e in result.entries}
    identities = {
        catalog_id: entry.to_spec_identity(
            source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK"
        )
        for catalog_id, entry in entries_by_catalog_id.items()
    }

    # Grouping real identities purely by model_code would incorrectly merge
    # two distinct real catalog entries into one bucket — proving that any
    # production code path keyed on model_code alone (instead of
    # SpecIdentity.stable_key()) would silently lose real catalog identity.
    grouped_by_model_code_only: dict[str, list[str]] = {}
    for identity in identities.values():
        grouped_by_model_code_only.setdefault(identity.model_code, []).append(identity.stable_key())

    assert len(grouped_by_model_code_only) == 1  # a single model_code bucket...
    stable_keys_in_bucket = grouped_by_model_code_only["S7BC8A"]
    assert len(set(stable_keys_in_bucket)) == 2  # ...hides two distinct real identities
