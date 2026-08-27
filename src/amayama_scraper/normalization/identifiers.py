"""normalize_schema_id()/normalize_pnc() — contracts/normalization-fingerprint-contracts.md."""

from __future__ import annotations

from amayama_scraper.normalization.text import normalize_text


def normalize_schema_id(schema_id: str) -> str:
    return normalize_text(schema_id)


def normalize_pnc(position_pnc: str) -> str:
    return normalize_text(position_pnc).upper()
