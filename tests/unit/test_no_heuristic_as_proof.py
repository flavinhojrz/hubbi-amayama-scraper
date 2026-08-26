"""T144 — candidatos heurísticos nunca influenciam can_deduplicate() (FR-020).

can_deduplicate() aceita apenas os dois SpecSnapshot e o scope de cada
lado — nenhum parâmetro de "candidato"/"score"/"similaridade" existe na
assinatura, e o resultado depende exclusivamente de hash exato
(spec_parts_hash), nunca de um sinal heurístico externo.
"""

import inspect
from datetime import UTC, datetime

from amayama_scraper.equivalence.evaluate import can_deduplicate
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def _snapshot(**overrides: object) -> SpecSnapshot:
    defaults: dict[str, object] = dict(
        snapshot_id="snap-1",
        spec_identity_ref="spec-1",
        idempotency_key="idem-1",
        collected_at=datetime.now(UTC),
        parser_version="amayama-parser-v1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=True,
        structure_hash="s" * 64,
        spec_parts_hash="p" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="i" * 64,
        state=SnapshotState.VALID,
    )
    defaults.update(overrides)
    return SpecSnapshot(**defaults)  # type: ignore[arg-type]


def test_signature_has_no_heuristic_style_parameter():
    params = set(inspect.signature(can_deduplicate).parameters)
    assert params == {"a", "b", "scope_a", "scope_b"}


def test_near_identical_but_not_hash_equal_snapshots_cannot_deduplicate():
    # e.g. two specs whose model_code shares a prefix and whose parts are
    # almost identical except one OEM digit — a text/prefix heuristic could
    # flag these as "candidates", but only exact hash equality proves it.
    a = _snapshot(spec_parts_hash="a" * 63 + "1")
    b = _snapshot(spec_parts_hash="a" * 63 + "2")
    assert can_deduplicate(a, b, scope_a=SCOPE, scope_b=SCOPE) is False
