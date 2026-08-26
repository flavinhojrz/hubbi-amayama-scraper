"""normalize_text() — regra genérica "Todo texto".

contracts/normalization-fingerprint-contracts.md.

NFKC; NBSP e variantes de quebra de linha normalizadas para espaço/`\\n`
padrão; whitespace técnico redundante colapsado; `strip()` nas
extremidades. Nunca tradução/stemming/fuzzy/sinonímia/correção
ortográfica/remoção arbitrária de acentos (FR-016).
"""

from __future__ import annotations

import re
import unicodedata

_LINE_BREAK_VARIANTS = re.compile(r"\r\n|\r")

#: NBSP + other Unicode "technical" space separators, normalized to a plain
#: ASCII space: U+00A0 (NBSP), U+2000-U+200A (en/em/thin/hair spaces),
#: U+202F (narrow NBSP), U+205F (medium math space), U+3000 (ideographic).
_TECHNICAL_SPACE_CODEPOINTS = [0x00A0, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000]
_TECHNICAL_SPACES = re.compile("[" + "".join(chr(c) for c in _TECHNICAL_SPACE_CODEPOINTS) + "]")
_HORIZONTAL_WHITESPACE_RUN = re.compile(r"[ \t]+")
_BLANK_LINE_RUN = re.compile(r"\n{2,}")


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text)
    value = _LINE_BREAK_VARIANTS.sub("\n", value)
    value = _TECHNICAL_SPACES.sub(" ", value)
    value = _HORIZONTAL_WHITESPACE_RUN.sub(" ", value)
    value = _BLANK_LINE_RUN.sub("\n", value)
    return value.strip()
