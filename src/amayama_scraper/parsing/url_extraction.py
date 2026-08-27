"""extract_category_and_group_from_url() — research.md §19.

Contrato v1: os dois segmentos finais do path da URL de um group detail.
Ex.: ".../s1bc3x-56087/front-axle-steering/407" -> ("front-axle-steering", "407").
Falha explícita (drift estrutural) quando a URL não tem esse formato —
nunca infere a partir de texto visível/traduzido da página.
"""

from __future__ import annotations

from urllib.parse import urlparse


class UrlStructuralDriftError(ValueError):
    """A URL não tem o formato de 2 segmentos finais esperado (research.md §19)."""


def extract_category_and_group_from_url(source_url: str) -> tuple[str, str]:
    path = urlparse(source_url).path
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        raise UrlStructuralDriftError(
            f"expected at least 2 path segments (category_slug, group_id) in {source_url!r}, "
            f"got {segments!r}"
        )
    category_slug, group_id = segments[-2], segments[-1]
    return category_slug, group_id
