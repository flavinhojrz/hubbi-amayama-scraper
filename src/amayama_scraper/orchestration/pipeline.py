"""orchestration/pipeline.py — coordena as Phases 3-13 (plan.md pipeline conceitual).

`orchestration/` é a camada de composição raiz (contracts/ports-contract.md)
— o único lugar autorizado a conhecer tanto os módulos de domínio quanto os
adapters concretos de `persistence/`. Nenhuma regra de domínio é
reimplementada aqui (T238) — apenas roteamento e composição.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent
from amayama_scraper.checkpoint.resume import NoAuthoritativeManifestError, get_pending_groups
from amayama_scraper.checkpoint.upsert import upsert_checkpoint
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
from amayama_scraper.persistence.db import run_in_transaction
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    save_discovered_spec_entry,
    save_spec_identity,
)
from amayama_scraper.snapshots.finalize import finalize_spec_entry
from amayama_scraper.snapshots.snapshot import SpecSnapshot
from amayama_scraper.validation.classify import classify_capture
from amayama_scraper.validation.types import ValidationOutcome

_IDENTITY_CONSTANTS = dict(source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK")


@dataclass(frozen=True, slots=True)
class ProcessCaptureResult:
    capture_id: str
    validation_outcome: ValidationOutcome
    routed_to_parser: bool
    critical_error: bool = False


def process_capture(
    conn: sqlite3.Connection,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
    run_id: str,
    capture_input: RawCaptureInput,
    *,
    category_slug: str | None = None,
    group_id: str | None = None,
    spec_key: str | None = None,
) -> ProcessCaptureResult:
    """Constitution §4: raw é preservado ANTES de qualquer validação."""
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
        if result.critical_error is None:
            for entry in result.entries:
                identity = entry.to_spec_identity(**_IDENTITY_CONSTANTS)
                stable_key = save_spec_identity(conn, identity)
                save_discovered_spec_entry(conn, entry, stable_key)
        return ProcessCaptureResult(
            capture_id=raw_capture.capture_id,
            validation_outcome=validation.primary_outcome,
            routed_to_parser=True,
            critical_error=result.critical_error is not None,
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
) -> SpecSnapshot | None:
    """Chamado após cada GROUP_DETAIL ACCEPTED — finaliza quando o manifesto
    está totalmente coberto (data-model.md §17)."""
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
        run_in_transaction=lambda fn: run_in_transaction(conn, fn),
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
            try_finalize_spec_entry(conn, blob_store, capture_repo, run_id, item.spec_key)
    return results
