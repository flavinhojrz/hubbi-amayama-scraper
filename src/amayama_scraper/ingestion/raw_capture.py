"""RawCapture — Observation, evento de coleta com identidade própria (data-model.md §4b).

Duas RawCapture com o mesmo content_hash NUNCA são colapsadas — cada
observação preserva seu próprio capture_id/run_id/collected_at/provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from amayama_scraper.domain.identity import ExpectedIdentityContext
from amayama_scraper.ingestion.capture_kind import AcquisitionMode, CaptureKind


@dataclass(frozen=True, slots=True)
class RawCapture:
    capture_id: str
    run_id: str
    content_hash: str
    source_url: str
    collected_at: datetime
    capture_kind: CaptureKind
    acquisition_mode: AcquisitionMode = AcquisitionMode.MANUAL_BROWSER
    expected_identity_context: ExpectedIdentityContext | None = None
    collection_metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("capture_id", "run_id", "content_hash", "source_url"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"RawCapture.{field_name} must not be empty")
