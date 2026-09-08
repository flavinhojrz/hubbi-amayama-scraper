"""T007 — hierarquia de exceções de transporte (data-model.md §3, DEC-006).

Nunca confundidas com ValidationOutcome — uma falha de transporte jamais
alcança classify_capture() (research.md §10).
"""

from __future__ import annotations

from amayama_scraper.transport.errors import (
    ChromeNotReachableError,
    NavigationFailedError,
    NavigationTimeoutError,
    TransportError,
)
from amayama_scraper.validation.types import ValidationOutcome


def test_all_transport_errors_are_transport_error_subclasses() -> None:
    assert issubclass(ChromeNotReachableError, TransportError)
    assert issubclass(NavigationTimeoutError, TransportError)
    assert issubclass(NavigationFailedError, TransportError)


def test_transport_error_is_not_a_validation_outcome() -> None:
    assert not issubclass(TransportError, ValidationOutcome)
    assert not isinstance(TransportError("x"), ValidationOutcome)


def test_transport_errors_carry_a_message() -> None:
    exc = ChromeNotReachableError("http://127.0.0.1:9222/json/version unreachable")
    assert "unreachable" in str(exc)
