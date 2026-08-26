"""revalidate_spec_entry() — contracts/equivalence-contracts.md "Revalidação incremental".

Interpretação documentada: como `SpecSnapshot` persiste apenas o
`FingerprintSet` agregado (não fingerprints por category/group), a
localização hierárquica de divergência exige as DUAS árvores já
reconstruídas (`previous_tree`/`current_tree` — ambas via o mesmo caminho
de reconstrução determinística de `snapshots/finalize.py`, nunca a partir
de estado em memória de uma execução anterior). `structure_hash` é
comparado primeiro (mais barato); só quando ele (ou `spec_parts_hash`)
diverge é que a localização por `category_fingerprint`/`group_fingerprint`
é calculada — e mesmo essa localização sempre recomputa os fingerprints
reais dos dois lados (nunca assume que um Group não mudou sem recomputar
seu `group_fingerprint`, ponto 18 do PLAN).
"""

from __future__ import annotations

from dataclasses import dataclass

from amayama_scraper.fingerprints.category import category_fingerprint
from amayama_scraper.fingerprints.group import group_fingerprint
from amayama_scraper.fingerprints.spec import AssembledSpecTree
from amayama_scraper.fingerprints.version import compute_fingerprint_set


@dataclass(frozen=True, slots=True)
class RevalidationReport:
    structure_changed: bool
    content_changed: bool
    schema_changed: bool
    image_changed: bool
    divergent_category_slugs: tuple[str, ...] = ()
    divergent_group_keys: tuple[tuple[str, str], ...] = ()

    @property
    def is_stale(self) -> bool:
        return self.structure_changed or self.content_changed or self.schema_changed


def revalidate_spec_entry(
    previous_tree: AssembledSpecTree, current_tree: AssembledSpecTree
) -> RevalidationReport:
    previous_fp = compute_fingerprint_set(previous_tree)
    current_fp = compute_fingerprint_set(current_tree)

    structure_changed = current_fp.structure_hash != previous_fp.structure_hash
    content_changed = current_fp.spec_parts_hash != previous_fp.spec_parts_hash
    schema_changed = current_fp.schema_semantic_hash != previous_fp.schema_semantic_hash
    image_changed = current_fp.image_hash != previous_fp.image_hash

    divergent_category_slugs: tuple[str, ...] = ()
    divergent_group_keys: tuple[tuple[str, str], ...] = ()

    if structure_changed or content_changed:
        previous_categories = {c.category_slug: c for c in previous_tree}
        current_categories = {c.category_slug: c for c in current_tree}
        all_slugs = set(previous_categories) | set(current_categories)

        divergent_slugs = []
        for slug in sorted(all_slugs):
            prev_cat = previous_categories.get(slug)
            cur_cat = current_categories.get(slug)
            prev_hash = category_fingerprint(prev_cat) if prev_cat is not None else None
            cur_hash = category_fingerprint(cur_cat) if cur_cat is not None else None
            if prev_hash != cur_hash:
                divergent_slugs.append(slug)
        divergent_category_slugs = tuple(divergent_slugs)

        divergent_groups: list[tuple[str, str]] = []
        for slug in divergent_category_slugs:
            prev_cat = previous_categories.get(slug)
            cur_cat = current_categories.get(slug)
            prev_groups = {g.group_id: g for g in prev_cat.groups} if prev_cat is not None else {}
            cur_groups = {g.group_id: g for g in cur_cat.groups} if cur_cat is not None else {}
            for group_id in sorted(set(prev_groups) | set(cur_groups)):
                prev_g = prev_groups.get(group_id)
                cur_g = cur_groups.get(group_id)
                prev_gh = group_fingerprint(prev_g) if prev_g is not None else None
                cur_gh = group_fingerprint(cur_g) if cur_g is not None else None
                if prev_gh != cur_gh:
                    divergent_groups.append((slug, group_id))
        divergent_group_keys = tuple(divergent_groups)

    return RevalidationReport(
        structure_changed=structure_changed,
        content_changed=content_changed,
        schema_changed=schema_changed,
        image_changed=image_changed,
        divergent_category_slugs=divergent_category_slugs,
        divergent_group_keys=divergent_group_keys,
    )
