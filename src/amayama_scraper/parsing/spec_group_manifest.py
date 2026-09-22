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

`manifest_complete` — CORREÇÃO (bug de manifest truncado, auditoria real:
57,46% dos manifests Volkswagen BR truncados, ex. Saveiro com 4/10
categorias e 5/75 grupos salvos como "completo"): esta função parseia UMA
página (a base da spec OU a página dedicada de UMA categoria) e NUNCA pode,
sozinha, provar que o universo de grupos está completo — a página base
frequentemente mostra cards de apenas um subconjunto das categorias
declaradas em `.epcVariation__schemaGroups`. Por isso `manifest_complete` é
sempre `False` aqui, incondicionalmente; só `orchestration.collection_driver.
discover_spec_manifest()` pode marcar `True`, e apenas depois de visitar e
parsear com sucesso TODAS as categorias declaradas (uma por uma, cada
uma via esta mesma função aplicada à página da categoria). `validation_
evidence["declared_category_urls"]` carrega o mapa `{category_slug: url}`
extraído da navegação desta página — é o que permite ao orquestrador saber
quais categorias ainda precisa visitar.

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


def _declared_categories(nav: Tag) -> dict[str, str]:
    """slug -> URL for every declared domain category (never the "All" link).

    The URL is what lets the orchestrator visit each declared category on
    its own page (root-cause fix) — dropped by the old `_declared_category_slugs()`,
    which only needed the slug for the (insufficient) same-page completeness check.
    """
    categories: dict[str, str] = {}
    for link in nav.select(selectors.SPEC_NAV_CATEGORY_LINK):
        data_id = link.get("data-id")
        if not data_id:
            continue  # the "All" link (data-id="") — never a domain category
        href = link.get("href")
        if not href:
            continue
        categories[_category_slug_from_href(str(href))] = str(href)
    return categories


def parse_spec_group_manifest(
    html: str, spec_key: str, source_capture_id: str, *, expected_category_slug: str | None = None
) -> ParseManifestResult:
    """`expected_category_slug` (bug fix, evidência real 2026-09-10): quando a
    página parseada é a de UMA categoria específica (não a base da spec), o
    site NUNCA renderiza `.epcVariation__schemaGroups` nela — só a página
    base ("all schemas") tem essa nav; exigi-la incondicionalmente fazia
    TODA visita de categoria ser rejeitada em produção (0 grupos aceitos
    apesar de a página conter `.epcVariation__schemas` real e válido).
    Quando fornecido, a nav deixa de ser obrigatória: os cards da página são
    validados contra o slug já conhecido pelo chamador (a própria URL
    visitada), em vez de depender da nav ausente."""
    soup = BeautifulSoup(html, "lxml")

    if soup.select_one(selectors.SPEC_NAV_DETAILS) is None:
        return ParseManifestResult(
            critical_error=ParseError(
                message=f"missing expected root marker {selectors.SPEC_NAV_DETAILS!r}"
            ),
            parser_version=PARSER_VERSION,
        )

    nav = soup.select_one(selectors.SPEC_NAV_CATEGORY_NAV)
    if nav is not None:
        declared_category_urls = _declared_categories(nav)
        declared_slugs = set(declared_category_urls)
    elif expected_category_slug is not None:
        declared_category_urls = {}
        declared_slugs = {expected_category_slug}
    else:
        return ParseManifestResult(
            critical_error=ParseError(
                message=f"missing expected category nav {selectors.SPEC_NAV_CATEGORY_NAV!r}"
            ),
            parser_version=PARSER_VERSION,
        )

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

    manifest = SpecGroupManifest(
        spec_key=spec_key,
        source_capture_id=source_capture_id,
        discovered_at=datetime.now(UTC),
        categories=categories,
        # A single page (base or one category's own) never proves the full
        # universe is covered — see module docstring. Only the multi-page
        # assembler (orchestration/collection_driver.py::discover_spec_manifest())
        # may set this True.
        manifest_complete=False,
        validation_evidence={
            "category_count": len(declared_slugs),
            "group_count": group_count,
            "declared_category_urls": declared_category_urls,
        },
    )

    return ParseManifestResult(
        manifest=manifest,
        parse_errors=tuple(parse_errors),
        critical_error=None,
        parser_version=PARSER_VERSION,
    )
