"""resolve_image() — contracts/image-contract.md "Resolução de imagem".

Interpretação documentada (composição, sem inventar novo sinal): `spec_entry`
e `cluster` do contrato são compostos aqui como parâmetros explícitos —
`spec_identity_ref`+`own_image_refs` (a spec em questão) e
`cluster`+`member_own_image_refs` (o cluster já comprovado, Phase 8, e as
`own_image_refs` conhecidas de cada membro). `ResolvedImage.image_url_or_ref`
é uma referência única — quando várias `own_image_refs` existem, a
referência canônica escolhida é a lexicograficamente menor (desempate
determinístico, mesmo padrão de `research.md` §12 critério 5), nunca uma
ordem de descoberta incidental.
"""

from __future__ import annotations

from collections.abc import Mapping

from amayama_scraper.assets.types import ResolvedImage
from amayama_scraper.equivalence.cluster_types import EquivalenceClass


def resolve_image(
    *,
    spec_identity_ref: str,
    own_image_refs: tuple[str, ...],
    cluster: EquivalenceClass | None,
    member_own_image_refs: Mapping[str, tuple[str, ...]],
) -> ResolvedImage | None:
    if own_image_refs:
        return ResolvedImage(
            spec_identity_ref=spec_identity_ref,
            origin_spec_ref=spec_identity_ref,
            image_url_or_ref=min(own_image_refs),
            is_fallback=False,
        )

    if cluster is not None and spec_identity_ref in cluster.member_spec_refs:
        candidate_origins = sorted(
            member_ref
            for member_ref in cluster.member_spec_refs
            if member_ref != spec_identity_ref and member_own_image_refs.get(member_ref)
        )
        if candidate_origins:
            origin = candidate_origins[0]
            return ResolvedImage(
                spec_identity_ref=spec_identity_ref,
                origin_spec_ref=origin,
                image_url_or_ref=min(member_own_image_refs[origin]),
                is_fallback=True,
                resolved_within_cluster_key=cluster.cluster_key,
            )

    return None
