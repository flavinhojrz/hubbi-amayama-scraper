"""collection_driver.py — laço de descoberta-e-ação e pausa/retomada de
challenge (contracts/browser-transport-contract.md §3-§4).

Reutiliza exclusivamente primitivas já existentes do núcleo de 001
(process_capture, get_pending_groups, try_finalize_spec_entry) — nenhuma
regra de domínio/validação/parsing é reimplementada aqui. Nenhum import de
`selenium`/`transport.chrome_cdp_adapter` — este módulo depende apenas do
Protocol `BrowserTransport` (transport/port.py), nunca do adapter concreto
(composição acontece em cli/main.py).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from amayama_scraper.checkpoint.resume import get_pending_groups
from amayama_scraper.domain.collection_context import CollectionContext, ContextScopeMismatchError
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.domain.identity import ExpectedIdentityContext, SpecIdentity
from amayama_scraper.domain.manifest import SpecGroupManifest
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import AcquisitionMode, CaptureKind
from amayama_scraper.ingestion.ports import RawBlobStore, RawCaptureRepository
from amayama_scraper.orchestration.pipeline import (
    ProcessCaptureResult,
    process_capture,
    try_finalize_spec_entry,
)
from amayama_scraper.orchestration.retry_classification import (
    classify_pending_unit,
    should_attempt_this_pass,
)
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    get_collection_run,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope
from amayama_scraper.transport.port import BrowserCapture, BrowserTransport
from amayama_scraper.validation.types import ValidationOutcome

_DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS = 5.0
_DEFAULT_MIN_INTERVAL_SECONDS = 0.0


def to_raw_capture_input(
    capture: BrowserCapture,
    *,
    capture_kind: CaptureKind,
    run_id: str,
    expected_identity_context: ExpectedIdentityContext | None = None,
) -> RawCaptureInput:
    """Converte BrowserCapture -> RawCaptureInput sem transformação (data-model.md §1, FR-005).

    acquisition_mode é sempre AUTOMATED_BROWSER_CDP — este é o único produtor
    desse valor em todo o sistema (research.md §6).
    """
    return RawCaptureInput(
        capture_kind=capture_kind,
        source_url=capture.effective_url,
        collected_at=capture.captured_at,
        raw_content=capture.page_source.encode("utf-8"),
        run_id=run_id,
        acquisition_mode=AcquisitionMode.AUTOMATED_BROWSER_CDP,
        expected_identity_context=expected_identity_context,
    )


@dataclass(frozen=True, slots=True)
class ChallengeWaitOutcome:
    result: ProcessCaptureResult | None
    timed_out: bool


def await_challenge_resolution(
    transport: BrowserTransport,
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    *,
    run_id: str,
    capture_kind: CaptureKind,
    source_url_hint: str,
    context: CollectionContext,
    expected_identity_context: ExpectedIdentityContext | None = None,
    category_slug: str | None = None,
    group_id: str | None = None,
    spec_key: str | None = None,
    poll_interval: float = _DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS,
    timeout: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_event: Callable[..., None] = lambda event, **kwargs: None,
    process_capture_fn: Callable[..., ProcessCaptureResult] = process_capture,
) -> ChallengeWaitOutcome:
    """Laço bloqueante de pausa/retomada — contracts/browser-transport-contract.md §4.

    Sempre reprocessa via process_capture()/classify_capture() reais a cada
    verificação — nunca uma decisão paralela de "resolvido". Só retorna
    quando o outcome deixa de ser CHALLENGE, ou quando `timeout` (opcional)
    é excedido (desiste apenas desta unidade, nunca da execução inteira).
    `transport.current_capture()` pode levantar ChromeNotReachableError —
    propositalmente propagada (não capturada aqui), sinalizando sessão de
    navegador perdida (research.md §11).

    `process_capture_fn` (005 hardening, BLOCKER 1 — lease fencing):
    default `process_capture` (comportamento idêntico a antes — nenhuma
    mudança para `--workers 1`). `orchestration/worker_pool.py` injeta uma
    versão que verifica o lease/token do worker atomicamente antes de cada
    escrita de poll, para que um worker que já perdeu o lease nunca persista
    o resultado de uma resolução de challenge tardia."""
    # capture_kind/spec_key incluídos em todo evento abaixo (005 — aditivo,
    # nunca decide outcome, mesmo espírito de FR-015 para effective_url):
    # permite a `orchestration/worker_pool.py` instrumentar `challenge_event`
    # (data-model.md §3) sem precisar rastrear "qual spec/capture_kind está
    # em challenge agora" por fora — o próprio evento já carrega o contexto.
    on_event(
        "CHALLENGE_WAITING",
        source_url=source_url_hint,
        capture_kind=capture_kind.value,
        spec_key=spec_key,
    )
    started_at = now()

    while True:
        sleep(poll_interval)
        if timeout is not None and (now() - started_at).total_seconds() > timeout:
            on_event(
                "CHALLENGE_TIMEOUT",
                source_url=source_url_hint,
                capture_kind=capture_kind.value,
                spec_key=spec_key,
            )
            return ChallengeWaitOutcome(result=None, timed_out=True)

        capture = transport.current_capture()
        capture_input = to_raw_capture_input(
            capture,
            capture_kind=capture_kind,
            run_id=run_id,
            expected_identity_context=expected_identity_context,
        )
        result = process_capture_fn(
            conn,
            blob_store,
            capture_repo,
            run_id,
            capture_input,
            context=context,
            category_slug=category_slug,
            group_id=group_id,
            spec_key=spec_key,
        )
        if result.validation_outcome is not ValidationOutcome.CHALLENGE:
            on_event(
                "CHALLENGE_RESOLVED",
                outcome=result.validation_outcome,
                capture_kind=capture_kind.value,
                spec_key=spec_key,
            )
            return ChallengeWaitOutcome(result=result, timed_out=False)
        # ainda CHALLENGE — o laço continua; effective_url é incluído apenas
        # como sinal diagnóstico não-autoritativo (FR-015), nunca decide o outcome.
        on_event(
            "CHALLENGE_STILL_PRESENT",
            source_url=source_url_hint,
            observed_url=capture.effective_url,
            capture_kind=capture_kind.value,
            spec_key=spec_key,
        )


# --- Controles de escopo (FR-023 a FR-025, DEC-008) -------------------------


@dataclass(frozen=True, slots=True)
class OperationalFilters:
    spec_filter: list[str] | None = None
    limit_specs: int | None = None
    limit_groups: int | None = None
    force: list[str] = field(default_factory=list)
    retry_rejected: bool = False


class UnknownSpecFilterError(ValueError):
    """--spec referencia um stable_key não descoberto (FR-025, FR-009)."""


def apply_operational_filters(
    identities: list[SpecIdentity], filters: OperationalFilters
) -> list[SpecIdentity]:
    """T076/T077/T091/T092 — filtra por identidade JÁ descoberta, nunca por
    regra de descoberta em produção (FR-009, FR-023, FR-025)."""
    result = identities
    if filters.spec_filter is not None:
        known_keys = {identity.stable_key() for identity in identities}
        unknown = [key for key in filters.spec_filter if key not in known_keys]
        if unknown:
            raise UnknownSpecFilterError(
                f"--spec references unknown/undiscovered stable_key(s): {unknown}"
            )
        allowed = set(filters.spec_filter)
        result = [identity for identity in result if identity.stable_key() in allowed]
    if filters.limit_specs is not None:
        result = result[: filters.limit_specs]
    return result


def apply_group_limit(pending: list[tuple[str, str]], limit: int | None) -> list[tuple[str, str]]:
    """T086/T087 — trunca deterministicamente, sem reordenar (FR-024)."""
    if limit is None:
        return pending
    return pending[:limit]


def _source_url_for_group(manifest: SpecGroupManifest, category_slug: str, group_id: str) -> str:
    for category in manifest.categories:
        if category.category_slug != category_slug:
            continue
        for group in category.groups:
            if group.group_id == group_id:
                return group.source_url
    raise LookupError(
        f"group {(category_slug, group_id)!r} not found in manifest "
        f"for spec_key={manifest.spec_key!r}"
    )


def _expected_context(identity: SpecIdentity) -> ExpectedIdentityContext:
    return ExpectedIdentityContext(
        market=identity.market,
        model_code=identity.model_code,
        amayama_catalog_id=identity.amayama_catalog_id,
    )


# --- Conclusão de run (Blocker 2 — DEC-005/FR-019; escopo multi-modelo 004) --


def _maybe_mark_run_completed(
    conn: sqlite3.Connection,
    run_id: str,
    now: Callable[[], datetime],
    *,
    context: CollectionContext,
) -> None:
    """Marca `CollectionRun.completed_at` somente quando TODAS as specs já
    conhecidas *deste contexto* (context.manufacturer/vehicle_model/market —
    nunca todas as specs do banco, que pode conter outros modelos/mercados
    coexistindo) estão VALID/STALE. Reaproveita o lifecycle já existente de
    `CollectionRun` (`save_collection_run()` já faz upsert de
    `completed_at` — nenhuma entidade nova, nenhuma migration).

    Nunca marca cedo demais: uma lista vazia (nada descoberto ainda) nunca
    conta como completa (universal quantifier sobre conjunto vazio seria
    vacuamente verdadeiro — guardado explicitamente abaixo). Uma spec ainda
    sem manifesto, com grupo REJECTED aguardando retry manual, ou parada em
    challenge-timeout nunca passa no `all(...)`, então o run permanece
    incompleto — exatamente como uma interrupção/exceção no meio do laço
    também nunca alcança esta função (o `return` antecipado ou a exceção
    propagada impedem a chamada)."""
    all_known_specs = list_by_scope(
        conn,
        manufacturer=context.manufacturer,
        vehicle_model=context.vehicle_model,
        market=context.market,
    )
    if not all_known_specs:
        return
    if not all(get_current_state(conn, spec.stable_key()) is not None for spec in all_known_specs):
        return
    run = get_collection_run(conn, run_id)
    if run is None or run.completed_at is not None:
        return
    save_collection_run(conn, replace(run, completed_at=now()))


# --- Processamento de uma spec (005 T509 — extraído do laço de descoberta- -
# -e-ação para ser reusado tanto pelo caminho legado quanto pelo worker pool)


class SpecPassDisposition(StrEnum):
    """005 hardening (BLOCKER 2, 2ª rodada — terminalidade real, nunca
    backoff temporal): classifica o resultado de UMA passagem de
    `process_one_spec()` em exatamente três categorias, usadas por
    `orchestration/worker_pool.py` para decidir elegibilidade futura —
    nunca por tempo, sempre por disposição explícita persistida
    (`spec_pool_disposition`, chaveada por `run_id + spec_key`).

    - `PROGRESSED`: pelo menos um `GROUP_ACCEPTED` nesta passagem — a spec
      segue elegível normalmente (qualquer disposição anterior é limpa).
    - `MANUAL_RETRY_REQUIRED`: pelo menos um grupo pendente foi classificado
      como exigindo retry manual (`GROUP_REJECTED_AWAITING_MANUAL_RETRY`) —
      nunca reelegível em execução normal, mesmo depois de tempo/novo
      `--resume`; só `--retry-rejected` reabre.
    - `DEFERRED_THIS_SESSION`: falha transitória sem progresso e sem
      nenhuma unidade exigindo retry manual (challenge não resolvido,
      navegação rejeitada) — inelegível pelo restante desta invocação de
      `run_pool()` (mesmo `pool_session_id`), mas uma nova invocação
      (`--resume`) pode tentar de novo.

    Ignorado pelo caminho legado (`--workers 1`, que não decide nada com
    base nisso — `run_collection_driver()` descarta o valor de retorno)."""

    PROGRESSED = "PROGRESSED"
    MANUAL_RETRY_REQUIRED = "MANUAL_RETRY_REQUIRED"
    DEFERRED_THIS_SESSION = "DEFERRED_THIS_SESSION"


@dataclass(frozen=True, slots=True)
class SpecPassOutcome:
    disposition: SpecPassDisposition


def process_one_spec(
    transport: BrowserTransport,
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    *,
    run_id: str,
    context: CollectionContext,
    spec: SpecIdentity,
    filters: OperationalFilters,
    throttled_navigate: Callable[[str], BrowserCapture],
    poll_interval: float = _DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS,
    challenge_timeout: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_event: Callable[..., None] = lambda event, **kwargs: None,
    process_capture_fn: Callable[..., ProcessCaptureResult] = process_capture,
    finalize_fn: Callable[..., object] = try_finalize_spec_entry,
) -> SpecPassOutcome:
    """SPEC_NAVIGATION (se necessário) -> grupos pendentes -> GROUP_DETAIL ->
    `try_finalize_spec_entry()` — mesma lógica por-spec que antes vivia
    inline no laço `for spec in specs_to_process` de `run_collection_driver()`
    (extração mecânica, 005 T509 — nenhuma mudança de comportamento
    observável, contracts/worker-pool-contract.md §2). Reusada tanto pelo
    caminho legado (`--workers 1`, chamada sequencialmente pelo próprio
    `run_collection_driver()`, que ignora o valor de retorno — nenhuma
    mudança de comportamento) quanto pelo laço de worker com lease
    (`orchestration/worker_pool.py`).

    Não decide se a spec já é `VALID`/deve ser pulada — essa checagem
    precede a chamada (no laço legado, antes de chamar; no worker pool,
    antes do claim, contracts/worker-pool-contract.md §3, FR-024) — nem
    emite `SPEC_STARTED`/`progress` (específico de cada chamador, já que o
    worker pool não tem uma noção global de "índice de N" por spec
    reivindicada dinamicamente).

    `process_capture_fn`/`finalize_fn` (005 hardening, BLOCKER 1 — lease
    fencing): defaults `process_capture`/`try_finalize_spec_entry`
    (comportamento idêntico a antes). `orchestration/worker_pool.py` injeta
    versões com fencing atômico (checagem de lease/token na mesma transação
    da escrita) — um worker que perdeu o lease nunca persiste depois de um
    takeover."""
    key = spec.stable_key()

    manifest = get_authoritative(conn, key, run_id)
    if manifest is None:
        nav_capture = throttled_navigate(spec.source_url)
        nav_input = to_raw_capture_input(
            nav_capture,
            capture_kind=CaptureKind.SPEC_NAVIGATION,
            run_id=run_id,
            expected_identity_context=_expected_context(spec),
        )
        nav_result = process_capture_fn(
            conn, blob_store, capture_repo, run_id, nav_input, context=context, spec_key=key
        )
        if nav_result.validation_outcome is ValidationOutcome.CHALLENGE:
            nav_outcome = await_challenge_resolution(
                transport,
                conn,
                blob_store,
                capture_repo,
                run_id=run_id,
                capture_kind=CaptureKind.SPEC_NAVIGATION,
                source_url_hint=spec.source_url,
                context=context,
                expected_identity_context=_expected_context(spec),
                spec_key=key,
                poll_interval=poll_interval,
                timeout=challenge_timeout,
                sleep=sleep,
                now=now,
                on_event=on_event,
                process_capture_fn=process_capture_fn,
            )
            if nav_outcome.result is None:
                on_event("SPEC_NAVIGATION_CHALLENGE_TIMEOUT", spec_key=key)
                return SpecPassOutcome(disposition=SpecPassDisposition.DEFERRED_THIS_SESSION)
        manifest = get_authoritative(conn, key, run_id)
        if manifest is None:
            on_event("SPEC_NAVIGATION_REJECTED", spec_key=key)
            return SpecPassOutcome(disposition=SpecPassDisposition.DEFERRED_THIS_SESSION)

    pending = get_pending_groups(conn, run_id, key)
    pending = apply_group_limit(pending, filters.limit_groups)

    made_progress = False
    saw_manual_retry_required = False
    for category_slug, group_id in pending:
        entry = get_checkpoint_entry(conn, run_id, key, category_slug, group_id)
        classification = classify_pending_unit(entry)
        if not should_attempt_this_pass(classification, retry_rejected=filters.retry_rejected):
            saw_manual_retry_required = True
            on_event(
                "GROUP_REJECTED_AWAITING_MANUAL_RETRY",
                spec_key=key,
                category_slug=category_slug,
                group_id=group_id,
            )
            continue

        group_url = _source_url_for_group(manifest, category_slug, group_id)
        group_capture = throttled_navigate(group_url)
        group_input = to_raw_capture_input(
            group_capture,
            capture_kind=CaptureKind.GROUP_DETAIL,
            run_id=run_id,
            expected_identity_context=_expected_context(spec),
        )
        group_result = process_capture_fn(
            conn,
            blob_store,
            capture_repo,
            run_id,
            group_input,
            context=context,
            category_slug=category_slug,
            group_id=group_id,
            spec_key=key,
        )
        if group_result.validation_outcome is ValidationOutcome.CHALLENGE:
            group_outcome = await_challenge_resolution(
                transport,
                conn,
                blob_store,
                capture_repo,
                run_id=run_id,
                capture_kind=CaptureKind.GROUP_DETAIL,
                source_url_hint=group_url,
                context=context,
                expected_identity_context=_expected_context(spec),
                category_slug=category_slug,
                group_id=group_id,
                spec_key=key,
                poll_interval=poll_interval,
                timeout=challenge_timeout,
                sleep=sleep,
                now=now,
                on_event=on_event,
                process_capture_fn=process_capture_fn,
            )
            if group_outcome.result is None:
                on_event(
                    "GROUP_CHALLENGE_TIMEOUT",
                    spec_key=key,
                    category_slug=category_slug,
                    group_id=group_id,
                )
                continue
            group_result = group_outcome.result

        if group_result.routed_to_parser and not group_result.critical_error:
            finalize_fn(conn, blob_store, capture_repo, run_id, key, context=context)
            made_progress = True
            on_event("GROUP_ACCEPTED", spec_key=key, category_slug=category_slug, group_id=group_id)
        else:
            on_event(
                "GROUP_REJECTED",
                spec_key=key,
                category_slug=category_slug,
                group_id=group_id,
                outcome=group_result.validation_outcome,
            )

    on_event("SPEC_PASS_COMPLETE", spec_key=key)
    if made_progress:
        disposition = SpecPassDisposition.PROGRESSED
    elif saw_manual_retry_required:
        disposition = SpecPassDisposition.MANUAL_RETRY_REQUIRED
    else:
        disposition = SpecPassDisposition.DEFERRED_THIS_SESSION
    return SpecPassOutcome(disposition=disposition)


# --- Nível A: MARKET_INDEX (005 T511 — extraído para ser reusado também --
# -- pelo orquestrador do worker pool, sempre sequencial, contracts/ ------
# -- worker-pool-contract.md §1) ------------------------------------------


def run_market_index_phase(
    transport: BrowserTransport,
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    *,
    run_id: str,
    context: CollectionContext,
    throttled_navigate: Callable[[str], BrowserCapture],
    poll_interval: float = _DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS,
    challenge_timeout: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_event: Callable[..., None] = lambda event, **kwargs: None,
) -> bool:
    """Nível A — MARKET_INDEX (extração mecânica de `run_collection_driver()`,
    005 — nenhuma mudança de comportamento). `--workers 1` continua chamando
    isto exclusivamente através de `run_collection_driver()`;
    `orchestration/worker_pool.py::run_pool()` chama diretamente, sempre no
    processo orquestrador, sempre antes de qualquer spawn de worker
    (contracts/worker-pool-contract.md §1 — nunca paralelizado: há no máximo
    uma página de índice por run).

    Retorna `True` quando a descoberta pode prosseguir (specs já
    persistidas via `process_capture`); `False` quando o run foi abortado
    (`RUN_ABORTED` já emitido, nada mais deve navegar/persistir)."""
    market_index_url = build_market_index_url(context)
    capture = throttled_navigate(market_index_url)
    capture_input = to_raw_capture_input(
        capture, capture_kind=CaptureKind.MARKET_INDEX, run_id=run_id
    )
    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        run_id,
        capture_input,
        context=context,
    )
    if result.validation_outcome is ValidationOutcome.CHALLENGE:
        outcome = await_challenge_resolution(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id=run_id,
            capture_kind=CaptureKind.MARKET_INDEX,
            source_url_hint=market_index_url,
            context=context,
            poll_interval=poll_interval,
            timeout=challenge_timeout,
            sleep=sleep,
            now=now,
            on_event=on_event,
        )
        if outcome.result is None:
            on_event("RUN_ABORTED", reason="MARKET_INDEX_CHALLENGE_TIMEOUT")
            return False
        result = outcome.result

    if result.critical_error:
        # 004, item 5/FR-041 (Cenário F): parse malformado OU market
        # extraído da página diverge de context.market — process_capture()
        # já garantiu que nada foi persistido; aqui só abortamos o run antes
        # de prosseguir para a descoberta de specs.
        on_event("RUN_ABORTED", reason="MARKET_INDEX_REJECTED")
        return False
    return True


# --- Laço de descoberta-e-ação (contracts/browser-transport-contract.md §3) -


def run_collection_driver(
    transport: BrowserTransport,
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    *,
    run_id: str,
    context: CollectionContext,
    filters: OperationalFilters | None = None,
    poll_interval: float = _DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS,
    challenge_timeout: float | None = None,
    min_interval: float = _DEFAULT_MIN_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_event: Callable[..., None] = lambda event, **kwargs: None,
) -> None:
    """MARKET_INDEX -> specs descobertas -> SPEC_NAVIGATION -> grupos pendentes
    -> GROUP_DETAIL -> try_finalize_spec_entry() (contracts/browser-transport-
    contract.md §3). Reutiliza exclusivamente process_capture()/
    get_pending_groups()/try_finalize_spec_entry() já existentes de 001 —
    nenhuma regra de domínio é reimplementada aqui.

    `context` (CollectionContext, 004) é a única fonte do contexto
    operacional desta coleta — escopa tanto a identidade atribuída às specs
    recém-descobertas no MARKET_INDEX (roteada por `process_capture`) quanto
    a descoberta (`list_by_scope`) usada para decidir o que processar nesta
    passada. Antes de qualquer `navigate()`/persistência, validamos que
    `context` corresponde exatamente ao `CollectionRun.scope` já persistido
    para `run_id` — um chamador que misture (por engano) o `run_id` de um
    modelo com o `context` de outro nunca chega a navegar ou escrever nada
    (item 1 da correção 004; ver também a mesma validação, independente, em
    `process_capture()`).

    A URL do índice de mercado é sempre derivada aqui, internamente, a
    partir de `context` (`build_market_index_url`) — nunca recebida como
    parâmetro separado (004, item 4/achado do Codex: duas fontes de verdade
    independentes — `context` e uma `market_index_url` solta — permitiriam
    navegar para a URL de um modelo enquanto processa/persiste sob o
    `context` de outro; com uma única fonte, isso é estruturalmente
    impossível).

    `min_interval` (Blocker 3, FR-029/US6) garante um espaçamento mínimo
    entre navegações reais sucessivas — nunca a primeira navegação, nunca
    aplicado aos polls de `current_capture()` do laço de challenge (esses já
    têm seu próprio `poll_interval`), e nunca confundido com o retry/backoff
    de falha de transporte (que vive inteiramente dentro do adapter
    concreto, invisível aqui). `min_interval=0` (default) nunca introduz
    espera.
    """
    run = get_collection_run(conn, run_id)
    if run is None or run.scope != context.scope():
        raise ContextScopeMismatchError(
            f"context {context.scope()!r} does not match CollectionRun(run_id={run_id!r})"
            f" — refusing to navigate, process or persist anything for this run"
        )

    filters = filters if filters is not None else OperationalFilters()

    last_navigate_at: datetime | None = None

    def throttled_navigate(url: str) -> BrowserCapture:
        nonlocal last_navigate_at
        if min_interval > 0 and last_navigate_at is not None:
            elapsed = (now() - last_navigate_at).total_seconds()
            remaining = min_interval - elapsed
            if remaining > 0:
                sleep(remaining)
        capture = transport.navigate(url)
        last_navigate_at = now()
        return capture

    # Nível A — MARKET_INDEX (005 T509/T511: extraído para run_market_index_phase())
    proceeded = run_market_index_phase(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id=run_id,
        context=context,
        throttled_navigate=throttled_navigate,
        poll_interval=poll_interval,
        challenge_timeout=challenge_timeout,
        sleep=sleep,
        now=now,
        on_event=on_event,
    )
    if not proceeded:
        return

    all_specs = list_by_scope(
        conn,
        manufacturer=context.manufacturer,
        vehicle_model=context.vehicle_model,
        market=context.market,
    )
    specs_to_process = apply_operational_filters(all_specs, filters)
    on_event("RUN_STARTED", discovered=len(all_specs), selected=len(specs_to_process))

    for index, spec in enumerate(specs_to_process, start=1):
        key = spec.stable_key()
        current_state = get_current_state(conn, key)
        if current_state is not None and key not in filters.force:
            on_event(
                "SPEC_SKIPPED_ALREADY_VALID", spec_key=key, progress=(index, len(specs_to_process))
            )
            continue

        on_event("SPEC_STARTED", spec_key=key, progress=(index, len(specs_to_process)))
        process_one_spec(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id=run_id,
            context=context,
            spec=spec,
            filters=filters,
            throttled_navigate=throttled_navigate,
            poll_interval=poll_interval,
            challenge_timeout=challenge_timeout,
            sleep=sleep,
            now=now,
            on_event=on_event,
        )

    _maybe_mark_run_completed(conn, run_id, now, context=context)
    on_event("RUN_SUMMARY")
