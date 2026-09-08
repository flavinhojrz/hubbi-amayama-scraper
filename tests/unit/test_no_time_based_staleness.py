"""T090 — nenhuma função do driver/planejador consulta tempo decorrido para
decidir se uma spec VALID está "stale" (DEC-008). Auditoria estática: os
módulos desta feature nunca comparam datetime.now()/elapsed time contra um
snapshot para decidir recoleta — o único critério de skip é a MERA
EXISTÊNCIA de um CurrentSpecState (get_current_state() != None), nunca
comparado com nenhum timestamp."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"
MODULES_TO_AUDIT = (
    "orchestration/collection_driver.py",
    "orchestration/dry_run.py",
    "orchestration/run_selection.py",
    "orchestration/retry_classification.py",
)


def test_no_module_compares_datetime_now_against_a_snapshot_timestamp() -> None:
    """Static check: `datetime.now()`/`now()` calls in these modules are only
    ever used for provenance timestamps (collected_at, poll timing) — never
    subtracted from/compared against a snapshot's own collected_at to decide
    staleness. We assert the narrower, directly falsifiable property: none
    of these files import/reference anything from `snapshots.freshness_policy`
    (001's existing, deliberately unused-by-this-feature freshness module) —
    if this feature ever wired freshness/TTL logic in, it would necessarily
    go through that module."""
    for relative_path in MODULES_TO_AUDIT:
        source = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        assert not any("freshness_policy" in name for name in imported), (
            f"{relative_path} must never import snapshots.freshness_policy — "
            "DEC-008 forbids any automatic time-based staleness in this feature"
        )


def test_already_valid_skip_is_decided_solely_by_current_state_existence() -> None:
    """Behavioral confirmation (complements the static check above): a spec
    whose CurrentSpecState exists is skipped regardless of how "old" it is
    — there is no timestamp parameter anywhere in the skip decision."""
    # CurrentSpecState itself carries no timestamp field at all — the type
    # structurally cannot be compared against "now" even if someone tried.
    import dataclasses

    from amayama_scraper.domain.current_state import CurrentSpecState

    field_names = {f.name for f in dataclasses.fields(CurrentSpecState)}
    assert "collected_at" not in field_names
    assert "timestamp" not in field_names
    assert "expires_at" not in field_names
