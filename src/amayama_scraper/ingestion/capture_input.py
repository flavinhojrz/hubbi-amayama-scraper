"""RawCaptureInput — contrato de entrada agnóstico de transporte (contracts/input-contracts.md §1).

Satisfaz FR-034: todo mecanismo de aquisição (manual/browser-in-the-loop
nesta feature; automação futura) deve produzir exatamente esta forma.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from amayama_scraper.domain.identity import ExpectedIdentityContext
from amayama_scraper.ingestion.capture_kind import AcquisitionMode, CaptureKind


def _is_absolute_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme) and bool(parsed.netloc)


@dataclass(frozen=True, slots=True)
class RawCaptureInput:
    capture_kind: CaptureKind
    source_url: str
    collected_at: datetime
    raw_content: bytes
    run_id: str
    acquisition_mode: AcquisitionMode = AcquisitionMode.MANUAL_BROWSER
    expected_identity_context: ExpectedIdentityContext | None = None
    collection_metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_url or not self.source_url.strip():
            raise ValueError("RawCaptureInput.source_url must not be empty")
        if not _is_absolute_url(self.source_url):
            raise ValueError(
                f"RawCaptureInput.source_url must be absolute, got {self.source_url!r}"
            )
        if not self.run_id or not self.run_id.strip():
            raise ValueError("RawCaptureInput.run_id must not be empty")
        if len(self.raw_content) == 0:
            # contracts/input-contracts.md §1: rejeitado antes da validação
            # (INVALID, não INCOMPLETE).
            raise ValueError("RawCaptureInput.raw_content must not be empty")
