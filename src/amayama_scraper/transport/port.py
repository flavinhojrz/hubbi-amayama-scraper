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
