"""parse_spec_group_manifest() — Nível B (contracts/domain-contracts.md "Nível B").

Seletores comprovados contra evidência real capturada manualmente em
2026-08-26 (browser-in-the-loop, DEC-001) — ver research.md §21. Produz o
`SpecGroupManifest` autoritativo do universo esperado de `(category_slug,
group_id)` (data-model.md §15).

Interpretação documentada (composição dos seletores evidenciados, sem
inventar nenhum novo): o link `.epcVariation__schemaGroup` com
`data-id=""` ("All") nunca representa uma categoria de domínio e é sempre
ignorado; a invariante `card data-id == último segmento da URL do card` e
"category_slug do card está entre as categorias declaradas na navegação"
são ambas tratadas como `critical_error` do manifesto inteiro quando
violadas — nunca é escolhido um valor arbitrariamente entre os dois lados
de uma divergência (research.md §21).

`manifest_complete` — limitação de observabilidade registrada em
research.md §21: não existe, na evidência estática atual, nenhum sinal que
distinga "manifesto legitimamente menor" de "manifesto truncado mas
estruturalmente perfeito" (ex.: lazy-load de infinite scroll incompleto).
O único sinal realmente observável e usado aqui é o caso degenerado
"container de groups presente, mas vazio, apesar de a navegação declarar
categorias" — tratado como `manifest_complete=False`. Nenhuma contagem/
cardinalidade é usada como heurística.

parser_version = "amayama-spec-group-manifest-parser-v1" (Constitution §13).
"""

from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup
from bs4.element import Tag

from amayama_scraper.domain.hierarchy import DuplicateGroupIdError
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.parsing import selectors
from amayama_scraper.parsing.results import ParseError, ParseManifestResult

PARSER_VERSION = "amayama-spec-group-manifest-parser-v1"


def _category_slug_from_href(href: str) -> str:
    return href.rstrip("/").rsplit("/", 1)[-1]


def _declared_category_slugs(nav: Tag) -> set[str]:
    slugs: set[str] = set()
    for link in nav.select(selectors.SPEC_NAV_CATEGORY_LINK):
        data_id = link.get("data-id")
        if not data_id:
            continue  # the "All" link (data-id="") — never a domain category
        href = link.get("href")
        if not href:
            continue
        slugs.add(_category_slug_from_href(str(href)))
    return slugs


def parse_spec_group_manifest(
    html: str, spec_key: str, source_capture_id: str
) -> ParseManifestResult:
    soup = BeautifulSoup(html, "lxml")

    if soup.select_one(selectors.SPEC_NAV_DETAILS) is None:
        return ParseManifestResult(
            critical_error=ParseError(
                message=f"missing expected root marker {selectors.SPEC_NAV_DETAILS!r}"
            ),
            parser_version=PARSER_VERSION,
        )

    nav = soup.select_one(selectors.SPEC_NAV_CATEGORY_NAV)
    if nav is None:
        return ParseManifestResult(
            critical_error=ParseError(
                message=f"missing expected category nav {selectors.SPEC_NAV_CATEGORY_NAV!r}"
            ),
            parser_version=PARSER_VERSION,
        )
    declared_slugs = _declared_category_slugs(nav)

    groups_container = soup.select_one(selectors.SPEC_NAV_GROUPS_CONTAINER)
    if groups_container is None:
        return ParseManifestResult(
            critical_error=ParseError(
                message=f"missing expected groups container {selectors.SPEC_NAV_GROUPS_CONTAINER!r}"
            ),
            parser_version=PARSER_VERSION,
        )

    cards = groups_container.select(selectors.SPEC_NAV_GROUP_CARD)
    parse_errors: list[ParseError] = []
    by_category: dict[str, list[ManifestGroupRef]] = {}

    for card in cards:
        data_id = card.get("data-id")
        name_link = card.select_one(selectors.SPEC_NAV_GROUP_NAME_LINK)
        href = name_link.get("href") if name_link is not None else None
        if not data_id or not href:
            parse_errors.append(ParseError(message="group card missing data-id or name link href"))
            continue
        href = str(href)

        path_segments = href.rstrip("/").split("/")
        if len(path_segments) < 2:
            return ParseManifestResult(
                critical_error=ParseError(
                    message="group card href does not have 2 trailing path segments",
                    context={"href": href},
                ),
                parser_version=PARSER_VERSION,
            )
        group_id_from_url, category_slug = path_segments[-1], path_segments[-2]

        if group_id_from_url != data_id:
            return ParseManifestResult(
                critical_error=ParseError(
                    message="group card data-id diverges from href last path segment",
                    context={"data_id": str(data_id), "href_group_id": group_id_from_url},
                ),
                parser_version=PARSER_VERSION,
            )

        if category_slug not in declared_slugs:
            return ParseManifestResult(
                critical_error=ParseError(
                    message="group card category_slug not declared in category nav",
                    context={"category_slug": category_slug, "href": href},
                ),
                parser_version=PARSER_VERSION,
            )

        by_category.setdefault(category_slug, []).append(
            ManifestGroupRef(group_id=str(data_id), source_url=href)
        )

    try:
        categories = tuple(
            ManifestCategory(category_slug=slug, groups=tuple(refs))
            for slug, refs in by_category.items()
        )
    except DuplicateGroupIdError as exc:
        return ParseManifestResult(
            critical_error=ParseError(message=str(exc)),
            parser_version=PARSER_VERSION,
        )

    group_count = sum(len(cat.groups) for cat in categories)
    manifest_complete = not (declared_slugs and group_count == 0)

    manifest = SpecGroupManifest(
        spec_key=spec_key,
        source_capture_id=source_capture_id,
        discovered_at=datetime.now(UTC),
        categories=categories,
        manifest_complete=manifest_complete,
        validation_evidence={
            "category_count": len(declared_slugs),
            "group_count": group_count,
        },
    )

    return ParseManifestResult(
        manifest=manifest,
        parse_errors=tuple(parse_errors),
        critical_error=None,
        parser_version=PARSER_VERSION,
    )
