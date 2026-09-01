"""T064 — ReadOnlyRepos não expõe nenhum atributo de escrita (DEC-009,
contracts/orchestration-contract.md §3, SC-014).

Mutação é estruturalmente impossível, não apenas evitada por convenção: o
dataclass simplesmente não tem nenhum campo save_*/upsert_*/insert_*."""

from __future__ import annotations

import dataclasses

from amayama_scraper.orchestration.dry_run import ReadOnlyRepos

_FORBIDDEN_PREFIXES = ("save_", "upsert_", "insert_", "write_", "delete_", "update_")


def test_read_only_repos_has_no_write_shaped_field_names() -> None:
    field_names = {f.name for f in dataclasses.fields(ReadOnlyRepos)}
    for name in field_names:
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{name!r} looks like a write dependency"


def test_read_only_repos_field_names_are_exactly_the_expected_reads() -> None:
    field_names = {f.name for f in dataclasses.fields(ReadOnlyRepos)}
    assert field_names == {
        "get_collection_run",
        "list_incomplete_runs",
        "list_all_spec_identities",
        "get_current_state",
        "get_authoritative_manifest",
        "get_pending_groups",
    }
