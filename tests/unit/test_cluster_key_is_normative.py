"""T157 — cluster_key recomputado é sempre a fonte da verdade (ponto 14 do PLAN).

Nenhuma estrutura auxiliar (DSU/Union-Find) foi implementada nesta feature
— este teste documenta e trava a invariante para quando uma existir:
recomputar cluster_key a partir dos mesmos inputs sempre produz o mesmo
valor, independente de qualquer cache/estrutura auxiliar externa.
"""

from amayama_scraper.equivalence.cluster import cluster_key

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_recomputing_from_the_same_inputs_is_always_authoritative():
    kwargs = dict(
        scope=SCOPE, normalizer_version="v1", fingerprint_version="v1", spec_parts_hash="x" * 64
    )
    first = cluster_key(**kwargs)
    second = cluster_key(**kwargs)
    third = cluster_key(**kwargs)
    assert first == second == third
