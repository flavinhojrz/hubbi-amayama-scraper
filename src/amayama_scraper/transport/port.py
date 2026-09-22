"""BrowserTransport (Protocol) + BrowserCapture — contracts/browser-transport-contract.md §1.

Fronteira mínima entre o transporte real de navegador e o resto do sistema.
Nenhum método de "resolver challenge", "aguardar N segundos" ou "decidir se é
challenge" existe aqui — essas responsabilidades pertencem, respectivamente:
nunca (proibido), ao driver (orchestration/collection_driver.py), e a
classify_capture() (núcleo já existente de 001). Este port não sabe o que é
CaptureKind, spec_key, category_slug ou group_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

#: Defaults técnicos de retry de falha de transporte (research.md §10) —
#: vivem aqui (não em chrome_cdp_adapter.py) porque são um conceito de
#: transporte em geral, não específico de CDP/Selenium; isso também permite
#: que cli/options.py os reutilize sem importar o adapter concreto (research.md
#: §5 — nenhum arquivo além de chrome_cdp_adapter.py precisa saber de Selenium).
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0

#: Defaults de fetch em lote (navigate_many), validados empiricamente em
#: spikes/batched_fetch_spike.py contra o Amayama real — mesma razão de
#: viverem aqui (não em chrome_cdp_adapter.py): cli/options.py e
#: orchestration/collection_driver.py/worker_pool.py precisam desses valores
#: sem importar o adapter concreto/Selenium.
DEFAULT_DETAIL_FETCH_BATCH_SIZE = 150
DEFAULT_DETAIL_FETCH_CHUNK_SIZE = 3
DEFAULT_DETAIL_FETCH_TIMEOUT_MS = 30_000


@dataclass(frozen=True, slots=True)
class BrowserCapture:
    page_source: str
    effective_url: str
    captured_at: datetime


class BrowserTransport(Protocol):
    def navigate(self, url: str) -> BrowserCapture:
        """Navega até `url`, aguarda o carregamento, retorna o estado capturado.

        Levanta uma subclasse de transport.errors.TransportError quando a
        navegação falha antes que qualquer conteúdo possa ser lido — nunca
        retorna uma BrowserCapture parcial/vazia como se fosse sucesso."""
        ...

    def current_capture(self) -> BrowserCapture:
        """Relê o estado ATUAL da página sem nova navegação — usado pelo laço
        de pausa/retomada de challenge (contracts/browser-transport-contract.md §4)."""
        ...

    def navigate_many(
        self,
        urls: list[str],
        *,
        chunk_size: int = DEFAULT_DETAIL_FETCH_CHUNK_SIZE,
        timeout_ms: int = DEFAULT_DETAIL_FETCH_TIMEOUT_MS,
    ) -> dict[str, BrowserCapture]:
        """Busca várias URLs via fetch() disparado de dentro do navegador já
        autenticado (credentials incluídas), SEM navegar a aba — mais rápido
        e, empiricamente, muito menos sujeito a challenge que `navigate()`
        repetido (spikes/batched_fetch_spike.py: ~5.900 requisições reais
        contra o Amayama, 0 challenges no modo lote vs. ~90-100% no modo
        navigate).

        URLs ausentes do dict retornado (falha de rede, timeout por-URL,
        challenge, resposta vazia) devem ser reprocessadas pelo chamador via
        `navigate()` — este método nunca levanta por falha de UMA url, só por
        falha de transporte total (ex.: Chrome inatingível no meio do lote)."""
        ...
