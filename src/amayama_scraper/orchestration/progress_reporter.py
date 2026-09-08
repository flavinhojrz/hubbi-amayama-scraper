"""progress_reporter.py — observabilidade objetiva de terminal (FR-027).

Reuso estrito de orchestration/logging.py::log_event() já existente — sem
novo framework de logging (spec.md: "sem framework de logging excessivo se
o existente atender"). Nunca vaza page_source/raw_content/html: log_event()
já recusa ativamente esses campos (RawContentInLogError), e nenhuma chamada
feita por collection_driver.py/await_challenge_resolution() os inclui.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from amayama_scraper.orchestration.logging import log_event

#: Marcos exigidos por FR-027: RUN, SPEC, GROUP, progresso, ACCEPTED,
#: SKIPPED, CHALLENGE, RETRY_TRANSPORT, REJECTED, COMPLETE, resumo final.
_SUMMARY_BUCKETS: dict[str, str] = {
    "GROUP_ACCEPTED": "ACCEPTED",
    "SPEC_SKIPPED_ALREADY_VALID": "SKIPPED",
    "CHALLENGE_WAITING": "CHALLENGE",
    "CHALLENGE_STILL_PRESENT": "CHALLENGE",
    "GROUP_REJECTED_AWAITING_MANUAL_RETRY": "REJECTED",
    "GROUP_REJECTED": "REJECTED",
    "GROUP_CHALLENGE_TIMEOUT": "REJECTED",
    "SPEC_NAVIGATION_REJECTED": "REJECTED",
    "SPEC_NAVIGATION_CHALLENGE_TIMEOUT": "REJECTED",
}


def make_terminal_reporter(
    *, run_id: str, emit: Callable[[str], None] = print
) -> Callable[..., None]:
    """Retorna um `on_event(event, **fields)` pronto para uso em
    collection_driver.py/await_challenge_resolution(). Cada chamada emite
    uma linha JSON via log_event() e acumula um resumo em memória, impresso
    quando o evento RUN_SUMMARY é recebido."""
    counters: Counter[str] = Counter()

    def on_event(event: str, **fields: object) -> None:
        log_event(run_id=run_id, event=event, emit=emit, **fields)
        bucket = _SUMMARY_BUCKETS.get(event)
        if bucket is not None:
            counters[bucket] += 1
        if event == "RUN_SUMMARY":
            summary = " ".join(f"{key}={value}" for key, value in sorted(counters.items()))
            emit(f"SUMMARY run_id={run_id} {summary}")

    return on_event
