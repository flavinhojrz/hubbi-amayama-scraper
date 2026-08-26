"""get_pending_groups() — universo esperado sempre derivado do manifesto autoritativo.

data-model.md §15/§11. Nunca inferido apenas dos CheckpointEntry
observados — sem manifesto autoritativo, não há como saber com segurança
o que ainda falta (research.md §17).
"""

from __future__ import annotations

from typing import Any

from amayama_scraper.persistence.repositories.checkpoint_repo import list_accepted
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative


class NoAuthoritativeManifestError(ValueError):
    """Sem manifesto autoritativo não há universo esperado conhecido (data-model.md §15)."""


def get_pending_groups(conn: Any, run_id: str, spec_key: str) -> list[tuple[str, str]]:
    manifest = get_authoritative(conn, spec_key, run_id)
    if manifest is None:
        raise NoAuthoritativeManifestError(
            f"no authoritative SpecGroupManifest for spec_key={spec_key!r}, run_id={run_id!r}"
        )

    expected = manifest.expected_group_keys()
    accepted_keys = {
        (entry.category_slug, entry.group_id) for entry in list_accepted(conn, run_id, spec_key)
    }
    pending = expected - accepted_keys
    return sorted(pending)
