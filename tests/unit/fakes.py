"""In-memory fakes for the ingestion ports (contracts/ports-contract.md).

Used across the test suite to keep everything above Phase 10 testable
100% offline, independent of SQLite/filesystem.

FakeBrowserTransport (T009/T010) extends this to the browser transport port
(contracts/browser-transport-contract.md §1) — the single substitution point
that keeps the collection driver/orchestration testable without Chrome/Selenium.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from amayama_scraper.ingestion.raw_blob import RawBlob
from amayama_scraper.ingestion.raw_capture import RawCapture
from amayama_scraper.transport.port import BrowserCapture


@dataclass
class InMemoryRawBlobStore:
    _blobs: dict[str, bytes] = field(default_factory=dict)
    _records: dict[str, RawBlob] = field(default_factory=dict)

    def get_or_create(self, content_hash: str, raw_content: bytes) -> RawBlob:
        existing = self._records.get(content_hash)
        if existing is not None:
            return existing
        record = RawBlob(
            content_hash=content_hash,
            size_bytes=len(raw_content),
            storage_path=f"raw/{content_hash[:2]}/{content_hash}",
            first_seen_at=datetime.now(UTC),
        )
        self._blobs[content_hash] = raw_content
        self._records[content_hash] = record
        return record

    def read(self, content_hash: str) -> bytes:
        try:
            return self._blobs[content_hash]
        except KeyError as exc:
            raise LookupError(f"RawBlob not found for content_hash={content_hash!r}") from exc


@dataclass
class InMemoryRawCaptureRepository:
    _captures: dict[str, RawCapture] = field(default_factory=dict)

    def save(self, capture: RawCapture) -> None:
        # Sempre insere uma nova observação — nunca faz upsert por content_hash.
        self._captures[capture.capture_id] = capture

    def get(self, capture_id: str) -> RawCapture | None:
        return self._captures.get(capture_id)


@dataclass
class FakeBrowserTransport:
    """Double de BrowserTransport — programável por chamada, sem Chrome/CDP real.

    `queue_navigate()`/`queue_current_capture()` aceitam tanto uma
    `BrowserCapture` (sucesso) quanto uma instância de exceção (falha de
    transporte) — permitindo simular falhas de rede intermitentes e o laço
    de poll de challenge (várias leituras de `current_capture()` sem nova
    navegação) sem qualquer dependência de rede real.
    """

    navigate_calls: list[str] = field(default_factory=list)
    current_capture_calls: int = 0
    _navigate_queue: deque[BrowserCapture | Exception] = field(default_factory=deque)
    _current_capture_queue: deque[BrowserCapture | Exception] = field(default_factory=deque)
    _last_capture: BrowserCapture | None = None

    def queue_navigate(self, item: BrowserCapture | Exception) -> None:
        self._navigate_queue.append(item)

    def queue_current_capture(self, item: BrowserCapture | Exception) -> None:
        self._current_capture_queue.append(item)

    def navigate(self, url: str) -> BrowserCapture:
        self.navigate_calls.append(url)
        if not self._navigate_queue:
            raise AssertionError(
                f"FakeBrowserTransport.navigate({url!r}) called with no queued response"
            )
        item = self._navigate_queue.popleft()
        if isinstance(item, Exception):
            raise item
        self._last_capture = item
        return item

    def current_capture(self) -> BrowserCapture:
        self.current_capture_calls += 1
        if self._current_capture_queue:
            item = self._current_capture_queue.popleft()
            if isinstance(item, Exception):
                raise item
            self._last_capture = item
            return item
        if self._last_capture is None:
            raise AssertionError(
                "FakeBrowserTransport.current_capture() called before any "
                "navigate()/queued response"
            )
        return self._last_capture
