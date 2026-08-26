"""T230 — revalidação NUNCA afirma que um Group mudou (ou não) sem recomputar seu
group_fingerprint a partir de captura real (ponto 18 do PLAN).

revalidate_spec_entry() só aceita duas árvores já reconstruídas (AssembledSpecTree)
— não existe nenhum parâmetro de "assumir sem mudança"/cache de terceiros; toda
comparação recomputa group_fingerprint/category_fingerprint dos dois lados.
"""

import inspect

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.snapshots.revalidation import revalidate_spec_entry


def test_signature_has_no_assume_unchanged_or_cache_parameter():
    params = set(inspect.signature(revalidate_spec_entry).parameters)
    assert params == {"previous_tree", "current_tree"}


def test_group_absent_from_one_side_is_never_silently_assumed_unchanged():
    previous = (Category("engine", groups=(Group("1"), Group("2"))),)
    current = (Category("engine", groups=(Group("1"),)),)  # group "2" no longer captured

    report = revalidate_spec_entry(previous, current)
    assert ("engine", "2") in report.divergent_group_keys


def test_identical_group_content_produces_no_divergence_only_because_recomputed_equal():
    def _tree():
        return (
            Category(
                "engine",
                groups=(Group("1", schemas=(Schema("s1", parts=(Part("s1", "SAME"),)),)),),
            ),
        )

    report = revalidate_spec_entry(_tree(), _tree())
    assert report.divergent_group_keys == ()
