"""Fetch em lote de GROUP_DETAIL (`enable_detail_batch_fetch=True`) —
`spikes/batched_fetch_spike.py` validou empiricamente que isso é muito mais
rápido e muito menos sujeito a challenge que `navigate()` repetido.

`enable_detail_batch_fetch=False` (default de `run_collection_driver()`)
preserva o comportamento de hoje byte-a-byte — coberto pelos testes já
existentes (`test_collection_driver_group_detail.py` etc.), que continuam
passando sem nenhuma alteração. Aqui cobrimos exclusivamente o caminho novo:

1. Todo o lote vem com sucesso — nenhum fallback single-navigate acionado.
2. Uma URL ausente do lote (falha de rede/timeout) — cai pro fallback.
3. Uma URL vem CHALLENGE dentro do lote — NUNCA resolvida via
   `await_challenge_resolution()` direto sobre o resultado do lote (a aba
   nunca foi navegada até essa URL); cai pro fallback (navigate() real),
   que só então entra no laço de poll normal se ainda for CHALLENGE.
4. `navigate_many()` levanta TransportError (falha de transporte do lote
   inteiro) — todo o lote cai pro fallback per-URL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
)
from amayama_scraper.transport.errors import ChromeNotReachableError
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)
_SPEC_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-62184"
)
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")

_GROUP_407_URL = "https://x/front-axle-steering/407"
_GROUP_100_URL = "https://x/engine/100"

# Duas categorias/grupos, pra exercitar mais de uma URL no mesmo lote.
MANIFEST_HTML = f"""
<html><body>
  <div class="epcVariation__details">
    <div class="epcVariation__filters">
      <div class="epcVariation__schemaGroups">
        <a class="epcVariation__schemaGroup active" data-id="" href="https://x#">All</a>
        <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
        <a class="epcVariation__schemaGroup" data-id="1" href="https://x/engine">EN</a>
      </div>
    </div>
    <div class="epcVariation__schemas">
      <div class="epcVariation__schema" data-id="407">
        <div class="epcVariation__schema-name"><a href="{_GROUP_407_URL}">407</a></div>
      </div>
      <div class="epcVariation__schema" data-id="100">
        <div class="epcVariation__schema-name"><a href="{_GROUP_100_URL}">100</a></div>
      </div>
    </div>
  </div>
</body></html>
"""


def _group_html(part_number: str) -> str:
    return f"""
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">{part_number}</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def _bounded_now(base: datetime, step_seconds: float = 5.0):
    ticks = iter(base + timedelta(seconds=i * step_seconds) for i in range(200))
    return lambda: next(ticks)


def test_all_urls_succeed_via_batch_no_fallback_used(tmp_path):
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    # Bug fix (manifest truncado) + bug fix (CAPTCHA regression): the base
    # page itself (pré-passagem em lote) AND both declared categories
    # (sorted: engine, front-axle-steering) are all fetched via
    # navigate_many() (batch fetch), the SAME technique GROUP_DETAIL already
    # uses to avoid the near-100% challenge rate of sequential navigate()
    # (spikes/batched_fetch_spike.py) — manifest discovery reuses it too
    # whenever enable_detail_batch_fetch=True.
    transport.queue_navigate_many({_SPEC_URL: _capture(MANIFEST_HTML, _SPEC_URL)})
    transport.queue_navigate_many(
        {
            "https://x/engine": _capture(MANIFEST_HTML, "https://x/engine"),
            "https://x/front-axle-steering": _capture(
                MANIFEST_HTML, "https://x/front-axle-steering"
            ),
        }
    )
    transport.queue_navigate_many(
        {
            _GROUP_407_URL: _capture(_group_html("1K0407151"), _GROUP_407_URL),
            _GROUP_100_URL: _capture(_group_html("06L100175"), _GROUP_100_URL),
        }
    )

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        enable_detail_batch_fetch=True,
        on_event=lambda event, **kw: events.append(event),
    )

    # MARKET_INDEX only via single navigate() — the base page, both
    # category-page visits, AND the two GROUP_DETAILs were entirely
    # resolved by batch calls.
    assert transport.navigate_calls == [MARKET_INDEX_URL]
    # get_pending_groups() ordena por (category_slug, group_id) — "engine" < "front-axle-steering".
    assert transport.navigate_many_calls == [
        [_SPEC_URL],
        ["https://x/engine", "https://x/front-axle-steering"],
        [_GROUP_100_URL, _GROUP_407_URL],
    ]
    assert events.count("GROUP_ACCEPTED") == 2

    key = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    assert get_current_state(conn, key) is not None  # spec chegou a VALID


def test_url_missing_from_batch_falls_back_to_single_navigate(tmp_path):
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    # Bug fix (manifest truncado + CAPTCHA excessivo): the base page AND
    # both declared categories are all fetched via navigate_many() (batch
    # fetch) before the manifest can become complete.
    transport.queue_navigate_many({_SPEC_URL: _capture(MANIFEST_HTML, _SPEC_URL)})
    transport.queue_navigate_many(
        {
            "https://x/engine": _capture(MANIFEST_HTML, "https://x/engine"),
            "https://x/front-axle-steering": _capture(
                MANIFEST_HTML, "https://x/front-axle-steering"
            ),
        }
    )
    # Lote só devolve UMA das duas URLs pedidas (a outra "falhou"/deu timeout
    # dentro do fetch() — nunca aparece no dict, nunca levanta).
    transport.queue_navigate_many(
        {_GROUP_407_URL: _capture(_group_html("1K0407151"), _GROUP_407_URL)}
    )
    # Fallback: navigate() único pra URL que faltou no lote.
    transport.queue_navigate(_capture(_group_html("06L100175"), _GROUP_100_URL))

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        enable_detail_batch_fetch=True,
        on_event=lambda event, **kw: events.append(event),
    )

    assert transport.navigate_calls == [MARKET_INDEX_URL, _GROUP_100_URL]
    assert events.count("GROUP_ACCEPTED") == 2  # ambos aceitos, um via lote, um via fallback


def test_challenge_from_batch_never_polls_current_capture_falls_back_to_real_navigate(tmp_path):
    """O ponto central da técnica: uma captura vinda de fetch() em lote NUNCA
    é resolvida via await_challenge_resolution() diretamente (current_capture()
    leria a aba, que nunca foi navegada até essa URL) — sempre cai pro
    fallback de navigate() real primeiro, e SÓ ENTÃO (se ainda CHALLENGE)
    entra no laço de poll normal."""
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    # Bug fix (manifest truncado + CAPTCHA excessivo): the base page AND
    # both declared categories are all fetched via navigate_many() (batch
    # fetch) before the manifest can become complete.
    transport.queue_navigate_many({_SPEC_URL: _capture(MANIFEST_HTML, _SPEC_URL)})
    transport.queue_navigate_many(
        {
            "https://x/engine": _capture(MANIFEST_HTML, "https://x/engine"),
            "https://x/front-axle-steering": _capture(
                MANIFEST_HTML, "https://x/front-axle-steering"
            ),
        }
    )
    # Lote devolve as DUAS URLs, mas uma delas é challenge.
    transport.queue_navigate_many(
        {
            _GROUP_407_URL: _capture(CHALLENGE_HTML, _GROUP_407_URL),
            _GROUP_100_URL: _capture(_group_html("06L100175"), _GROUP_100_URL),
        }
    )
    # Fallback pra 407: navigate() real (a aba É navegada até lá desta vez)
    # — ainda challenge na primeira tentativa, resolve na segunda leitura de
    # current_capture() (o operador "resolveu" nesse meio tempo).
    transport.queue_navigate(_capture(CHALLENGE_HTML, _GROUP_407_URL))
    transport.queue_current_capture(_capture(CHALLENGE_HTML, _GROUP_407_URL))
    transport.queue_current_capture(_capture(_group_html("1K0407151"), _GROUP_407_URL))

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        enable_detail_batch_fetch=True,
        poll_interval=0.0,
        sleep=lambda _s: None,
        now=_bounded_now(datetime(2026, 8, 28, tzinfo=UTC)),
        on_event=lambda event, **kw: events.append(event),
    )

    # A URL challenged no lote foi renavegada de verdade (fallback) — nunca
    # resolvida só relendo a aba (que nunca esteve lá).
    assert _GROUP_407_URL in transport.navigate_calls
    assert "CHALLENGE_WAITING" in events
    assert "CHALLENGE_RESOLVED" in events
    assert events.count("GROUP_ACCEPTED") == 2  # ambos os grupos, no final, aceitos


def test_navigate_many_transport_error_falls_back_to_single_navigate_per_url(tmp_path):
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    # Bug fix (manifest truncado + CAPTCHA excessivo): the base page AND
    # both declared categories are all fetched via navigate_many() (batch
    # fetch) before the manifest can become complete.
    transport.queue_navigate_many({_SPEC_URL: _capture(MANIFEST_HTML, _SPEC_URL)})
    transport.queue_navigate_many(
        {
            "https://x/engine": _capture(MANIFEST_HTML, "https://x/engine"),
            "https://x/front-axle-steering": _capture(
                MANIFEST_HTML, "https://x/front-axle-steering"
            ),
        }
    )
    # Falha de transporte do lote inteiro (ex.: Chrome caiu no meio).
    transport.queue_navigate_many(ChromeNotReachableError("CDP endpoint unreachable"))
    # Todo o chunk cai pro fallback per-URL — navigate() único pras duas, na
    # ordem de get_pending_groups() (sorted por category_slug/group_id):
    # engine/100 antes de front-axle-steering/407. FakeBrowserTransport.
    # navigate() é FIFO puro (não casa por URL) — a ordem de fila importa.
    transport.queue_navigate(_capture(_group_html("06L100175"), _GROUP_100_URL))
    transport.queue_navigate(_capture(_group_html("1K0407151"), _GROUP_407_URL))

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        enable_detail_batch_fetch=True,
        on_event=lambda event, **kw: events.append(event),
    )

    assert transport.navigate_calls == [
        MARKET_INDEX_URL,
        _GROUP_100_URL,
        _GROUP_407_URL,
    ]
    assert events.count("GROUP_ACCEPTED") == 2


def test_default_behavior_never_calls_navigate_many(tmp_path):
    """enable_detail_batch_fetch=False (default) — comportamento de hoje
    byte-a-byte, navigate_many() nunca é sequer chamado."""
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    # Bug fix (manifest truncado): both declared categories (sorted: engine,
    # front-axle-steering) are each visited on their own URL before the
    # manifest can become complete.
    transport.queue_navigate(_capture(MANIFEST_HTML, "https://x/engine"))
    transport.queue_navigate(_capture(MANIFEST_HTML, "https://x/front-axle-steering"))
    # Ordem de get_pending_groups(): engine/100 antes de front-axle-steering/407.
    transport.queue_navigate(_capture(_group_html("06L100175"), _GROUP_100_URL))
    transport.queue_navigate(_capture(_group_html("1K0407151"), _GROUP_407_URL))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        # enable_detail_batch_fetch omitido -> default False
    )

    assert transport.navigate_many_calls == []
    assert transport.navigate_calls == [
        MARKET_INDEX_URL,
        _SPEC_URL,
        "https://x/engine",
        "https://x/front-axle-steering",
        _GROUP_100_URL,
        _GROUP_407_URL,
    ]
