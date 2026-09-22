"""Erros de transporte — nunca confundidos com ValidationOutcome (data-model.md §3, DEC-006).

Uma exceção daqui significa que nenhuma RawCaptureInput chegou a ser
construída — a captura nunca alcançou classify_capture(). O driver trata
essas falhas exclusivamente pela via de "falha de transporte" (retry
configurável, research.md §10), nunca pela via de "rejeição de validação".
"""

from __future__ import annotations


class TransportError(Exception):
    """Base — nunca instanciada diretamente."""


class ChromeNotReachableError(TransportError):
    """O endpoint CDP configurado não responde (research.md §4)."""


class ChromeLaunchFailedError(TransportError):
    """`undetected_chrome_adapter.py` não conseguiu iniciar seu próprio
    Chrome (binário ausente, perfil corrompido, todas as tentativas de
    retry esgotadas)."""


class NavigationTimeoutError(TransportError):
    """A navegação não completou dentro do timeout interno do adapter."""


class NavigationFailedError(TransportError):
    """Falha de navegação não coberta pelas duas exceções acima."""
