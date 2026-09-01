"""T069 — plan_operation() nunca instancia/recebe um BrowserTransport
(spec.md DEC-009 "zero navegação"). Verificação estrutural: a assinatura
não aceita transporte como argumento — não apenas comportamental."""

from __future__ import annotations

import inspect

from amayama_scraper.orchestration.dry_run import plan_operation


def test_plan_operation_signature_has_no_transport_parameter() -> None:
    signature = inspect.signature(plan_operation)
    param_names = set(signature.parameters)
    assert "transport" not in param_names
    for name in param_names:
        assert "transport" not in name.lower() and "browser" not in name.lower()
