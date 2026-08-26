"""assemble_spec_tree() — montagem da árvore agregada (contracts/domain-contracts.md).

Combina o manifesto (universo esperado) com os ParsedGroupDetail já
disponíveis. Groups ainda não capturados são omitidos (não fabricados
como "vazios") — um Group verdadeiramente vazio (já ACCEPTED, sem
schemas/parts) é distinto e É incluído. A decisão de completude
(collection_complete) é responsabilidade de quem chama esta função
(contracts/snapshot-contract.md), não desta função.
"""

from __future__ import annotations

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.manifest import SpecGroupManifest
from amayama_scraper.parsing.results import ParsedGroupDetail

GroupDetailsByKey = dict[tuple[str, str], ParsedGroupDetail]


def assemble_spec_tree(
    manifest: SpecGroupManifest, group_details: GroupDetailsByKey
) -> tuple[Category, ...]:
    categories: list[Category] = []

    for manifest_category in manifest.categories:
        groups: list[Group] = []
        for group_ref in manifest_category.groups:
            detail = group_details.get((manifest_category.category_slug, group_ref.group_id))
            if detail is None:
                continue  # ainda não capturado — omitido, não fabricado como vazio
            schemas = tuple(
                Schema(
                    schema_id=parsed_schema.schema_id,
                    parts=tuple(p.to_part() for p in parsed_schema.parts),
                )
                for parsed_schema in detail.schemas
            )
            groups.append(Group(group_id=group_ref.group_id, schemas=schemas))

        if groups:
            categories.append(
                Category(category_slug=manifest_category.category_slug, groups=tuple(groups))
            )

    return tuple(categories)
