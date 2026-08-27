"""parse_group_detail() — Nível C (contracts/domain-contracts.md).

Usa exclusivamente os seletores v1 já evidenciados (parsing/selectors.py).
Falha explicitamente (critical_error) diante de drift estrutural — nunca
parsing permissivo que oculte a divergência (ponto 20 do PLAN).

Interpretação documentada (sem inventar seletor novo, apenas compondo os
já dados): cada `.epcSchema__schema[data-id]` é um Schema; sua
`.entriesTable` contém as linhas de peça (`tr[data-key]`, onde
`data-key` é o PNC/position); `.entriesTable__number` é o OEM;
`.entriesTable__description` é a descrição; `.entriesPncDescriptionTable`
aninhada (quando presente) é tratada como `details`; `.entriesTable__period`
e `.entriesTable__required` são período/quantidade; a imagem
(`.imgMap img[src]`) é associada no nível do Schema (não há seletor
por-linha evidenciado). `pr_codes` NÃO tem seletor comprovado na pesquisa
atual — permanece sempre ausente (field_status=ABSENT) até evidência real
confirmar onde extraí-lo; isto é registrado explicitamente, não inferido.

parser_version = "amayama-parser-v1" (Constitution §13).
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import Tag

from amayama_scraper.parsing import selectors
from amayama_scraper.parsing.results import (
    FieldStatus,
    ParsedGroupDetail,
    ParsedPart,
    ParsedSchema,
    ParseError,
)

PARSER_VERSION = "amayama-parser-v1"


def _text_or_none(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    text = tag.get_text(strip=True)
    return text or None


def _schema_image_url(schema_tag: Tag) -> str | None:
    img = schema_tag.select_one(selectors.IMAGE)
    if img is None:
        return None
    src = img.get("src")
    return str(src) if src else None


def _parse_part_row(row: Tag, schema_id: str, image_url: str | None) -> ParsedPart:
    field_status: dict[str, FieldStatus] = {}

    position_pnc = row.get("data-key")
    if not position_pnc:
        # A linha existe mas não carrega o atributo esperado — erro de parsing
        # do próprio campo obrigatório, não ausência legítima.
        raise _PartRowMissingKeyError("tr[data-key] sem atributo data-key")
    position_pnc = str(position_pnc)

    oem_tag = row.select_one(selectors.OEM_NUMBER)
    oem_code = _text_or_none(oem_tag)
    field_status["oem_code"] = FieldStatus.PRESENT if oem_code else FieldStatus.ABSENT

    description_tag = row.select_one(selectors.DESCRIPTION)
    details: str | None = None
    description: str | None = None
    if description_tag is not None:
        nested = description_tag.select_one(selectors.NESTED_DESCRIPTION)
        if nested is not None:
            details = _text_or_none(nested)
            nested.extract()  # avoid double-counting nested text in the outer description
        description = _text_or_none(description_tag)
    field_status["description"] = FieldStatus.PRESENT if description else FieldStatus.ABSENT
    field_status["details"] = FieldStatus.PRESENT if details else FieldStatus.ABSENT

    period_tag = row.select_one(selectors.PERIOD)
    period = _text_or_none(period_tag)
    field_status["period_application_text"] = FieldStatus.PRESENT if period else FieldStatus.ABSENT

    quantity_tag = row.select_one(selectors.QUANTITY)
    quantity = _text_or_none(quantity_tag)
    field_status["quantity"] = FieldStatus.PRESENT if quantity else FieldStatus.ABSENT

    # pr_codes: nenhum seletor comprovado na pesquisa atual — sempre ausente,
    # nunca inferido (ver docstring do módulo).
    field_status["pr_codes"] = FieldStatus.ABSENT
    field_status["image_url"] = FieldStatus.PRESENT if image_url else FieldStatus.ABSENT

    return ParsedPart(
        schema_id=schema_id,
        position_pnc=position_pnc,
        field_status=field_status,
        oem_code=oem_code,
        description=description,
        details=details,
        period_application_text=period,
        pr_codes=(),
        quantity=quantity,
        image_url=image_url,
    )


class _PartRowMissingKeyError(ValueError):
    """Erro interno — linha de peça sem data-key. Vira parse_error, não crash."""


def parse_group_detail(html: str, category_slug: str, group_id: str) -> ParsedGroupDetail:
    soup = BeautifulSoup(html, "lxml")

    if soup.select_one(selectors.VARIATION_DETAILS) is None:
        return ParsedGroupDetail(
            category_slug=category_slug,
            group_id=group_id,
            critical_error=ParseError(
                message=f"missing expected root marker {selectors.VARIATION_DETAILS!r}"
            ),
            parser_version=PARSER_VERSION,
        )

    schemas_container = soup.select_one(selectors.SCHEMAS_CONTAINER)
    if schemas_container is None:
        return ParsedGroupDetail(
            category_slug=category_slug,
            group_id=group_id,
            critical_error=ParseError(
                message=f"missing expected schemas container {selectors.SCHEMAS_CONTAINER!r}"
            ),
            parser_version=PARSER_VERSION,
        )

    schema_tags = schemas_container.select(selectors.SCHEMA)
    parsed_schemas: list[ParsedSchema] = []
    parse_errors: list[ParseError] = []

    for schema_tag in schema_tags:
        schema_id = schema_tag.get("data-id")
        if not schema_id:
            parse_errors.append(ParseError(message="schema element missing data-id"))
            continue
        schema_id = str(schema_id)

        image_url = _schema_image_url(schema_tag)
        table = schema_tag.select_one(selectors.ENTRIES_TABLE)
        parts: list[ParsedPart] = []
        if table is not None:
            for row in table.select(selectors.PNC_ROW):
                try:
                    parts.append(_parse_part_row(row, schema_id, image_url))
                except _PartRowMissingKeyError as exc:
                    parse_errors.append(
                        ParseError(message=str(exc), context={"schema_id": schema_id})
                    )

        parsed_schemas.append(ParsedSchema(schema_id=schema_id, parts=tuple(parts)))

    return ParsedGroupDetail(
        category_slug=category_slug,
        group_id=group_id,
        schemas=tuple(parsed_schemas),
        parse_errors=tuple(parse_errors),
        critical_error=None,
        parser_version=PARSER_VERSION,
    )
