"""orchestration/pipeline.py — coordena as Phases 3-13 (plan.md pipeline conceitual).

`orchestration/` é a camada de composição raiz (contracts/ports-contract.md)
— o único lugar autorizado a conhecer tanto os módulos de domínio quanto os
adapters concretos de `persistence/`. Nenhuma regra de domínio é
reimplementada aqui (T238) — apenas roteamento e composição.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent
from amayama_scraper.checkpoint.resume import NoAuthoritativeManifestError, get_pending_groups
from amayama_scraper.checkpoint.upsert import upsert_checkpoint
from amayama_scraper.domain.collection_context import (
    CaptureRunMismatchError,
    CollectionContext,
    ContextScopeMismatchError,
    UnregisteredSpecIdentityError,
    require_spec_identity_matches_context,
)
from amayama_scraper.ingestion.accept import accept_capture
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.ingestion.ports import RawBlobStore, RawCaptureRepository
from amayama_scraper.parsing.group_detail import parse_group_detail
from amayama_scraper.parsing.market_index import parse_market_spec_index
from amayama_scraper.parsing.spec_group_manifest import parse_spec_group_manifest
from amayama_scraper.persistence.adapters.snapshot_adapters import (
    SqliteCheckpointQueryRepositoryAdapter,
    SqliteCurrentStateRepositoryAdapter,
    SqliteFingerprintWriteRepositoryAdapter,
    SqliteManifestRepositoryAdapter,
    SqliteSnapshotRepositoryAdapter,
)
from amayama_scraper.persistence.db import run_in_transaction as db_run_in_transaction
from amayama_scraper.persistence.repositories.checkpoint_repo import get_collection_run
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    get_spec_identity,
    save_discovered_spec_entry,
    save_spec_identity,
)
from amayama_scraper.snapshots.finalize import finalize_spec_entry
from amayama_scraper.snapshots.snapshot import SpecSnapshot
from amayama_scraper.validation.classify import classify_capture
from amayama_scraper.validation.types import ValidationOutcome


@dataclass(frozen=True, slots=True)
class ProcessCaptureResult:
    capture_id: str
    validation_outcome: ValidationOutcome
    routed_to_parser: bool
    critical_error: bool = False


def _require_matching_context(
    conn: sqlite3.Connection, run_id: str, context: CollectionContext
) -> None:
    """004, item 1/FR-002/FR-005: nenhum call site pode processar/persistir
    conteúdo sob um contexto operacional diferente do que o CollectionRun já
    persistido para `run_id` representa — validado aqui, sempre, antes de
    qualquer efeito colateral (accept_capture incluído), independentemente
    de quem chama process_capture()."""
    run = get_collection_run(conn, run_id)
    if run is None:
        raise ContextScopeMismatchError(
            f"no CollectionRun found for run_id={run_id!r} — cannot validate the given "
            f"CollectionContext ({context.scope()!r}) before processing/persisting"
        )
    if run.scope != context.scope():
        raise ContextScopeMismatchError(
            f"context {context.scope()!r} does not match CollectionRun(run_id={run_id!r})"
            f".scope {run.scope!r} — refusing to process/persist under a mismatched "
            "operational context"
        )


def _require_matching_spec_context(
    conn: sqlite3.Connection, spec_key: str | None, context: CollectionContext
) -> None:
    """004 Blocker 1 (achado do Codex) + hardening final: valida também
    `spec_key -> context`, não só `run_id -> context`. Sem isto, um
    `spec_key` de outro modelo/mercado (ex.: uma spec da Amarok) passado por
    engano para um run de GOL — mesmo com `run_id`/`context` corretos entre
    si — seria processado como se pertencesse a GOL. `spec_key` é `None` só
    para MARKET_INDEX (nenhuma spec ainda identificada nesse nível) — nesse
    caso não há nada a validar.

    Falha fechada: um `spec_key` sem `SpecIdentity` registrada NUNCA é
    tratado como "nada a validar, prossiga" — em operação real todo
    `spec_key` que chega a SPEC_NAVIGATION/GROUP_DETAIL/finalização já foi
    registrado via MARKET_INDEX (`run_collection_driver()` só passa
    `spec_key` de specs já descobertas, `list_by_scope()`); um `spec_key`
    não registrado é sempre um erro de programação ou dado corrompido,
    nunca um caso legítimo a ignorar (levanta `UnregisteredSpecIdentityError`)."""
    if spec_key is None:
        return
    identity = get_spec_identity(conn, spec_key)
    if identity is None:
        raise UnregisteredSpecIdentityError(
            f"spec_key={spec_key!r} has no SpecIdentity registered in spec_registry — "
            f"cannot validate it against context {context.scope()!r}; refusing to "
            "process/persist under an unregistered spec_key"
        )
    require_spec_identity_matches_context(identity, context)


def process_capture(
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    run_id: str,
    capture_input: RawCaptureInput,
    *,
    context: CollectionContext,
    category_slug: str | None = None,
    group_id: str | None = None,
    spec_key: str | None = None,
) -> ProcessCaptureResult:
    """Constitution §4: raw é preservado ANTES de qualquer validação — mas a
    validação de contexto (004) acontece ANTES até disso: um contexto
    divergente do CollectionRun.scope (ou um spec_key de outro modelo/
    mercado, Blocker 1) nunca chega a acionar accept_capture()."""
    if capture_input.run_id != run_id:
        # 004, hardening final: process_capture() valida contexto/spec_key
        # contra `run_id`, mas accept_capture() persistiria usando
        # `capture_input.run_id` — sem esta checagem os dois poderiam
        # divergir, quebrando a garantia de que o que foi validado é
        # exatamente o que é persistido.
        raise CaptureRunMismatchError(
            f"capture_input.run_id={capture_input.run_id!r} does not match the "
            f"run_id={run_id!r} process_capture() was called with — refusing to "
            "validate/process/persist under a mismatched run_id"
        )
    _require_matching_context(conn, run_id, context)
    _require_matching_spec_context(conn, spec_key, context)

    raw_capture = accept_capture(capture_input, blob_store, capture_repo)
    validation = classify_capture(capture_input.raw_content, capture_input.capture_kind)
    accepted = validation.primary_outcome is ValidationOutcome.ACCEPTED

    if capture_input.capture_kind is CaptureKind.GROUP_DETAIL:
        return _route_group_detail(
            conn,
            run_id=run_id,
            spec_key=spec_key,
            category_slug=category_slug,
            group_id=group_id,
            raw_capture_id=raw_capture.capture_id,
            raw_content=capture_input.raw_content,
            accepted=accepted,
            validation_outcome=validation.primary_outcome,
        )

    if not accepted:
        return ProcessCaptureResult(
            capture_id=raw_capture.capture_id,
            validation_outcome=validation.primary_outcome,
            routed_to_parser=False,
        )

    if capture_input.capture_kind is CaptureKind.MARKET_INDEX:
        result = parse_market_spec_index(
            capture_input.raw_content.decode("utf-8"), source_capture_id=raw_capture.capture_id
        )
        if result.critical_error is not None:
            return ProcessCaptureResult(
                capture_id=raw_capture.capture_id,
                validation_outcome=validation.primary_outcome,
                routed_to_parser=True,
                critical_error=True,
            )
        # 004, item 5/FR-040: o `market` é o único componente de identidade
        # efetivamente extraído da página (manufacturer/vehicle_model são
        # sempre atribuídos a partir de `context`, nunca parseados — não
        # podem divergir aqui). Se a página retornar um market diferente do
        # contexto do run, nada é persistido — nunca misturado com o run.
        market_mismatch = any(
            entry.market.strip().upper() != context.market for entry in result.entries
        )
        if market_mismatch:
            return ProcessCaptureResult(
                capture_id=raw_capture.capture_id,
                validation_outcome=validation.primary_outcome,
                routed_to_parser=True,
                critical_error=True,
            )
        for entry in result.entries:
            identity = entry.to_spec_identity(
                source=context.source,
                manufacturer=context.manufacturer,
                vehicle_model=context.vehicle_model,
            )
            stable_key = save_spec_identity(conn, identity)
            save_discovered_spec_entry(conn, entry, stable_key)
        return ProcessCaptureResult(
            capture_id=raw_capture.capture_id,
            validation_outcome=validation.primary_outcome,
            routed_to_parser=True,
            critical_error=False,
        )

    # SPEC_NAVIGATION
    assert spec_key is not None, "spec_key required to route a SPEC_NAVIGATION capture"
    manifest_result = parse_spec_group_manifest(
        capture_input.raw_content.decode("utf-8"),
        spec_key=spec_key,
        source_capture_id=raw_capture.capture_id,
    )
    if manifest_result.manifest is not None:
        save_manifest(conn, manifest_result.manifest, run_id=run_id)
    return ProcessCaptureResult(
        capture_id=raw_capture.capture_id,
        validation_outcome=validation.primary_outcome,
        routed_to_parser=True,
        critical_error=manifest_result.critical_error is not None,
    )


def _route_group_detail(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    spec_key: str | None,
    category_slug: str | None,
    group_id: str | None,
    raw_capture_id: str,
    raw_content: bytes,
    accepted: bool,
    validation_outcome: ValidationOutcome,
) -> ProcessCaptureResult:
    assert spec_key is not None and category_slug is not None and group_id is not None, (
        "spec_key/category_slug/group_id required to route a GROUP_DETAIL capture"
    )
    upsert_checkpoint(
        conn,
        run_id=run_id,
        spec_key=spec_key,
        category_slug=category_slug,
        group_id=group_id,
        event=CheckpointEvent.START_ATTEMPT,
    )

    if not accepted:
        upsert_checkpoint(
            conn,
            run_id=run_id,
            spec_key=spec_key,
            category_slug=category_slug,
            group_id=group_id,
            event=CheckpointEvent.REJECT,
            evidence={"outcome": validation_outcome.value},
        )
        return ProcessCaptureResult(
            capture_id=raw_capture_id, validation_outcome=validation_outcome, routed_to_parser=False
        )

    parsed = parse_group_detail(
        raw_content.decode("utf-8"), category_slug=category_slug, group_id=group_id
    )
    if parsed.critical_error is not None:
        upsert_checkpoint(
            conn,
            run_id=run_id,
            spec_key=spec_key,
            category_slug=category_slug,
            group_id=group_id,
            event=CheckpointEvent.REJECT,
            evidence={"critical_error": parsed.critical_error.message},
        )
        return ProcessCaptureResult(
            capture_id=raw_capture_id,
            validation_outcome=validation_outcome,
            routed_to_parser=True,
            critical_error=True,
        )

    upsert_checkpoint(
        conn,
        run_id=run_id,
        spec_key=spec_key,
        category_slug=category_slug,
        group_id=group_id,
        event=CheckpointEvent.ACCEPT,
        raw_capture_id=raw_capture_id,
    )
    return ProcessCaptureResult(
        capture_id=raw_capture_id, validation_outcome=validation_outcome, routed_to_parser=True
    )


def try_finalize_spec_entry(
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    run_id: str,
    spec_key: str,
    *,
    context: CollectionContext,
    run_in_transaction: Callable[[Callable[[], SpecSnapshot]], SpecSnapshot] | None = None,
) -> SpecSnapshot | None:
    """Chamado após cada GROUP_DETAIL ACCEPTED — finaliza quando o manifesto
    está totalmente coberto (data-model.md §17).

    004 Blocker 1: este é o caminho que efetivamente cria snapshot/
    current_state/estado VALID — validado de forma independente de
    `process_capture()` (nunca confia que o caller já validou antes de
    chegar aqui; "não confie apenas no caller").

    `run_in_transaction` (005 hardening, BLOCKER 1 — lease fencing): opcional;
    por default, é `lambda fn: db_run_in_transaction(conn, fn)` (comportamento
    idêntico a antes — nenhuma mudança para nenhum caller existente). Um
    caller pode injetar sua PRÓPRIA implementação (ex.:
    `orchestration/worker_pool.py`, que já abriu sua própria transação com um
    check de fencing e só precisa que `fn()` rode dentro dela, sem uma nova
    `BEGIN IMMEDIATE` aninhada)."""
    _require_matching_context(conn, run_id, context)
    _require_matching_spec_context(conn, spec_key, context)
    try:
        pending = get_pending_groups(conn, run_id, spec_key)
    except NoAuthoritativeManifestError:
        return None
    if pending:
        return None

    return finalize_spec_entry(
        spec_key=spec_key,
        run_id=run_id,
        spec_identity_ref=spec_key,
        manifest_repo=SqliteManifestRepositoryAdapter(conn),
        checkpoint_repo=SqliteCheckpointQueryRepositoryAdapter(conn),
        capture_repo=capture_repo,
        blob_store=blob_store,
        snapshot_repo=SqliteSnapshotRepositoryAdapter(conn),
        fingerprint_repo=SqliteFingerprintWriteRepositoryAdapter(conn),
        current_state_repo=SqliteCurrentStateRepositoryAdapter(conn),
        run_in_transaction=run_in_transaction or (lambda fn: db_run_in_transaction(conn, fn)),
        snapshot_id_factory=lambda: str(uuid.uuid4()),
        now_factory=lambda: datetime.now(UTC),
    )


@dataclass(frozen=True, slots=True)
class CollectionInput:
    capture_input: RawCaptureInput
    category_slug: str | None = None
    group_id: str | None = None
    spec_key: str | None = None


def run_collection(
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    run_id: str,
    captures: list[CollectionInput],
    *,
    context: CollectionContext,
) -> list[ProcessCaptureResult]:
    """Coordena múltiplas capturas (dos três níveis) sob o mesmo CollectionRun (FR-001)."""
    results: list[ProcessCaptureResult] = []
    for item in captures:
        result = process_capture(
            conn,
            blob_store,
            capture_repo,
            run_id,
            item.capture_input,
            context=context,
            category_slug=item.category_slug,
            group_id=item.group_id,
            spec_key=item.spec_key,
        )
        results.append(result)
        if (
            item.capture_input.capture_kind is CaptureKind.GROUP_DETAIL
            and result.routed_to_parser
            and not result.critical_error
            and item.spec_key is not None
        ):
            try_finalize_spec_entry(
                conn, blob_store, capture_repo, run_id, item.spec_key, context=context
            )
    return results
