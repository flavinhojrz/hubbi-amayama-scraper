"""Divergência entre expected_identity_context e identidade parseada (data-model.md §4b).

Nunca é fonte de verdade — apenas evidência de auditoria. Ausência de
contexto esperado nunca é tratada como erro (nada a comparar).
"""

from __future__ import annotations

from amayama_scraper.domain.identity import ExpectedIdentityContext, SpecIdentity

DivergenceMap = dict[str, tuple[str, str]]


def detect_identity_context_divergence(
    expected: ExpectedIdentityContext | None, actual: SpecIdentity
) -> DivergenceMap:
    """Retorna {campo: (esperado, real)} para cada campo divergente.

    Dicionário vazio significa "sem contexto esperado" (nada a comparar,
    não é erro) ou "contexto totalmente compatível".
    """
    if expected is None:
        return {}

    divergences: DivergenceMap = {}
    if expected.market is not None and expected.market != actual.market:
        divergences["market"] = (expected.market, actual.market)
    if expected.model_code is not None and expected.model_code != actual.model_code:
        divergences["model_code"] = (expected.model_code, actual.model_code)
    if (
        expected.amayama_catalog_id is not None
        and expected.amayama_catalog_id != actual.amayama_catalog_id
    ):
        divergences["amayama_catalog_id"] = (
            expected.amayama_catalog_id,
            actual.amayama_catalog_id,
        )
    return divergences
