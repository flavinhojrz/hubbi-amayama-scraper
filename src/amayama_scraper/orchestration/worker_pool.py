"""worker_pool.py — orquestrador de paralelismo controlado por spec (005).

Composição raiz (mesmo papel de `collection_driver.py`, Constitution §6) —
conhece domínio + adapters concretos, nunca reimplementa regra de negócio.
`--workers 1` NUNCA passa por este módulo (`cli/main.py` chama
`run_collection_driver()` diretamente, FR-003) — nenhuma linha aqui é
executada no caminho legado.

Dois papéis distintos (contracts/worker-pool-contract.md §1-§2):

  - `run_pool()`: roda no processo ORQUESTRADOR — Nível A (MARKET_INDEX)
    sequencial (`run_market_index_phase()`, reusado de `collection_driver.py`
    sem alteração), spawn dos processos worker, loop de métricas, shutdown
    determinístico (`try/finally`), verificação de `exitcode`,
    `_maybe_mark_run_completed()` uma única vez (FR-033).
  - `run_worker_loop()`: roda em cada processo FILHO — reivindica specs via
    claim/lease atômico com fencing por token (`next_claimable_spec()`,
    FR-020/FR-062), processando cada uma com `process_one_spec()` (T509),
    validando o lease/token atomicamente antes de cada escrita.

Este módulo NUNCA importa `transport.chrome_cdp_adapter`/`selenium`
(`tests/unit/test_cli_composition_root.py` — só `cli/main.py` pode) — o
`transport: BrowserTransport` do orquestrador e o `worker_target`/
`process_factory`/`stop_event` usados para os processos filhos são sempre
injetados por quem monta a composição real (`cli/main.py`), nunca
construídos aqui.

Hardening pós-review (BLOCKER/HIGH, ver specs/005-performance-worker-pool/
tasks.md "Fase 9"/"Fase 10: Hardening pós-review"):

1. **Fencing de lease** (BLOCKER): `spec_lease.lease_token` incrementa a
   cada claim/renovação/takeover bem-sucedido. Toda escrita de estado da
   spec no caminho paralelo (`process_capture`/`try_finalize_spec_entry`,
   injetados em `process_one_spec()`/`await_challenge_resolution()`) é
   envolvida numa transação curta que primeiro confirma `(owner, token)`
   contra o estado atual — um worker que perdeu o lease nunca persiste
   depois de um takeover, e uma renovação que falha interrompe o
   processamento imediatamente (`LeaseFencingError`).
2. **Reclaim infinito — terminalidade real, nunca backoff temporal**
   (BLOCKER, 2ª rodada): `process_one_spec()` retorna
   `SpecPassOutcome.disposition` (`PROGRESSED`/`MANUAL_RETRY_REQUIRED`/
   `DEFERRED_THIS_SESSION`). Sem progresso, o worker grava uma disposição
   explícita em `spec_pool_disposition` (chaveada por `run_id + spec_key`,
   nunca por tempo de lease) e SEMPRE libera o lease normalmente.
   `next_claimable_spec()` exclui `MANUAL_RETRY_REQUIRED` da execução
   normal (só `--retry-rejected` reabre) e `DEFERRED_THIS_SESSION` apenas
   para o `pool_session_id` corrente — um novo `pool_session_id` (nova
   invocação de `run_pool()`, ex. `--resume`) pode tentar de novo.
3. **Shutdown determinístico** (BLOCKER): `run_pool()` registra cada
   `_ProcessHandle` na lista monitorada ANTES de chamar `.start()` (nunca
   depois — fecha a janela em que um `KeyboardInterrupt` durante/logo após
   `start()` deixaria um filho já iniciado fora do cleanup), sinaliza
   `stop_event` em `finally`, aguarda os filhos com timeout, `terminate()`
   os que sobrarem, e sempre `join()` todos antes de retornar/propagar.
   Cada etapa do cleanup checa `handle.pid is not None` antes de
   join()/terminate()/is_alive() — nunca chama essas operações num
   `_ProcessHandle` cujo `start()` nunca chegou a criar o processo real.
4. **Exitcode de worker** (HIGH): após o `join()` final, `run_pool()`
   verifica `exitcode` de cada processo — qualquer um != 0 vira
   `WorkerProcessFailedError` (identifica worker/porta/exitcode).
5. **Rate limiter não mata workers** (HIGH): `next_claimable_spec()`
   distingue "sem slot agora" (`throttled=True`, o worker permanece vivo e
   tenta de novo) de "nenhum trabalho pendente em lugar nenhum"
   (`throttled=False`, aí sim o worker encerra).
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from amayama_scraper.domain.collection_context import CollectionContext, ContextScopeMismatchError
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.ingestion.ports import RawBlobStore, RawCaptureRepository
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    SpecPassDisposition,
    apply_operational_filters,
    process_one_spec,
    run_market_index_phase,
)
from amayama_scraper.orchestration.collection_driver import (
    _maybe_mark_run_completed as maybe_mark_run_completed,
)
from amayama_scraper.orchestration.metrics import MetricsSnapshot, query_metrics
from amayama_scraper.orchestration.pipeline import (
    ProcessCaptureResult,
    process_capture,
    try_finalize_spec_entry,
)
from amayama_scraper.orchestration.rate_limiter import (
    RateLimiterConfig,
    on_challenge_observed,
    on_stability_tick,
)
from amayama_scraper.persistence.db import transaction
from amayama_scraper.persistence.repositories import (
    challenge_event_repo,
    lease_repo,
    rate_limiter_repo,
    spec_pool_disposition_repo,
    worker_heartbeat_repo,
)
from amayama_scraper.persistence.repositories.checkpoint_repo import get_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope
from amayama_scraper.snapshots.snapshot import SpecSnapshot
from amayama_scraper.transport.port import BrowserCapture, BrowserTransport

_DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS = 5.0
_DEFAULT_MIN_INTERVAL_SECONDS = 0.0
_DEFAULT_TERMINATE_TIMEOUT_SECONDS = 30.0


class LeaseFencingError(RuntimeError):
    """005 hardening (BLOCKER 1): o `(owner, lease_token)` que este worker
    detinha para uma spec não confere mais com o estado persistido — outro
    worker já fez takeover (lease expirado e reclamado, ou renovação
    concorrente). Levantada ANTES de qualquer escrita — nunca depois — e
    nunca capturada silenciosamente: interrompe imediatamente o
    processamento desta spec (contracts: "worker antigo nunca pode
    continuar gravando após takeover")."""


class WorkerProcessFailedError(RuntimeError):
    """005 hardening (HIGH — exitcode de worker): pelo menos um processo
    worker encerrou com `exitcode` inesperado (!= 0) — o pool nunca reporta
    sucesso silenciosamente nesse caso."""

    def __init__(self, failures: list[tuple[int, int, int | None]]) -> None:
        self.failures = failures
        detail = ", ".join(
            f"worker_index={index} cdp_port={port} exitcode={exitcode}"
            for index, port, exitcode in failures
        )
        super().__init__(f"{len(failures)} worker process(es) failed: {detail}")


@dataclass(frozen=True, slots=True)
class WorkerPoolConfig:
    """plan.md "Decisões de design" — todos os defaults são pontos de
    partida sugeridos, sempre configuráveis via CLI (`cli/options.py`)."""

    workers: int
    lease_seconds: float = 120.0
    challenge_window_seconds: float = 300.0
    challenge_threshold: int = 1
    stability_seconds: float = 600.0
    metrics_interval_seconds: float = 30.0
    heartbeat_staleness_seconds: float = 240.0

    def __post_init__(self) -> None:
        if not 1 <= self.workers <= 4:
            raise ValueError("WorkerPoolConfig.workers must be in [1, 4] (FR-001)")

    def rate_limiter_config(self) -> RateLimiterConfig:
        return RateLimiterConfig(
            max_concurrency=self.workers,
            challenge_window_seconds=self.challenge_window_seconds,
            challenge_threshold=self.challenge_threshold,
            stability_seconds=self.stability_seconds,
        )


def _require_run_context(conn: sqlite3.Connection, run_id: str, context: CollectionContext) -> None:
    """FR-100/FR-101: mesma validação de `run_collection_driver()` —
    reforçada aqui, em cada processo (orquestrador e cada worker), antes de
    qualquer navegação/claim/persistência."""
    run = get_collection_run(conn, run_id)
    if run is None or run.scope != context.scope():
        raise ContextScopeMismatchError(
            f"context {context.scope()!r} does not match CollectionRun(run_id={run_id!r})"
            " — refusing to navigate, claim or persist anything for this process"
        )


# --- Claim/lease (contracts/worker-pool-contract.md §3, FR-020, FR-024, FR-062) --


@dataclass(frozen=True, slots=True)
class ClaimedSpec:
    spec: SpecIdentity
    lease_token: int


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """005 hardening (HIGH — rate limiter não mata workers): `throttled=True`
    sinaliza que existe trabalho pendente em algum lugar deste run, apenas
    não disponível para este worker agora (sem slot de concorrência
    efetiva, ou todas as specs pendentes já ativamente leased por outros) —
    o chamador deve permanecer vivo e tentar de novo. `throttled=False` com
    `claimed=None` sinaliza terminal genuíno: nenhuma spec pendente resta,
    para ninguém."""

    claimed: ClaimedSpec | None
    throttled: bool


def _is_eligible(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    spec_key: str,
    pool_session_id: str,
    retry_rejected: bool,
) -> bool:
    """005 hardening (BLOCKER 2 — 2ª rodada): terminalidade real via
    disposição explícita (`spec_pool_disposition`), nunca por tempo de
    lease. `MANUAL_RETRY_REQUIRED` só é elegível com `--retry-rejected`
    (`filters.retry_rejected`) ativo — mesma semântica de
    `retry_classification.should_attempt_this_pass()` já usada dentro de
    `process_one_spec()`, agora também aplicada ANTES do claim.
    `DEFERRED_THIS_SESSION` só bloqueia para o `pool_session_id` que a
    produziu — uma nova invocação de `run_pool()` (`pool_session_id`
    diferente) sempre reavalia do zero."""
    disposition = spec_pool_disposition_repo.get(conn, run_id=run_id, spec_key=spec_key)
    if disposition is None:
        return True
    if disposition.state == "MANUAL_RETRY_REQUIRED":
        return retry_rejected
    if disposition.state == "DEFERRED_THIS_SESSION":
        return disposition.pool_session_id != pool_session_id
    return True  # pragma: no cover - estado desconhecido, falha aberta deliberadamente


def next_claimable_spec(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    context: CollectionContext,
    worker_id: str,
    filters: OperationalFilters,
    pool_config: WorkerPoolConfig,
    pool_session_id: str,
    now: datetime,
) -> ClaimResult:
    """Checagem de `effective_concurrency` + tentativa de claim, tudo dentro
    de UMA única transação `BEGIN IMMEDIATE` (FR-031, FR-062) — nunca dois
    workers leem "ainda há slot" e ambos reivindicam além do limite. Specs já
    `VALID`/`STALE` (exceto as listadas em `filters.force`) nunca são
    reivindicadas (FR-024). Specs com disposição `MANUAL_RETRY_REQUIRED`/
    `DEFERRED_THIS_SESSION` (005 hardening, BLOCKER 2 — 2ª rodada) são
    excluídas conforme `_is_eligible()` — nunca por backoff temporal. Uma
    spec com lease ativo em tempo real (outro worker processando agora) é
    excluída independente do dono."""
    with transaction(conn):
        config = pool_config.rate_limiter_config()
        state = rate_limiter_repo.read_state(conn, run_id=run_id, config=config, now=now)
        # FR-064: cada tentativa de claim é também uma oportunidade de
        # recuperação gradual — se o período estável já decorreu, sobe 1
        # nível ANTES de decidir se há slot para esta tentativa. Roda mesmo
        # quando não há mais candidatos pendentes (mantém o estado do rate
        # limiter correto para observabilidade/US4).
        recovered_state = on_stability_tick(state, now, config)
        if recovered_state != state:
            rate_limiter_repo.write_state(conn, run_id=run_id, state=recovered_state, now=now)
            state = recovered_state

        all_specs = list_by_scope(
            conn,
            manufacturer=context.manufacturer,
            vehicle_model=context.vehicle_model,
            market=context.market,
        )
        candidates = apply_operational_filters(all_specs, filters)
        pending_specs = [
            spec
            for spec in candidates
            if get_current_state(conn, spec.stable_key()) is None
            or spec.stable_key() in filters.force
        ]
        if not pending_specs:
            return ClaimResult(claimed=None, throttled=False)  # nada pendente, para ninguém

        eligible_specs = [
            spec
            for spec in pending_specs
            if _is_eligible(
                conn,
                run_id=run_id,
                spec_key=spec.stable_key(),
                pool_session_id=pool_session_id,
                retry_rejected=filters.retry_rejected,
            )
        ]
        if not eligible_specs:
            # só resta trabalho MANUAL_RETRY_REQUIRED (sem --retry-rejected)
            # e/ou DEFERRED_THIS_SESSION desta mesma sessão — terminal para
            # ESTA invocação de run_pool(), nunca um estado do qual o pool
            # "acorda" sozinho depois de esperar mais.
            return ClaimResult(claimed=None, throttled=False)

        active_spec_keys = lease_repo.list_active_lease_spec_keys(conn, run_id=run_id, now=now)
        if len(active_spec_keys) >= state.effective_concurrency:
            return ClaimResult(claimed=None, throttled=True)

        for spec in eligible_specs:
            key = spec.stable_key()
            if key in active_spec_keys:
                continue
            token = lease_repo.try_claim(
                conn,
                run_id=run_id,
                spec_key=key,
                owner=worker_id,
                now=now,
                lease_seconds=pool_config.lease_seconds,
            )
            if token is not None:
                return ClaimResult(
                    claimed=ClaimedSpec(spec=spec, lease_token=token), throttled=False
                )
        # havia specs elegíveis, mas todas ativamente leased por outros (ou
        # perdemos a corrida do try_claim) — ainda há trabalho, só não agora.
        return ClaimResult(claimed=None, throttled=True)


# --- Fencing das escritas (contracts, BLOCKER 1) ----------------------------


def _make_fenced_process_capture(
    conn: sqlite3.Connection, *, run_id: str, held: dict[str, object]
) -> Callable[..., ProcessCaptureResult]:
    """Envolve `process_capture()` numa transação curta que primeiro
    confirma `(owner, lease_token)` — nunca escreve sob um lease perdido."""

    def fenced(conn_arg, blob_store, capture_repo, run_id_arg, capture_input, **kwargs):  # type: ignore[no-untyped-def]
        with transaction(conn_arg):
            spec_key = held.get("spec_key")
            current = lease_repo.get_lease_token(conn_arg, run_id=run_id, spec_key=str(spec_key))
            if current != (held.get("owner"), held.get("token")):
                raise LeaseFencingError(
                    f"lease fencing check failed for spec_key={spec_key!r}: held "
                    f"(owner={held.get('owner')!r}, token={held.get('token')!r}) does not match "
                    f"current lease {current!r} — refusing to persist, another worker took over"
                )
            return process_capture(
                conn_arg, blob_store, capture_repo, run_id_arg, capture_input, **kwargs
            )

    return fenced


def _make_fenced_finalize(
    conn: sqlite3.Connection, *, run_id: str, held: dict[str, object]
) -> Callable[..., SpecSnapshot | None]:
    """Envolve `try_finalize_spec_entry()` para que a escrita de
    snapshot/current_state (`finalize_spec_entry`'s `fn()`) rode dentro da
    MESMA transação do check de fencing — substitui o
    `run_in_transaction` default (`persistence.db.run_in_transaction`) por
    um que primeiro confirma `(owner, lease_token)`."""

    def fenced(conn_arg, blob_store, capture_repo, run_id_arg, spec_key_arg, *, context):  # type: ignore[no-untyped-def]
        def checked_run_in_transaction(
            fn: Callable[[], SpecSnapshot],
        ) -> SpecSnapshot:
            with transaction(conn_arg):
                current = lease_repo.get_lease_token(conn_arg, run_id=run_id, spec_key=spec_key_arg)
                if current != (held.get("owner"), held.get("token")):
                    raise LeaseFencingError(
                        f"lease fencing check failed for spec_key={spec_key_arg!r}: held "
                        f"(owner={held.get('owner')!r}, token={held.get('token')!r}) does not "
                        f"match current lease {current!r} — refusing to finalize, another worker "
                        "took over"
                    )
                return fn()

        return try_finalize_spec_entry(
            conn_arg,
            blob_store,
            capture_repo,
            run_id_arg,
            spec_key_arg,
            context=context,
            run_in_transaction=checked_run_in_transaction,
        )

    return fenced


# --- Instrumentação de challenge/rate-limiter/heartbeat/renovação (US3, US4) -


def _instrumented_on_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    worker_id: str,
    pool_config: WorkerPoolConfig,
    now: Callable[[], datetime],
    held: dict[str, object],
    inner_on_event: Callable[..., None],
) -> Callable[..., None]:
    """Envolve o `on_event` já existente (nunca substitui — sempre repassa
    ao final) para: (a) renovar o lease da spec em progresso a cada evento
    (FR-022 — `held["spec_key"]` é `None` para o processo orquestrador
    durante o Nível A, que não detém lease nenhum); uma renovação que falha
    (005 hardening, BLOCKER 1) levanta `LeaseFencingError` IMEDIATAMENTE —
    nunca continua processando sob um lease perdido; (b) registrar
    `challenge_event` e reagir no rate limiter (FR-051, FR-063) quando um
    challenge é observado/resolvido."""
    open_event_id: dict[str, int] = {}

    def on_event(event: str, **fields: object) -> None:
        moment = now()
        spec_key = held.get("spec_key")
        if spec_key is not None:
            new_token = lease_repo.renew_lease(
                conn,
                run_id=run_id,
                spec_key=str(spec_key),
                owner=str(held.get("owner")),
                now=moment,
                lease_seconds=pool_config.lease_seconds,
            )
            if new_token is None:
                raise LeaseFencingError(
                    f"renewal failed for spec_key={spec_key!r}, owner={held.get('owner')!r} — "
                    "lease already taken over by another worker; interrupting immediately"
                )
            held["token"] = new_token

        if event == "CHALLENGE_WAITING":
            raw_capture_kind = fields.get("capture_kind")
            event_id = challenge_event_repo.record_observed(
                conn,
                run_id=run_id,
                worker_id=worker_id,
                capture_kind=str(raw_capture_kind) if raw_capture_kind is not None else "UNKNOWN",
                observed_at=moment,
                spec_key=str(spec_key) if spec_key is not None else None,
            )
            open_event_id["id"] = event_id

            config = pool_config.rate_limiter_config()
            state = rate_limiter_repo.read_state(conn, run_id=run_id, config=config, now=moment)
            count = challenge_event_repo.count_in_window(
                conn, run_id=run_id, now=moment, window_seconds=pool_config.challenge_window_seconds
            )
            new_state = on_challenge_observed(
                state, moment, config, recent_challenge_count_in_window=count
            )
            rate_limiter_repo.write_state(conn, run_id=run_id, state=new_state, now=moment)
        elif event in ("CHALLENGE_RESOLVED", "CHALLENGE_TIMEOUT"):
            closed_event_id = open_event_id.pop("id", None)
            if closed_event_id is not None:
                challenge_event_repo.record_resolved(
                    conn, event_id=closed_event_id, resolved_at=moment
                )

        inner_on_event(event, **fields)

    return on_event


# --- Worker: loop de claim -> process_one_spec -> release/backoff (§2) -----


class StopEventLike(Protocol):
    """Duck-typed — `threading.Event` (testes) ou
    `multiprocessing.synchronize.Event` (produção, `cli/main.py`)."""

    def is_set(self) -> bool: ...
    def set(self) -> None: ...


def run_worker_loop(
    transport: BrowserTransport,
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    *,
    run_id: str,
    context: CollectionContext,
    worker_id: str,
    filters: OperationalFilters,
    pool_config: WorkerPoolConfig,
    pool_session_id: str,
    poll_interval: float = _DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS,
    challenge_timeout: float | None = None,
    min_interval: float = _DEFAULT_MIN_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_event: Callable[..., None] = lambda event, **kwargs: None,
    stop_event: StopEventLike | None = None,
) -> None:
    """Loop de um worker: reivindica a próxima spec claimable
    (`next_claimable_spec()`, sempre com o MESMO `pool_session_id` desta
    invocação de `run_pool()` — todos os workers de uma mesma invocação
    compartilham o mesmo valor), processa via `process_one_spec()` (T509,
    reuso estrito — nenhuma regra de domínio reimplementada) com escrita
    fencing (BLOCKER 1). Ao final de cada passagem sem progresso, grava uma
    disposição explícita (`MANUAL_RETRY_REQUIRED`/`DEFERRED_THIS_SESSION`,
    BLOCKER 2 — 2ª rodada) e SEMPRE libera o lease normalmente — a
    elegibilidade futura nunca depende de tempo de lease. Repete até não
    haver mais trabalho elegível em lugar nenhum
    (`ClaimResult.throttled is False`) ou até `stop_event` ser sinalizado
    (BLOCKER 3 — checado a cada iteração, entre specs).

    Recebe `transport`/`conn` já construídos — nunca constrói
    `ChromeCdpTransport` (isso violaria a fronteira verificada por
    `tests/unit/test_cli_composition_root.py`; a construção real vive em
    `cli/main.py`, o único módulo autorizado)."""
    _require_run_context(conn, run_id, context)

    held: dict[str, object] = {"owner": worker_id, "token": None, "spec_key": None}
    instrumented = _instrumented_on_event(
        conn,
        run_id=run_id,
        worker_id=worker_id,
        pool_config=pool_config,
        now=now,
        held=held,
        inner_on_event=on_event,
    )
    fenced_process_capture = _make_fenced_process_capture(conn, run_id=run_id, held=held)
    fenced_finalize = _make_fenced_finalize(conn, run_id=run_id, held=held)

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

    while True:
        if stop_event is not None and stop_event.is_set():
            on_event("WORKER_STOPPING", worker_id=worker_id, reason="stop_event")
            return

        moment = now()
        worker_heartbeat_repo.upsert_heartbeat(
            conn, run_id=run_id, worker_id=worker_id, pid=os.getpid(), now=moment
        )
        result = next_claimable_spec(
            conn,
            run_id=run_id,
            context=context,
            worker_id=worker_id,
            filters=filters,
            pool_config=pool_config,
            pool_session_id=pool_session_id,
            now=moment,
        )
        if result.claimed is None:
            if result.throttled:
                on_event("WORKER_THROTTLED_WAITING_FOR_SLOT", worker_id=worker_id)
                sleep(poll_interval)
                continue
            on_event("WORKER_IDLE_NO_CLAIMABLE_SPEC", worker_id=worker_id)
            return

        spec = result.claimed.spec
        key = spec.stable_key()
        held["token"] = result.claimed.lease_token
        held["spec_key"] = key
        instrumented("SPEC_STARTED", spec_key=key, worker_id=worker_id)
        try:
            outcome = process_one_spec(
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
                on_event=instrumented,
                process_capture_fn=fenced_process_capture,
                finalize_fn=fenced_finalize,
            )
        except LeaseFencingError as exc:
            # 005 hardening (BLOCKER 1): este worker perdeu o lease durante o
            # processamento — nunca libera/renova/persiste mais nada para
            # esta spec (não é mais seu dono); segue para a próxima
            # tentativa de claim, não derruba o worker inteiro.
            on_event("LEASE_LOST", worker_id=worker_id, spec_key=key, reason=str(exc))
            held["spec_key"] = None
            held["token"] = None
            continue
        finally:
            held["spec_key"] = None

        # 005 hardening (BLOCKER 2 — 2ª rodada): disposição explícita
        # decide elegibilidade FUTURA; o lease em si é SEMPRE liberado
        # normalmente aqui — nunca estendido como mecanismo de cooldown.
        if outcome.disposition is SpecPassDisposition.PROGRESSED:
            spec_pool_disposition_repo.clear(conn, run_id=run_id, spec_key=key)
        elif outcome.disposition is SpecPassDisposition.MANUAL_RETRY_REQUIRED:
            spec_pool_disposition_repo.set_manual_retry_required(
                conn, run_id=run_id, spec_key=key, now=now()
            )
        else:  # DEFERRED_THIS_SESSION
            spec_pool_disposition_repo.set_deferred_this_session(
                conn, run_id=run_id, spec_key=key, pool_session_id=pool_session_id, now=now()
            )
        lease_repo.release_lease(conn, run_id=run_id, spec_key=key, owner=worker_id, now=now())


# --- Processo filho: args picklable (multiprocessing, contexto spawn) -----


@dataclass(frozen=True, slots=True)
class WorkerProcessArgs:
    """Payload picklable passado a cada processo worker real
    (`multiprocessing.get_context("spawn").Process`, contracts/
    worker-pool-contract.md §0/§1) — apenas dados (strings/números/
    dataclasses de dados), nunca um objeto vivo (conexão/transporte) do
    processo pai. O entrypoint real que consome isto e constrói
    `ChromeCdpTransport`/`sqlite3.Connection` vive em `cli/main.py` (único
    módulo autorizado a importar `transport.chrome_cdp_adapter`)."""

    db_path: str
    raw_root: str
    run_id: str
    context: CollectionContext
    worker_index: int
    cdp_host: str
    cdp_port: int
    filters: OperationalFilters
    pool_config: WorkerPoolConfig
    pool_session_id: str
    poll_interval: float
    challenge_timeout: float | None
    min_interval: float


def worker_id_for(run_id: str, worker_index: int, pid: int) -> str:
    return f"{run_id}:{worker_index}:{pid}"


class _ProcessHandle(Protocol):
    def start(self) -> None: ...
    def join(self, timeout: float | None = None) -> None: ...
    def is_alive(self) -> bool: ...
    def terminate(self) -> None: ...
    @property
    def exitcode(self) -> int | None: ...
    @property
    def pid(self) -> int | None:
        """005 hardening (HIGH — race entre `Process.start()` e registro do
        filho): `None` até `start()` efetivamente criar o processo/thread
        real; nunca `None` depois. O cleanup de `run_pool()` usa isto para
        decidir com segurança se `join()`/`terminate()`/`is_alive()` podem
        ser chamados num handle registrado cujo `start()` pode não ter
        chegado a criar o filho real (`multiprocessing.Process`/
        `threading.Thread` ambos levantam erro ao chamar essas operações
        antes de iniciar)."""
        ...


# --- Orquestrador: Nível A sequencial -> spawn -> métricas -> shutdown (§1) -


def run_pool(
    transport: BrowserTransport,
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    *,
    run_id: str,
    context: CollectionContext,
    filters: OperationalFilters,
    pool_config: WorkerPoolConfig,
    db_path: str,
    raw_root: str,
    cdp_host: str,
    cdp_ports: list[int],
    worker_target: Callable[[WorkerProcessArgs, StopEventLike], None],
    process_factory: Callable[
        [Callable[[WorkerProcessArgs, StopEventLike], None], WorkerProcessArgs, StopEventLike],
        _ProcessHandle,
    ],
    stop_event: StopEventLike,
    poll_interval: float = _DEFAULT_CHALLENGE_POLL_INTERVAL_SECONDS,
    challenge_timeout: float | None = None,
    min_interval: float = _DEFAULT_MIN_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_event: Callable[..., None] = lambda event, **kwargs: None,
    terminate_timeout: float = _DEFAULT_TERMINATE_TIMEOUT_SECONDS,
) -> None:
    """`--workers N > 1` (FR-003 nunca aplicável aqui — este é o caminho
    exclusivo de N > 1). `transport` é do PRÓPRIO orquestrador, usado apenas
    para o Nível A (MARKET_INDEX, sempre sequencial — contracts/
    worker-pool-contract.md §1/"Decisões de design" #3). `process_factory`/
    `worker_target`/`stop_event` são sempre injetados — em produção,
    `multiprocessing.get_context("spawn")` (montado por `cli/main.py`); em
    teste, um double que roda `worker_target` síncrono/em thread, sem
    exigir Chrome real.

    Shutdown determinístico (005 hardening, BLOCKER 3; HIGH — race
    `Process.start()`/registro, 2ª rodada): cada `_ProcessHandle` é
    registrado na lista monitorada ANTES de `.start()` ser chamado (nunca
    depois — um `KeyboardInterrupt` durante/logo após `start()` nunca deixa
    um filho já iniciado fora do cleanup). A partir do primeiro registro,
    todo spawn+monitoramento roda dentro de um `try/finally` —
    `KeyboardInterrupt` (ou qualquer exceção) sinaliza `stop_event`, aguarda
    os filhos com `terminate_timeout`, `terminate()` os que sobrarem, e
    sempre `join()` todos antes de retornar/propagar a exceção original.
    Cada etapa do cleanup checa `handle.pid is not None` primeiro — um
    handle registrado cujo `start()` nunca chegou a criar o processo/thread
    real nunca é join()ado/terminate()ado/consultado com `is_alive()`
    (ambos os tipos de `_ProcessHandle` levantam erro nessas chamadas antes
    de iniciar). Nenhum worker órfão após esta função retornar ou levantar.
    Após o `join()` final, cada `exitcode` é verificado (005 hardening,
    HIGH) — qualquer um != 0 vira `WorkerProcessFailedError`, nunca sucesso
    silencioso.

    `pool_session_id` (005 hardening, BLOCKER 2 — 2ª rodada): gerado UMA
    vez por invocação de `run_pool()`, repassado a todos os workers via
    `WorkerProcessArgs` — usado para escopar `DEFERRED_THIS_SESSION`
    (falhas transitórias sem progresso só ficam inelegíveis NESTA
    invocação; uma nova invocação, ex. `--resume`, gera outro
    `pool_session_id` e pode tentar de novo)."""
    _require_run_context(conn, run_id, context)

    if len(cdp_ports) != pool_config.workers:
        raise ValueError(
            f"cdp_ports must have exactly {pool_config.workers} entries (one per worker), "
            f"got {len(cdp_ports)}"
        )

    held: dict[str, object] = {"owner": "orchestrator", "token": None, "spec_key": None}
    orchestrator_on_event = _instrumented_on_event(
        conn,
        run_id=run_id,
        worker_id="orchestrator",
        pool_config=pool_config,
        now=now,
        held=held,
        inner_on_event=on_event,
    )

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
        on_event=orchestrator_on_event,
    )
    if not proceeded:
        return

    all_specs = list_by_scope(
        conn,
        manufacturer=context.manufacturer,
        vehicle_model=context.vehicle_model,
        market=context.market,
    )
    selected = apply_operational_filters(all_specs, filters)
    on_event("RUN_STARTED", discovered=len(all_specs), selected=len(selected))

    pool_session_id = str(uuid.uuid4())

    workers: list[tuple[int, int, _ProcessHandle]] = []
    try:
        for index, cdp_port in enumerate(cdp_ports):
            args = WorkerProcessArgs(
                db_path=db_path,
                raw_root=raw_root,
                run_id=run_id,
                context=context,
                worker_index=index,
                cdp_host=cdp_host,
                cdp_port=cdp_port,
                filters=filters,
                pool_config=pool_config,
                pool_session_id=pool_session_id,
                poll_interval=poll_interval,
                challenge_timeout=challenge_timeout,
                min_interval=min_interval,
            )
            handle = process_factory(worker_target, args, stop_event)
            # 005 hardening (HIGH — race entre Process.start() e registro do
            # filho, 2ª rodada): registrado ANTES de start() — se
            # KeyboardInterrupt (ou qualquer exceção) ocorrer dentro/logo
            # após start(), este handle já está na lista que o `finally`
            # abaixo aguarda/encerra, nunca ficando de fora do cleanup.
            workers.append((index, cdp_port, handle))
            handle.start()

        previous_snapshot: MetricsSnapshot | None = None
        previous_at = now()
        while any(handle.is_alive() for _, _, handle in workers):
            if stop_event.is_set():
                break
            sleep(pool_config.metrics_interval_seconds)
            moment = now()
            snapshot = query_metrics(
                conn,
                run_id=run_id,
                context=context,
                previous=previous_snapshot,
                previous_at=previous_at,
                now=moment,
                pool_config=pool_config,
            )
            on_event("METRICS", **asdict(snapshot))
            previous_snapshot, previous_at = snapshot, moment
    finally:
        stop_event.set()
        # Cada etapa checa `pid is not None` primeiro — um handle registrado
        # cujo start() nunca chegou a criar o processo/thread real (falhou
        # antes, ou foi interrompido antes de completar) nunca é
        # join()ado/terminate()ado/consultado com is_alive() (ambos
        # multiprocessing.Process e o double de teste levantam erro nessas
        # chamadas antes de iniciar) — mas TODO processo que chegou a
        # iniciar passa por join() obrigatoriamente abaixo.
        deadline = now() + timedelta(seconds=terminate_timeout)
        for _, _, handle in workers:
            if handle.pid is None:
                continue
            remaining = max(0.0, (deadline - now()).total_seconds())
            handle.join(remaining)
        for _, _, handle in workers:
            if handle.pid is not None and handle.is_alive():
                handle.terminate()
        for _, _, handle in workers:
            if handle.pid is not None:
                handle.join()

    failures = [
        (index, port, handle.exitcode)
        for index, port, handle in workers
        if handle.exitcode not in (0, None)
    ]
    if failures:
        raise WorkerProcessFailedError(failures)

    maybe_mark_run_completed(conn, run_id, now, context=context)
    on_event("RUN_SUMMARY")


__all__ = [
    "ClaimResult",
    "ClaimedSpec",
    "LeaseFencingError",
    "StopEventLike",
    "WorkerPoolConfig",
    "WorkerProcessArgs",
    "WorkerProcessFailedError",
    "next_claimable_spec",
    "run_pool",
    "run_worker_loop",
    "worker_id_for",
]
