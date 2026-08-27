"""accept_capture() — preserva raw ANTES de qualquer validação (Constitution §4).

contracts/input-contracts.md §1 pós-condição. Recebe os ports por
injeção de dependência — nenhum import de SQLite/filesystem concreto
(contracts/ports-contract.md, research.md §18).
"""

from __future__ import annotations

import uuid

from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.hashing import content_hash
from amayama_scraper.ingestion.ports import RawBlobStore, RawCaptureRepository
from amayama_scraper.ingestion.raw_capture import RawCapture


def accept_capture(
    capture_input: RawCaptureInput,
    blob_store: RawBlobStore,
    capture_repo: RawCaptureRepository,
) -> RawCapture:
    """Grava RawBlob (dedup por content_hash) e uma nova RawCapture (Observation).

    A RawCapture nunca é colapsada com outra que compartilhe o mesmo
    content_hash — capture_id é sempre novo (data-model.md §4b).
    """
    digest = content_hash(capture_input.raw_content)
    blob_store.get_or_create(digest, capture_input.raw_content)

    capture = RawCapture(
        capture_id=str(uuid.uuid4()),
        run_id=capture_input.run_id,
        content_hash=digest,
        source_url=capture_input.source_url,
        collected_at=capture_input.collected_at,
        capture_kind=capture_input.capture_kind,
        acquisition_mode=capture_input.acquisition_mode,
        expected_identity_context=capture_input.expected_identity_context,
        collection_metadata=capture_input.collection_metadata,
    )
    capture_repo.save(capture)
    return capture
