"""SpecIdentity — normative identity of a spec entry (data-model.md §1).

Never depends on model_code alone (FR-003). stable_key/display_key per
research.md §10 (hardened identity — correction accepted by the PO).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from amayama_scraper.fingerprints.canonical import domain_hash

_STABLE_KEY_SEPARATOR = "amayama:spec-identity:v1\0"

_IDENTITY_FIELDS = (
    "source",
    "manufacturer",
    "vehicle_model",
    "market",
    "model_code",
    "amayama_catalog_id",
)


def _normalize_identity_component(value: str) -> str:
    return value.strip().upper()


def _escape_display_component(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


@dataclass(frozen=True, slots=True)
class SpecIdentity:
    """Identidade normativa de uma spec entry.

    Campos obrigatórios formam a tupla de identidade (research.md §10).
    production_start/production_end/source_url NUNCA entram no stable_key —
    podem mudar sem representar uma nova identidade de catálogo.
    """

    source: str
    manufacturer: str
    vehicle_model: str
    market: str
    model_code: str
    amayama_catalog_id: str
    production_period_raw: str
    source_url: str
    production_start: date | None = None
    production_end: date | None = None
    grade: str | None = None
    configuration: str | None = None

    def __post_init__(self) -> None:
        for field_name in (*_IDENTITY_FIELDS, "production_period_raw", "source_url"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"SpecIdentity.{field_name} must not be empty")

    def _normalized_identity_payload(self) -> dict[str, str]:
        return {
            field_name: _normalize_identity_component(getattr(self, field_name))
            for field_name in _IDENTITY_FIELDS
        }

    def stable_key(self) -> str:
        """Deterministic hash over the 6-field identity tuple (research.md §10)."""
        return domain_hash(_STABLE_KEY_SEPARATOR, self._normalized_identity_payload())

    def display_key(self) -> str:
        """Human-readable, escaped representation — for logs only, never for equality/lookup."""
        payload = self._normalized_identity_payload()
        components = (
            payload["source"],
            payload["market"],
            payload["model_code"],
            payload["amayama_catalog_id"],
        )
        return ":".join(_escape_display_component(c) for c in components)


@dataclass(frozen=True, slots=True)
class ExpectedIdentityContext:
    """Identidade parcial presumida pela navegação, antes de o parsing confirmar.

    Usado para detectar divergência (data-model.md §4b) — nunca é usado
    como fonte de verdade, apenas como sinal de auditoria.
    """

    market: str | None = None
    model_code: str | None = None
    amayama_catalog_id: str | None = None
