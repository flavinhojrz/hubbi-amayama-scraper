"""cli/main.py — entrypoint fino. Único lugar que instancia ChromeCdpTransport
concreto (research.md §5; verificado por tests/unit/test_cli_composition_root.py).

A CLI apenas: valida opções (cli/options.py), monta configuração, seleciona
o modo (dry-run vs. execução real), chama orchestration/, retorna exit code.
Nenhuma lógica de parsing EPC/domínio vive aqui.

Exit codes documentados:
    0 — sucesso (dry-run ou run real).
    2 — --resume incompatível/ambíguo (IncompatibleResumeRunError/AmbiguousResumeError).
    3 — Chrome/CDP inalcançável (ChromeNotReachableError).
    4 — --manufacturer/--vehicle-model/--market inválido (InvalidScopeComponentError).
    5 — CollectionRun.scope corrompido no banco (InvalidScopeError/
        InvalidScopeComponentError ao reconstruir uma linha já persistida) —
        falha fechada, nunca tratado silenciosamente como Amarok/default (004).
    6 — --workers fora de [1, 4], ou --cdp-ports com número de portas
        diferente de --workers (005 FR-001).
    7 — pelo menos um worker filho encerrou com exitcode inesperado
        (WorkerProcessFailedError, 005 hardening pós-review — nunca sucesso
        silencioso).
    8 — --repair-manifest combinado com --resume/--new-run/--dry-run
        (gerencia a seleção de run sozinho, ver _run_repair()), ou nenhum
        scope encontrado para reparar (--repair-all-scopes sem nenhuma
        CollectionRun existente para --manufacturer).
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sqlite3
import sys
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from amayama_scraper.checkpoint.resume import get_pending_groups
from amayama_scraper.cli.options import parse_args
from amayama_scraper.domain.collection_context import (
    CollectionContext,
    InvalidScopeComponentError,
    InvalidScopeError,
    normalize_scope_component,
    parse_scope,
)
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.orchestration.dry_run import OperationalPlan, ReadOnlyRepos, plan_operation
from amayama_scraper.orchestration.progress_reporter import make_terminal_reporter
from amayama_scraper.orchestration.run_selection import (
    AmbiguousResumeError,
    IncompatibleResumeRunError,
    select_run,
)
from amayama_scraper.orchestration.worker_pool import (
    StopEventLike,
    WorkerPoolConfig,
    WorkerProcessArgs,
    WorkerProcessFailedError,
    run_pool,
    run_worker_loop,
    worker_id_for,
)
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    get_latest_run_for_scope,
    list_distinct_scopes_for_manufacturer,
    list_incomplete_runs,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope
from amayama_scraper.transport.chrome_cdp_adapter import (
    ChromeCdpTransport,
    resolve_cdp_host,
    resolve_cdp_port,
)
from amayama_scraper.transport.errors import ChromeLaunchFailedError, ChromeNotReachableError
from amayama_scraper.transport.port import BrowserTransport
from amayama_scraper.transport.undetected_chrome_adapter import UndetectedChromeTransport

DEFAULT_DB_PATH = "amayama.db"
DEFAULT_RAW_ROOT = "amayama_raw"


def _resolve_cdp_ports(args: argparse.Namespace) -> list[int]:
    """005 FR-042: uma porta por worker — lista explícita (`--cdp-ports`) ou
    derivada de `--cdp-port`/`AMAYAMA_CDP_PORT`/9222 como base + índice do
    worker (plan.md "Decisões de design" #2)."""
    if args.cdp_ports:
        return [int(part.strip()) for part in args.cdp_ports.split(",")]
    base = resolve_cdp_port(args.cdp_port)
    return [base + i for i in range(args.workers)]


def _worker_process_entrypoint(worker_args: WorkerProcessArgs, stop_event: StopEventLike) -> None:
    """Entrypoint do processo filho (`multiprocessing`, contexto `spawn` —
    contracts/worker-pool-contract.md §0/§2). Único lugar, junto com
    `main()` abaixo, que constrói um `ChromeCdpTransport`/
    `UndetectedChromeTransport` real para um worker — `orchestration/
    worker_pool.py` nunca importa nenhum dos dois adapters
    (tests/unit/test_cli_composition_root.py).

    `stop_event` (005 hardening, BLOCKER 3 — shutdown determinístico):
    checado por `run_worker_loop()` a cada iteração — sinalizado pelo
    processo pai (`run_pool()`) em `finally`, garante encerramento
    cooperativo entre specs em vez de depender só de `terminate()`."""
    conn = connect(worker_args.db_path)
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(Path(worker_args.raw_root), conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    transport: BrowserTransport
    if worker_args.own_chrome:
        transport = UndetectedChromeTransport(headless=worker_args.chrome_headless)
    else:
        transport = ChromeCdpTransport(host=worker_args.cdp_host, port=worker_args.cdp_port)
    worker_id = worker_id_for(worker_args.run_id, worker_args.worker_index, os.getpid())
    on_event = make_terminal_reporter(run_id=f"{worker_args.run_id}:{worker_id}")
    try:
        run_worker_loop(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id=worker_args.run_id,
            context=worker_args.context,
            worker_id=worker_id,
            filters=worker_args.filters,
            pool_config=worker_args.pool_config,
            pool_session_id=worker_args.pool_session_id,
            poll_interval=worker_args.poll_interval,
            challenge_timeout=worker_args.challenge_timeout,
            min_interval=worker_args.min_interval,
            enable_detail_batch_fetch=worker_args.enable_detail_batch_fetch,
            detail_fetch_batch_size=worker_args.detail_fetch_batch_size,
            detail_fetch_chunk_size=worker_args.detail_fetch_chunk_size,
            detail_fetch_timeout_ms=worker_args.detail_fetch_timeout_ms,
            on_event=on_event,
            stop_event=stop_event,
        )
    finally:
        if worker_args.own_chrome:
            transport.close()  # type: ignore[union-attr]


def _spawn_worker_process(
    target: Callable[[WorkerProcessArgs, StopEventLike], None],
    worker_args: WorkerProcessArgs,
    stop_event: StopEventLike,
) -> multiprocessing.process.BaseProcess:
    ctx = multiprocessing.get_context("spawn")
    return ctx.Process(target=target, args=(worker_args, stop_event))


def _read_only_repos(
    conn: sqlite3.Connection, *, manufacturer: str, vehicle_model: str, market: str
) -> ReadOnlyRepos:
    return ReadOnlyRepos(
        get_collection_run=partial(get_collection_run, conn),
        list_incomplete_runs=partial(list_incomplete_runs, conn),
        list_all_spec_identities=partial(
            list_by_scope,
            conn,
            manufacturer=manufacturer,
            vehicle_model=vehicle_model,
            market=market,
        ),
        get_current_state=partial(get_current_state, conn),
        get_authoritative_manifest=partial(get_authoritative, conn),
        get_pending_groups=partial(get_pending_groups, conn),
    )


def _empty_read_only_repos() -> ReadOnlyRepos:
    """Blocker 1 (Codex) — usada quando --db-path aponta para um arquivo que
    ainda não existe: DEC-009 proíbe que --dry-run crie o DB. Estado vazio
    é reportado sem tocar o filesystem, sem abrir nenhuma conexão SQLite."""
    return ReadOnlyRepos(
        get_collection_run=lambda run_id: None,
        list_incomplete_runs=lambda scope: [],
        list_all_spec_identities=list,
        get_current_state=lambda key: None,
        get_authoritative_manifest=lambda key, run_id: None,
        get_pending_groups=lambda run_id, key: [],
    )


def _has_pending_wal_data(db_path: str) -> bool:
    """True quando `<db_path>-wal` existe e tem conteúdo — ou seja, há
    commits reais ainda não checkpointados para o arquivo principal, feitos
    por um writer que continua com a conexão aberta (Codex — regressão do
    Blocker 1 original).

    Confirmado empiricamente (não apenas por leitura da documentação do
    SQLite): um banco recém-fechado normalmente por
    `persistence.db.connect()` (que sempre liga WAL) não deixa nenhum
    `-wal`/`-shm` para trás — o checkpoint automático do SQLite ao fechar a
    última conexão os remove. `-wal` só existe e tem tamanho > 0 quando um
    writer ainda está com a conexão aberta e já commitou algo (autocommit,
    `isolation_level=None`, como todo o resto deste projeto usa) sem que um
    checkpoint completo tenha ocorrido ainda — exatamente o cenário relatado
    pelo Codex."""
    wal_path = Path(f"{db_path}-wal")
    return wal_path.exists() and wal_path.stat().st_size > 0


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    """Blocker 1 (Codex, corrigido) — conexão somente-leitura para --dry-run
    quando o DB já existe. Duas estratégias, escolhidas dinamicamente,
    nunca uma única "universal":

    - Sem WAL pendente (nenhum `-wal`/`-shm` preexistente, ou `-wal`
      totalmente checkpontado/vazio): `mode=ro&immutable=1`. Evita que o
      SQLite crie `-shm`/`-wal` como efeito colateral de uma leitura pura
      (Blocker 1 original) — seguro aqui porque não há nada pendente que
      `immutable=1` poderia deixar de enxergar.
    - Com WAL pendente (writer legítimo ainda aberto, dados já commitados
      só no WAL — regressão reportada pelo Codex): `mode=ro` SEM
      `immutable=1`. `immutable=1` faz o SQLite ler apenas o arquivo
      principal, ignorando o WAL inteiramente — confirmado empiricamente
      que isso chega a esconder até `CREATE TABLE`s existentes somente no
      WAL. `mode=ro` puro participa do protocolo de leitura do WAL
      corretamente, reaproveitando os `-shm`/`-wal` JÁ EXISTENTES (criados
      pelo writer, não por esta conexão) sem criar nada novo nem alterar o
      tamanho desses arquivos — confirmado empiricamente (ver testes desta
      correção). Nunca abre read-write, nunca executa checkpoint, nunca
      altera journal_mode, nunca força o fechamento do writer.
    """
    if _has_pending_wal_data(db_path):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _print_plan(plan: OperationalPlan) -> None:
    print(f"run: {plan.run_decision}")
    print(f"discovered specs: {plan.discovered_spec_count}")
    print(f"specs to process: {len(plan.specs_to_process)}")
    for key in plan.specs_to_process:
        if key in plan.pending_groups_by_spec:
            print(f"  {key}: {len(plan.pending_groups_by_spec[key])} pending group(s)")
        elif key in plan.specs_without_manifest_yet:
            print(f"  {key}: manifest not yet captured")
    print(f"already VALID (would be skipped): {len(plan.already_valid_specs)}")


def _execute_collection(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    blob_store: FilesystemRawBlobStore,
    capture_repo: SqliteRawCaptureRepository,
    *,
    run_id: str,
    context: CollectionContext,
    filters: OperationalFilters,
    db_path: str,
    raw_root: Path,
    cdp_ports: list[int] | None,
) -> int:
    """Corpo comum de execução real (`--workers 1` via `run_collection_driver()`
    ou `--workers N>1` via `run_pool()`) — extraído de `main()` para ser
    reusado também por `_run_repair()` (bug fix de manifest truncado): o
    repair só precisa decidir QUAL `run_id`/`context`/`filters` usar (reabre
    a CollectionRun existente do scope em vez de `select_run()`), a
    execução real em si é idêntica byte-a-byte à de `run`.

    `--own-chrome` (decisão do usuário, 2026-09-10): troca `ChromeCdpTransport`
    (anexa a um Chrome já aberto) por `UndetectedChromeTransport` (lança seu
    próprio Chrome por worker, resolve reCAPTCHA automaticamente quando
    `CAPTCHA_API_URL`/`TOKEN_API` estão configurados). `cdp_ports`/`--workers`
    continuam controlando SÓ a contagem de workers nesse modo — cada um lança
    seu Chrome independente, nenhuma porta CDP é usada."""
    if args.workers > 1:
        pool_config = WorkerPoolConfig(
            workers=args.workers,
            lease_seconds=args.lease_seconds,
            challenge_window_seconds=args.challenge_window_seconds,
            challenge_threshold=args.challenge_threshold,
            stability_seconds=args.stability_seconds,
            metrics_interval_seconds=args.metrics_interval_seconds,
        )
        on_event = make_terminal_reporter(run_id=run_id)
        stop_event = multiprocessing.get_context("spawn").Event()

        transport: BrowserTransport
        if args.own_chrome:
            # O orquestrador só usa `transport` para o Nível A (MARKET_INDEX,
            # sempre sequencial) — também ganha seu próprio Chrome nesse modo.
            try:
                transport = UndetectedChromeTransport(headless=args.chrome_headless)
            except ChromeLaunchFailedError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 3
            cdp_host, effective_cdp_ports = "", []
        else:
            assert cdp_ports is not None  # computed and validated near the top of main()
            cdp_host = resolve_cdp_host(args.cdp_host)
            try:
                transport = ChromeCdpTransport(
                    host=cdp_host,
                    port=cdp_ports[0],
                    max_retries=args.transport_max_retries,
                    backoff_seconds=args.transport_backoff_seconds,
                )
            except ChromeNotReachableError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 3
            effective_cdp_ports = cdp_ports

        try:
            run_pool(
                transport,
                conn,
                blob_store,
                capture_repo,
                run_id=run_id,
                context=context,
                filters=filters,
                pool_config=pool_config,
                db_path=db_path,
                raw_root=str(raw_root),
                cdp_host=cdp_host,
                cdp_ports=effective_cdp_ports,
                worker_target=_worker_process_entrypoint,
                process_factory=_spawn_worker_process,
                stop_event=stop_event,
                poll_interval=args.challenge_poll_interval,
                challenge_timeout=args.challenge_timeout,
                min_interval=args.min_interval,
                enable_detail_batch_fetch=not args.no_detail_batch_fetch,
                detail_fetch_batch_size=args.detail_fetch_batch_size,
                detail_fetch_chunk_size=args.detail_fetch_chunk_size,
                detail_fetch_timeout_ms=args.detail_fetch_timeout_ms,
                own_chrome=args.own_chrome,
                chrome_headless=args.chrome_headless,
                on_event=on_event,
            )
        except WorkerProcessFailedError as exc:
            # 005 hardening (HIGH — exitcode de worker): nunca sucesso
            # silencioso quando um worker filho falhou inesperadamente.
            print(f"error: {exc}", file=sys.stderr)
            return 7
        finally:
            _close_if_closeable(transport)
        return 0

    single_transport = _build_single_worker_transport(args)
    if single_transport is None:
        return 3

    on_event = make_terminal_reporter(run_id=run_id)
    try:
        run_collection_driver(
            single_transport,
            conn,
            blob_store,
            capture_repo,
            run_id=run_id,
            context=context,
            filters=filters,
            poll_interval=args.challenge_poll_interval,
            challenge_timeout=args.challenge_timeout,
            min_interval=args.min_interval,
            enable_detail_batch_fetch=not args.no_detail_batch_fetch,
            detail_fetch_batch_size=args.detail_fetch_batch_size,
            detail_fetch_chunk_size=args.detail_fetch_chunk_size,
            detail_fetch_timeout_ms=args.detail_fetch_timeout_ms,
            on_event=on_event,
        )
    finally:
        _close_if_closeable(single_transport)
    return 0


def _close_if_closeable(transport: BrowserTransport) -> None:
    """`ChromeCdpTransport` nunca fecha o Chrome do operador (não tem
    `close()`); `UndetectedChromeTransport` é dono do seu próprio Chrome e
    precisa ser fechado ao final — `getattr` em vez de checar `args.own_chrome`
    de novo aqui, para nunca poder divergir de qual transporte foi
    efetivamente construído."""
    close = getattr(transport, "close", None)
    if close is not None:
        close()


def _build_single_worker_transport(args: argparse.Namespace) -> BrowserTransport | None:
    """`--workers 1`: constrói `UndetectedChromeTransport` (`--own-chrome`)
    ou `ChromeCdpTransport` (default) — `None` quando o Chrome não pôde ser
    alcançado/lançado (erro já impresso, chamador retorna exit code 3)."""
    if args.own_chrome:
        try:
            return UndetectedChromeTransport(headless=args.chrome_headless)
        except ChromeLaunchFailedError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None
    try:
        return ChromeCdpTransport(
            host=args.cdp_host,
            port=args.cdp_port,
            max_retries=args.transport_max_retries,
            backoff_seconds=args.transport_backoff_seconds,
        )
    except ChromeNotReachableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _run_repair(
    args: argparse.Namespace,
    *,
    db_path: str,
    cdp_ports: list[int] | None,
) -> int:
    """`--repair-manifest` (bug fix de manifest truncado): redescobre o
    manifesto categoria-a-categoria para specs JÁ existentes de um (ou,
    com `--repair-all-scopes`, todo) scope — nunca cria uma CollectionRun
    nova; reabre (`completed_at` limpo) a mais recente já existente para o
    scope (`get_latest_run_for_scope()`), preservando checkpoints/visitas de
    categoria já `ACCEPTED` sob esse mesmo `run_id` (nunca baixa de novo o
    que já está correto). Delega a execução real a `_execute_collection()` —
    mesmo caminho de código de `run` (`run_collection_driver()`/`run_pool()`),
    apenas com `run_id`/`filters` diferentes."""
    if args.new_run or (args.resume is not None and args.repair_all_scopes):
        print(
            "error: --repair-manifest cannot be combined with --resume/--new-run "
            "(it manages run selection/reopening itself)",
            file=sys.stderr,
        )
        return 8
    if args.dry_run:
        print("error: --repair-manifest does not support --dry-run", file=sys.stderr)
        return 8

    raw_root = Path(args.raw_root) if args.raw_root else Path(DEFAULT_RAW_ROOT)
    raw_root.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(raw_root, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    try:
        if args.repair_all_scopes:
            manufacturer = normalize_scope_component(args.manufacturer, field_name="manufacturer")
            scopes = list_distinct_scopes_for_manufacturer(conn, manufacturer)
            contexts = [parse_scope(s) for s in scopes]
        else:
            contexts = [
                CollectionContext(
                    manufacturer=args.manufacturer,
                    vehicle_model=args.vehicle_model,
                    market=args.market,
                )
            ]
    except (InvalidScopeError, InvalidScopeComponentError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    if not contexts:
        print(
            f"error: --repair-all-scopes found no existing CollectionRun for "
            f"manufacturer={args.manufacturer!r} — nothing to repair",
            file=sys.stderr,
        )
        return 8

    exit_code = 0
    for context in contexts:
        scope = context.scope()
        existing = (
            get_collection_run(conn, args.resume)
            if args.resume is not None
            else get_latest_run_for_scope(conn, scope)
        )
        if existing is not None and existing.scope != scope:
            print(
                f"error: --resume run {existing.run_id!r} belongs to scope "
                f"{existing.scope!r}, expected {scope!r}",
                file=sys.stderr,
            )
            return 2
        if existing is None:
            print(f"skip: no existing CollectionRun for scope {scope!r} — nothing to repair")
            continue

        reopened = replace(existing, completed_at=None, resumed_at=datetime.now(UTC))
        save_collection_run(conn, reopened)

        target_specs = list_by_scope(
            conn,
            manufacturer=context.manufacturer,
            vehicle_model=context.vehicle_model,
            market=context.market,
        )
        target_keys = [identity.stable_key() for identity in target_specs]
        filters = OperationalFilters(
            spec_filter=args.spec,
            limit_specs=args.limit_specs,
            limit_groups=args.limit_groups,
            force=target_keys,
            retry_rejected=args.retry_rejected,
            force_manifest_rediscovery=True,
        )
        print(
            f"repairing scope {scope!r} under run_id={existing.run_id!r} "
            f"({len(target_keys)} known spec(s))"
        )
        scope_exit_code = _execute_collection(
            args,
            conn,
            blob_store,
            capture_repo,
            run_id=existing.run_id,
            context=context,
            filters=filters,
            db_path=db_path,
            raw_root=raw_root,
            cdp_ports=cdp_ports,
        )
        if scope_exit_code != 0:
            exit_code = scope_exit_code
            print(
                f"error: repair failed for scope {scope!r} (exit {scope_exit_code}) — "
                "continuing to next scope",
                file=sys.stderr,
            )

    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    # 005 FR-001: validado antes de qualquer navegação/escrita — mesmo
    # espírito de fail-fast de --manufacturer/--vehicle-model/--market (004).
    if not 1 <= args.workers <= 4:
        print(f"error: --workers must be between 1 and 4, got {args.workers}", file=sys.stderr)
        return 6

    cdp_ports: list[int] | None = None
    if args.workers > 1:
        try:
            cdp_ports = _resolve_cdp_ports(args)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 6
        if len(cdp_ports) != args.workers:
            print(
                f"error: --cdp-ports must have exactly --workers ({args.workers}) entries, "
                f"got {len(cdp_ports)}",
                file=sys.stderr,
            )
            return 6

    db_path = args.db_path or DEFAULT_DB_PATH

    if args.repair_manifest:
        # Bug fix (manifest truncado) — repair/backfill: gerencia sua PRÓPRIA
        # seleção/reabertura de CollectionRun (nunca select_run()/--dry-run,
        # ver _run_repair()); nunca chega ao caminho de `run` normal abaixo.
        return _run_repair(args, db_path=db_path, cdp_ports=cdp_ports)

    try:
        context = CollectionContext(
            manufacturer=args.manufacturer, vehicle_model=args.vehicle_model, market=args.market
        )
    except InvalidScopeComponentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    scope = context.scope()

    if args.dry_run:
        # Blocker 1 (Codex) — DEC-009: --dry-run nunca cria DB, nunca cria
        # raw_root, nunca roda migration, nunca escreve nada. Se o DB
        # informado já existir, abre-o genuinamente read-only; se não
        # existir, trata como estado vazio sem tocar o filesystem.
        try:
            if Path(db_path).exists():
                conn = _connect_read_only(db_path)
                try:
                    repos = _read_only_repos(
                        conn,
                        manufacturer=context.manufacturer,
                        vehicle_model=context.vehicle_model,
                        market=context.market,
                    )
                    plan = plan_operation(
                        repos,
                        resume_run_id=args.resume,
                        new_run=args.new_run,
                        scope=scope,
                        limit_specs=args.limit_specs,
                        limit_groups=args.limit_groups,
                        spec_filter=args.spec,
                        force=args.force,
                    )
                finally:
                    conn.close()
            else:
                plan = plan_operation(
                    _empty_read_only_repos(),
                    resume_run_id=args.resume,
                    new_run=args.new_run,
                    scope=scope,
                    limit_specs=args.limit_specs,
                    limit_groups=args.limit_groups,
                    spec_filter=args.spec,
                    force=args.force,
                )
        except (InvalidScopeError, InvalidScopeComponentError) as exc:
            # 004, item 5: um CollectionRun.scope corrompido no banco (nunca
            # escrito por este projeto — só via SQL direto externo) nunca é
            # silenciosamente tratado como Amarok/default. Falha fechada,
            # nenhum traceback cru, nenhuma escrita (--dry-run já não
            # escreve nada, DEC-009).
            print(f"error: corrupted CollectionRun.scope in database: {exc}", file=sys.stderr)
            return 5
        _print_plan(plan)
        return 0

    raw_root = Path(args.raw_root) if args.raw_root else Path(DEFAULT_RAW_ROOT)
    raw_root.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(raw_root, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    try:
        selection = select_run(
            resume_run_id=args.resume,
            new_run=args.new_run,
            scope=scope,
            now=datetime.now(UTC),
            run_id_factory=lambda: str(uuid.uuid4()),
            get_collection_run=partial(get_collection_run, conn),
            list_incomplete_runs=partial(list_incomplete_runs, conn),
            save_collection_run=partial(save_collection_run, conn),
        )
    except (IncompatibleResumeRunError, AmbiguousResumeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (InvalidScopeError, InvalidScopeComponentError) as exc:
        # 004, item 5: mesma falha fechada do ramo --dry-run — um scope
        # corrompido lido do banco (via get_collection_run/list_incomplete_runs
        # dentro de select_run()) nunca vira Amarok/default silenciosamente,
        # e nada foi escrito até aqui (migrations à parte, idempotentes).
        print(f"error: corrupted CollectionRun.scope in database: {exc}", file=sys.stderr)
        return 5

    filters = OperationalFilters(
        spec_filter=args.spec,
        limit_specs=args.limit_specs,
        limit_groups=args.limit_groups,
        force=args.force or [],
        retry_rejected=args.retry_rejected,
    )

    # 005 FR-003: --workers 1 (default) é EXATAMENTE o caminho de código
    # legado — nenhuma linha relacionada a worker_pool é executada nesse
    # ramo dentro de `_execute_collection()`. --workers N > 1 é o único
    # caminho que usa run_pool().
    return _execute_collection(
        args,
        conn,
        blob_store,
        capture_repo,
        run_id=selection.run.run_id,
        context=context,
        filters=filters,
        db_path=db_path,
        raw_root=raw_root,
        cdp_ports=cdp_ports,
    )


if __name__ == "__main__":  # pragma: no cover - thin process entrypoint
    raise SystemExit(main())
