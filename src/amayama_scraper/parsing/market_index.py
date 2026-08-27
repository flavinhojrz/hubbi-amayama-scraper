"""parse_market_spec_index() — Nível A (contracts/domain-contracts.md "Nível A").

Seletores comprovados contra evidência real capturada manualmente em
2026-08-26 (browser-in-the-loop, DEC-001) — ver research.md §21. Implementa
FR-001 (descoberta/enumeração de spec entries do Amarok no mercado AMA-BR).

Interpretação documentada (composição dos seletores evidenciados, sem
inventar nenhum novo): `market` é validado pela identidade estrutural da
própria página (`.breadcrumbs__last-item`), nunca inferido de `grade` ou do
`model_code`; `amayama_catalog_id` é o sufixo numérico final do último
segmento de path da URL da row (nunca uma decodificação do `model_code`);
`configuration` não tem fonte estrutural comprovada nesta captura e
permanece sempre ausente (nunca derivado de `grade`).

parser_version = "amayama-market-index-parser-v1" (Constitution §13).
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup
from bs4.element import Tag

from amayama_scraper.domain.discovery import DiscoveredSpecEntry
from amayama_scraper.parsing import selectors
from amayama_scraper.parsing.results import ParseError, ParseMarketIndexResult

PARSER_VERSION = "amayama-market-index-parser-v1"

_CATALOG_ID_SUFFIX = re.compile(r"-(\d+)$")
_PERIOD_MONTH = re.compile(r"^(\d{4})\.(\d{2})$")


def _text_or_none(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    text = tag.get_text(strip=True)
    return text or None


def _extract_market(soup: BeautifulSoup) -> str | None:
    breadcrumb_last = soup.select_one(".breadcrumbs__last-item")
    text = _text_or_none(breadcrumb_last)
    if text is None:
        return None
    return text.strip().upper().replace(" ", "-")


def _extract_catalog_id(source_url: str) -> str | None:
    last_segment = source_url.rstrip("/").rsplit("/", 1)[-1]
    match = _CATALOG_ID_SUFFIX.search(last_segment)
    if match is None:
        return None
    return match.group(1)


def _parse_period_bound(text: str) -> date | None:
    match = _PERIOD_MONTH.match(text.strip())
    if match is None:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    return date(year, month, 1)


def _parse_production_period(raw: str | None) -> tuple[date | None, date | None]:
    if raw is None:
        return None, None
    parts = raw.split(" - ", 1)
    if len(parts) != 2:
        return None, None
    start_text, end_text = parts[0].strip(), parts[1].strip()
    start = _parse_period_bound(start_text)
    end = None if end_text == "..." else _parse_period_bound(end_text)
    return start, end


def _parse_row(
    row: Tag, market: str, source_capture_id: str
) -> tuple[DiscoveredSpecEntry | None, ParseError | None]:
    tds = row.find_all("td", recursive=False)
    if len(tds) != 3:
        return None, ParseError(
            message=f"expected 3 <td> in {selectors.MARKET_INDEX_ROW!r}, found {len(tds)}"
        )

    link_tag = tds[0].find("a")
    if link_tag is None or not link_tag.get("href"):
        return None, ParseError(message="row missing model link (<a href>) in first <td>")

    model_code = _text_or_none(link_tag)
    source_url = str(link_tag["href"])
    if not model_code:
        return None, ParseError(
            message="row link has no text (model_code)", context={"source_url": source_url}
        )

    amayama_catalog_id = _extract_catalog_id(source_url)
    if amayama_catalog_id is None:
        return None, ParseError(
            message="could not extract numeric amayama_catalog_id suffix from source_url",
            context={"source_url": source_url},
        )

    production_period_raw = _text_or_none(tds[1])
    production_start, production_end = _parse_production_period(production_period_raw)

    grade_tag = tds[2].select_one(selectors.MARKET_INDEX_GRADE)
    grade = _text_or_none(grade_tag)

    entry = DiscoveredSpecEntry(
        market=market,
        model_code=model_code,
        amayama_catalog_id=amayama_catalog_id,
        source_url=source_url,
        source_capture_id=source_capture_id,
        production_period_raw=production_period_raw,
        production_start=production_start,
        production_end=production_end,
        grade=grade,
        configuration=None,
    )
    return entry, None


def parse_market_spec_index(html: str, source_capture_id: str) -> ParseMarketIndexResult:
    soup = BeautifulSoup(html, "lxml")

    if soup.select_one(selectors.MARKET_INDEX_CONTAINER) is None:
        return ParseMarketIndexResult(
            critical_error=ParseError(
                message=f"missing expected root marker {selectors.MARKET_INDEX_CONTAINER!r}"
            ),
            parser_version=PARSER_VERSION,
        )

    market = _extract_market(soup)
    if market is None:
        return ParseMarketIndexResult(
            critical_error=ParseError(
                message="could not establish market identity from .breadcrumbs__last-item"
            ),
            parser_version=PARSER_VERSION,
        )

    entries: list[DiscoveredSpecEntry] = []
    parse_errors: list[ParseError] = []
    for row in soup.select(selectors.MARKET_INDEX_ROW):
        entry, error = _parse_row(row, market, source_capture_id)
        if error is not None:
            parse_errors.append(error)
        if entry is not None:
            entries.append(entry)

    return ParseMarketIndexResult(
        entries=tuple(entries),
        parse_errors=tuple(parse_errors),
        critical_error=None,
        parser_version=PARSER_VERSION,
    )
