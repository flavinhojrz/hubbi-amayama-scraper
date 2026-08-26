"""T206 — category_slug é usado apenas como índice; só group_id tem status (data-model.md §11)."""

import dataclasses

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry


def test_checkpoint_entry_has_no_category_level_status_field():
    field_names = {f.name for f in dataclasses.fields(CheckpointEntry)}
    assert "status" in field_names
    assert "category_status" not in field_names
    assert "category_slug" in field_names  # present only as an index component


def test_key_includes_category_slug_only_as_index_component():
    entry = CheckpointEntry(run_id="r", spec_key="s", category_slug="engine", group_id="1")
    assert entry.key == ("r", "s", "engine", "1")
