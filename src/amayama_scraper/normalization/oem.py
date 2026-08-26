"""normalize_oem() — contracts/normalization-fingerprint-contracts.md.

strip() + upper() + remoção de whitespace técnico interno (comprovadamente
apenas formatação — códigos OEM não têm espaço internamente significativo).
"""

from __future__ import annotations

import re

from amayama_scraper.normalization.text import normalize_text

_INTERNAL_WHITESPACE = re.compile(r"\s+")


def normalize_oem(oem_code: str) -> str:
    value = normalize_text(oem_code).upper()
    return _INTERNAL_WHITESPACE.sub("", value)
