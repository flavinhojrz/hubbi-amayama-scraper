"""Logging estruturado — JSON lines, correlacionado por run_id (research.md §14).

Nunca despeja `raw_content` completo — apenas referências (`content_hash`/
caminho/tamanho). `log_event()` recusa explicitamente qualquer campo
`raw_content` ou valor `bytes`, em vez de confiar que o chamador nunca vai
passar um por engano.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

_FORBIDDEN_FIELD_NAMES = frozenset({"raw_content", "raw_html", "html"})


class RawContentInLogError(ValueError):
    """log_event() recusou um campo que pareceria despejar conteúdo bruto completo."""


def _default_emit(line: str) -> None:
    print(line, file=sys.stdout, flush=True)


def log_event(
    *,
    run_id: str,
    event: str,
    emit: Callable[[str], None] = _default_emit,
    **fields: Any,
) -> str:
    for name, value in fields.items():
        if name in _FORBIDDEN_FIELD_NAMES:
            raise RawContentInLogError(
                f"log_event() field {name!r} looks like a raw-content dump — "
                "pass a reference (content_hash/capture_id/size), never the raw bytes/text"
            )
        if isinstance(value, bytes | bytearray):
            raise RawContentInLogError(
                f"log_event() field {name!r} is bytes-like ({len(value)} bytes) — "
                "pass a reference (content_hash/capture_id/size), never the raw content itself"
            )

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "event": event,
        **fields,
    }
    line = json.dumps(payload, sort_keys=True, default=str)
    emit(line)
    return line
