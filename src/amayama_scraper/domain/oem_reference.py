"""OemReference — projeção derivada dos oem_code distintos de um Schema.

research.md §11: o nó "OEM" ao final da hierarquia da Constitution é
modelado como projeção derivada, não como entidade coletada de página
própria — nenhum dado novo é coletado além do que Part.oem_code já exige.
"""

from __future__ import annotations

from dataclasses import dataclass

from amayama_scraper.domain.hierarchy import Schema


@dataclass(frozen=True, slots=True)
class OemReference:
    schema_id: str
    oem_codes: tuple[str, ...]


def derive_oem_reference(schema: Schema) -> OemReference:
    """Aggregate distinct, non-empty oem_code values from a Schema's parts.

    Deterministic (sorted) — never invents an OEM code not present in Part.oem_code.
    """
    distinct = sorted({part.oem_code for part in schema.parts if part.oem_code})
    return OemReference(schema_id=schema.schema_id, oem_codes=tuple(distinct))
